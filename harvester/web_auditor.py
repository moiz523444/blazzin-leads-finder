import asyncio
import datetime
import re
import time
from typing import Dict, Any, Optional

import httpx
from bs4 import BeautifulSoup

import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}
_psi_sem = asyncio.Semaphore(4)


async def pagespeed_mobile_score(url: str) -> Optional[int]:
    """Google Lighthouse mobile performance score (0-100) via PageSpeed Insights. None if unavailable."""
    if not config.PAGESPEED_API_KEY:
        return None
    params = {"url": url, "strategy": "mobile", "category": "performance", "key": config.PAGESPEED_API_KEY}
    try:
        async with _psi_sem:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed", params=params)
        if res.status_code != 200:
            return None
        score = res.json()["lighthouseResult"]["categories"]["performance"]["score"]
        return int(round(score * 100)) if score is not None else None
    except Exception:
        return None


async def _fetch(url: str, verify: bool):
    """GET with one slower retry, so a single network hiccup is never reported as 'site down'."""
    for attempt, timeout in enumerate((10.0, 20.0)):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=verify, headers=HEADERS) as client:
                start = time.time()
                res = await client.get(url)
                return res, int((time.time() - start) * 1000)
        except (httpx.ConnectTimeout, httpx.ReadTimeout):
            if attempt == 1:
                raise
        except httpx.ConnectError as e:
            if attempt == 1 or "CERTIFICATE" in str(e).upper() or "SSL" in str(e).upper():
                raise


async def our_internet_ok() -> bool:
    """Guards 'site is down' claims against our OWN flaky DNS/network."""
    for probe in ("https://www.google.com/generate_204", "https://cloudflare.com/cdn-cgi/trace"):
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.get(probe)
            return True
        except Exception:
            continue
    return False


async def domain_exists(host: str) -> Optional[bool]:
    """
    Asks public DNS-over-HTTPS resolvers (bypassing the local, sometimes flaky DNS) whether a domain resolves.
    True = resolves, False = does not exist / no address, None = could not find out.
    """
    host = (host or "").split(":")[0].strip().lower()
    for resolver in ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve"):
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(resolver, params={"name": host, "type": "A"}, headers={"accept": "application/dns-json"})
            data = res.json()
            if data.get("Status") == 3:  # NXDOMAIN
                return False
            if data.get("Status") == 0:
                return any(a.get("type") in (1, 5) for a in data.get("Answer", []))
        except Exception:
            continue
    return None


# Status codes that usually mean "our scraper was blocked or rate-limited", not "the site is broken"
_BLOCKED_STATUSES = {401, 403, 405, 406, 429, 503}

FREE_BUILDER_HOSTS = ("ueniweb.com", "wixsite.com", "business.site", "weebly.com", "godaddysites.com",
                      "square.site", "carrd.co", "blogspot.com", "wordpress.com", "webnode.", "site123.me",
                      "jimdosite.com", "mystrikingly.com", "yolasite.com", "web.app", "netlify.app", "vercel.app")


def _inconclusive(reason: str, cms: str = "Unknown") -> Dict[str, Any]:
    return {
        "has_website": True, "audit_score": 50, "needs_work": False,
        "pain_points": [], "summary": f"Audit could not complete: {reason}",
        "speed_ms": 0, "cms": cms, "pagespeed_mobile": None,
    }


