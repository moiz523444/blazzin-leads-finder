import sqlite3
import json
import csv
import io
import threading
from typing import List, Dict, Any, Optional
from models import Lead

# Pure In-Memory SQLite Database (0 Bytes on Disk - No folder growth!)
_lock = threading.Lock()
_conn = sqlite3.connect(":memory:", check_same_thread=False)
_conn.row_factory = sqlite3.Row

def init_db():
    """Initializes in-memory tables. Stored purely in RAM."""
    with _lock:
        cursor = _conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            source TEXT NOT NULL,
            service_needed TEXT NOT NULL,
            website TEXT,
            has_website INTEGER DEFAULT 1,
            location TEXT,
            email TEXT,
            phone TEXT,
            whatsapp TEXT,
            contact_name TEXT,
            social_links TEXT,
            pain_points TEXT,
            intent_level TEXT,
            budget_estimate TEXT,
            audit_score INTEGER,
            audit_summary TEXT,
            ai_pitch TEXT,
            status TEXT DEFAULT 'new',
            created_at TEXT,
            UNIQUE(business_name, phone, website)
        )
        """)
        _conn.commit()

def save_lead(lead: Lead) -> Optional[int]:
    """Saves lead into RAM with deduplication."""
    with _lock:
        cursor = _conn.cursor()
        try:
            cursor.execute("""
            INSERT OR IGNORE INTO leads (
                business_name, source, service_needed, website, has_website,
                location, email, phone, whatsapp, contact_name, social_links,
                pain_points, intent_level, budget_estimate, audit_score,
                audit_summary, ai_pitch, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lead.business_name,
                lead.source,
                lead.service_needed,
                lead.website or "",
                1 if lead.has_website else 0,
                lead.location or "Global",
                lead.email or "",
                lead.phone or "",
                lead.whatsapp or "",
                lead.contact_name or "",
                json.dumps(lead.social_links or {}),
                json.dumps(lead.pain_points or []),
                lead.intent_level or "High",
                lead.budget_estimate or "Unknown",
                lead.audit_score if lead.audit_score is not None else 50,
                lead.audit_summary or "",
                lead.ai_pitch or "",
                lead.status or "new",
                lead.created_at
            ))
            _conn.commit()
            if cursor.rowcount == 0:
                row = _conn.execute(
                    "SELECT id FROM leads WHERE business_name = ? AND phone = ? AND website = ?",
                    (lead.business_name, lead.phone or "", lead.website or "")
                ).fetchone()
                return row["id"] if row else None
            return cursor.lastrowid
        except Exception as e:
            print(f"In-memory DB error: {e}")
            return None

def get_leads(source: Optional[str] = None, country: Optional[str] = None, service: Optional[str] = None, status: Optional[str] = None, search: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    """Retrieves leads from RAM with active filtering."""
    with _lock:
        cursor = _conn.cursor()
        query = "SELECT * FROM leads WHERE 1=1"
        params = []
        
        if source and source != "all":
            query += " AND source = ?"
            params.append(source)
        if country and country != "all":
            query += " AND (location LIKE ? OR location LIKE ?)"
            params.extend([f"%, {country}%", f"%{country}%"])
        if service and service != "all":
            query += " AND service_needed = ?"
            params.append(service)
        if status and status != "all":
            query += " AND status = ?"
            params.append(status)
        if search:
            query += " AND (business_name LIKE ? OR website LIKE ? OR location LIKE ? OR pain_points LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s, s])
            
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        leads = []
        for row in rows:
            item = dict(row)
            try:
                item["social_links"] = json.loads(item["social_links"]) if item["social_links"] else {}
            except Exception:
                item["social_links"] = {}
            try:
                item["pain_points"] = json.loads(item["pain_points"]) if item["pain_points"] else []
            except Exception:
                item["pain_points"] = []
            leads.append(item)
        return leads

def update_lead_status(lead_id: int, status: str):
    """Updates lead contact status in RAM."""
    with _lock:
        cursor = _conn.cursor()
        cursor.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
        _conn.commit()

def get_stats() -> Dict[str, Any]:
    """Calculates real-time stats directly from RAM."""
    with _lock:
        cursor = _conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM leads")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM leads WHERE intent_level IN ('High', 'Extreme')")
        high_intent = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM leads WHERE has_website = 0")
        no_website = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'contacted'")
        contacted = cursor.fetchone()[0]
        
        cursor.execute("SELECT source, COUNT(*) as count FROM leads GROUP BY source")
        source_counts = {row["source"]: row["count"] for row in cursor.fetchall()}
        
        cursor.execute("SELECT service_needed, COUNT(*) as count FROM leads GROUP BY service_needed")
        service_counts = {row["service_needed"]: row["count"] for row in cursor.fetchall()}

        return {
            "total_leads": total,
            "high_intent_leads": high_intent,
            "no_website_leads": no_website,
            "contacted_leads": contacted,
            "by_source": source_counts,
            "by_service": service_counts
        }

def export_leads_csv() -> str:
    """Streams CSV directly from RAM without touching disk."""
    leads = get_leads(limit=5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Business Name", "Source", "Service Needed", "Website", "Has Website",
        "Location", "Email", "Phone", "WhatsApp", "Pain Points", "Intent Level",
        "Budget Estimate", "Audit Score", "AI Pitch", "Status", "Created At"
    ])
    for l in leads:
        writer.writerow([
            l.get("id"),
            l.get("business_name"),
            l.get("source"),
            l.get("service_needed"),
            l.get("website"),
            "Yes" if l.get("has_website") else "No",
            l.get("location"),
            l.get("email"),
            l.get("phone"),
            l.get("whatsapp"),
            " | ".join(l.get("pain_points", [])),
            l.get("intent_level"),
            l.get("budget_estimate"),
            l.get("audit_score"),
            l.get("ai_pitch"),
            l.get("status"),
            l.get("created_at")
        ])
    return output.getvalue()

def clear_all_leads():
    """Wipes in-memory leads cleanly."""
    with _lock:
        cursor = _conn.cursor()
        cursor.execute("DELETE FROM leads")
        _conn.commit()
