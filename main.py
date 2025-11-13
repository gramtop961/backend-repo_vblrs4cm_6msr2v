import os
import csv
import io
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------- Utility helpers ----------------------
from bson import ObjectId

def oid(val: str) -> ObjectId:
    try:
        return ObjectId(val)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")

def serialize(doc):
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # convert datetimes
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def render_template(template: str, data: dict) -> str:
    # simple placeholder replacement
    for key, value in {
        "First Name": data.get("first_name", ""),
        "Company Name": data.get("company_name", ""),
        "Job Title": data.get("job_title", ""),
        "Personalized Line": data.get("personalized_line", ""),
    }.items():
        template = template.replace(f"{{{{{key}}}}}", str(value or ""))
    return template


# ---------------------- Models ----------------------
class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None

class TemplateSet(BaseModel):
    campaign_id: str
    connection_template: str
    followup_template: str

class ProspectSearchRequest(BaseModel):
    job_title_query: str


# ---------------------- Basic routes ----------------------
@app.get("/")
def read_root():
    return {"message": "LinkedIn Lead Automation Backend running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


# ---------------------- Campaigns ----------------------
@app.post("/api/campaigns")
def create_campaign(payload: CampaignCreate):
    doc = {
        "name": payload.name,
        "description": payload.description,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    new_id = db["campaign"].insert_one(doc).inserted_id
    return {"id": str(new_id), "name": payload.name, "description": payload.description}


@app.get("/api/campaigns")
def list_campaigns():
    items = [serialize(x) for x in db["campaign"].find().sort("created_at", -1)]
    return items


# ---------------------- Companies upload (CSV) ----------------------
@app.post("/api/campaigns/{campaign_id}/companies/upload")
async def upload_companies(campaign_id: str, file: UploadFile = File(...)):
    if file.content_type not in ("text/csv", "application/vnd.ms-excel", "application/csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    count = 0
    for row in reader:
        company_name = row.get("Company Name") or row.get("company_name")
        linkedin_url = row.get("Company LinkedIn URL") or row.get("linkedin_url")
        if not company_name:
            continue
        db["company"].insert_one({
            "campaign_id": campaign_id,
            "company_name": company_name.strip(),
            "linkedin_url": (linkedin_url or "").strip(),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        count += 1
    return {"inserted": count}


@app.get("/api/campaigns/{campaign_id}/companies")
def list_companies(campaign_id: str):
    items = [serialize(x) for x in db["company"].find({"campaign_id": campaign_id}).sort("company_name", 1)]
    return items


# ---------------------- Templates ----------------------
@app.post("/api/templates")
def upsert_templates(payload: TemplateSet):
    db["template"].update_one(
        {"campaign_id": payload.campaign_id},
        {"$set": {
            "connection_template": payload.connection_template,
            "followup_template": payload.followup_template,
            "updated_at": datetime.now(timezone.utc)
        }, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    doc = db["template"].find_one({"campaign_id": payload.campaign_id})
    return serialize(doc)


@app.get("/api/templates/{campaign_id}")
def get_templates(campaign_id: str):
    doc = db["template"].find_one({"campaign_id": campaign_id})
    return serialize(doc) if doc else {}


# ---------------------- Prospect search (mock) ----------------------
@app.post("/api/campaigns/{campaign_id}/prospects/search")
def search_and_create_prospects(campaign_id: str, payload: ProspectSearchRequest):
    # NOTE: In production, this requires LinkedIn API or a compliant third-party service.
    # Here we mock by generating names per company.
    companies = list(db["company"].find({"campaign_id": campaign_id}))
    if not companies:
        raise HTTPException(status_code=400, detail="No companies found for this campaign")

    created = 0
    for c in companies:
        for i in range(2):  # create two prospects per company for demo
            first = random.choice(["Alex", "Jordan", "Taylor", "Casey", "Riley", "Drew", "Chris"]) \
                + random.choice(["", "-Lee", "-Ray"])[:0]
            last = random.choice(["Smith", "Johnson", "Lee", "Brown", "Davis", "Miller"]) \
                + random.choice(["", "-Jr"])[:0]
            db["prospect"].insert_one({
                "campaign_id": campaign_id,
                "company_name": c.get("company_name"),
                "first_name": first,
                "last_name": last,
                "job_title": payload.job_title_query,
                "profile_url": None,
                "personalized_line": None,
                "status": "pending",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "last_action_at": None,
            })
            created += 1
    return {"created": created}


@app.get("/api/campaigns/{campaign_id}/prospects")
def list_prospects(campaign_id: str):
    items = [serialize(x) for x in db["prospect"].find({"campaign_id": campaign_id}).sort("created_at", -1)]
    return items


# ---------------------- Stats ----------------------
@app.get("/api/campaigns/{campaign_id}/stats")
def campaign_stats(campaign_id: str):
    total = db["prospect"].count_documents({"campaign_id": campaign_id})
    requested = db["prospect"].count_documents({"campaign_id": campaign_id, "status": "requested"})
    followed = db["prospect"].count_documents({"campaign_id": campaign_id, "status": "followed_up"})
    accepted = db["prospect"].count_documents({"campaign_id": campaign_id, "status": "accepted"})
    replied = db["prospect"].count_documents({"campaign_id": campaign_id, "status": "replied"})
    pending = db["prospect"].count_documents({"campaign_id": campaign_id, "status": "pending"})
    return {
        "total": total,
        "requests_sent": requested,
        "followups_sent": followed,
        "connections_accepted": accepted,
        "replies_received": replied,
        "pending": pending,
    }


# ---------------------- Automation Engine (simulated) ----------------------
class AutomationStart(BaseModel):
    campaign_id: str


def process_automation(campaign_id: str):
    template = db["template"].find_one({"campaign_id": campaign_id})
    connection_tmpl = (template or {}).get("connection_template", "Hi {{First Name}}, would love to connect.")
    followup_tmpl = (template or {}).get("followup_template", "Following up on my request, {{First Name}}.")

    # Daily limits & randomization (simulation)
    daily_limit = random.randint(10, 20)
    processed = 0

    # 1) Send connection requests to pending prospects
    cursor = db["prospect"].find({"campaign_id": campaign_id, "status": "pending"}).limit(daily_limit)
    for p in cursor:
        if processed >= daily_limit:
            break
        # simulate human-like delay window (we just record it, not actually sleep)
        scheduled_at = datetime.now(timezone.utc) + timedelta(minutes=random.randint(2, 30))
        content = render_template(connection_tmpl, p)
        db["messagelog"].insert_one({
            "campaign_id": campaign_id,
            "prospect_id": str(p["_id"]),
            "type": "connection",
            "status": "sent",
            "scheduled_at": scheduled_at,
            "sent_at": datetime.now(timezone.utc),
            "content": content,
        })
        db["prospect"].update_one({"_id": p["_id"]}, {"$set": {"status": "requested", "last_action_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}})
        processed += 1

    # 2) Send follow-ups if 3+ days since request and not accepted
    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
    cursor = db["prospect"].find({
        "campaign_id": campaign_id,
        "status": "requested",
        "last_action_at": {"$lte": three_days_ago}
    }).limit(daily_limit)
    for p in cursor:
        scheduled_at = datetime.now(timezone.utc) + timedelta(minutes=random.randint(5, 45))
        content = render_template(followup_tmpl, p)
        db["messagelog"].insert_one({
            "campaign_id": campaign_id,
            "prospect_id": str(p["_id"]),
            "type": "followup",
            "status": "sent",
            "scheduled_at": scheduled_at,
            "sent_at": datetime.now(timezone.utc),
            "content": content,
        })
        db["prospect"].update_one({"_id": p["_id"]}, {"$set": {"status": "followed_up", "last_action_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}})


@app.post("/api/automation/start")
def start_automation(payload: AutomationStart, background_tasks: BackgroundTasks):
    # In production, this would enqueue scheduled jobs with randomized delays and enforce daily limits per user.
    background_tasks.add_task(process_automation, payload.campaign_id)
    return {"scheduled": True}


# ---------------------- Inbox (replies) ----------------------
@app.get("/api/inbox")
def inbox():
    # Only prospects that have status 'replied'
    items = [serialize(x) for x in db["prospect"].find({"status": "replied"}).sort("updated_at", -1)]
    return items


# ---------------------- Safety & Integration Notice ----------------------
@app.get("/api/notice")
def notice():
    return {
        "message": "This MVP simulates scheduling and logging only. Real LinkedIn messaging requires integration with the official LinkedIn API or a compliant third-party automation provider that respects LinkedIn's terms of service. The system includes randomized scheduling windows and daily limits for human-like behavior.",
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
