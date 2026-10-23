import netfix
netfix.install()  # survive the local DNS failing lookups at random - must run before any network code

from fastapi import FastAPI, Request, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio
from typing import Optional, List

import re
from datetime import datetime

import config
from models import Lead, ScanRequest, StatusUpdate
import database as db
from harvester.local_business import harvest_local_businesses
from harvester.regions import list_regions, COUNTRY_NAMES
from harvester.meta_ads import harvest_meta_ads
from harvester.ecom_funnel import harvest_ecom_stores
from harvester.zero_website import harvest_zero_website_leads
from harvester.app_store import harvest_app_store
from harvester.social_media import harvest_social_leads
from enricher.ai_pitcher import generate_pitch

app = FastAPI(title="Omni-Lead AI Engine", description="Autonomous High-Intent Lead Intelligence Platform for Software Agencies")

# Mount static and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Initialize DB on startup
@app.on_event("startup")
def on_startup():
    db.init_db()
    if config.TOMTOM_API_KEY:
        print("[setup] TomTom key loaded - using TomTom for verified local businesses")
    else:
        print("[setup] No TOMTOM_API_KEY in .env - falling back to slow free OpenStreetMap servers")

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    stats = db.get_stats()
    leads = db.get_leads(limit=100)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "stats": stats,
            "initial_leads": leads
        }
    )

@app.get("/api/stats")
async def get_stats():
    return db.get_stats()

@app.get("/api/regions")
async def get_regions():
    return {"countries": COUNTRY_NAMES, "regions": list_regions()}

@app.get("/api/leads")
async def get_leads(
    source: Optional[str] = "all",
    country: Optional[str] = "all",
    region: Optional[str] = "all",
    service: Optional[str] = "all",
    status: Optional[str] = "all",
    search: Optional[str] = None,
    limit: int = 300
):
    leads = db.get_leads(source=source, country=country, region=region, service=service, status=status, search=search, limit=limit)
    return {"leads": leads, "total": len(leads)}

@app.post("/api/leads/{lead_id}/status")
async def update_status(lead_id: int, status_update: StatusUpdate):
    db.update_lead_status(lead_id, status_update.status)
    return {"success": True, "lead_id": lead_id, "status": status_update.status}


_COUNTRY_HINTS = [
    ("UAE", r"\bUAE\b|United Arab Emirates|Dubai|Abu Dhabi|Sharjah|Ajman|Fujairah|Ras Al Khaimah|\bae\b"),
    ("QA", r"\bQA\b|Qatar|Doha|Lusail|Al Rayyan|Wakrah"),
    ("UK", r"\bUK\b|United Kingdom|\bGB\b|England|Scotland|Wales|London|Manchester|Birmingham"),
    ("CA", r"\bCA\b|Canada|Toronto|Vancouver|Montreal|Calgary|Ontario|Quebec"),
    ("US", r"\bUS\b|\bUSA\b|United States"),
]

def infer_country(lead: Lead, scan_country: str) -> str:
    """Older harvesters only write free-text locations - derive the country code used for filtering."""
    if lead.country:
        return lead.country.upper()
    if scan_country and scan_country.upper() != "ALL":
        return scan_country.upper()
    for code, pattern in _COUNTRY_HINTS:
        if re.search(pattern, lead.location or "", re.I):
            return code
    return ""


