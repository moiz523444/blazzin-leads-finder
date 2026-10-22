"""
Verified local businesses from map data, across every state / province / emirate.

Sources (both return the business's own listed phone, website and address - nothing is guessed):
  1. TomTom Search API  - used when TOMTOM_API_KEY is set (free 2,500 requests/day)
  2. OpenStreetMap Overpass API - free, keyless fallback (slower, public servers are often busy)

A business only becomes a lead when there is evidence it needs a service:
  - no website (listing has none AND no live site carrying its name was found), or
  - only a Facebook/Instagram page, or
  - its website has problems the auditor actually observed.
"""
import asyncio
import math
import random
import re
import time
import urllib.parse
from collections import Counter
from typing import Any, Dict, List, Optional, Set

import httpx

import config
from models import Lead
from harvester.regions import pick_targets, ISO2, REGIONS
from harvester.web_auditor import audit_website, our_internet_ok
from enricher.contact_extractor import extract_contacts_from_url, phone_info, is_valid_email
from enricher.lead_quality import find_company_domain

# (keywords in the niche text, TomTom search phrase, OSM tag filters, display category)
CATEGORIES = [
    (["dental", "dentist"], "dentist", [("amenity", "dentist")], "Dental clinic"),
    (["aesthetic", "beauty", "salon", "spa", "plastic"], "beauty salon", [("shop", "beauty|hairdresser|cosmetics"), ("leisure", "spa")], "Beauty & aesthetics"),
    (["medical", "clinic", "health", "doctor", "physio"], "medical clinic", [("amenity", "clinic|doctors"), ("healthcare", "clinic|doctor|physiotherapist")], "Medical clinic"),
    # "a|b" = several TomTom search phrases for categories where one phrase returns few listings
    (["real estate", "property", "properties", "realtor"], "real estate agency|realtor", [("office", "estate_agent")], "Real estate agency"),
    (["law", "legal", "attorney", "lawyer"], "lawyer|law firm|attorney", [("office", "lawyer|notary")], "Law firm"),
    (["accounting", "accountant", "tax", "bookkeep"], "accountant|tax services", [("office", "accountant|tax_advisor")], "Accounting firm"),
    (["restaurant", "dining", "cafe", "food", "hospitality"], "restaurant", [("amenity", "restaurant|cafe")], "Restaurant / cafe"),
    (["hotel", "resort", "guest house"], "hotel", [("tourism", "hotel|guest_house|motel")], "Hotel"),
    (["fitness", "gym", "wellness", "yoga"], "gym", [("leisure", "fitness_centre|sports_centre")], "Gym / fitness"),
    (["car rental", "chauffeur", "limo"], "car rental", [("amenity", "car_rental")], "Car rental"),
    (["automotive", "auto", "car repair", "garage", "mechanic"], "car repair", [("shop", "car_repair|car|tyres")], "Auto repair / dealer"),
    (["construction", "builder", "contractor", "roofing", "plumb", "electric"], "construction company", [("craft", "builder|carpenter|electrician|plumber|roofer|hvac"), ("office", "construction_company")], "Construction / trades"),
    (["logistics", "freight", "shipping", "courier", "moving"], "logistics company", [("office", "logistics|courier|moving_company"), ("shop", "courier")], "Logistics"),
    (["travel", "tour"], "travel agency", [("shop", "travel_agency"), ("office", "travel_agent")], "Travel agency"),
    (["fashion", "clothing", "boutique", "apparel"], "clothing store", [("shop", "clothes|boutique|shoes")], "Fashion store"),
    (["e-commerce", "ecommerce", "dtc", "retail", "store", "shop"], "boutique store", [("shop", "boutique|jewelry|cosmetics|furniture|gift|clothes")], "Retail store"),
    (["education", "academy", "school", "training", "tutor"], "training center", [("amenity", "language_school|driving_school|music_school|prep_school"), ("office", "educational_institution")], "Education / training"),
    (["finance", "insurance", "financial", "investment"], "financial advisor", [("office", "financial|financial_advisor|insurance")], "Finance / insurance"),
    (["saas", "tech", "software", "it services"], "IT company", [("office", "it|telecommunication")], "IT / tech company"),
    (["vet", "pet"], "veterinarian", [("amenity", "veterinary"), ("shop", "pet|pet_grooming")], "Vet / pet services"),
    (["cleaning", "laundry"], "cleaning service", [("shop", "dry_cleaning|laundry"), ("craft", "cleaning")], "Cleaning services"),
]
# Used for "All Industries" - categories whose owners typically buy websites/marketing
ALL_POOL = ["Dental clinic", "Beauty & aesthetics", "Medical clinic", "Real estate agency", "Law firm",
            "Accounting firm", "Restaurant / cafe", "Gym / fitness", "Auto repair / dealer",
            "Construction / trades", "Travel agency", "Fashion store", "Education / training",
            "Vet / pet services", "Car rental", "Hotel"]

