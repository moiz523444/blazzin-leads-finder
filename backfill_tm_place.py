"""
Adds "Place of organization/citizenship" to trademark leads saved before that field existed.

    python backfill_tm_place.py

Re-reads each lead's USPTO record once (one request every 2 seconds without USPTO_API_KEY),
so ~370 leads take about 12-13 minutes. Don't run it while a trademark scan is running - both share USPTO's limit.
"""
import asyncio

import netfix
netfix.install()

from bs4 import BeautifulSoup

import database as db
from harvester import trademark as tm


async def main():
    db.init_db()
    todo = [l for l in db.get_leads(source="trademark", limit=100000) if l.get("serial") and not l.get("organized_in")]
    print(f"{len(todo)} trademark leads missing place of organization/citizenship")
    client = tm.TsdrClient()
    filled = 0
    try:
        for i, l in enumerate(todo, 1):
            outcome, html = await client.fetch(int(l["serial"]))
            if outcome == tm.FOUND:
                soup = BeautifulSoup(html, "html.parser")
                place = tm._value(soup, "State or Country Where Organized") or tm._value(soup, "Citizenship")
                if place:
                    db.set_organized_in(l["serial"], place[:80])
                    filled += 1
            if i % 25 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} done, {filled} filled")
    finally:
        await client.close()
    print(f"Finished: {filled}/{len(todo)} leads now have place of organization/citizenship.")


if __name__ == "__main__":
    asyncio.run(main())
