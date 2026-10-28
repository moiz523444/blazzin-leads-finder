"""
Background scan jobs: keep harvesting round after round (new states/cities each round) until the target
number of NEW verified leads is reached, saving every lead the moment it is verified so the dashboard can
show live progress and an estimated time remaining.
"""
import asyncio
import re
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Optional

import config
import database as db
from models import Lead, ScanRequest
from enricher.ai_pitcher import generate_pitch
from harvester.local_business import harvest_local_businesses
from harvester.meta_ads import harvest_meta_ads
from harvester.ecom_funnel import harvest_ecom_stores
from harvester.zero_website import harvest_zero_website_leads
from harvester.app_store import harvest_app_store
from harvester.social_media import harvest_social_leads

MAX_SECONDS = 25 * 60       # hard stop so one job can't burn the whole free TomTom quota (~2,500 requests/day)
MAX_ROUNDS = 12             # each round searches ~10 new cities
MAX_EMPTY_ROUNDS = 3        # stop when the chosen niche/area keeps returning nothing new
ROUND_BUDGET_S = 180        # one round = one batch of cities
INITIAL_SECONDS_PER_LEAD = 6.5  # measured: 30 leads in ~200s with full verification; replaced by the live rate

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


class ScanJob:
    def __init__(self, req: ScanRequest):
        self.id = datetime.now().strftime("%Y%m%d-%H%M%S")  # also the scan_id stamped on every lead
        self.token = uuid.uuid4().hex[:8]
        self.req = req
        self.target = req.limit
        self.found = 0
        self.round = 0
        self.state = "running"  # running | done | stopped | exhausted | timeout | error
        self.message = ""
        self.started = time.time()
        self.finished: Optional[float] = None
        self.stop_requested = False
        self._log = deque(maxlen=300)
        self._seq = 0

    def log(self, text: str, kind: str = "normal"):
        self._seq += 1
        self._log.append({"seq": self._seq, "text": text, "kind": kind})

    def eta_seconds(self) -> Optional[int]:
        if self.state != "running":
            return 0
        elapsed = time.time() - self.started
        remaining = self.target - self.found
        if self.found >= 3 and elapsed > 20:
            per_lead = elapsed / self.found
        else:
            per_lead = INITIAL_SECONDS_PER_LEAD
        return int(min(remaining * per_lead, max(0, MAX_SECONDS - elapsed)))

    def status(self, since: int = 0) -> Dict:
        end = self.finished or time.time()
        return {
            "job_id": self.token,
            "scan_id": self.id,
            "state": self.state,
            "found": self.found,
            "target": self.target,
            "round": self.round,
            "elapsed": int(end - self.started),
            "eta_seconds": self.eta_seconds(),
            "message": self.message,
            "log": [e for e in self._log if e["seq"] > since],
        }


_current: Optional[ScanJob] = None


def current_job() -> Optional[ScanJob]:
    return _current


def start_job(req: ScanRequest) -> ScanJob:
    global _current
    if _current and _current.state == "running":
        return _current
    _current = ScanJob(req)
    asyncio.get_running_loop().create_task(_run(_current))
    return _current


async def _run(job: ScanJob):
    req = job.req
    # DNS lookups run in the default thread pool; the stock size (~12 threads) queues up during big scans
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=64))
    exclude = db.get_existing_signatures()

    async def accept(lead: Lead) -> bool:
        """Final checks + save. Returns False for leads that are not new."""
        lead.country = infer_country(lead, req.country)
        if not (lead.phone or lead.whatsapp):
            return False
        p = (lead.phone or "").strip()
        w = (lead.website or "").strip().lower()
        b = (lead.business_name or "").strip().lower()
        if p in exclude or (w and w in exclude) or b in exclude:
            return False
        exclude.update(s for s in (p, w, b) if s)
        lead.scan_id = job.id
        lead.ai_pitch = await generate_pitch(lead, gemini_api_key=req.gemini_api_key)
        if not db.save_lead(lead):
            return False
        job.found += 1
        job.log(f"[{job.found}/{job.target}] {lead.business_name} - {lead.location} ({lead.pain_points[0] if lead.pain_points else ''})"[:160], "success")
        return True

    try:
        mode = "TomTom" if config.TOMTOM_API_KEY else "free OpenStreetMap (slow - add TOMTOM_API_KEY for speed)"
        job.log(f"Scan started: target {job.target} new leads, niche [{req.niche}], {req.country}"
                f"{'' if (req.region or 'all') == 'all' else ' / ' + req.region}, source: {mode}", "info")

        legacy = [s for s in req.sources if s != "local_verified"]
        if legacy:
            job.log(f"Running experimental channels once: {', '.join(legacy)}", "warn")
            per_source = max(2, min(10, job.target // max(1, len(req.sources))))
            makers = {"meta_ads": harvest_meta_ads, "ecom_funnel": harvest_ecom_stores, "new_business": harvest_zero_website_leads,
                      "app_store": harvest_app_store, "social_media": harvest_social_leads}
            results = await asyncio.gather(*(makers[s](niche=req.niche, country=req.country, limit=per_source)
                                             for s in legacy if s in makers), return_exceptions=True)
            for res in results:
                for lead in (res if isinstance(res, list) else []):
                    if job.found < job.target:
                        await accept(lead)

        empty_rounds = 0
        while "local_verified" in req.sources and job.found < job.target:
            elapsed = time.time() - job.started
            if job.stop_requested:
                job.state = "stopped"
                break
            if elapsed >= MAX_SECONDS:
                job.state, job.message = "timeout", f"Stopped at the {MAX_SECONDS // 60}-minute safety limit."
                break
            if job.round >= MAX_ROUNDS:
                job.state, job.message = "exhausted", f"Stopped after {MAX_ROUNDS} rounds of cities."
                break
            job.round += 1
            before = job.found
            job.log(f"Round {job.round}: searching new cities for {job.target - job.found} more leads...", "info")
            await harvest_local_businesses(
                niche=req.niche, country=req.country, region=req.region or "all",
                limit=job.target - job.found, exclude=exclude,
                time_budget_s=min(ROUND_BUDGET_S, MAX_SECONDS - elapsed),
                on_lead=accept, should_stop=lambda: job.stop_requested)
            got = job.found - before
            job.log(f"Round {job.round} done: +{got} leads ({job.found}/{job.target})", "info")
            empty_rounds = empty_rounds + 1 if got == 0 else 0
            if empty_rounds >= MAX_EMPTY_ROUNDS:
                job.state = "exhausted"
                job.message = ("No new leads in the last 3 rounds - this niche/area looks used up. "
                               "Try another niche, country or 'All Industries'.")
                break

        if job.state == "running":
            job.state = "done" if job.found >= job.target else "exhausted"
    except Exception as e:
        job.state, job.message = "error", f"{type(e).__name__}: {e}"
        job.log(f"Scan error: {job.message}", "warn")
    finally:
        job.finished = time.time()
        db.record_scan(job.id, job.found)
        mins, secs = divmod(int(job.finished - job.started), 60)
        job.log(f"Finished ({job.state}): {job.found} new leads in {mins}m {secs}s. {job.message}".strip(),
                "success" if job.found else "warn")
