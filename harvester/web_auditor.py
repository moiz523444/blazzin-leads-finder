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

            # Check SSL
            if not str(res.url).startswith("https://"):
                pain_points.append("No SSL Certificate (Insecure HTTP)")
                score -= 20

            # Check Speed
            if speed_ms > 2500:
                pain_points.append(f"Slow response time ({speed_ms}ms) - Hurts mobile conversions")
                score -= 25
            elif speed_ms > 1400:
                pain_points.append(f"Sub-optimal speed ({speed_ms}ms)")
                score -= 10

            # Check Mobile Viewport
            viewport = soup.find("meta", attrs={"name": re.compile(r"viewport", re.I)})
            if not viewport:
                pain_points.append("Missing Mobile Viewport (Not optimized for smartphones)")
                score -= 30

            # Check Meta SEO Tags
            title = soup.find("title")
            meta_desc = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
            if not title or len(title.text.strip()) < 5:
                pain_points.append("Missing or weak SEO Title tag")
                score -= 10
            if not meta_desc:
                pain_points.append("Missing Meta Description (Hurts Google ranking)")
                score -= 15

            # Detect CMS / Outdated platforms
            html_lower = html.lower()
            if "wp-content" in html_lower or "wordpress" in html_lower:
                cms = "WordPress"
            elif "shopify" in html_lower:
                cms = "Shopify"
            elif "wix.com" in html_lower:
                cms = "Wix (Sub-optimal for scale)"
                score -= 10
                pain_points.append("Built on Wix template - Limited performance & SEO capabilities")
            elif "squarespace" in html_lower:
                cms = "Squarespace"

            # Check Outdated Copyright year in footer
            matches = re.findall(r"(?:copyright|©)\s*([12][0-9]{3})", html_lower)
            if matches:
                year = int(matches[-1])
                if year <= 2021:
                    pain_points.append(f"Outdated site copyright ({year}) - Has not been updated in years")
                    score -= 15

            # Missing modern conversion elements (no WhatsApp or live chat or clear CTA)
            if "wa.me" not in html_lower and "whatsapp" not in html_lower:
                pain_points.append("No instant WhatsApp / Quick chat conversion button")
                score -= 10

    except httpx.ConnectTimeout:
        pain_points.append("Website times out / Very slow server hosting")
        score = 20
    except httpx.ConnectError:
        pain_points.append("Domain connection failed / DNS configuration issue")
        score = 15
    except Exception as e:
        pain_points.append(f"Audit warning: {str(e)[:50]}")
        score = 40

    if not pain_points:
        pain_points.append("Standard website - Potential for modern app or custom feature expansion")

    score = max(5, min(score, 100))
    summary = f"Audit Score: {score}/100. Issues detected: {', '.join(pain_points[:2])}."

    return {
        "has_website": True,
        "audit_score": score,
        "pain_points": pain_points,
        "summary": summary,
        "speed_ms": speed_ms,
        "cms": cms
    }
