import re
import asyncio
import urllib.parse
from typing import List, Dict, Any

from models import Lead
from enricher.contact_extractor import clean_whatsapp_number, is_valid_email, format_phone_international
from enricher.lead_quality import ddg_search, normalize_niche

COUNTRY_GEO = {
    "US": ("United States", "New York", "+1"),
    "UK": ("United Kingdom", "London", "+44"),
    "CA": ("Canada", "Toronto", "+1"),
    "UAE": ("United Arab Emirates", "Dubai", "+971"),
    "QA": ("Qatar", "Doha", "+974")
}

PHONE_REGEX = re.compile(r'(\+?[0-9]{1,3}[\s\-]?[0-9]{2,4}[\s\-]?[0-9]{3,4}[\s\-]?[0-9]{3,4})')
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')

async def harvest_social_leads(niche: str = "local business", country: str = "US", limit: int = 15) -> List[Lead]:
    """
    Harvests active client opportunities directly from social channels:
    LinkedIn, Instagram, Facebook, X (Twitter), and Reddit.
    Finds founders, business pages, and hiring posts seeking dev/marketing/software services.
    """
    country_up = (country or "US").upper()
    c_name, main_city, def_prefix = COUNTRY_GEO.get(country_up, ("United States", "New York", "+1"))
    phrase, _ = normalize_niche(niche)
    target_term = phrase if phrase != "local business" else "business"

    import random
    country_cities = {
        "US": ["New York", "Los Angeles", "Chicago", "Miami", "Houston", "Dallas"],
        "UK": ["London", "Manchester", "Birmingham", "Leeds"],
        "CA": ["Toronto", "Vancouver", "Calgary", "Montreal"],
        "UAE": ["Dubai", "Abu Dhabi", "Sharjah"],
        "QA": ["Doha", "Lusail"],
    }
    pool = [(ck, c) for ck, cs in country_cities.items() for c in cs] if country_up == "ALL" \
        else [(country_up, c) for c in country_cities.get(country_up, ["New York"])]
    picks = [random.choice(pool) for _ in range(3)]

    # (query, platform label, platform key, country code, city shown as location)
    queries = [
        (f'facebook {target_term} {picks[0][1]} call', "Facebook", "facebook", picks[0][0], picks[0][1]),
        (f'facebook {target_term} {picks[1][1]} phone', "Facebook", "facebook", picks[1][0], picks[1][1]),
        (f'facebook {target_term} {picks[2][1]} whatsapp', "Facebook", "facebook", picks[2][0], picks[2][1]),
        (f'reddit hiring {target_term} developer', "Reddit", "reddit", "" if country_up == "ALL" else country_up, "Online"),
    ]
    random.shuffle(queries)

    leads = []
    seen = set()

    search_tasks = [ddg_search(q[0]) for q in queries]
    all_results_list = await asyncio.gather(*search_tasks, return_exceptions=True)

    for (q, platform_label, p_key, q_country, q_city), query_res in zip(queries, all_results_list):
        def_prefix = COUNTRY_GEO.get(q_country or "US", COUNTRY_GEO["US"])[2]
        if len(leads) >= limit:
            break
        if not isinstance(query_res, list):
            continue
        for r in query_res:
            if len(leads) >= limit:
                break
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            # Extract phone or WhatsApp (ONLY from title and snippet, NEVER from URL digits)
            text_without_url = f"{title} {snippet}"
            phone = ""
            whatsapp = ""
            email = ""

            em_match = EMAIL_REGEX.search(text_without_url)
            if em_match:
                candidate_email = em_match.group(0).lower().strip()
                if is_valid_email(candidate_email):
                    email = candidate_email

            # Extract phone using multi-pattern parser
            from harvester.zero_website import extract_phone_from_text
            extracted_ph = extract_phone_from_text(text_without_url, default_prefix=def_prefix)
            if extracted_ph:
                fmt_p, wa_d = format_phone_international(extracted_ph, default_country=q_country or "US")
                if fmt_p:
                    phone = fmt_p
                    whatsapp = wa_d

            # Extract direct WhatsApp link if present in snippet
            if "wa.me/" in text_without_url or "whatsapp" in text_without_url.lower():
                wa_m = re.search(r'(?:wa\.me/|whatsapp[^\d]*)([0-9+]{8,16})', text_without_url, re.I)
                if wa_m:
                    fmt_w, wa_d = format_phone_international(wa_m.group(1), default_country=q_country or "US")
                    if wa_d:
                        whatsapp = wa_d
                        if not phone and fmt_w:
                            phone = fmt_w


            # Clean name
            b_name = re.sub(r' \| .*| - .*|: .*| on LinkedIn.*| on Instagram.*| on Facebook.*| / X$', '', title).strip()
            if not b_name or len(b_name) < 3:
                b_name = f"{phrase.title()} Provider ({platform_label})"

            # Must come from a genuine social profile or listing
            if not any(domain_part in url.lower() for domain_part in ["linkedin.com", "instagram.com", "facebook.com", "reddit.com", "x.com", "twitter.com"]):
                continue

            # Must have at least a verified contact (Phone, WA, or Email)
            if not (email or phone or whatsapp):
                continue

            uniq_key = email or phone or url
            if uniq_key in seen:
                continue
            seen.add(uniq_key)

            leads.append(Lead(
                business_name=b_name[:60],
                source="social_media",
                service_needed="web_development" if "web" in phrase or "site" in phrase else "software_services",
                website=url if "http" in url else "",
                has_website=False if any(d in url for d in ["instagram.com", "facebook.com"]) else True,
                location=f"{q_city}, {q_country}" if q_country else q_city,
                country=q_country,
                email=email,
                phone=phone,
                whatsapp=whatsapp,
                social_links={p_key: url},
                pain_points=[
                    f"Discovered via active {platform_label} outreach channel",
                    "Needs dedicated custom digital portal / website conversion system",
                    "High conversion prospect for freelance software & web solutions"
                ],
                intent_level="High",
                budget_estimate="$2,000 - $6,000",
                audit_score=45,
                audit_summary=f"Active opportunity discovered across {platform_label}. Profile actively fielding inquiries.",
                ai_pitch=f"Hi {b_name} team,\n\nI came across your active profile on {platform_label} regarding your {phrase} services in {q_city}. We specialize in building automated client booking systems and fast web portals that convert social traffic into paid clients. Would you be open to a quick 2-minute demo of how we can help?",
                status="new"
            ))

    # No App Store "fallback": app developers are not social-media leads
    return leads