COUNTRY_TLDS = {"US": [".com"], "UK": [".co.uk", ".com"], "CA": [".ca", ".com"], "UAE": [".ae", ".com"], "QA": [".qa", ".com"]}
SOCIAL_HOSTS = ("facebook.com", "fb.com", "instagram.com", "linktr.ee", "tiktok.com", "twitter.com", "x.com",
                # Google Business profile / maps short links - a listing, not the business's own website
                "share.google", "g.page", "goo.gl", "maps.app.goo.gl", "google.com")
# A listing that links to a sub-page like /locations/... belongs to a multi-branch company (chain)
CHAIN_PATH = re.compile(r"/(locations?|stores?|branches|clinics|offices|pages|find-a-|salons?|studios?|team|agents?|our-people|doctors?)\b", re.I)
# Franchises, hotel brands, public bodies and non-businesses are real but don't hire freelancers for a website
CHAIN_NAME = re.compile(
    r"\bfranchis|\bhospital\b|\buniversity\b|\bministry\b|\bgovernment\b|\bembassy\b|\bmunicipality\b|\bcouncil\b"
    r"|\b(westin|marriott|sheraton|hilton|hyatt|radisson|rotana|m[eé]ridien|novotel|ibis|holiday inn|best western|"
    r"ramada|crowne plaza|intercontinental|four seasons|ritz|courtyard|hampton inn|premier inn|travelodge)\b"
    r"|wastewater|treatment plant|\bcondominium|\bholdings\b|highway operations|\b\d{2,4}\s*(am|fm)\b|\bradio\b",
    re.I)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
_overpass_sem = asyncio.Semaphore(2)  # public servers allow ~2 parallel queries per IP
_UA = {"User-Agent": "BlazzinLeadFinder/1.0 (local business research)"}


def resolve_categories(niche: str) -> List[Dict[str, Any]]:
    n = (niche or "").strip().lower()
    by_label = {c[3]: c for c in CATEGORIES}
    if not n or n in ("all", "technology") or n.startswith("all industries"):
        return [_cat(by_label[l]) for l in ALL_POOL]
    matched = [_cat(c) for c in CATEGORIES if any(k in n for k in c[0])]
    if matched:
        return matched[:2]
    # Free-text niche: search by text on TomTom, by business name on OSM
    clean = re.sub(r"[^a-z0-9 ]", " ", n).strip()
    return [{"query": clean, "osm": [("name", re.escape(clean))], "label": clean.title(), "free_text": True}]


def _cat(c) -> Dict[str, Any]:
    return {"query": c[1], "osm": c[2], "label": c[3], "free_text": False}


# ---------------------------------------------------------------------------
# Provider 1: TomTom Search API
# ---------------------------------------------------------------------------
_tomtom_sem = asyncio.Semaphore(3)  # free keys are rate-limited (HTTP 429 when ~20 requests fire at once)


