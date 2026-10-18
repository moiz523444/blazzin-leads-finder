import re
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import Dict, Any, Tuple, Optional
from urllib.parse import urlparse

# Stricter email regex requiring at least 2 alphabetic characters for TLD (excludes package versions like @5.3.3)
EMAIL_REGEX = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.(?:[a-zA-Z]{2,}\.)*[a-zA-Z]{2,}'
# Supports US/CA (+1), UK (+44), UAE (+971), Qatar (+974) and international formats
PHONE_REGEX = r'(?:\+?(\d{1,3}))?[-.\s]?(?:\(?(\d{2,4})\)?)?[-.\s]?(\d{3,4})[-.\s]?(\d{3,4})'

EXCLUDED_EMAIL_PARTS = [
    ".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", "example.com", "domain.com",
    "wixpress.com", "sentry.io", "w3.org", "schema.org", "github.com", "cloudflare.com",
    "jsdelivr", "unpkg", "bootstrap", "tailwind", "cdnjs", "fontawesome", "googleapis", "npm",
    "sentry", "yourdomain", "yoursite", "yourcompany", "mysite.", "website.com", "email.com",
    "company.com", "test.com", "sample.", "placeholder", "wordpress.org", "wix.com", "godaddy.com",
]
# Template / placeholder local-parts that appear in contact-form examples (e.g. your@email.com)
PLACEHOLDER_LOCAL_PARTS = {
    "your", "you", "yourname", "your.name", "name", "email", "youremail", "your.email", "user",
    "username", "test", "johndoe", "john.doe", "john", "jane", "janedoe", "jane.doe", "someone",
    "example", "abc", "xyz", "me", "mail", "address", "noreply", "no-reply", "donotreply",
}
FREE_MAIL = ("gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "live.com",
             "aol.com", "proton.me", "protonmail.com")


def is_valid_email(email: str) -> bool:
    e = (email or "").strip().lower()
    if not re.fullmatch(EMAIL_REGEX, e):
        return False
    local = e.split("@")[0]
    if len(local) < 2 or local in PLACEHOLDER_LOCAL_PARTS:
        return False
    if any(bad in e for bad in EXCLUDED_EMAIL_PARTS):
        return False
    return True


import phonenumbers
from phonenumbers import geocoder

COUNTRY_DEFAULT_REGIONS = {
    "UAE": "AE", "QA": "QA", "US": "US", "UK": "GB", "CA": "CA"
}

def format_phone_international(raw: str, default_country: str = "US") -> Tuple[Optional[str], Optional[str]]:
    """
    Validates and formats a phone number into:
    - (formatted_international, whatsapp_clean_digits)
    Returns (None, None) if the number is invalid, fake, or uncallable.
    """
    if not raw or not raw.strip():
        return (None, None)

    # Fast clean
    clean_raw = raw.strip()
    digits = re.sub(r"\D", "", clean_raw)
    if not (7 <= len(digits) <= 15):
        return (None, None)

    # Disallow template repetitions
    if re.search(r"(\d)\1{5,}", digits):
        return (None, None)
    if any(seq in digits for seq in ("123456", "234567", "987654", "55501", "55512", "55533")):
        return (None, None)

    reg = COUNTRY_DEFAULT_REGIONS.get((default_country or "US").upper(), "US")

    # Try parsing
    parsed_num = None
    # 1. If starts with +, parse directly
    if clean_raw.startswith("+"):
        try:
            p = phonenumbers.parse(clean_raw, None)
            if phonenumbers.is_valid_number(p):
                parsed_num = p
        except Exception:
            pass

    # 2. Try with default region
    if not parsed_num:
        try:
            p = phonenumbers.parse(clean_raw, reg)
            if phonenumbers.is_valid_number(p):
                parsed_num = p
        except Exception:
            pass

    # 3. Try with other major regions if still not valid
    if not parsed_num:
        for fallback_reg in ["AE", "GB", "US", "QA", "CA"]:
            if fallback_reg == reg:
                continue
            try:
                p = phonenumbers.parse(clean_raw, fallback_reg)
                if phonenumbers.is_valid_number(p):
                    parsed_num = p
                    break
            except Exception:
                pass

    if not parsed_num:
        return (None, None)

    formatted = phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    wa_digits = phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.E164).replace("+", "")

    return (formatted, wa_digits)


def is_valid_phone(raw: str) -> bool:
    fmt, _ = format_phone_international(raw)
    return fmt is not None


