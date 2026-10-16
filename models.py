from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class Lead(BaseModel):
    id: Optional[int] = None
    business_name: str
    source: str # 'meta_ads', 'job_intent', 'new_business', 'app_store'
    service_needed: str # 'web_development', 'mobile_apps', 'seo', 'social_media', 'ecommerce'
    website: Optional[str] = ""
    has_website: bool = True
    location: Optional[str] = "Global"
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
    created_at: Optional[str] = Field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

class ScanRequest(BaseModel):
    sources: List[str] = ["new_business", "meta_ads", "job_intent", "app_store"]
    services: List[str] = ["web_development", "mobile_apps", "seo", "social_media", "ecommerce"]
    niche: Optional[str] = "All Industries / Multi-Niche"
    country: Optional[str] = "ALL"
    limit: int = 50
    gemini_api_key: Optional[str] = ""
