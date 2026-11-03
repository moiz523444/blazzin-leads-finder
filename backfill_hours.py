"""
Adds local time zone + opening hours to leads saved before those fields existed.

    python backfill_hours.py            # all leads missing hours
    python backfill_hours.py --limit 300

Uses one TomTom request per lead (free key: 2,500 Search requests/MONTH, shared with scans), so only run it for small backlogs.
"""
import argparse
import asyncio
import re

import netfix
netfix.install()

import httpx

import config
import database as db
from harvester.local_business import hours_from_tomtom
from harvester.regions import timezone_for

_sem = asyncio.Semaphore(3)
_quota_hit = False  # TomTom said 403 (monthly allowance used up) - keep setting time zones, skip hours


async def place_hours(entity_id: str):
    """Returns (hours or None, ok). ok=False means the request failed and the lead should be retried later."""
    global _quota_hit
    params = {"entityId": entity_id, "key": config.TOMTOM_API_KEY, "openingHours": "nextSevenDays"}
    for attempt in range(4):
        if _quota_hit:
            return None, False
        async with _sem:
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    res = await client.get("https://api.tomtom.com/search/2/place.json", params=params)
            except Exception:
                res = None
            await asyncio.sleep(0.3)
        if res is not None and res.status_code == 200:
            results = res.json().get("results") or []
            return (hours_from_tomtom((results[0].get("poi") or {}).get("openingHours")) if results else None), True
        if res is not None and res.status_code == 403:
            if not _quota_hit:
                print("TomTom monthly allowance used up (403) - setting time zones only; run this again next month for hours.")
            _quota_hit = True
            return None, False
        await asyncio.sleep(1.5 * (attempt + 1))
    return None, False


async def main(limit: int):
    db.init_db()
    leads = [l for l in db.get_leads(limit=100000)
             if (not l.get("hours") and l.get("hours") != {}) or not l.get("timezone")]
    todo = leads[:limit] if limit else leads
    print(f"{len(leads)} leads missing hours; processing {len(todo)}")
    done = found = 0

    async def one(l):
        nonlocal done, found
        city = (l.get("location") or "").split(",")[0].strip()
        tz = timezone_for(l.get("country", ""), l.get("region", ""), city)
        if l.get("hours") or l.get("hours") == {}:  # hours already checked - only the time zone was missing
            db.set_timezone_and_hours(l["id"], tz, l["hours"] or None, hours_checked=True)
            done += 1
            return
        m = re.search(r"tomtom:([A-Za-z0-9_\-]+)", l.get("audit_summary") or "")
        hours, ok = (await place_hours(m.group(1))) if (m and config.TOMTOM_API_KEY) else (None, True)
        db.set_timezone_and_hours(l["id"], tz, hours, hours_checked=ok)
        done += 1
        found += bool(hours)
        if done % 50 == 0 or done == len(todo):
            print(f"  {done}/{len(todo)} done, {found} with opening hours")

    await asyncio.gather(*(one(l) for l in todo))
    print(f"Finished: {found}/{len(todo)} leads now have opening hours; all have a local time zone."
          + (" Hours for the rest: run again next month (TomTom monthly allowance)." if _quota_hit else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max leads to process (0 = all)")
    asyncio.run(main(ap.parse_args().limit))