def clean_whatsapp_number(raw: str) -> str:
    """Returns E164 digits without plus (e.g. 971505912922)"""
    _, wa = format_phone_international(raw)
    if wa:
        return wa
    digits = re.sub(r'\D', '', raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    return digits if 8 <= len(digits) <= 15 else ""


async def extract_contacts_from_url(url: str) -> Dict[str, Any]:
    """
    Crawls home page and subpages (/contact, /contact-us, /about) to extract:
    - Real Email addresses (placeholders rejected, business's own domain preferred)
    - Real Phone numbers
    - Real WhatsApp direct links
    - Real Social links (LinkedIn, Instagram, Facebook, X)
    - Real brand name (og:site_name)
    """
    contacts = {
        "email": "",
        "phone": "",
        "whatsapp": "",
        "social_links": {},
        "site_name": ""
    }

    if not url or not url.strip():
        return contacts

    clean_url = url.strip()
    if not clean_url.startswith("http"):
        clean_url = "https://" + clean_url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }

    site_domain = urlparse(clean_url).netloc.lower().replace("www.", "")
    site_root = site_domain.split(".")[0]

    def email_rank(e: str) -> int:
        dom = e.split("@")[-1].lower()
        if dom == site_domain or dom.endswith("." + site_domain) or (len(site_root) >= 4 and site_root in dom):
            return 0  # business's own domain - best
        if dom in FREE_MAIL:
            return 1  # small businesses often use gmail
        return 2      # third-party domain (agency/vendor) - least trusted

    email_candidates = []

    parsed = urlparse(clean_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    # Check homepage + most common contact paths in parallel
    pages_to_check = [clean_url, f"{root}/contact", f"{root}/contact-us", f"{root}/about"]

    async with httpx.AsyncClient(timeout=3.0, follow_redirects=True, verify=False) as client:
        async def fetch_page(idx: int, target_page: str):
            try:
                res = await client.get(target_page, headers=headers)
                if res.status_code < 400:
                    return idx, res.text
                if res.status_code == 403:
                    # Cloudflare / anti-bot block - bypass with primp browser TLS in thread pool
                    import primp
                    def _sync_primp():
                        try:
                            p_client = primp.Client(impersonate="random", impersonate_os="random", timeout=3.5)
                            p_res = p_client.get(target_page)
                            if p_res.status_code < 400:
                                return p_res.text
                        except Exception:
                            pass
                        return None
                    loop = asyncio.get_running_loop()
                    p_text = await loop.run_in_executor(None, _sync_primp)
                    if p_text:
                        return idx, p_text
            except Exception:
                pass
            return idx, None

        fetched = await asyncio.gather(*(fetch_page(i, u) for i, u in enumerate(pages_to_check)))

        for idx, html in fetched:
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")

            # 0. Real brand name from homepage
            if idx == 0:
                og = soup.find("meta", property="og:site_name")
                if og and og.get("content", "").strip():
                    contacts["site_name"] = og["content"].strip()[:60]

            # 1. mailto links, 2. regex emails in page source
            for tag in soup.select("a[href^='mailto:']"):
                e = tag.get("href", "").replace("mailto:", "").split("?")[0].strip()
                if is_valid_email(e):
                    email_candidates.append(e)
            for e in re.findall(EMAIL_REGEX, html):
                if is_valid_email(e):
                    email_candidates.append(e)

            # 3. Find tel: links or visible phone numbers in HTML
            if not contacts["phone"]:
                for tag in soup.select("a[href^='tel:']"):
                    raw_phone = tag.get("href", "").replace("tel:", "").strip()
                    fmt_p, wa_d = format_phone_international(raw_phone)
                    if fmt_p:
                        contacts["phone"] = fmt_p
                        if not contacts["whatsapp"] and wa_d:
                            contacts["whatsapp"] = wa_d
                        break

            # 3b. Search visible text for phone patterns (US, UK, CA numbers)
            if not contacts["phone"]:
                for match in re.finditer(PHONE_REGEX, html):
                    candidate = match.group(0).strip()
                    fmt_p, wa_d = format_phone_international(candidate)
                    if fmt_p:
                        contacts["phone"] = fmt_p
                        if not contacts["whatsapp"] and wa_d:
                            contacts["whatsapp"] = wa_d
                        break

            # 4. Find WhatsApp direct links
            if not contacts["whatsapp"]:
                wa_tags = soup.select("a[href*='wa.me'], a[href*='api.whatsapp.com'], a[href*='whatsapp.com/send']")
                for tag in wa_tags:
                    href = tag.get("href", "")
                    wa_match = re.search(r'(?:wa\.me/|phone=|send\?phone=)([0-9+]+)', href)
                    if wa_match:
                        cleaned_wa = clean_whatsapp_number(wa_match.group(1))
                        if 10 <= len(cleaned_wa) <= 15 and is_valid_phone(cleaned_wa):
                            contacts["whatsapp"] = cleaned_wa
                            if not contacts["phone"]:
                                contacts["phone"] = "+" + cleaned_wa
                            break

            # 5. Extract Social Profiles
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                href_l = href.lower()
                if "linkedin.com/company/" in href_l and "linkedin" not in contacts["social_links"]:
                    contacts["social_links"]["linkedin"] = href
                elif "instagram.com/" in href_l and not any(x in href_l for x in ["/p/", "/reel/", "/explore/", "/stories/"]) and "instagram" not in contacts["social_links"]:
                    contacts["social_links"]["instagram"] = href
                elif "facebook.com/" in href_l and not any(x in href_l for x in ["/sharer", "/share", "/dialog"]) and "facebook" not in contacts["social_links"]:
                    contacts["social_links"]["facebook"] = href
                elif ("twitter.com/" in href_l or "x.com/" in href_l) and not any(x in href_l for x in ["/intent/", "/share"]) and "twitter" not in contacts["social_links"]:
                    contacts["social_links"]["twitter"] = href

    if email_candidates:
        # Own domain first, then free mail, then third-party; page order kept within a rank
        contacts["email"] = sorted(dict.fromkeys(email_candidates), key=email_rank)[0]

    return contacts
