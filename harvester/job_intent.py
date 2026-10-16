import httpx
import re
import asyncio
from typing import List, Dict, Any
from models import Lead
from harvester.web_auditor import audit_website
from enricher.contact_extractor import extract_contacts_from_url
from enricher.lead_quality import verify_company_domain

# Valid Jobicy geoSlug values (see https://jobicy.com/api/v2/remote-jobs?get=locations)
JOBICY_GEO = {"US": "usa", "UK": "uk", "CA": "canada", "UAE": "united-arab-emirates", "QA": "emea"}

# Country search tokens for job boards
COUNTRY_JOB_TAGS = {
    "US": ["usa", "united states", "us", "america", "remote"],
    "UK": ["uk", "united kingdom", "london", "great britain", "remote"],
    "CA": ["canada", "toronto", "vancouver", "remote"],
    "UAE": ["uae", "dubai", "abu dhabi", "united arab emirates", "middle east", "remote"],
    "QA": ["qatar", "doha", "middle east", "remote"]
}

async def fetch_live_jobicy_jobs(country: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Fetches real live remote & tech job postings from Jobicy Open API."""
    jobs = []
    try:
        geo_param = JOBICY_GEO.get(country.upper(), "")
        url = f"https://jobicy.com/api/v2/remote-jobs?count={limit}"
        if geo_param:
            url += f"&geo={geo_param}"
            
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                for j in data.get("jobs", []):
                    c_name = j.get("companyName", "").strip()
                    title = j.get("jobTitle", "").strip()
                    url_link = j.get("url", "")
                    geo = j.get("jobGeo", "Remote")
                    salary = ""
                    s_min = j.get("annualSalaryMin")
                    s_max = j.get("annualSalaryMax")
                    currency = j.get("salaryCurrency", "USD")
                    if s_min and s_max:
                        salary = f"{currency} {s_min:,} - {s_max:,} / yr"
                    elif s_min:
                        salary = f"{currency} {s_min:,}+ / yr"
                    else:
                        salary = "Salary not disclosed"

                    if c_name and title:
                        jobs.append({
                            "company": c_name,
                            "position": title,
                            "location": geo,
                            "salary": salary,
                            "job_url": url_link
                        })
    except Exception as e:
        print(f"Jobicy API error: {e}")
    return jobs

async def fetch_live_remoteok_jobs(limit: int = 25) -> List[Dict[str, Any]]:
    """Fetches real live active hiring jobs from RemoteOK API."""
    jobs = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
            res = await client.get("https://remoteok.com/api")
            if res.status_code == 200:
                data = res.json()
                for item in data[1:100]:
                    c_name = item.get("company", "").strip()
                    pos = item.get("position", "").strip()
                    loc = item.get("location", "Remote")
                    s_min = item.get("salary_min")
                    s_max = item.get("salary_max")
                    
                    salary = ""
                    if s_min and s_max:
                        salary = f"${s_min:,} - ${s_max:,} / yr"
                    elif s_min:
                        salary = f"${s_min:,}+ / yr"
                    else:
                        salary = "Salary not disclosed"

                    url = item.get("url") or ""
                    if c_name and pos:
                        jobs.append({
                            "company": c_name,
                            "position": pos,
                            "location": loc,
                            "salary": salary,
                            "job_url": url
                        })
                    if len(jobs) >= limit:
                        break
    except Exception as e:
        print(f"RemoteOK API error: {e}")
    return jobs

async def harvest_job_intent(niche: str = "web", country: str = "US", limit: int = 15) -> List[Lead]:
    """
    Harvests 100% REAL hiring companies from live Jobicy & RemoteOK feeds.
    Crawls their real corporate websites for genuine contact information.
    """
    leads = []
    
    # Query both live sources concurrently
    j_task = fetch_live_jobicy_jobs(country=country, limit=limit * 2)
    r_task = fetch_live_remoteok_jobs(limit=limit * 2)
    j_jobs, r_jobs = await asyncio.gather(j_task, r_task, return_exceptions=True)

    all_jobs = []
    if isinstance(j_jobs, list):
        all_jobs.extend(j_jobs)
    if isinstance(r_jobs, list):
        all_jobs.extend(r_jobs)

    # Filter by target niche relevance
    niche_lower = niche.lower()
    keywords = ["react", "web", "frontend", "backend", "full stack", "software", "mobile", "ios", "android", "flutter", "marketing", "seo", "design", "ui", "ux", "python", "devops", "shopify", "wordpress"]
    
    if niche_lower != "all" and niche_lower != "technology":
        keywords.insert(0, niche_lower)

    filtered_jobs = []
    seen_companies = set()

    for item in all_jobs:
        c_name = item["company"]
        pos = item["position"].lower()
        if c_name.lower() in seen_companies:
            continue
        # Check relevance
        if any(k in pos for k in keywords):
            seen_companies.add(c_name.lower())
            filtered_jobs.append(item)
            if len(filtered_jobs) >= limit:
                break

    if len(filtered_jobs) < limit:
        for item in all_jobs:
            c_name = item["company"]
            if c_name.lower() not in seen_companies:
                seen_companies.add(c_name.lower())
                filtered_jobs.append(item)
                if len(filtered_jobs) >= limit:
                    break

    async def process_job_lead(item: Dict[str, Any]) -> Lead:
        c_name = item["company"]
        pos = item["position"]
        loc = item.get("location", f"{country}")
        salary = item.get("salary") or "Salary not disclosed"
        
        # Categorize service needed
        pos_l = pos.lower()
        if any(k in pos_l for k in ["mobile", "ios", "android", "flutter", "react native"]):
            service = "mobile_apps"
        elif any(k in pos_l for k in ["seo", "growth", "organic", "content"]):
            service = "seo"
        elif any(k in pos_l for k in ["social", "instagram", "marketing", "media", "community"]):
            service = "social_media"
        elif any(k in pos_l for k in ["shopify", "ecommerce", "woocommerce", "store", "magento"]):
            service = "ecommerce"
        else:
            service = "web_development"

        # Only use a company domain that is live AND carries the company's name
        site_url = await verify_company_domain(c_name, [".com", ".io", ".co", ".ai"])
        contacts = {"email": "", "phone": "", "whatsapp": "", "social_links": {}}
        if site_url:
            contacts = await extract_contacts_from_url(site_url)
        email = contacts.get("email", "")  # real email or empty - never invented
        job_url = item.get("job_url", "")

        pain_points = [
            f"Actively hiring for '{pos}' (Annual salary budget: {salary})",
            f"Facing lengthy 45-60 day recruitment cycle & recruiter fees",
            f"Paying high employer taxes, benefits, and management overhead for in-house staff",
            f"Immediate agency deployment can take over the roadmap at 40% less overhead"
        ]

        return Lead(
            business_name=c_name,
            source="job_intent",
            service_needed=service,
            website=site_url or job_url,
            has_website=True,
            location=loc,
            email=email,
            phone=contacts.get("phone", ""),
            whatsapp=contacts.get("whatsapp", ""),
            contact_name=f"Hiring Team @ {c_name}",
            social_links=contacts.get("social_links", {}),
            pain_points=pain_points,
            intent_level="High",
            budget_estimate=f"Allocated Budget: {salary}",
            audit_score=65,
            audit_summary=(f"Company is actively recruiting for {pos}. Job post: {job_url}"
                           + ("" if site_url else " | Company website could not be verified automatically."))
        )

    tasks = [process_job_lead(item) for item in filtered_jobs[:limit]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Lead):
            leads.append(r)

    return leads