async def tomtom_search(query: str, iso2: str, lat: float, lon: float, radius_m: int = 25000) -> List[Dict[str, Any]]:
    url = f"https://api.tomtom.com/search/2/poiSearch/{urllib.parse.quote(query)}.json"
    params = {"key": config.TOMTOM_API_KEY, "lat": lat, "lon": lon, "radius": radius_m,
              "limit": 100, "countrySet": iso2, "language": "en-GB"}
    for attempt in range(4):
        async with _tomtom_sem:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, params=params)
            await asyncio.sleep(0.3)  # keep well under the per-second limit
        if res.status_code != 429:
            break
        await asyncio.sleep(1.5 * (attempt + 1))
    if res.status_code != 200:
        raise RuntimeError(f"TomTom HTTP {res.status_code}: {res.text[:120]}")
    out = []
    for r in res.json().get("results", []):
        poi = r.get("poi", {}) or {}
        addr = r.get("address", {}) or {}
        out.append({
            "ref": f"tomtom:{r.get('id', '')}",
            "name": (poi.get("name") or "").strip(),
            "phone": poi.get("phone") or "",
            "website": poi.get("url") or "",
            "email": "",
            "socials": {},
            "is_brand": bool(poi.get("brands")),
            "address": addr.get("freeformAddress", ""),
            "city": addr.get("municipality", "") or addr.get("localName", ""),
            "subdivision": addr.get("countrySubdivisionName", "") or addr.get("countrySubdivision", ""),
        })
    return out


# ---------------------------------------------------------------------------
# Provider 2: OpenStreetMap Overpass (free, keyless)
# ---------------------------------------------------------------------------
def _bbox(lat: float, lon: float, km: float) -> str:
    d = km / 111.0
    dl = d / max(0.2, math.cos(math.radians(lat)))
    return f"{lat - d:.4f},{lon - dl:.4f},{lat + d:.4f},{lon + dl:.4f}"


async def overpass_search(categories: List[Dict[str, Any]], lat: float, lon: float, km: float = 12) -> List[Dict[str, Any]]:
    b = _bbox(lat, lon, km)
    parts = []
    for cat in categories:
        for key, values in cat["osm"]:
            flt = f'["{key}"~"{values}",i]' if key == "name" else f'["{key}"~"^({values})$"]'
            for phone_key in ("phone", "contact:phone", "contact:mobile"):
                parts.append(f'nwr{flt}["{phone_key}"][!"brand"]({b});')
    query = f'[out:json][timeout:40];({"".join(parts)});out tags center 150;'

    last_err = None
    endpoints = OVERPASS_ENDPOINTS[:]
    random.shuffle(endpoints)
    async with _overpass_sem:
        for ep in endpoints:
            try:
                async with httpx.AsyncClient(timeout=50.0, headers=_UA) as client:
                    res = await client.post(ep, data={"data": query})
                if res.status_code == 200:
                    return [_osm_to_business(el) for el in res.json().get("elements", [])]
                last_err = f"HTTP {res.status_code}"
            except Exception as e:
                last_err = type(e).__name__
    raise RuntimeError(f"Overpass unavailable ({last_err})")


def _osm_to_business(el: Dict[str, Any]) -> Dict[str, Any]:
    t = el.get("tags", {}) or {}
    phone = (t.get("phone") or t.get("contact:phone") or t.get("contact:mobile") or "").split(";")[0].strip()
    socials = {}
    for k in ("facebook", "instagram"):
        v = t.get(f"contact:{k}") or t.get(k)
        if v:
            socials[k] = v if v.startswith("http") else f"https://www.{k}.com/{v.lstrip('@')}"
    addr = ", ".join(filter(None, [" ".join(filter(None, [t.get("addr:housenumber"), t.get("addr:street")])),
                                   t.get("addr:city"), t.get("addr:postcode")]))
    return {
        "ref": f"osm:{el.get('type')}/{el.get('id')}",
        "name": (t.get("name:en") or t.get("name") or "").strip(),
        "phone": phone,
        "website": t.get("website") or t.get("contact:website") or t.get("url") or "",
        "email": (t.get("email") or t.get("contact:email") or "").split(";")[0].strip(),
        "socials": socials,
        "is_brand": bool(t.get("brand") or t.get("brand:wikidata")),
        "address": addr,
        "city": t.get("addr:city", ""),
        "tags": t,
    }


# ---------------------------------------------------------------------------
# Lead building
# ---------------------------------------------------------------------------
# TomTom gives no state for Qatar - its municipality field maps to the 8 municipalities
QA_MUNICIPALITIES = {"doha": "Doha", "al rayyan": "Al Rayyan", "al wakra": "Al Wakrah", "al wakrah": "Al Wakrah",
                     "al khor": "Al Khor", "umm salal": "Umm Salal", "al dhaayen": "Al Daayen", "al daayen": "Al Daayen",
                     "lusail": "Al Daayen", "al shamal": "Al Shamal", "madinat ash shamal": "Al Shamal",
                     "al shahaniya": "Al Shahaniya", "al shahaniyah": "Al Shahaniya"}


