import httpx
from typing import Optional
from models import Lead

async def generate_pitch(lead: Lead, gemini_api_key: Optional[str] = None) -> str:
    """
    Generates a personalized, high-converting outreach message based on the exact
    pain points identified for this lead.
    """
    # If Gemini API key is available, use Gemini Flash for deep AI synthesis
    if gemini_api_key and gemini_api_key.strip():
        try:
            prompt = f"""
            You are a top-tier software agency growth director. Write a short, punchy, 
            personalized cold outreach email (under 120 words) for this prospective client:
            
            Business Name: {lead.business_name}
            Lead Source: {lead.source}
            Service: {lead.service_needed}
            Website: {lead.website}
            Has Website: {lead.has_website}
            Pain Points Identified: {', '.join(lead.pain_points)}
            Audit Score: {lead.audit_score}/100
            
            Rules:
            1. No generic robotic greetings. Be direct, respectful, and mention their specific pain point.
            2. Offer a concrete 2-minute video walkthrough or a quick 3-step solution.
            3. End with a low-friction call to action (e.g., 'Worth a quick chat this Thursday?').
            4. ONLY mention facts listed above. Do not claim you saw their ads, reviews, or anything not listed.
            """
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_api_key.strip()}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    ai_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return ai_text
                print(f"Gemini API returned {res.status_code}: {res.text[:200]}")
        except Exception as e:
            print(f"Gemini API fallback: {e}")

    # Built-in High-Converting Formula based on Source & Pain Points
    source = lead.source
    b_name = lead.business_name
    primary_pain = lead.pain_points[0] if lead.pain_points else "improving your digital conversion rate"
    
    if not lead.has_website:
        # PITCH FOR ZERO-WEBSITE BUSINESSES (HOT LEADS)
        pitch = f"""Hi {b_name} team,

I was looking for your business in {lead.location} and noticed you don't have an official website or digital storefront yet.

Over 70% of potential customers looking for {lead.service_needed.replace('_', ' ')} check a website or portfolio before they call or book. Without one, valuable clients are going straight to competitors.

We design high-converting, mobile-first websites with direct WhatsApp ordering and automated booking systems, ready to launch in 5-7 days.

Would you be open to a quick 60-second video demo showing how this could look for {b_name}?

Best regards,
Lead Software Solutions"""

    elif lead.service_needed == "ecommerce" or source == "job_intent":
        # PITCH FOR E-COMMERCE CONVERSION REVAMP
        pitch = f"""Hi {b_name} Store Team,

I was reviewing your online store and ran a quick mobile conversion audit on it.

A critical factor stood out: {primary_pain}. For modern online stores, even a 1-second mobile delay or friction at checkout reduces completed purchases by up to 20%.

We specialize in high-speed Shopify and Next.js custom e-commerce optimization, boosting mobile checkout conversions and adding direct WhatsApp one-click order flows.

Mind if I send over a quick 2-minute video breakdown of 3 conversion fixes you can implement right away?

Best regards,
E-Commerce Growth Team"""

    elif source == "app_store" or lead.service_needed == "mobile_apps":
        # PITCH FOR MOBILE APP REVAMP
        pitch = f"""Hi {b_name} Team,

I was analyzing your mobile app: {primary_pain}.

When apps lag behind on modern UI updates or user ratings, user churn accelerates and store ranking drops significantly.

Our agency specializes in mobile app modernization — upgrading legacy apps to clean, high-performance Flutter or React Native with smooth UX, offline capability, and modern API architecture.

Can I share a short 3-minute UI/UX teardown showing how we can revamp the app and lift user ratings?

Best regards,
Mobile Engineering Team"""

    else:
        # HIGH-CONVERTING PITCH FOR WEBSITE TECH REVAMP
        pitch = f"""Hi {b_name} Leadership Team,

I visited your website and ran a technical performance and mobile security diagnostic on it.

A severe issue immediately showed up: {primary_pain}.

When potential clients visit your site from their phones and experience this, over 50% immediately bounce and hire your direct competitors instead. For an active business in {lead.location}, this is quietly costing you tens of thousands of dollars in lost bookings every month.

We engineer high-converting Next.js / modern web systems with sub-second mobile speeds, bank-grade SSL, and automated 1-click WhatsApp booking systems.

I've put together a quick 90-second video teardown showing the exact fixes you need. Mind if I send the link over to you here?

Best regards,
Agency Technical Director"""

    return pitch.strip()
