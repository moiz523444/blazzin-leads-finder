import app
import models
import database
import asyncio
from harvester.meta_ads import harvest_meta_ads
from harvester.job_intent import harvest_job_intent
from harvester.new_companies import harvest_new_companies
from harvester.app_store import harvest_app_store
from enricher.ai_pitcher import generate_pitch

async def main():
    database.init_db()
    print("Database initialized successfully.")
    
    # Test Meta Ads harvester
    meta_leads = await harvest_meta_ads(niche="dental", limit=2)
    print(f"Meta Ads Harvester: {len(meta_leads)} leads generated.")
    for l in meta_leads:
        l.ai_pitch = await generate_pitch(l)
        database.save_lead(l)
        print(f" - [{l.source}] {l.business_name} | {l.service_needed} | {l.email}")

    # Test Job Intent harvester
    job_leads = await harvest_job_intent(niche="web", limit=2)
    print(f"Job Intent Harvester: {len(job_leads)} leads generated.")
    for l in job_leads:
        l.ai_pitch = await generate_pitch(l)
        database.save_lead(l)
        print(f" - [{l.source}] {l.business_name} | Budget: {l.budget_estimate}")

    # Test New Companies harvester
    biz_leads = await harvest_new_companies(niche="clinic", limit=2)
    print(f"New Companies Harvester: {len(biz_leads)} leads generated.")
    for l in biz_leads:
        l.ai_pitch = await generate_pitch(l)
        database.save_lead(l)
        print(f" - [{l.source}] {l.business_name} | {l.location}")

    stats = database.get_stats()
    print(f"Stats check: {stats}")

if __name__ == "__main__":
    asyncio.run(main())
