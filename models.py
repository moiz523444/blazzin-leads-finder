from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone

class Lead(BaseModel):
    id: Optional[int] = None
    business_name: str
    source: str # 'local_verified', 'meta_ads', 'ecom_funnel', 'new_business', 'app_store', 'social_media'
    service_needed: str # 'web_development', 'website_redesign', 'mobile_apps', 'seo', 'social_media', 'ecommerce'
    category: Optional[str] = "" # business type, e.g. 'Dental clinic'
    website: Optional[str] = ""
    has_website: bool = True
    location: Optional[str] = "Global"
    country: Optional[str] = "" # 'US', 'UK', 'CA', 'UAE', 'QA'
    region: Optional[str] = "" # state / province / emirate
    email: Optional[str] = ""
    phone: Optional[str] = ""
    whatsapp: Optional[str] = ""
    contact_name: Optional[str] = ""
    social_links: Optional[Dict[str, str]] = {}
    pain_points: List[str] = []
    intent_level: str = "High" # 'High', 'Extreme', 'First-Mover'
    budget_estimate: Optional[str] = "Unknown"
    audit_score: Optional[int] = 50 # 0-100 (lower score = bigger opportunity for agency)
    audit_summary: Optional[str] = ""
    ai_pitch: Optional[str] = ""
    status: str = "new" # 'new', 'contacted', 'replied', 'closed'
    created_at: Optional[str] = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

class ScanRequest(BaseModel):
    sources: List[str] = ["local_verified"]
    services: List[str] = ["web_development", "mobile_apps", "seo", "social_media", "ecommerce"]
    niche: Optional[str] = "All Industries / Multi-Niche"
    country: Optional[str] = "ALL"
    region: Optional[str] = "all"
    limit: int = Field(default=40, ge=1, le=200)
    gemini_api_key: Optional[str] = ""

class StatusUpdate(BaseModel):
    status: Literal["new", "contacted", "replied", "closed"]
