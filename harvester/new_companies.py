import re
import asyncio
import datetime
import urllib.parse
from typing import List

import httpx
from bs4 import BeautifulSoup

from models import Lead
from harvester.web_auditor import audit_website
from enricher.contact_extractor import extract_contacts_from_url
from enricher.lead_quality import (
    BROWSER_HEADERS, ddg_search, is_directory_result, normalize_niche, verify_company_domain,
    name_from_domain, GENERIC_TITLE
)

CH_BASE = "https://find-and-update.company-information.service.gov.uk"


async def fetch_uk_companies_house(niche: str, limit: int = 15, days: int = 30) -> List[Lead]:
    """
    Queries the official UK Companies House advanced search for ACTIVE companies
    incorporated in the last `days` days. Extracts real name, company number,
    incorporation date and registered office address.
    Website/email are only filled if a live website carrying the company name is verified.
    """
    _, keyword = normalize_niche(niche)
    # Pakistan time is ahead of the UK; Companies House rejects "to" dates that are not in the past there
    to_d = datetime.date.today() - datetime.timedelta(days=2)
    from_d = to_d - datetime.timedelta(days=days)
    params = {
        "status": "active",
        "incorporationFromDay": from_d.day, "incorporationFromMonth": from_d.month, "incorporationFromYear": from_d.year,
        "incorporationToDay": to_d.day, "incorporationToMonth": to_d.month, "incorporationToYear": to_d.year,
    }
    if keyword:
        params["companyNameIncludes"] = keyword

    raw = []
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=BROWSER_HEADERS, follow_redirects=True) as client:
            res = await client.get(f"{CH_BASE}/advanced-search/get-results", params=params)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                err = soup.select_one(".govuk-error-summary")
                if err:
                    print(f"Companies House rejected query: {err.get_text(' ', strip=True)[:200]}")
                for row in soup.select("table tbody tr"):
                    a_tag = row.select_one("h2 a")
                    if not a_tag:
                        continue
                    hidden = a_tag.select_one(".govuk-visually-hidden")
                    if hidden:
                        hidden.extract()
                    name = a_tag.get_text(" ", strip=True)
                    profile = CH_BASE + a_tag.get("href", "")
                    items = [li.get_text(" ", strip=True) for li in row.select("ul li") if li.get_text(strip=True)]
                    number, incorp, address = "", "", ""
                    for t in items:
                        m = re.match(r"([A-Z0-9]{6,8}) - (?:Incorporated|Registered) on (.+)", t)
                        if m:
                            number, incorp = m.group(1), m.group(2)
                        elif not t.startswith("SIC codes") and not any(k in t.lower() for k in ("company", "partnership", "limited by")) and not address:
                            address = t
                    raw.append({"name": name, "number": number, "incorp": incorp, "address": address, "profile": profile})
                    if len(raw) >= limit:
                        break
    except Exception as e:
        print(f"UK Companies House error: {e}")

    async def build(item) -> Lead:
        name = item["name"]
        # Try to find a REAL website for this company (most brand-new companies have none)
        site = await verify_company_domain(name, [".co.uk", ".com", ".uk"])
        contacts = {"email": "", "phone": "", "whatsapp": "", "social_links": {}}
        if site:
            contacts = await extract_contacts_from_url(site)
        contacts.setdefault("social_links", {})
        contacts["social_links"]["companies_house"] = item["profile"]

        # City/postcode = last part of registered address
        loc = item["address"] or "United Kingdom"
        pain_points = [
            f"Official UK company #{item['number']} - incorporated {item['incorp']}",
            f"Registered office: {item['address']}" if item["address"] else "Registered office on Companies House",
            "No website found for this company yet" if not site else "Website live - early-stage digital presence",
            "Needs corporate website, domain email, Google Business profile & branding",
        ]
        return Lead(
            business_name=name,
            source="new_business",
            service_needed="web_development",
            website=site,
            has_website=bool(site),
            location=loc,
            email=contacts.get("email", ""),
            phone=contacts.get("phone", ""),
            whatsapp=contacts.get("whatsapp", ""),
            contact_name=f"Directors of {name}",
            social_links=contacts.get("social_links", {}),
            pain_points=pain_points,
            intent_level="First-Mover",
            budget_estimate="Est. $1,500 - $4,000 (launch package)",
            audit_score=15 if not site else 40,
            audit_summary=f"Incorporated {item['incorp']} (Companies House #{item['number']}). Verify directors: {item['profile']}/officers"
        )

    results = await asyncio.gather(*[build(i) for i in raw], return_exceptions=True)
    return [r for r in results if isinstance(r, Lead)]


