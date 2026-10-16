import httpx
import asyncio
import datetime
import urllib.parse
from typing import List, Dict, Any

from models import Lead
from harvester.web_auditor import audit_website
from enricher.contact_extractor import extract_contacts_from_url
from enricher.lead_quality import normalize_niche

# iTunes Store Country Code mapping
COUNTRY_APP_STORE = {
    "US": "us",
    "UK": "gb",
    "CA": "ca",
    "UAE": "ae",
    "QA": "qa"
}
STORE_LABEL = {"us": "US", "gb": "UK", "ca": "Canada", "ae": "UAE", "qa": "Qatar"}


def _days_since(iso: str) -> int:
    try:
        d = datetime.datetime.strptime(iso[:10], "%Y-%m-%d").date()
        return (datetime.date.today() - d).days
    except Exception:
        return -1


async def harvest_app_store(niche: str = "fitness", country: str = "US", limit: int = 15) -> List[Lead]:
    """
    Harvests REAL business apps from the Apple App Store (US, UK, Canada, Qatar, UAE).
    Games are excluded. Apps with low ratings or no update in a long time are prioritised.
    Every pain point is derived from real App Store data (rating, review count, last update).
    """
    leads = []
    country_up = country.upper()
    c_codes = ["ae", "qa", "us", "gb", "ca"] if country_up == "ALL" else [COUNTRY_APP_STORE.get(country_up, "us")]
    phrase, _ = normalize_niche(niche)

    app_candidates = []
    seen_sellers = set()
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for c_code in c_codes:
                url = f"https://itunes.apple.com/search?term={urllib.parse.quote(phrase)}&country={c_code}&entity=software&limit=50"
                res = await client.get(url)
                if res.status_code != 200:
                    continue
                for item in res.json().get("results", []):
                    track_name = item.get("trackName", "")
                    seller_name = item.get("sellerName", "") or item.get("artistName", "")
                    if not track_name or not seller_name:
                        continue
                    # Skip games - kids' game studios are not agency clients
                    genres = [g.lower() for g in item.get("genres", [])] + [item.get("primaryGenreName", "").lower()]
                    if any("game" in g for g in genres):
                        continue
                    if seller_name.lower() in seen_sellers:
                        continue
                    seen_sellers.add(seller_name.lower())

                    rating = item.get("averageUserRating") or 0
                    app_candidates.append({
                        "name": track_name,
                        "seller": seller_name,
                        "rating": round(rating, 1),
                        "rating_count": item.get("userRatingCount", 0) or 0,
                        "seller_url": item.get("sellerUrl", "") or "",  # real developer website only
                        "app_url": item.get("trackViewUrl", ""),
                        "days_since_update": _days_since(item.get("currentVersionReleaseDate", "")),
                        "store": c_code,
                    })
    except Exception as e:
        print(f"App Store search error: {e}")

    # Opportunity score: low rating and stale apps first
    def opportunity(x):
        r = x["rating"] if x["rating"] > 0 else 4.0
        stale = 1 if x["days_since_update"] > 365 else 0
        return (-stale, r)
    app_candidates.sort(key=opportunity)

    async def process_app(item: Dict[str, Any]) -> Lead:
        app_name = item["name"]
        seller = item["seller"]
        rating = item["rating"]
        web_url = item["seller_url"]
        store = STORE_LABEL.get(item["store"], item["store"].upper())

        contacts = {"email": "", "phone": "", "whatsapp": "", "social_links": {}}
        audit_res = {"audit_score": 35, "pain_points": [], "summary": ""}

        # Discover real developer website if sellerUrl is missing
        if not web_url or "apple.com" in web_url:
            clean_seller = re.sub(r'[^\w\s]', '', seller).strip()
            if len(clean_seller) >= 3:
                discovered = await ddg_search(f"{clean_seller} official website")
                for d in discovered[:3]:
                    d_url = d.get("url", "")
                    if d_url.startswith("http") and not any(bad in d_url for bad in ["apple.com", "google.com", "wikipedia.org", "linkedin.com"]):
                        web_url = d_url
                        break

        # Only audit/crawl the developer's own website
        if web_url and web_url.startswith("http") and "apple.com" not in web_url:
            a_res, c_res = await asyncio.gather(audit_website(web_url), extract_contacts_from_url(web_url), return_exceptions=True)
            if not isinstance(a_res, Exception):
                audit_res = a_res
            if not isinstance(c_res, Exception):
                contacts = c_res
        else:
            web_url = ""

        # MANDATORY FOR FREELANCER: Must have at least 1 reachable contact
        email = contacts.get("email", "")
        phone = contacts.get("phone", "")
        whatsapp = contacts.get("whatsapp", "")
        if not (email or phone or whatsapp):
            return None

        contacts.setdefault("social_links", {})
        contacts["social_links"]["app_store"] = item["app_url"]

        # Real, data-backed pain points
        if rating > 0:
            pain_points = [f"'{app_name}' rated {rating} stars from {item['rating_count']:,} ratings ({store} App Store)"]
        else:
            pain_points = [f"'{app_name}' has low review count on the {store} App Store"]
        d = item["days_since_update"]
        if d > 365:
            pain_points.append(f"App not updated in {d // 30} months - needs modern UI/UX overhaul")
        elif d >= 0:
            pain_points.append(f"Last updated {d} days ago")
        if rating and rating < 4.0:
            pain_points.append("Below-4-star rating hurts user retention and conversions")
        pain_points.extend(audit_res.get("pain_points", [])[:2])

        score = int(min(70, max(15, (rating or 3.0) * 12 - (15 if d > 365 else 0))))
        return Lead(
            business_name=f"{seller} — {app_name[:30]}",
            source="app_store",
            service_needed="mobile_apps",
            website=web_url or item["app_url"],
            has_website=bool(web_url),
            location=f"{store} App Store",
            email=email,
            phone=phone,
            whatsapp=whatsapp,
            contact_name=seller,
            social_links=contacts.get("social_links", {}),
            pain_points=pain_points[:4],
            intent_level="High",
            budget_estimate="$4,500 - $12,000",
            audit_score=score,
            audit_summary=f"Rating {rating or 'n/a'} ({item['rating_count']} ratings), last update {d} days ago. App: {item['app_url']}"
        )

    tasks = [process_app(item) for item in app_candidates[:limit * 3]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Lead):
            leads.append(r)
            if len(leads) >= limit:
                break

    return leads
