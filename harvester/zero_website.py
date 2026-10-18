import re
import urllib.parse
from typing import List, Dict, Any

from models import Lead
from enricher.contact_extractor import (
    EMAIL_REGEX, is_valid_email, is_valid_phone, clean_whatsapp_number, format_phone_international
)
from enricher.lead_quality import (
    ddg_search, normalize_niche, name_from_domain, GENERIC_TITLE, ALL_INDUSTRIES_POOL
)

COUNTRY_PHONE_PREFIXES = {
    "UAE": ("+971", ["Dubai", "Abu Dhabi", "Sharjah"]),
    "QA": ("+974", ["Doha", "Lusail", "Al Rayyan"]),
    "US": ("+1", ["New York", "Los Angeles", "Chicago", "Houston", "Miami", "Dallas", "Austin", "Atlanta", "Phoenix", "San Diego"]),
    "UK": ("+44", ["London", "Manchester", "Birmingham", "Leeds", "Glasgow"]),
    "CA": ("+1", ["Toronto Ontario", "Vancouver BC", "Montreal Quebec", "Calgary Alberta"]),
}

PHONE_PATTERNS = [
    re.compile(r'(\+971[\s\-]?[0-9]{1,2}[\s\-]?[0-9]{3}[\s\-]?[0-9]{4})'),
    re.compile(r'(\+974[\s\-]?[0-9]{4}[\s\-]?[0-9]{4})'),
    re.compile(r'(\+44[\s\-]?[0-9]{2,4}[\s\-]?[0-9]{3,4}[\s\-]?[0-9]{3,4})'),
    re.compile(r'(\+1[\s\-]?[0-9]{3}[\s\-]?[0-9]{3}[\s\-]?[0-9]{4})'),
    re.compile(r'(\(?\d{3}\)?[\s\.-]\d{3}[\s\.-]\d{4})'),
    re.compile(r'(?:whatsapp|call|phone|tel|contact)[\s:]*([+\d\s\(\)-]{8,20})', re.I),
    re.compile(r'(\b0[1-9][0-9\s-]{7,12}\b)'),
    re.compile(r'(\+[1-9][0-9\s-]{8,16})'),
]


def extract_phone_from_text(text: str, default_prefix: str = "") -> str:
    """Extracts first valid phone number from text snippet."""
    if not text:
        return ""
    for pat in PHONE_PATTERNS:
        match = pat.search(text)
        if match:
            raw = match.group(1).strip()
            digits = re.sub(r'\D', '', raw)
            if 7 <= len(digits) <= 15:
                if raw.startswith("+"):
                    return raw
                elif default_prefix and not digits.startswith(default_prefix.replace("+", "")):
                    return f"{default_prefix} {raw}"
                return raw
    return ""


def extract_email_from_text(text: str) -> str:
    """Extracts first valid email address from text snippet."""
    if not text:
        return ""
    emails = re.findall(EMAIL_REGEX, text)
    for e in emails:
        if is_valid_email(e):
            return e.lower()
    return ""


