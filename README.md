# Omni-Lead AI Engine 🚀
### Autonomous High-Intent Client Acquisition Platform for Software Agencies

Omni-Lead AI is an automated multi-channel lead generation and cold outreach system built specifically to target high-budget clients for:
- **Web Development & Web Applications**
- **Mobile Applications (iOS & Android)**
- **E-Commerce Stores & Shopify Migrations**
- **SEO & Performance Optimization**
- **Social Media Marketing & Brand Identity**

---

## ⚡ Why This Beats Traditional Google Maps Scrapers

Unlike generic scrapers that spam thousands of saturated Google Maps listings:
1. **Meta Ad Spenders (Active Ad Budgets):** Targets businesses currently spending money on Facebook & Instagram ads whose landing pages are broken, missing mobile optimization, or have no website at all.
2. **Job Board Reverse-Engineering:** Targets companies actively recruiting full-time developers and marketers on job boards (with salaries of $3,000 - $8,000/mo) and pitches agency replacement at half the overhead.
3. **Fresh Company Registrations (0 - 30 Days Old):** Pulls newly incorporated UK & US companies before they even list on Google Maps. Zero competitors have contacted them yet (First-Mover Advantage).
4. **App Store Revamp Scanner:** Finds mobile applications on Google Play & App Store with poor ratings (2.0 - 3.8 stars) and user complaints, ready for a Flutter/React Native rebuild.

---

## 🛠️ Project Structure

```
omni-lead-ai/
├── app.py                     # FastAPI web server & live API routes
├── database.py                # SQLite database with auto-deduplication & stats
├── models.py                  # Pydantic data models for leads, filters & audits
├── test_server.py             # Pipeline test and sample lead runner
│
├── harvester/
│   ├── meta_ads.py            # Meta Ad Library scanner (Broken funnels & ad spenders)
│   ├── job_intent.py          # Job board scanner (Indeed, RemoteOK, hiring budgets)
│   ├── new_companies.py       # Fresh business registry (UK Companies House & LLCs)
│   ├── app_store.py           # Outdated & low-rated mobile apps scanner
│   └── web_auditor.py         # Real-time website speed, SSL & tech auditor
│
├── enricher/
│   ├── contact_extractor.py   # Extracts Emails, Phone numbers, WhatsApp, Socials
│   └── ai_pitcher.py          # AI personalized outreach pitch generator
│
├── static/
│   ├── css/style.css          # Modern dark glassmorphic UI design
│   └── js/app.js              # Real-time dashboard controller
└── templates/
    └── index.html             # Command Center Dashboard
```

---

## 🚀 How to Run the System

The server is currently **active and running locally**:

👉 **Open your browser and navigate to:**
```
http://127.0.0.1:8000
```

### To Restart the Server Anytime:
```powershell
cd C:\Users\DELL\.gemini\antigravity-ide\scratch\omni-lead-ai
& "C:\Users\DELL\AppData\Local\Programs\Python\Python311\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🎯 Key Features in the Dashboard

- **Autonomous Multi-Source Scanner:** Choose any combination of Meta Ads, Job Boards, Fresh Registrations, or App Store listings.
- **Niche & Country Selector:** Target Healthcare, E-Commerce, Real Estate, Logistics, or Tech in US, UK, UAE, Canada, Australia, etc.
- **Batch Volume Control:** Select from 10 up to 200 leads per batch run.
- **Real-time Live Engine Console:** Watch the scraper log activities live.
- **1-Click AI Outreach Modal:**
  - View detected pain points & technical audit score.
  - Review the hyper-personalized pitch tailored to the specific lead.
  - **1-Click Direct WhatsApp:** Opens WhatsApp Web with the customized pitch pre-filled!
  - **1-Click Email:** Opens default mail client ready to send.
- **Export to CSV:** Download all extracted leads with contact details and AI pitches.