async def fetch_fresh_regional_businesses(niche: str, country: str, limit: int = 15) -> List[Lead]:
    """
    Hunts newly launched / emerging businesses in US, Canada, Qatar, or UAE via live web search.
    (No official public registry with free access exists for these countries.)
    """
    country_map = {
        "US": ("United States", ["New York", "California"]),
        "CA": ("Canada", ["Toronto", "Vancouver"]),
        "UAE": ("United Arab Emirates", ["Dubai", "Abu Dhabi"]),
        "QA": ("Qatar", ["Doha", "Lusail"])
    }
    c_name, cities = country_map.get(country.upper(), (country, [country]))
    phrase, _ = normalize_niche(niche)

    raw_sites, seen = [], set()
    for city in cities:
        if len(raw_sites) >= limit:
            break
        for r in await ddg_search(f"new {phrase} opening {city} {datetime.date.today().year}"):
            domain = urllib.parse.urlparse(r["url"]).netloc.lower()
            if domain in seen or is_directory_result(domain, r["title"]):
                continue
            seen.add(domain)
            name = re.sub(r' - .*| \| .*|: .*', '', r["title"]).strip()
            if not name or GENERIC_TITLE.search(name):
                name = name_from_domain(domain)
            p = urllib.parse.urlparse(r["url"])
            raw_sites.append({"name": name, "url": f"{p.scheme}://{p.netloc}/", "location": f"{city}, {c_name}"})
            if len(raw_sites) >= limit:
                break

    async def build(item) -> Lead:
        url = item["url"]
        contacts, audit = await asyncio.gather(extract_contacts_from_url(url), audit_website(url))
        if contacts.get("site_name") and not GENERIC_TITLE.search(contacts["site_name"]):
            item["name"] = contacts["site_name"]

        pain_points = [f"Emerging business discovered in {item['location']}"]
        pain_points.extend(audit.get("pain_points", [])[:3])

        return Lead(
            business_name=item["name"][:50],
            source="new_business",
            service_needed="web_development",
            website=url,
            has_website=True,
            location=item["location"],
            email=contacts.get("email", ""),
            phone=contacts.get("phone", ""),
            whatsapp=contacts.get("whatsapp", ""),
            social_links=contacts.get("social_links", {}),
            pain_points=pain_points[:4],
            intent_level="First-Mover",
            budget_estimate="Est. $2,000 - $6,000 (launch package)",
            audit_score=audit.get("audit_score", 45),
            audit_summary=audit.get("summary", "New market venture.")
        )

    results = await asyncio.gather(*[build(i) for i in raw_sites], return_exceptions=True)
    return [r for r in results if isinstance(r, Lead)]


async def harvest_new_companies(niche: str = "consulting", country: str = "UK", limit: int = 15) -> List[Lead]:
    """
    Dispatches to official UK Companies House for UK, or live regional discovery for US, CA, UAE, QA.
    """
    country_up = country.upper()
    if country_up == "UK":
        return await fetch_uk_companies_house(niche=niche, limit=limit)
    elif country_up == "ALL":
        half = max(2, limit // 2)
        uk_task = fetch_uk_companies_house(niche=niche, limit=half)
        reg_task = fetch_fresh_regional_businesses(niche=niche, country="UAE", limit=half)
        res1, res2 = await asyncio.gather(uk_task, reg_task, return_exceptions=True)
        leads = []
        if isinstance(res1, list):
            leads.extend(res1)
        if isinstance(res2, list):
            leads.extend(res2)
        return leads[:limit]
    else:
        return await fetch_fresh_regional_businesses(niche=niche, country=country, limit=limit)
