from fastapi import FastAPI, Request, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio
from typing import Optional, List

from models import Lead, ScanRequest
import database as db
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

@app.get("/api/leads")
async def get_leads(
    source: Optional[str] = "all",
    country: Optional[str] = "all",
    service: Optional[str] = "all",
    status: Optional[str] = "all",
    search: Optional[str] = None,
    limit: int = 150
):
    leads = db.get_leads(source=source, country=country, service=service, status=status, search=search, limit=limit)
    return {"leads": leads, "total": len(leads)}

@app.post("/api/leads/{lead_id}/status")
async def update_status(lead_id: int, status_update: dict):
    new_status = status_update.get("status", "contacted")
    db.update_lead_status(lead_id, new_status)
    return {"success": True, "lead_id": lead_id, "status": new_status}

@app.post("/api/scan")
async def run_scan(req: ScanRequest):
    """
    Executes an autonomous multi-source harvesting and enrichment cycle.
    """
    all_harvested = []
    per_source_limit = min(15, max(3, req.limit // max(1, len(req.sources))))

    tasks = []
    if "meta_ads" in req.sources:
        tasks.append(harvest_meta_ads(niche=req.niche, country=req.country, limit=per_source_limit))
    if "ecom_funnel" in req.sources or "job_intent" in req.sources:
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

    valid_leads = [
        lead for lead in all_harvested
        if (lead.phone or lead.whatsapp or lead.email)
    ]

    async def enrich_lead(lead: Lead):
        lead.ai_pitch = await generate_pitch(lead, gemini_api_key=req.gemini_api_key)
        lead_id = db.save_lead(lead)
        if lead_id:
            lead.id = lead_id
        return lead.model_dump()

    # Parallel enrichment for maximum speed
    saved_leads = await asyncio.gather(*(enrich_lead(l) for l in valid_leads), return_exceptions=False)

    return {
        "success": True,
        "harvested_count": len(saved_leads),
        "leads": saved_leads,
        "stats": db.get_stats()
    }

@app.get("/api/export")
async def export_csv():
    csv_data = db.export_leads_csv()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=omni_agency_leads.csv"}
    )

@app.post("/api/clear")
async def clear_database():
    db.clear_all_leads()
    return {"success": True, "message": "All leads cleared"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