@app.post("/api/scan")
async def run_scan(req: ScanRequest):
    """
    Executes an autonomous multi-source harvesting and enrichment cycle.
    New leads are added to the existing ones; anything already saved is skipped.
    """
    all_harvested = []
    existing_sigs = db.get_existing_signatures()
    # Sortable ID shared by every lead this scan saves, so "Export last scan" returns only these
    scan_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    # The search-engine sources are capped (they rely on a handful of web searches); verified local scales with the slider
    legacy_sources = [s for s in req.sources if s != "local_verified"]
    per_source_limit = max(2, min(10, req.limit // max(1, len(req.sources))))

    tasks = []
    if "local_verified" in req.sources:
        local_limit = req.limit - per_source_limit * len(legacy_sources) if legacy_sources else req.limit
        tasks.append(harvest_local_businesses(niche=req.niche, country=req.country, region=req.region or "all",
                                              limit=max(5, local_limit), exclude=existing_sigs))
    if "meta_ads" in req.sources:
        tasks.append(harvest_meta_ads(niche=req.niche, country=req.country, limit=per_source_limit))
    if "ecom_funnel" in req.sources:
        tasks.append(harvest_ecom_stores(niche=req.niche, country=req.country, limit=per_source_limit))
    if "new_business" in req.sources:
        tasks.append(harvest_zero_website_leads(niche=req.niche, country=req.country, limit=per_source_limit))
    if "app_store" in req.sources:
        tasks.append(harvest_app_store(niche=req.niche, country=req.country, limit=per_source_limit))
    if "social_media" in req.sources:
        tasks.append(harvest_social_leads(niche=req.niche, country=req.country, limit=per_source_limit))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for res in results:
        if isinstance(res, list):
            all_harvested.extend(res)
        elif isinstance(res, Exception):
            print(f"Harvester failed: {type(res).__name__}: {res}")

    for lead in all_harvested:
        lead.country = infer_country(lead, req.country)

    # STRICT RULE: Must have callable PHONE or WHATSAPP + NEVER REPEAT ALREADY HARVESTED LEADS
    fresh_leads = []
    seen_in_scan = set()

    for lead in all_harvested:
        if not (lead.phone or lead.whatsapp):
            continue
        p = (lead.phone or "").strip()
        w = (lead.website or "").strip().lower()
        b = (lead.business_name or "").strip().lower()

        # Check if already in database from previous scans
        if p in existing_sigs or (w and w in existing_sigs) or b in existing_sigs:
            continue
        # Check if already seen in current scan
        if p in seen_in_scan or (w and w in seen_in_scan) or b in seen_in_scan:
            continue

        seen_in_scan.add(p)
        if w:
            seen_in_scan.add(w)
        seen_in_scan.add(b)
        fresh_leads.append(lead)

    valid_leads = fresh_leads


    async def enrich_lead(lead: Lead):
        lead.scan_id = scan_id
        lead.ai_pitch = await generate_pitch(lead, gemini_api_key=req.gemini_api_key)
        lead_id = db.save_lead(lead)
        if lead_id:
            lead.id = lead_id
        return lead.model_dump()

    # Parallel enrichment for maximum speed
    saved_leads = await asyncio.gather(*(enrich_lead(l) for l in valid_leads), return_exceptions=False)
    db.record_scan(scan_id, len(saved_leads))

    message = ""
    if "local_verified" in req.sources and not config.TOMTOM_API_KEY:
        message = ("Running on free OpenStreetMap servers (slow and often busy). "
                   "Add a free TOMTOM_API_KEY to .env for many more verified leads.")
    if not saved_leads:
        message = (message + " " if message else "") + "No new leads this time - scan again (each scan picks different states) or choose another niche."

    return {
        "success": True,
        "harvested_count": len(saved_leads),
        "scan_id": scan_id,
        "leads": saved_leads,
        "message": message,
        "stats": db.get_stats()
    }

@app.get("/api/export")
async def export_csv(scope: str = "last"):
    """scope=last (default): only the new leads from the most recent scan. scope=all: every saved lead."""
    if scope == "all":
        csv_data, filename = db.export_leads_csv(), "all_leads.csv"
    else:
        last = db.get_latest_scan_id()
        csv_data = db.export_leads_csv(scan_id=last or "__none__")
        filename = f"new_leads_{last or 'none'}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/last-scan")
async def last_scan():
    last = db.get_latest_scan_id()
    return {"scan_id": last, "count": len(db.get_leads(limit=100000, scan_id=last)) if last else 0}

@app.post("/api/clear")
async def clear_database():
    db.clear_all_leads()
    return {"success": True, "message": "All leads cleared"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
