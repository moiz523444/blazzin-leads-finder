import re
import urllib.parse
from typing import List, Dict, Any

from models import Lead
from enricher.contact_extractor import (
    EMAIL_REGEX, is_valid_email, is_valid_phone, clean_whatsapp_number
)
from enricher.lead_quality import (
    ddg_search, normalize_niche, name_from_domain, GENERIC_TITLE
)

COUNTRY_PHONE_PREFIXES = {
    "UAE": ("+971", ["Dubai", "Abu Dhabi", "Sharjah"]),
    "QA": ("+974", ["Doha", "Lusail", "Al Rayyan"]),
    "US": ("+1", ["New York", "Miami", "Los Angeles", "Austin"]),
    "UK": ("+44", ["London", "Manchester", "Birmingham"]),
    "CA": ("+1", ["Toronto", "Vancouver", "Montreal"]),
}

PHONE_PATTERNS = [
    re.compile(r'(\+971[\s\-]?[0-9]{1,2}[\s\-]?[0-9]{3}[\s\-]?[0-9]{4})'),
    re.compile(r'(\+974[\s\-]?[0-9]{4}[\s\-]?[0-9]{4})'),
    re.compile(r'(\+44[\s\-]?[0-9]{2,4}[\s\-]?[0-9]{3,4}[\s\-]?[0-9]{3,4})'),
    re.compile(r'(\+1[\s\-]?[0-9]{3}[\s\-]?[0-9]{3}[\s\-]?[0-9]{4})'),
    re.compile(r'(\(?\d{3}\)?[\s\.-]\d{3}[\s\.-]\d{4})'),
    re.compile(r'(?:whatsapp|call|phone|tel)[\s:]*([+\d\s\(\)-]{8,18})', re.I),
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

    target_countries = ["UAE", "US", "UK", "CA", "QA"] if country_key == "ALL" else [country_key]
    leads = []
    seen_contacts = set()

    queries = []
    if country_key == "ALL":
        # Ultra-fast parallel discovery: 1 top query per country
        for ck in target_countries:
            prefix, cities = COUNTRY_PHONE_PREFIXES.get(ck, ("+1", ["New York"]))
            c_term = phrase if phrase != "local business" else "clinic OR real estate OR store"
            queries.append((ck, prefix, cities[0], f'"{c_term}" {cities[0]} whatsapp OR phone'))
    else:
        prefix, cities = COUNTRY_PHONE_PREFIXES.get(country_key, ("+1", ["New York"]))
        c_term = phrase if phrase != "local business" else "business"
        queries.append((country_key, prefix, cities[0], f'"{c_term}" {cities[0]} whatsapp'))
        queries.append((country_key, prefix, cities[0], f'"{c_term}" {cities[0]} contact phone'))

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
            
            # Check WhatsApp
            whatsapp = ""
            wa_match = re.search(r'(?:wa\.me/|whatsapp[^\d]*)([0-9+]{8,16})', combined_text, re.I)
            if wa_match:
                clean_wa = clean_whatsapp_number(wa_match.group(1))
                if 8 <= len(clean_wa) <= 15:
                    whatsapp = clean_wa
            elif phone:
                clean_p = clean_whatsapp_number(phone)
                if 9 <= len(clean_p) <= 15:
                    whatsapp = clean_p

            # MANDATORY: Must have at least phone, whatsapp or email!
            if not (phone or whatsapp or email):
                continue

            contact_key = f"{phone}:{email}:{whatsapp}"
            if contact_key in seen_contacts:
                continue
            seen_contacts.add(contact_key)

            # Clean business name
            b_name = re.sub(r' - .*| \| .*|: .*| official .*| Home$| Homepage$| Facebook$| Instagram$', '', title, flags=re.I).strip()
            if not b_name or len(b_name) < 3 or GENERIC_TITLE.search(b_name):
                b_name = f"{phrase.title()} Center {city}"

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

