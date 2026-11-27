"""
USPTO trademark leads: brand-new trademark applications filed WITHOUT an attorney ("Attorney of Record - None").
The owner filed by themselves, so the public record carries their own name, address, phone and e-mail - a
business that is launching a brand and usually still needs a website, logo and social pages.

Data comes from USPTO TSDR (public records). With a free USPTO_API_KEY the official TSDR API is used
(60 requests/minute); without one the public status page is read slowly (one request every 2 seconds -
faster than that and USPTO answers HTTP 403).
"""
import asyncio
import re
import time
from typing import Any, Dict, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

import config
import netfix
from enricher.contact_extractor import phone_info, is_valid_email, FREE_MAIL
from harvester.regions import timezone_for
from models import Lead

STATUS_PAGE = "https://tsdr.uspto.gov/statusview/sn{sn}"
API_PAGE = "https://tsdrapi.uspto.gov/ts/cd/casestatus/sn{sn}/content.html"
CASE_LINK = "https://tsdr.uspto.gov/#caseNumber={sn}&caseType=SERIAL_NO&searchType=statusSearch"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"}

GAP_NO_KEY = 2.0    # measured: 2s between requests = no blocks; 1.2s = every second request blocked (403)
GAP_WITH_KEY = 1.05  # API key limit is 60 requests/minute

COUNTRY_CODES = {"UNITED STATES": "US", "UNITED KINGDOM": "UK", "CANADA": "CA",
                 "UNITED ARAB EMIRATES": "UAE", "QATAR": "QA"}

# Outcomes of one lookup
FOUND, MISSING, BLOCKED, ERROR = "found", "missing", "blocked", "error"


class TsdrClient:
    """Serial-number lookups, paced so USPTO never blocks us."""

    def __init__(self):
        self.use_api = bool(config.USPTO_API_KEY)
        self.gap = GAP_WITH_KEY if self.use_api else GAP_NO_KEY
        self._last = 0.0
        self._client = httpx.AsyncClient(timeout=30.0, headers=_UA)

    async def close(self):
        await self._client.aclose()

    async def _wait_turn(self):
        delay = self._last + self.gap - time.time()
        if delay > 0:
            await asyncio.sleep(delay)
        self._last = time.time()

    async def fetch(self, sn: int) -> Tuple[str, str]:
        """Returns (outcome, html). Retries a block with growing pauses before giving up."""
        for attempt in range(4):
            await self._wait_turn()
            try:
                if self.use_api:
                    res = await self._client.get(API_PAGE.format(sn=sn), headers={"USPTO-API-KEY": config.USPTO_API_KEY})
                    if res.status_code in (401, 403) and "api key" in res.text.lower():
                        print("[trademark] USPTO_API_KEY was rejected - switching to the public status page")
                        self.use_api, self.gap = False, GAP_NO_KEY
                        continue
                else:
                    res = await self._client.get(STATUS_PAGE.format(sn=sn))
            except httpx.HTTPError:
                await asyncio.sleep(3 * (attempt + 1))
                continue
            if res.status_code == 200 and "Application Filing Date" in res.text:
                return FOUND, res.text
            # A serial number that was never issued comes back as a tiny status fragment (503 or 200)
            if res.status_code in (200, 404, 503) and 'id="statusTab"' in res.text and "Filing Date" not in res.text:
                return MISSING, ""
            if res.status_code in (403, 429):
                self.gap = min(self.gap * 1.25, 4.0)  # USPTO slowed us down - stay slower from now on
                await asyncio.sleep(5 * (attempt + 1))
                continue
            await asyncio.sleep(2)
        return BLOCKED, ""

    async def filing_date(self, sn: int) -> Optional[str]:
        outcome, html = await self.fetch(sn)
        return _value(BeautifulSoup(html, "html.parser"), "Application Filing Date") if outcome == FOUND else None


async def find_latest_serial(client: TsdrClient, known_low: int) -> int:
    """Binary search for the newest serial number that exists (serials are issued in order, with small gaps)."""

    async def exists_near(sn: int) -> bool:
        for d in range(4):  # step over the small gaps between issued numbers
            if await client.filing_date(sn + d):
                return True
        return False

    lo, hi = known_low, known_low + 4000
    while await exists_near(hi):  # widen until we pass the newest application
        lo, hi = hi, hi + 4000
    while hi - lo > 8:
        mid = (lo + hi) // 2
        if await exists_near(mid):
            lo = mid
        else:
            hi = mid
    return lo + 4


# ---------------------------------------------------------------------------
# Parsing one status page
# ---------------------------------------------------------------------------
def _value(soup: BeautifulSoup, key: str, as_lines: bool = False):
    for k in soup.select("div.key"):
        if k.get_text(" ", strip=True).rstrip(":").strip().lower() == key.lower():
            v = k.find_next_sibling("div", class_="value")
            if v is None:
                return [] if as_lines else ""
            if as_lines:
                return [ln.strip().rstrip(",").strip() for ln in v.get_text("\n").split("\n") if ln.strip()]
            return re.sub(r"\s+", " ", v.get_text(" ", strip=True))
    return [] if as_lines else ""