def _region_from_listing(biz: Dict[str, Any], country: str, fallback: str) -> str:
    """The search circle can cross a border (e.g. Khor Fakkan is Sharjah, not Fujairah) - trust the listing's own state."""
    if country == "QA":
        return QA_MUNICIPALITIES.get((biz.get("city") or "").strip().lower(), fallback)
    sub = (biz.get("subdivision") or "").strip().lower()
    if not sub or country == "UK":  # TomTom only says "England" for UK - keep our finer region
        return fallback
    names = list(REGIONS.get(country, {}))
    for name in names:  # exact first, so "West Virginia" never matches "Virginia"
        if name.lower() == sub:
            return name
    for name in names:
        if name.lower() in sub or sub in name.lower():
            return name
    return fallback


async def _site_mentions(url: str, phone_digits: str, town: str) -> bool:
    """True if the homepage or contact page contains the business's phone (last 7 digits) or its town name."""
    root = url.rstrip("/")
    tail = phone_digits[-7:]
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, verify=False, headers=_UA) as client:
        for page in (root, root + "/contact", root + "/contact-us"):
            try:
                res = await client.get(page)
                if res.status_code >= 400:
                    continue
                text = res.text
                if tail and tail in re.sub(r"\D", "", text):
                    return True
                if town and len(town) >= 4 and town.lower() in text.lower():
                    return True
            except Exception:
                continue
    return False


CATEGORY_WORDS = {
    "Law firm": ["law", "legal", "lawyers"], "Dental clinic": ["dental", "dentistry", "smiles"],
    "Auto repair / dealer": ["auto", "automotive", "autobody"], "Construction / trades": ["construction", "contracting", "ltd"],
    "Real estate agency": ["realestate", "realty", "properties"], "Hotel": ["hotel", "inn"],
    "Beauty & aesthetics": ["salon", "beauty", "spa"], "Accounting firm": ["cpa", "accounting", "tax"],
    "Restaurant / cafe": ["restaurant", "cafe", "kitchen"], "Fashion store": ["boutique", "clothing", "shop"],
    "Travel agency": ["travel", "tours"], "Car rental": ["rentacar", "carrental"], "Medical clinic": ["clinic", "medical"],
    "Gym / fitness": ["fitness", "gym"], "Education / training": ["academy", "training"],
}
_NAME_STOP = {"the", "and", "of", "at", "by", "llc", "inc", "ltd", "co", "company", "corp", "limited", "plc", "group"}


async def _find_variant_domain(name: str, town: str, category: str, tlds: List[str], phone_digits: str) -> str:
    """Tries common short/variant domains and returns one only if its page shows this business's phone or town."""
    from harvester.web_auditor import domain_exists
    raw = [t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in _NAME_STOP]
    if not raw:
        return ""
    town_slug = re.sub(r"[^a-z]", "", (town or "").lower())
    slugs = {"".join(raw[:2]), raw[0] + town_slug, "".join(t[0] for t in raw) + town_slug}
    for word in CATEGORY_WORDS.get(category, []):
        slugs.update({raw[0] + word, "".join(raw[:2]) + word})
    slugs = {s for s in slugs if len(s) >= 5 and s != "".join(raw)}  # exact name already tried
    hosts = [f"{s}{tld}" for s in slugs for tld in tlds]

    async def check(host):
        if await domain_exists(host) is not True:
            return ""
        url = f"https://{host}"
        return url if await _site_mentions(url, phone_digits, town) else ""

    for r in await asyncio.gather(*(check(h) for h in hosts)):
        if r:
            return r
    return ""


