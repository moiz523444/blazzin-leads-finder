import netfix
netfix.install()  # survive the local DNS failing lookups at random - must run before any network code

from fastapi import FastAPI, Request, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional

import config
from models import ScanRequest, StatusUpdate
import database as db
import scan_jobs
from harvester.regions import list_regions, COUNTRY_NAMES

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


@app.post("/api/scan/start")
async def start_scan(req: ScanRequest):
    """Starts a background scan that keeps going until `limit` NEW leads are found (or a safety limit hits)."""
    running = scan_jobs.current_job()
    if running and running.state == "running":
        return {"success": False, "message": "A scan is already running.", **running.status()}
    job = scan_jobs.start_job(req)
    return {"success": True, **job.status()}

@app.get("/api/scan/status")
async def scan_status(since: int = 0):
    """Live progress of the current/last scan: found / target, ETA and new log lines after `since`."""
    job = scan_jobs.current_job()
    if not job:
        return {"state": "idle"}
    return job.status(since)

@app.post("/api/scan/stop")
async def stop_scan():
    job = scan_jobs.current_job()
    if job and job.state == "running":
        job.stop_requested = True
        job.log("Stop requested - finishing the leads being checked right now...", "warn")
    return {"success": True}

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
