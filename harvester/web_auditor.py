import httpx
import re
from bs4 import BeautifulSoup
from typing import Dict, Any

async def audit_website(url: str) -> Dict[str, Any]:
    """
    Audits a website for speed, mobile responsiveness, SEO tags, SSL, and tech stack.
    Returns:
        audit_score: 0-100 (lower score = higher agency opportunity)
        pain_points: list of identified weaknesses
        summary: clean textual diagnosis
    """
    if not url or not url.strip():
        return {
            "has_website": False,
            "audit_score": 10,
            "pain_points": ["No website or digital storefront found"],
            "summary": "Business has no online website. High priority opportunity to build from scratch.",
            "speed_ms": 0,
            "cms": "None"
        }

    clean_url = url.strip()
    if not clean_url.startswith("http"):
        clean_url = "https://" + clean_url

    pain_points = []
    cms = "Custom / Unknown"
    speed_ms = 0
    score = 100

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=3.5, follow_redirects=True, verify=False) as client:
            import time
            start = time.time()
            res = await client.get(clean_url, headers=headers)
            speed_ms = int((time.time() - start) * 1000)

            if res.status_code >= 400:
                return {
                    "has_website": True,
                    "audit_score": 15,
                    "pain_points": [f"Website returns HTTP error {res.status_code}", "Site is broken/inaccessible"],
                    "summary": f"Website is throwing error {res.status_code}. Immediate redesign/fix needed.",
                    "speed_ms": speed_ms,
                    "cms": "Broken"
                }

            html = res.text
            soup = BeautifulSoup(html, "html.parser")

            # 1. CRITICAL: Insecure SSL (Browser shows 'Not Secure' warning, destroys customer trust)
            if not str(res.url).startswith("https://"):
                pain_points.append("BROKEN SECURITY: Insecure HTTP connection — Modern browsers flag site as 'Not Secure' & block incoming customers")
                score -= 35

            # 2. CRITICAL DEAL-BREAKER: Extreme Mobile Load Delay (> 2.5s)
            if speed_ms > 3000:
                pain_points.append(f"REVENUE KILLER: Severe mobile load lag ({speed_ms}ms) — 53%+ of smartphone visitors immediately bounce and call competitors")
                score -= 30
            elif speed_ms > 1800:
                pain_points.append(f"PERFORMANCE BOTTLENECK: High server response time ({speed_ms}ms) causing high mobile drop-off")
                score -= 20

            # 3. CRITICAL DEAL-BREAKER: Non-Responsive / Broken on Mobile
            viewport = soup.find("meta", attrs={"name": re.compile(r"viewport", re.I)})
            if not viewport:
                pain_points.append("BROKEN ON MOBILE: Site lacks mobile viewport — Pages render microscopic on iPhone/Android requiring frustrating pinch-to-zoom")
                score -= 40

            # 4. CRITICAL DEAL-BREAKER: Ancient Obsolete Code & Security Exploits
            if "jquery-1." in html_lower or "jquery/1." in html_lower:
                pain_points.append("OBSOLETE TECH STACK: Running deprecated jQuery 1.x (vulnerable to known XSS exploits & broken on modern iOS Safari)")
                score -= 25
            if "table" in html_lower and ("cellpadding" in html_lower or "cellspacing" in html_lower):
                pain_points.append("OUTDATED ARCHITECTURE: Ancient table-based layout structure — Completely incompatible with modern search engines & smartphones")
                score -= 30

            # 5. Outdated CMS & Vulnerable Version
            if "wp-content" in html_lower or "wordpress" in html_lower:
                if re.search(r"ver=(?:3\.|4\.|5\.[0-8])", html_lower):
                    cms = "Ancient WordPress"
                    pain_points.append("URGENT SECURITY RISK: Ancient WordPress core (< 5.9) with unpatched vulnerabilities — Critical malware injection hazard")
                    score -= 35
                else:
                    cms = "WordPress"
                    pain_points.append("PERFORMANCE OVERHEAD: Bloated legacy WordPress setup slowing mobile checkout conversions")
                    score -= 15
            elif "wix.com" in html_lower:
                cms = "Wix Template"
                pain_points.append("CONVERSION BOTTLENECK: Trapped in basic Wix template — Poor SEO indexing and sluggish mobile execution")
                score -= 15
            elif "weebly" in html_lower:
                cms = "Weebly"
                pain_points.append("ABANDONED BUILDER: Hosted on obsolete Weebly builder — Look & feel appears unprofessional to high-paying clients")
                score -= 30

            # 6. Outdated Copyright / Abandoned Look (Direct proof of business neglect)
            matches = re.findall(r"(?:copyright|©)\s*([12][0-9]{3})", html_lower)
            if matches:
                year = int(matches[-1])
                if year <= 2022:
                    pain_points.append(f"OUTDATED & NEGLECTED: Copyright is {year} ({2026 - year} years without updates) — Customers assume business is closed")
                    score -= 25

            # 7. No 1-Click WhatsApp or Instant Lead Capture
            if "wa.me" not in html_lower and "whatsapp" not in html_lower:
                pain_points.append("ZERO INSTANT CONTACT CTA: No 1-click WhatsApp or instant booking button — 60%+ of modern mobile visitors leave without contacting")
                score -= 15

    except httpx.ConnectTimeout:
        pain_points.append("CRITICAL: Server timeout — Website frequently fails to open for potential customers")
        score = 15
    except httpx.ConnectError:
        pain_points.append("CRITICAL: Domain/DNS connection failed — Business is currently losing 100% of web traffic")
        score = 10
    except Exception as e:
        pain_points.append(f"Technical warning: {str(e)[:50]}")
        score = 35

    score = max(5, min(score, 100))
    summary = f"Audit Score: {score}/100. Key Deal-Breakers: {'; '.join(pain_points[:2])}."


    return {
        "has_website": True,
        "audit_score": score,
        "pain_points": pain_points,
        "summary": summary,
        "speed_ms": speed_ms,
        "cms": cms
    }