def _norm_site(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    return url


async def _build_lead(biz: Dict[str, Any], country: str, region: str, city: str, category: str) -> Optional[Lead]:
    formatted, digits, is_mobile = phone_info(biz["phone"], country)
    if not formatted:
        return None

    website = _norm_site(biz["website"])
    socials = dict(biz.get("socials") or {})
    parsed = urllib.parse.urlparse(website)
    host = parsed.netloc.lower()
    if CHAIN_NAME.search(biz["name"]) or (website and CHAIN_PATH.search(parsed.path or "")):
        return None  # branch of a multi-location company - not a freelance client
    social_only = False
    if website and any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS):
        key = "google_profile" if "goo" in host else host.replace("www.", "").split(".")[0]
        socials.setdefault(key, website)
        website, social_only = "", True

    region = _region_from_listing(biz, country, region)

    verified_by_lookup = False
    if not website:
        tlds = COUNTRY_TLDS.get(country, [".com"])
        # Second try because a single network failure would otherwise look like "no website"
        found, blocked = await find_company_domain(biz["name"], tlds)
        if not found:
            found, blocked2 = await find_company_domain(biz["name"], tlds)
            blocked = blocked or blocked2
        if not found and blocked:
            return None  # a site with its name exists but hides from checkers - can't claim "no website"
        if not found:
            # Many businesses use a short/variant domain (modeltown.ca for "Model Town Auto Service") -
            # accept one only when the page carries this business's phone or town
            found = await _find_variant_domain(biz["name"], biz.get("city") or city, category, tlds, digits)
            if found:
                website, verified_by_lookup = found, True
        if found and not website:
            # A domain carrying the same name may belong to a different business. Only accept it if the
            # page mentions this business's phone or town; otherwise we can't say "no website" either -> skip.
            if not await _site_mentions(found, digits, biz.get("city") or city):
                return None
            website, verified_by_lookup = found, True

    email = biz.get("email", "") if is_valid_email(biz.get("email", "")) else ""
    whatsapp = digits if is_mobile else ""
    location = ", ".join(filter(None, [biz.get("city") or city, region, country]))

    if website:
        audit, contacts = await asyncio.gather(audit_website(website),
                                               extract_contacts_from_url(website, default_country=country),
                                               return_exceptions=True)
        # A listing that links to a sub-page (e.g. /office-info/meet-dr-x) can 404 while the site itself is fine -
        # judge the homepage, not the stale deep link
        parsed_site = urllib.parse.urlparse(website)
        if (not isinstance(audit, Exception) and parsed_site.path not in ("", "/")
                and any("HTTP error" in p for p in audit.get("pain_points", []))):
            website = f"{parsed_site.scheme}://{parsed_site.netloc}/"
            audit = await audit_website(website)
        if isinstance(audit, Exception) or not audit.get("needs_work"):
            return None  # site is fine (or could not be checked) -> no evidence they need us
        if not isinstance(contacts, Exception):
            email = email or contacts.get("email", "")
            whatsapp = whatsapp or contacts.get("whatsapp", "")
            for k, v in (contacts.get("social_links") or {}).items():
                socials.setdefault(k, v)
        pain_points = audit["pain_points"][:4]
        if verified_by_lookup:
            pain_points.append("Website is not linked on its map listing (customers searching maps can't find it)")
        return Lead(
            business_name=biz["name"][:80], source="local_verified", service_needed="website_redesign",
            category=category, website=website, has_website=True, location=location,
            country=country, region=region, email=email, phone=formatted, whatsapp=whatsapp,
            social_links=socials, pain_points=pain_points[:5], intent_level="High",
            budget_estimate="$1,500 - $5,000", audit_score=audit["audit_score"],
            audit_summary=f"{audit['summary']} Address: {biz.get('address') or location}. Source: {biz['ref']}",
        )

    # "No website found" is only trustworthy if our own connection worked during the domain check
    if not await our_internet_ok():
        return None

    if social_only or socials:
        pain_points = ["Only has a social media page - no website of its own",
                       "No website found for its name (checked " + ", ".join(COUNTRY_TLDS.get(country, [".com"])) + ")"]
        service, score = "web_development", 15
    else:
        pain_points = ["No website on its map listing",
                       "No live website found for its name (checked " + ", ".join(COUNTRY_TLDS.get(country, [".com"])) + ")"]
        service, score = "web_development", 10
    return Lead(
        business_name=biz["name"][:80], source="local_verified", service_needed=service,
        category=category, website="", has_website=False, location=location,
        country=country, region=region, email=email, phone=formatted, whatsapp=whatsapp,
        social_links=socials, pain_points=pain_points, intent_level="First-Mover",
        budget_estimate="$800 - $3,000", audit_score=score,
        audit_summary=f"Listed {category.lower()} with a verified phone and no website. Address: {biz.get('address') or location}. Source: {biz['ref']}",
    )


