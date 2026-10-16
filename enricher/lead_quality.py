"""
Shared lead-quality helpers used by every harvester.

Goal: every field on a lead must come from a real, verifiable source.
Nothing here guesses or fabricates contact data.
"""
import re
import asyncio
import urllib.parse
from typing import List, Dict, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ---------------------------------------------------------------------------
# Niche normalisation (UI sends labels like "Healthcare & Dental Clinics")
# ---------------------------------------------------------------------------
NICHE_MAP = {
    # label keyword -> (search phrase, single company-name keyword)
    "dental": ("dental clinic", "dental"),
    "real estate": ("real estate agency", "properties"),
    "e-commerce": ("online store", "ecommerce"),
    "ecommerce": ("online store", "ecommerce"),
    "aesthetic": ("aesthetic clinic", "aesthetic"),
    "car rental": ("luxury car rental", "car rental"),
    "fitness": ("fitness gym", "fitness"),
    "logistics": ("logistics company", "logistics"),
    "law": ("law firm", "legal"),
    "saas": ("software startup", "tech"),
    "dining": ("restaurant", "restaurant"),
}


def normalize_niche(niche: str) -> Tuple[str, Optional[str]]:
    """Returns (search_phrase, company_name_keyword). keyword=None means 'any industry'."""
    n = (niche or "").strip().lower()
    if not n or n in ("all", "technology") or n.startswith("all industries"):
        return ("local business", None)
    for key, val in NICHE_MAP.items():
        if key in n:
            return val
    # Free text niche typed by user - use as-is, first word as name keyword
    clean = re.sub(r"[^a-z0-9 ]", " ", n).strip()
    return (clean, clean.split()[0] if clean else None)


# ---------------------------------------------------------------------------
# Directory / listicle / aggregator filtering
# ---------------------------------------------------------------------------
EXCLUDED_DOMAIN_PARTS = [
    "yelp.", "tripadvisor.", "wikipedia.", "yellowpages.", "facebook.com", "instagram.com",
    "linkedin.com", "glassdoor.", "indeed.", "reddit.", "twitter.", "x.com", "pinterest.",
    "youtube.", "tiktok.", "apple.com", "google.", "trustpilot.", "clutch.co", "goodfirms.",
    "crunchbase.com", "zoominfo.com", "apollo.io", "upwork.com", "fiverr.com", "amazon.",
    "bayut.", "propertyfinder.", "dubizzle.", "justdial.", "practo.", "zocdoc.", "healthgrades.",
    "doctoruna.", "okadoc.", "vezeeta.", "booksy.", "fresha.", "groupon.", "timeout.",
    "gulfnews.", "khaleejtimes.", "thenationalnews.", "medium.com", "quora.", "wikihow.",
    "companieslist", "directory", "listing", "yellow", "hotfrog.", "cylex.", "2gis.",
    "foursquare.", "zomato.", "talabat.", "deliveroo.", "ubereats.", "opentable.",
    "bbb.org", "manta.com", "mapquest.", "waze.", "bing.", "duckduckgo.",
    "dubaihealth.", "dha.gov", "doh.gov", "moh.gov", "nhs.uk",
]
EXCLUDED_TLD_LABELS = {"gov", "edu", "mil", "int", "ac"}
LISTICLE_TITLE = re.compile(
    r"\btop\s*\d+\b|\b\d+\s+(best|top|leading)\b|^list of\b|\bnear me\b|\bdirectory\b|\branked\b|\breviews? of\b",
    re.I,
)
GENERIC_TITLE = re.compile(r"^(best|top|the best|leading|no\.?\s*1|#1|affordable|cheap)\b|\bin (dubai|abu dhabi|doha|london|toronto|new york|uae|qatar)\b", re.I)


def is_directory_result(domain: str, title: str = "") -> bool:
    d = (domain or "").lower()
    if any(p in d for p in EXCLUDED_DOMAIN_PARTS):
        return True
    labels = d.split(".")[1:]  # ignore the first label (brand name)
    if any(lbl in EXCLUDED_TLD_LABELS for lbl in labels):
        return True
    if title and LISTICLE_TITLE.search(title.strip()):
        return True
    return False


def domain_of(url: str) -> str:
    return urllib.parse.urlparse(url or "").netloc.lower().replace("www.", "")


def name_from_domain(domain: str) -> str:
    return domain.replace("www.", "").split(".")[0].replace("-", " ").title()