def _split_address(lines) -> Dict[str, str]:
    """['835 Norwood Avenue', 'Key Largo', 'FLORIDA', 'UNITED STATES', '33037'] -> city/state/country."""
    out = {"street": "", "city": "", "state": "", "country_name": "", "postal": ""}
    # The country is the last all-capitals line without digits (postal codes have digits, cities are mixed case)
    caps = [i for i, ln in enumerate(lines) if i > 0 and re.fullmatch(r"[A-Z][A-Z .,'&()-]{2,}", ln)]
    if not caps:
        return out
    idx = caps[-1]
    out["country_name"] = lines[idx].upper()
    out["postal"] = " ".join(lines[idx + 1:])
    before = lines[:idx]
    if len(before) >= 3:
        out["street"], out["city"], out["state"] = ", ".join(before[:-2]), before[-2], before[-1]
    elif len(before) == 2:
        out["street"], out["city"] = before
    elif before:
        out["city"] = before[0]
    return out


def parse_case(html: str, sn: int) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    captions = [c.get_text(" ", strip=True) for c in soup.select("div.caption")]
    addr = _split_address(_value(soup, "Owner Address", as_lines=True))
    email_tag = soup.select_one("a[href^='mailto:']")
    return {
        "serial": sn,
        "mark": _value(soup, "Mark") or _value(soup, "Mark Literal Elements"),
        "filed": _value(soup, "Application Filing Date"),
        "status": _value(soup, "Status").replace("See current trademark processing wait times for more information.", "").strip(),
        "goods": _value(soup, "For"),
        "itu": _value(soup, "Filed ITU").lower().startswith("yes"),
        "owner": _value(soup, "Owner Name"),
        "entity": _value(soup, "Legal Entity Type"),
        # companies show where they are organized, individual owners show their citizenship
        "organized_in": _value(soup, "State or Country Where Organized") or _value(soup, "Citizenship"),
        "correspondent": (_value(soup, "Correspondent Name/Address", as_lines=True) or [""])[0],
        "phone": _value(soup, "Phone"),
        "email": email_tag["href"].replace("mailto:", "").strip() if email_tag else "",
        "no_attorney": any(c.startswith("Attorney of Record - None") for c in captions),
        **addr,
    }


# ---------------------------------------------------------------------------
# Case -> Lead
# ---------------------------------------------------------------------------
async def case_to_lead(case: Dict[str, Any], countries) -> Optional[Lead]:
    """Only pro-se filings (no attorney) from the chosen countries, with a usable phone or e-mail."""
    if not case["no_attorney"] or not case["owner"]:
        return None
    country = COUNTRY_CODES.get(case["country_name"], "")
    if countries and country not in countries:
        return None
    phone, digits, is_mobile = phone_info(case["phone"], country or "US") if case["phone"] else (None, None, False)
    email = case["email"] if is_valid_email(case["email"]) else ""
    if not (phone or email):
        return None

    region = case["state"].title() if case["state"] else ""
    website, has_website = "", False
    pains = [f'Filed trademark "{case["mark"]}" on {case["filed"]} - launching a new brand',
             "Filed without a lawyer (pro se) - the owner handles things personally"]
    if case["itu"]:
        pains.append("Intent-to-use filing: brand not launched yet - needs website, logo and social pages before launch")
    if case["goods"]:
        pains.append(f"Business: {case['goods'][:140]}")
    domain = email.split("@")[-1].lower() if email else ""
    if domain and domain not in FREE_MAIL and not domain.endswith((".edu", ".gov")):
        if await netfix.host_exists(domain) is True:
            website, has_website = f"https://{domain}", True
    elif domain:
        pains.append(f"Uses a free e-mail ({domain}) - no business domain / website yet")

    person = case["correspondent"] if case["correspondent"] and case["correspondent"] != case["owner"] else ""
    first = (person or (case["owner"] if case["entity"].upper() == "INDIVIDUAL" else "")).split(" ")[0].title()
    goods = case["goods"].split(";")[0][:80] if case["goods"] else "your business"
    pitch = (f"Hi {first or 'there'},\n\n"
             f"Congratulations on filing the trademark \"{case['mark']}\". I run a small web & design studio and "
             f"came across your application in the public USPTO records (we are not affiliated with the USPTO).\n\n"
             f"New brands usually need a professional website, logo and social media pages before launch - "
             f"especially for {goods.lower()}. We build fast, mobile-first websites and brand kits for new businesses.\n\n"
             f"Would it help if I sent a free homepage mock-up for \"{case['mark']}\"?\n\nBest regards")

    return Lead(
        business_name=case["owner"][:80], source="trademark", serial=str(case["serial"]),
        organized_in=case["organized_in"][:80],
        service_needed="website_redesign" if has_website else "web_development",
        category="New trademark filer", website=website, has_website=has_website,
        location=", ".join(filter(None, [case["city"].title(), region, country or case["country_name"].title()])),
        country=country, region=region, timezone=timezone_for(country, region, case["city"].title()) if country else "",
        email=email, phone=phone or "", whatsapp=digits if is_mobile else "", contact_name=person[:80],
        pain_points=pains, intent_level="First-Mover", budget_estimate="$800 - $3,000", audit_score=20,
        audit_summary=(f"USPTO serial {case['serial']} filed {case['filed']} ({case['entity'].title() or 'owner'}). "
                       f"Status: {case['status'][:90]}. Address: {', '.join(filter(None, [case['street'], case['city'], case['state'], case['postal']]))}. "
                       f"Record: {CASE_LINK.format(sn=case['serial'])}"),
        ai_pitch=pitch,
    )
