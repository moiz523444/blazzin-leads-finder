"""
Background trademark scans: walk USPTO serial numbers from the newest application backwards and keep every
pro-se filing (no attorney) from the chosen countries until the target number of NEW leads is saved.
Runs separately from the map scan in scan_jobs.py - both can run at the same time.
"""
import asyncio
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import database as db
from harvester import trademark as tm
from models import Lead

SEED_SERIAL = 50234600       # an application filed on 2026-11-24 - the newest-serial search starts here
MAX_SECONDS = 4 * 60 * 60    # hard stop
MAX_BLOCKED_IN_A_ROW = 15    # USPTO keeps refusing -> stop instead of hammering it
FRONTIER_MARGIN = 300        # serials this close to the newest may still be loading at USPTO - don't mark them missing
INITIAL_HIT_RATE = 0.10      # measured 2026-11-24: 11 of 105 new applications were US pro se with a contact


def _parse_date(text: str) -> Optional[datetime]:
    try:
        return datetime.strptime(text.replace(".", "").strip(), "%b %d, %Y")
    except ValueError:
        return None


class TrademarkJob:
    def __init__(self, target: int, countries: List[str], max_age_days: int):
        self.id = datetime.now().strftime("%Y%m%d-%H%M%S")  # scan_id stamped on every lead (same format as map scans)
        self.target = target
        self.countries = set(countries)
        self.max_age_days = max_age_days
        self.found = 0
        self.looked_up = 0
        self.state = "running"  # running | done | stopped | exhausted | timeout | blocked | error
        self.message = ""
        self.started = time.time()
        self.finished: Optional[float] = None
        self.stop_requested = False
        self.gap = tm.GAP_NO_KEY
        self._log = deque(maxlen=300)
        self._seq = 0

    def log(self, text: str, kind: str = "normal"):
        self._seq += 1
        self._log.append({"seq": self._seq, "text": f"[TM] {text}", "kind": kind})

    def eta_seconds(self) -> int:
        if self.state != "running":
            return 0
        rate = self.found / self.looked_up if self.looked_up >= 40 and self.found else INITIAL_HIT_RATE
        return int(min((self.target - self.found) / max(rate, 0.02) * self.gap, MAX_SECONDS - (time.time() - self.started)))

    def status(self, since: int = 0) -> Dict:
        end = self.finished or time.time()
        return {"scan_id": self.id, "state": self.state, "found": self.found, "target": self.target,
                "looked_up": self.looked_up, "elapsed": int(end - self.started), "eta_seconds": self.eta_seconds(),
                "message": self.message, "log": [e for e in self._log if e["seq"] > since]}


_current: Optional[TrademarkJob] = None


def current_job() -> Optional[TrademarkJob]:
    return _current


def start_job(target: int, countries: List[str], max_age_days: int) -> TrademarkJob:
    global _current
    if _current and _current.state == "running":
        return _current
    _current = TrademarkJob(target, countries, max_age_days)
    asyncio.get_running_loop().create_task(_run(_current))
    return _current


async def _run(job: TrademarkJob):
    client = tm.TsdrClient()
    exclude = db.get_existing_signatures()
    # USPTO dates filings in US Eastern time, so "today" is USPTO's today, not the caller's
    usa_today = datetime.now(ZoneInfo("America/New_York")).date()
    oldest_allowed = datetime.combine(usa_today - timedelta(days=job.max_age_days), datetime.min.time())
    blocked_in_a_row = 0
    try:
        mode = "official TSDR API (60/min)" if client.use_api else "public status page (30/min - add USPTO_API_KEY for 2x speed)"
        where = "any country" if not job.countries else ", ".join(sorted(job.countries))
        when = (f"filed today ({usa_today:%b %d} USPTO date)" if job.max_age_days == 0
                else f"filed in the last {job.max_age_days} days")
        job.log(f"Started: target {job.target} new trademark leads (no attorney, {where}, {when}) via {mode}", "info")
        job.log("Finding the newest USPTO application...", "info")
        latest = await tm.find_latest_serial(client, max(SEED_SERIAL, db.tm_highest_checked()))
        job.log(f"Newest serial number: {latest}. Working backwards from there.", "info")

        sn = latest
        while job.found < job.target:
            if job.stop_requested:
                job.state = "stopped"
                break
            if time.time() - job.started > MAX_SECONDS:
                job.state, job.message = "timeout", f"Stopped at the {MAX_SECONDS // 3600}-hour safety limit."
                break
            # Skip a whole block of serials that earlier scans already looked at
            low = sn - 500
            checked = db.tm_checked_serials(low, sn)
            while sn in checked:
                sn -= 1
                if sn < low:
                    low = sn - 500
                    checked = db.tm_checked_serials(low, sn)

            outcome, html = await client.fetch(sn)
            job.looked_up += 1
            job.gap = client.gap
            if outcome == tm.BLOCKED:
                blocked_in_a_row += 1
                if blocked_in_a_row >= MAX_BLOCKED_IN_A_ROW:
                    job.state = "blocked"
                    job.message = ("USPTO keeps refusing requests right now. Leads found so far are saved - "
                                   "try again in an hour (or add a free USPTO_API_KEY).")
                    break
                sn -= 1
                continue
            blocked_in_a_row = 0
            if outcome == tm.MISSING:
                if sn < latest - FRONTIER_MARGIN:
                    db.tm_mark_checked(sn, "missing")
                sn -= 1
                continue

            case = tm.parse_case(html, sn)
            filed = _parse_date(case["filed"])
            if filed and filed < oldest_allowed:
                job.state = "exhausted"
                job.message = (f"Reached applications filed before {oldest_allowed:%b %d, %Y} - every newer one is checked. "
                               + ("All of today's filings so far are done - USPTO adds more during the US working day, "
                                  "run again in a few hours." if job.max_age_days == 0 else
                                  "New applications arrive every working day; run again tomorrow or allow older filings."))
                break
            lead: Optional[Lead] = await tm.case_to_lead(case, job.countries)
            db.tm_mark_checked(sn, "lead" if lead else ("attorney" if not case["no_attorney"] else "skipped"))
            sn -= 1
            if not lead:
                continue
            # Same phone, website, name or e-mail as ANY saved lead (map or trademark) = duplicate
            sigs = [s for s in ((lead.phone or "").strip(), (lead.website or "").strip().lower(),
                                lead.business_name.strip().lower(), (lead.email or "").strip().lower()) if s]
            if any(s in exclude for s in sigs):
                continue
            exclude.update(sigs)
            lead.scan_id = job.id
            if not db.save_lead(lead):
                continue
            job.found += 1
            job.log(f"[{job.found}/{job.target}] {lead.business_name} - {lead.location} - \"{case['mark']}\" "
                    f"({case['filed']}){' - ' + lead.email if lead.email else ''}"[:170], "success")

        if job.state == "running":
            job.state = "done"
    except Exception as e:
        job.state, job.message = "error", f"{type(e).__name__}: {e}"
        job.log(f"Error: {job.message}", "warn")
    finally:
        await client.close()
        job.finished = time.time()
        db.record_scan(job.id, job.found)
        mins, secs = divmod(int(job.finished - job.started), 60)
        job.log(f"Finished ({job.state}): {job.found} new trademark leads from {job.looked_up} USPTO records "
                f"in {mins}m {secs}s. {job.message}".strip(), "success" if job.found else "warn")