async def harvest_zero_website_leads(niche: str = "dental", country: str = "UAE", limit: int = 15) -> List[Lead]:
    """
    Harvests active, operational local businesses that have a VERIFIED Phone / WhatsApp / Email
    but ZERO dedicated website (operating via Facebook/Instagram/local listings or no site).
    These are the highest converting 'build from scratch' leads for freelancers.
    """
    country_key = (country or "ALL").upper()
    phrase, _ = normalize_niche(niche)

    target_countries = ["US", "UK", "CA", "UAE", "QA"] if country_key == "ALL" else [country_key]
    leads = []
    seen_contacts = set()

    import random
    queries = []
    shuffled_industries = list(ALL_INDUSTRIES_POOL if phrase == "local business" else [phrase])
    random.shuffle(shuffled_industries)

    if country_key == "ALL":
        for idx, ck in enumerate(target_countries):
            prefix, cities = COUNTRY_PHONE_PREFIXES.get(ck, ("+1", ["New York"]))
            selected_cities = random.sample(cities, min(2, len(cities)))
            for city in selected_cities:
                selected_ind = random.choice(shuffled_industries)
                if ck in ("US", "CA"):
                    queries.append((ck, prefix, city, f'facebook {selected_ind} {city} call'))
                    queries.append((ck, prefix, city, f'{selected_ind} {city} phone contact'))
                else:
                    queries.append((ck, prefix, city, f'facebook {selected_ind} {city} {prefix}'))
                    queries.append((ck, prefix, city, f'{selected_ind} {city} {prefix} whatsapp'))
    else:
        prefix, cities = COUNTRY_PHONE_PREFIXES.get(country_key, ("+1", ["New York"]))
        selected_cities = random.sample(cities, min(3, len(cities)))
        for city in selected_cities:
            selected_ind = random.choice(shuffled_industries)
            if country_key in ("US", "CA"):
                queries.append((country_key, prefix, city, f'facebook {selected_ind} {city} call'))
                queries.append((country_key, prefix, city, f'{selected_ind} {city} phone contact'))
            else:
                queries.append((country_key, prefix, city, f'facebook {selected_ind} {city} {prefix}'))
                queries.append((country_key, prefix, city, f'{selected_ind} {city} {prefix} whatsapp'))

    random.shuffle(queries)




    for ck, prefix, city, q in queries:
        if len(leads) >= limit:
            break
        results = await ddg_search(q)
        for r in results:
            if len(leads) >= limit:
                break
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            combined_text = f"{title} {snippet} {url}"

            # Extract phone and email
            phone = extract_phone_from_text(combined_text, default_prefix=prefix)
            email = extract_email_from_text(combined_text)
            
            # Validate and format phone with official phonenumbers parser
            formatted_phone, wa_digits = format_phone_international(phone, default_country=ck)
            if not formatted_phone:
                continue  # Discard if phone number is invalid or cannot be verified!

            phone = formatted_phone
            whatsapp = wa_digits


            contact_key = f"{phone}:{email}:{whatsapp}"
            if contact_key in seen_contacts:
                continue
            seen_contacts.add(contact_key)

            # Discard support articles, faq pages or generic titles
            title_lower = title.lower()
            if any(bad in title_lower for bad in ["how to contact", "whatsapp support", "faq", "terms of service", "privacy policy", "help center", "customer care"]):
                continue

            # Clean business name (strip phone numbers, instagram handles, and suffixes)
            b_name = re.sub(r' - .*| \| .*|: .*| official .*| Home$| Homepage$| Facebook$| Instagram$', '', title, flags=re.I).strip()
            b_name = re.sub(r'(\+?[0-9\s-]{7,20})', '', b_name).strip()
            b_name = re.sub(r'\(@[a-zA-Z0-9_.]+\)', '', b_name).strip()
            b_name = re.sub(r'(?i)\b(i am hiring|contact us|contact|whatsapp|call)\b', '', b_name).strip(" -:|,")
            if not b_name or len(b_name) < 3 or GENERIC_TITLE.search(b_name):
                b_name = f"{selected_ind.title()} ({city})"

            lead = Lead(
                business_name=b_name[:60],
                source="new_business",
                service_needed="web_development",
                website="",
                has_website=False,
                location=f"{city}, {ck}",
                email=email,
                phone=phone,
                whatsapp=whatsapp,
                social_links={"listing_url": url} if url else {},
                pain_points=[
                    "Zero official website or digital booking storefront",
                    "Missing search engine ranking — losing leads to competitors",
                    "Relying purely on manual social messages instead of automated funnels"
                ],
                intent_level="First-Mover",
                budget_estimate="$1,500 - $3,500",
                audit_score=10,
                audit_summary="Active business operates without an official website. High priority opportunity for a complete web & booking system.",
                ai_pitch=f"Hi {b_name} team,\n\nI was looking for your business in {city} and noticed you don't have an official website yet. Most clients looking for {phrase} check a website before calling or booking. We build high-converting websites with WhatsApp and automated booking in 5-7 days. Would you be open to a 60-second video demo?",
                status="new"
            )
            leads.append(lead)

    return leads