async def audit_website(url: str) -> Dict[str, Any]:
    """
    Audits a website and reports ONLY problems that were actually observed.
    Returns:
        audit_score: 0-100 (lower score = bigger opportunity)
        pain_points: factual list of problems found
        needs_work: True when at least one significant problem was found
        summary, speed_ms, cms, pagespeed_mobile
    """
    if not url or not url.strip():
        return {
            "has_website": False, "audit_score": 10, "needs_work": True,
            "pain_points": ["No website found"],
            "summary": "No website found for this business.",
            "speed_ms": 0, "cms": "None", "pagespeed_mobile": None,
        }

    clean_url = url.strip()
    if not clean_url.startswith("http"):
        clean_url = "https://" + clean_url

    pain_points = []
    minor_points = []
    cms = "Custom / Unknown"
    speed_ms = 0
    score = 100
    ssl_invalid = False

    try:
        try:
            res, speed_ms = await _fetch(clean_url, verify=True)
        except httpx.ConnectError as e:
            if "CERTIFICATE" not in str(e).upper() and "SSL" not in str(e).upper():
                raise
            ssl_invalid = True
            res, speed_ms = await _fetch(clean_url, verify=False)

        # Only "page gone" (404/410) and server errors (5xx) prove a broken site; other 4xx codes
        # (403, 429, 432...) are firewalls/bot-blocks that a normal visitor never sees
        if res.status_code in _BLOCKED_STATUSES or (400 <= res.status_code < 500 and res.status_code not in (404, 410)):
            return _inconclusive(f"site blocked our checker (HTTP {res.status_code})", cms)
        if res.status_code >= 400:
            return {
                "has_website": True, "audit_score": 15, "needs_work": True,
                "pain_points": [f"Website returns HTTP error {res.status_code} (site broken or unreachable)"],
                "summary": f"Website returned HTTP {res.status_code} when visited.",
                "speed_ms": speed_ms, "cms": "Broken", "pagespeed_mobile": None,
            }

        html = res.text
        html_lower = html.lower()
        soup = BeautifulSoup(html, "html.parser")

        final_host = httpx.URL(str(res.url)).host.lower()
        builder = next((b for b in FREE_BUILDER_HOSTS if final_host.endswith(b) or b in final_host), None)
        if builder:
            pain_points.append(f"Website is on a free builder subdomain ({final_host}), not the business's own domain")
            score -= 25

        if ssl_invalid:
            pain_points.append("SSL certificate is invalid or expired - browsers show a security warning")
            score -= 35
        elif not str(res.url).startswith("https://"):
            pain_points.append("No HTTPS - browsers label the site 'Not Secure'")
            score -= 30

        if not soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)}):
            pain_points.append("Not mobile-responsive (no viewport meta tag) - site renders zoomed-out on phones")
            score -= 30

        # WordPress core version only from the generator tag (asset ?ver= values are plugin versions)
        gen = soup.find("meta", attrs={"name": re.compile(r"^generator$", re.I)})
        gen_content = (gen.get("content", "") if gen else "").strip()
        wp = re.search(r"wordpress\s+(\d+)\.(\d+)", gen_content, re.I)
        if wp:
            cms = f"WordPress {wp.group(1)}.{wp.group(2)}"
            if (int(wp.group(1)), int(wp.group(2))) < (6, 0):
                pain_points.append(f"Running outdated WordPress {wp.group(1)}.{wp.group(2)} (current major version is 6.x)")
                score -= 25
        elif "wp-content" in html_lower:
            cms = "WordPress"
        elif "wix.com" in html_lower or "wixstatic" in html_lower:
            cms = "Wix"
        elif "squarespace" in html_lower:
            cms = "Squarespace"
        elif "weebly" in html_lower:
            cms = "Weebly"
        elif "cdn.shopify.com" in html_lower:
            cms = "Shopify"

        jq = re.search(r"jquery[.-]?(1\.\d+(?:\.\d+)?)(?:\.min)?\.js", html_lower)
        if jq:
            pain_points.append(f"Uses jQuery {jq.group(1)} (released before 2016, has known security issues)")
            score -= 15

        if re.search(r"<table[^>]*(cellpadding|cellspacing)", html_lower) and not soup.find(["header", "nav", "section"]):
            pain_points.append("Old table-based page layout (pre-2010 web technique)")
            score -= 20

        if "<frameset" in html_lower or ".swf" in html_lower:
            pain_points.append("Uses frames or Flash, which modern browsers no longer support")
            score -= 25

        this_year = datetime.date.today().year
        years = [int(y) for y in re.findall(r"(?:copyright|&copy;|©)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})", html_lower)]
        if years and max(years) <= this_year - 3:
            pain_points.append(f"Footer copyright still says {max(years)} - site looks unmaintained")
            score -= 15

        # Our own timing includes our network distance to the server, so it is only a hint -
        # PageSpeed (below) is the real speed evidence
        if speed_ms > 8000:
            minor_points.append(f"Homepage took {speed_ms / 1000:.1f}s to load in our test")

        if "wa.me" not in html_lower and "whatsapp" not in html_lower:
            minor_points.append("No WhatsApp / click-to-chat button")

        if not soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)}):
            minor_points.append("Missing meta description (weaker Google search snippet)")

    except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as e:
        # Before telling a business its site is down, make sure the failure isn't on our side
        if not await our_internet_ok():
            return _inconclusive("our internet/DNS connection failed", cms)
        await asyncio.sleep(2)
        try:
            await _fetch(clean_url, verify=False)
            return _inconclusive("site loaded only on a later retry", cms)
        except Exception:
            pass
        if isinstance(e, httpx.ConnectError):
            # Our local DNS is unreliable - only claim this when public DNS confirms the domain is gone
            host = httpx.URL(clean_url).host
            exists = await domain_exists(host)
            if exists is False:
                # www.example.com may be missing while example.com works (or the reverse) - audit the working one
                alt = host[4:] if host.startswith("www.") else "www." + host
                if await domain_exists(alt) is True:
                    return await audit_website(f"https://{alt}/")
            if exists is not False:
                return _inconclusive("could not connect, but the domain still resolves (likely our network)", cms)
            pain_points.append(f"The website address {host} does not exist in DNS - visitors get 'site can't be reached' (domain expired or misconfigured)")
            score = 10
        else:
            pain_points.append("Website did not load (no response within 20 seconds, re-checked)")
            score = 15
    except Exception as e:
        return _inconclusive(str(e)[:60], cms)

    psi = None
    if score > 15:
        psi = await pagespeed_mobile_score(clean_url)
        if psi is not None and psi < 50:
            pain_points.insert(0, f"Google PageSpeed mobile score {psi}/100 (poor - Google recommends 90+)")
            score -= 25

    score = max(5, min(score, 100))
    needs_work = bool(pain_points)
    all_points = pain_points + minor_points
    summary = (f"Audit {score}/100" + (f", PageSpeed mobile {psi}/100" if psi is not None else "")
               + (f". Problems found: {'; '.join(pain_points[:2])}." if pain_points else ". No major problems found."))

    return {
        "has_website": True,
        "audit_score": score,
        "needs_work": needs_work,
        "pain_points": all_points,
        "summary": summary,
        "speed_ms": speed_ms,
        "cms": cms,
        "pagespeed_mobile": psi,
    }
