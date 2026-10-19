import re
import asyncio
import httpx
import urllib.parse
from typing import List, Dict, Any

from models import Lead
from harvester.web_auditor import audit_website
from enricher.contact_extractor import extract_contacts_from_url
from enricher.lead_quality import (
    ddg_search, is_directory_result, normalize_niche, name_from_domain, GENERIC_TITLE
)

COUNTRY_ECOM = {
    "US": ("United States", ["New York", "California", "Florida"]),
    "UK": ("United Kingdom", ["London", "Manchester"]),
    "CA": ("Canada", ["Toronto", "Vancouver"]),
    "UAE": ("United Arab Emirates", ["Dubai", "Abu Dhabi"]),
    "QA": ("Qatar", ["Doha"])
}

async def harvest_ecom_stores(niche: str = "ecommerce", country: str = "US", limit: int = 15) -> List[Lead]:
    """
    Harvests active E-Commerce & DTC online stores (Shopify, WooCommerce, Custom)
    in target markets. Audits mobile conversion issues, slow checkouts, and extracts
    direct customer support WhatsApp, Phone, and Email for agency pitches.
    """
    country_key = (country or "US").upper()
    phrase, _ = normalize_niche(niche)

    target_countries = ["US", "UK", "CA", "UAE", "QA"] if country_key == "ALL" else [country_key]
    leads = []
    seen_domains = set()
    raw_targets = []

    import random
    all_queries = []
    for ck in target_countries:
        c_name, cities = COUNTRY_ECOM.get(ck, (country, [country]))
        city = random.choice(cities)
        all_queries.append((ck, cities[0], f'{phrase} online store {city} {c_name} phone'))
        all_queries.append((ck, cities[0], f'{phrase} brand shop {city} contact'))
        all_queries.append((ck, cities[0], f'{phrase} powered by shopify {city}'))

    random.shuffle(all_queries)
    active_queries = all_queries[:4]
    search_tasks = [ddg_search(q) for _, _, q in active_queries]
    all_results_list = await asyncio.gather(*search_tasks, return_exceptions=True)

    for (ck, primary_city, q), query_res in zip(active_queries, all_results_list):
        if len(raw_targets) >= limit * 2:
            break
        if not isinstance(query_res, list):
            continue
        for r in query_res:
            real_url, title = r.get("url", ""), r.get("title", "")
            domain = urllib.parse.urlparse(real_url).netloc.lower()
            if not domain or domain in seen_domains or is_directory_result(domain, title):
                continue
            if any(bad in domain for bad in ["amazon.", "ebay.", "etsy.", "walmart.", "aliexpress.", "target."]):
                continue
            seen_domains.add(domain)

            clean_name = re.sub(r' - .*| \| .*|: .*| official .*| Home$| Store$| Online Store$', '', title, flags=re.I).strip()
            if not clean_name or len(clean_name) < 3 or GENERIC_TITLE.search(clean_name):
                clean_name = name_from_domain(domain)

            p = urllib.parse.urlparse(real_url)
            raw_targets.append({
                "name": clean_name[:60],
                "url": f"{p.scheme}://{p.netloc}/",
                "location": f"{primary_city}, {ck}",
                "country": ck,
            })
            if len(raw_targets) >= limit * 2:
                break

    # No App Store "fallback": app developers are not online stores and made leads look fake

    async def process_store(item: Dict[str, str]) -> Lead:
        b_name = item["name"]
        target_url = item["url"]
        loc = item["location"]

        audit_task = audit_website(target_url)
        contact_task = extract_contacts_from_url(target_url, default_country=item["country"])
        audit_res, contacts = await asyncio.gather(audit_task, contact_task, return_exceptions=True)

        # Only stores with problems we actually observed are leads
        if isinstance(audit_res, Exception) or not audit_res.get("needs_work"):
            return None
        if isinstance(contacts, Exception):
            contacts = {"email": "", "phone": "", "whatsapp": "", "social_links": {}, "site_name": ""}

        # MANDATORY FOR FREELANCER: Must have at least 1 reachable contact
        email = contacts.get("email", "")
        phone = contacts.get("phone", "")
        whatsapp = contacts.get("whatsapp", "")
        if not (email or phone or whatsapp):
            return None

        site_name = contacts.get("site_name", "")
        if site_name and len(site_name) >= 3 and not GENERIC_TITLE.search(site_name):
            b_name = site_name

        audit_score = audit_res.get("audit_score", 45)
        pain_points = list(audit_res.get("pain_points", []))

        return Lead(
            business_name=b_name,
            source="ecom_funnel",
            service_needed="ecommerce",
            website=target_url,
            has_website=True,
            location=loc,
            country=item["country"],
            email=email,
            phone=phone,
            whatsapp=whatsapp,
            contact_name="",
            social_links=contacts.get("social_links", {}),
            pain_points=pain_points[:4],
            intent_level="High",
            budget_estimate="$2,500 - $7,500",
            audit_score=audit_score,
            audit_summary=audit_res.get("summary", "E-Commerce performance audit completed.")
        )

    tasks = [process_store(item) for item in raw_targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Lead):
            leads.append(r)
            if len(leads) >= limit:
                break

    return leads
