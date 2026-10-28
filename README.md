# Blazzin Leads Finder

Finds local businesses in the **US, UK, Canada, UAE and Qatar** that show real evidence of needing
web / digital services, with their verified phone number, and writes an outreach pitch for each.

## Where leads come from

**Verified Local Businesses** (default channel, [harvester/local_business.py](harvester/local_business.py)):

1. Picks states / provinces / emirates from [harvester/regions.py](harvester/regions.py) - every state of all
   5 countries. "Rotate" mode picks different ones every scan; you can also pick one state.
2. Pulls business listings for the chosen niche from map data:
   - **TomTom Search API** when `TOMTOM_API_KEY` is set (free, recommended), otherwise
   - **OpenStreetMap Overpass** (free, no key, but the public servers are slow and often busy).
3. Keeps only independent businesses (chains removed) with a phone number that is valid for that country.
   WhatsApp is only filled when the number is a confirmed mobile or the business published a wa.me link.
4. Keeps a business only if there is evidence it needs you:
   - **No website**: none on its listing and no live website for its name (checked after confirming our own
     internet connection works), or only a Facebook/Instagram page; or
   - **Website problems actually observed**: broken/down, no HTTPS, invalid SSL, not mobile-friendly,
     outdated WordPress/jQuery, old copyright year, poor Google PageSpeed mobile score (with `PAGESPEED_API_KEY`).
5. Emails come only from the business's own listing or website.

The older search-engine channels (website revamp, e-commerce, zero-website, app store, social) are still
available as checkboxes; their fake App Store "fallbacks" and invented pain points have been removed.

## Setup

```powershell
pip install -r requirements.txt
copy .env.example .env   # then paste your free keys into .env
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open http://127.0.0.1:8000

### Free keys (optional but strongly recommended)

| Key | Where | Free limit |
|---|---|---|
| `TOMTOM_API_KEY` | https://developer.tomtom.com - sign up, Dashboard -> Keys | 2,500 requests/day, no card |
| `PAGESPEED_API_KEY` | Google Cloud console -> enable "PageSpeed Insights API" -> Credentials -> API key | 25,000/day |

A scan uses about 2 TomTom requests per city searched (roughly 10-20 per scan).

## Scans

A scan runs in the background ([scan_jobs.py](scan_jobs.py)) until the **target number of new leads** is
reached: each round searches ~10 new cities, every verified lead is saved immediately, and the dashboard shows
`found / target`, an estimated time remaining (from the live rate) and a Stop button. Safety limits: 25 minutes,
12 rounds, or 3 rounds in a row with nothing new (the niche/area is used up).

## Data

Leads are stored in `leads.db` (SQLite, git-ignored). Scans add new leads and skip ones already saved,
so contacted status is kept. **Export Last Scan** downloads only the new leads from the most recent scan;
**All** downloads everything. "Clear" in the dashboard deletes everything.

## Troubleshooting

- **Few or no leads without a TomTom key**: the free OpenStreetMap servers were too busy - scan again or add the key.
- **Random "connection failed" errors**: if your internet's DNS is unreliable, set Windows DNS to `1.1.1.1` / `8.8.8.8`.
- Cold outreach in the UK/EU (PECR/GDPR), Canada (CASL) and UAE has rules - include an opt-out in your messages.