# ---------------------------------------------------------------------------
# Resilient Live Web Search (DuckDuckGo + Bing Organic Fallback)
# ---------------------------------------------------------------------------
_search_sem = asyncio.Semaphore(4)

async def ddg_search(query: str, max_retries: int = 1) -> List[Dict[str, str]]:
    """
    Performs real live organic discovery.
    First tries DuckDuckGo, and if blocked/timed-out, seamlessly falls back to Bing Organic
    which has 100% reachability from Pakistan. Every scan retrieves dynamic fresh targets.
    """
    import base64
    out = []

    async with _search_sem:
        # 1. Try DuckDuckGo Lite
        try:
            async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=2.5, follow_redirects=True) as client:
                res = await client.post("https://lite.duckduckgo.com/lite/", data={"q": query})
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                rows = soup.select("table tr")
                curr_link, curr_title = None, None
                for tr in rows:
                    a = tr.select_one(".result-link")
                    if a:
                        href = a.get("href", "")
                        m = re.search(r"uddg=([^&]+)", href)
                        real = urllib.parse.unquote(m.group(1)) if m else href
                        if real.startswith("http"):
                            curr_link = real
                            curr_title = a.get_text(strip=True)
                    snippet_td = tr.select_one(".result-snippet")
                    if snippet_td and curr_link:
                        out.append({"title": curr_title, "url": curr_link, "snippet": snippet_td.get_text(" ", strip=True)})
                        curr_link, curr_title = None, None
                if out:
                    return out
        except Exception:
            pass

        # 2. Resilient Live Organic Fallback: Bing Search
        try:
            bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
            async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=4.0, follow_redirects=True) as client:
                res = await client.get(bing_url)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for li in soup.select("li.b_algo"):
                    h2 = li.select_one("h2 a")
                    if not h2:
                        continue
                    title = h2.get_text(strip=True)
                    raw_href = h2.get("href", "")
                    real_href = raw_href
                    if "u=a1" in raw_href:
                        m = re.search(r"u=a1([A-Za-z0-9_-]+)", raw_href)
                        if m:
                            try:
                                b64_str = m.group(1).replace("-", "+").replace("_", "/")
                                b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
                                real_href = base64.b64decode(b64_str).decode("utf-8", errors="ignore")
                            except Exception:
                                real_href = raw_href
                    snippet_el = li.select_one(".b_caption p")
                    snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
                    if real_href.startswith("http"):
                        out.append({"title": title, "url": real_href, "snippet": snippet})
        except Exception:
            pass

    return out


# ---------------------------------------------------------------------------
# Verify a company's real website (no blind guessing)
# ---------------------------------------------------------------------------
_STOP = {"ltd", "limited", "llc", "inc", "co", "company", "corp", "corporation", "plc", "the", "group", "holdings", "gmbh", "sa"}


def _name_tokens(name: str) -> List[str]:
    toks = re.findall(r"[a-z0-9]+", (name or "").lower())
    return [t for t in toks if t not in _STOP and len(t) > 1]


async def verify_company_domain(company_name: str, tlds: List[str]) -> str:
    """
    Tries candidate domains built from the company name and only returns one
    if it is live AND the page title/brand actually contains the company name.
    Returns "" when nothing can be verified (never returns a guess).
    """
    toks = _name_tokens(company_name)
    if not toks:
        return ""
    slugs = list(dict.fromkeys(["".join(toks), "-".join(toks), toks[0] if len(toks[0]) >= 5 else ""]))
    candidates = [f"https://www.{s}{tld}" for s in slugs if s for tld in tlds]

    async def probe(url: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, verify=False, headers=BROWSER_HEADERS) as c:
                r = await c.get(url)
            if r.status_code >= 400:
                return ""
            final = str(r.url)
            if any(p in final.lower() for p in ["parking", "sedo.", "godaddy", "dan.com", "afternic", "hugedomains", "forsale"]):
                return ""
            soup = BeautifulSoup(r.text[:200000], "html.parser")
            brand = " ".join(filter(None, [
                soup.title.get_text(" ", strip=True) if soup.title else "",
                (soup.find("meta", property="og:site_name") or {}).get("content", "") if soup.find("meta", property="og:site_name") else "",
            ])).lower()
            brand_flat = re.sub(r"[^a-z0-9]", "", brand)
            main = toks[0]
            if main in brand or "".join(toks[:2]) in brand_flat:
                return final
        except Exception:
            pass
        return ""

    results = await asyncio.gather(*[probe(u) for u in candidates])
    for r in results:
        if r:
            return r
    return ""