async def harvest_local_businesses(niche: str = "All Industries", country: str = "ALL", region: str = "all",
                                   limit: int = 20, exclude: Optional[Set[str]] = None,
                                   time_budget_s: float = 180.0) -> List[Lead]:
    """Returns up to `limit` verified local-business leads that show a real need for web/digital services."""
    started = time.time()
    exclude = exclude or set()
    use_tomtom = bool(config.TOMTOM_API_KEY)
    categories = resolve_categories(niche)
    n_targets = min(10, max(3, limit // 4)) if use_tomtom else min(4, max(2, limit // 10))
    targets = pick_targets(country, region, n_targets)

    async def collect(target):
        ck, reg, (city, lat, lon) = target
        cats = random.sample(categories, min(2, len(categories)))
        try:
            if use_tomtom:
                found = []
                for cat in cats:
                    for phrase in cat["query"].split("|"):
                        for b in await tomtom_search(phrase, ISO2[ck], lat, lon):
                            found.append((b, cat["label"]))
            else:
                found = []
                for b in await overpass_search(cats, lat, lon):
                    found.append((b, cats[0]["label"] if len(cats) == 1 else _label_for(b, cats)))
            print(f"[local] {city}, {reg}, {ck}: {len(found)} listings")
            return [(b, ck, reg, city, label) for b, label in found]
        except Exception as e:
            print(f"[local] {city}, {reg}, {ck}: {e}")
            return []

    collect_budget = max(30, time_budget_s * 0.5)

    async def collect_with_budget(target):
        try:
            return await asyncio.wait_for(collect(target), collect_budget)
        except asyncio.TimeoutError:
            print(f"[local] {target[2][0]}, {target[1]}, {target[0]}: map server too slow, skipped")
            return []

    batches = await asyncio.gather(*(collect_with_budget(t) for t in targets), return_exceptions=True)
    candidates, seen_refs = [], set()
    for batch in batches:
        for c in (batch if isinstance(batch, list) else []):
            # The same listing can come back from two category searches - count it once
            if c[0]["ref"] not in seen_refs:
                seen_refs.add(c[0]["ref"])
                candidates.append(c)

    # Chains: flagged as brand, or the same name on 3+ separate listings
    name_counts = Counter(c[0]["name"].lower() for c in candidates)
    seen: Set[str] = set()
    filtered = []
    for c in candidates:
        b = c[0]
        key = b["name"].lower()
        if not b["name"] or b["is_brand"] or name_counts[key] >= 3 or key in seen or key in exclude:
            continue
        fmt, _, _ = phone_info(b["phone"], c[1])
        if not fmt or fmt in exclude:
            continue
        seen.add(key)
        filtered.append(c)
    # Interleave by city so one dense city doesn't fill the whole batch
    random.shuffle(filtered)
    print(f"[local] {len(candidates)} listings -> {len(filtered)} independent businesses with valid phones")

    leads: List[Lead] = []
    sem = asyncio.Semaphore(12)

    async def process(c):
        async with sem:
            if len(leads) >= limit or time.time() - started > time_budget_s:
                return None
            try:
                return await asyncio.wait_for(_build_lead(c[0], c[1], c[2], c[3], c[4]), timeout=45)
            except Exception:
                return None

    chunk = max(12, limit)
    for i in range(0, len(filtered), chunk):
        if len(leads) >= limit or time.time() - started > time_budget_s:
            break
        for r in await asyncio.gather(*(process(c) for c in filtered[i:i + chunk])):
            if isinstance(r, Lead) and len(leads) < limit:
                leads.append(r)
    print(f"[local] {len(leads)} leads with verified need in {time.time() - started:.0f}s")
    return leads


def _label_for(biz: Dict[str, Any], cats: List[Dict[str, Any]]) -> str:
    """Overpass returns one combined list for several categories - match each element back by its tags."""
    tags = biz.get("tags", {})
    for cat in cats:
        for key, values in cat["osm"]:
            if key != "name" and re.fullmatch(values, tags.get(key, "")):
                return cat["label"]
    return cats[0]["label"]
