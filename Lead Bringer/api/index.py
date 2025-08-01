from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel
from typing import List, Optional
import datetime
import pytz
from dotenv import load_dotenv
import airtable
from fastapi.responses import JSONResponse
import logging
import traceback

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Lead Bringer CRM API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Airtable config
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
CALLS_TABLE = os.getenv("CALLS_TABLE", "Calls")
COMPANIES_TABLE = os.getenv("COMPANIES_TABLE", "Companies")
OFFERS_TABLE = os.getenv("OFFERS_TABLE", "Offers")
NO_CALL_TABLE = os.getenv("NO_CALL_TABLE", "No-Call List")

# Airtable client
at = airtable.Airtable(AIRTABLE_BASE_ID, AIRTABLE_API_KEY)

# Models
class CallLog(BaseModel):
    company_name: str
    contact_name: str
    notes: str
    follow_up_date: Optional[str] = None
    offer_made: Optional[str] = None

class Company(BaseModel):
    name: str
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

class FollowUp(BaseModel):
    id: str
    company_name: str
    contact_name: str
    follow_up_date: str
    notes: str

@app.get("/")
async def health_check():
    return {"status": "healthy", "message": "Lead Bringer CRM API is running"}

# 🔧 Updated /log-call with full traceback return
@app.post("/log-call")
async def log_call(call: CallLog):
    try:
        logger.info(f"Logging call for company: {call.company_name}")
        formula = f"LOWER({{Name}})=LOWER('{call.company_name}')"
        companies = at.get(COMPANIES_TABLE, filter_by_formula=formula)

        if not companies:
            company_data = {
                "Name": call.company_name,
                "Contact Name": call.contact_name
            }
            company = at.create(COMPANIES_TABLE, company_data)
            company_id = company["id"]
        else:
            company_id = companies[0]["id"]

        call_data = {
            "Company": [company_id],
            "Contact Name": call.contact_name,
            "Notes": call.notes
        }

        if call.follow_up_date:
            call_data["Follow-up Date"] = call.follow_up_date

        response = at.create(CALLS_TABLE, call_data)
        return {"success": True, "message": "Call logged successfully", "id": response["id"]}

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Full traceback:\n{tb}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Exception: {str(e)}", "trace": tb}
        )

@app.get("/follow-ups", response_model=List[FollowUp])
async def get_follow_ups():
    try:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        formula = f"AND(NOT({{Completed}}), {{Follow-up Date}}<='{today}')"
        calls = at.get(CALLS_TABLE, filter_by_formula=formula)

        results = []
        for call in calls:
            fields = call["fields"]
            company_name = ""
            if "Company" in fields and fields["Company"]:
                company = at.get(COMPANIES_TABLE, record_id=fields["Company"][0])
                if company:
                    company_name = company["fields"].get("Name", "")
            results.append(FollowUp(
                id=call["id"],
                company_name=company_name,
                contact_name=fields.get("Contact Name", ""),
                follow_up_date=fields.get("Follow-up Date", ""),
                notes=fields.get("Notes", "")
            ))
        return results

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Follow-up retrieval failed:\n{tb}")
        return []

@app.post("/complete-follow-up/{follow_up_id}")
async def complete_follow_up(follow_up_id: str):
    try:
        at.update(CALLS_TABLE, follow_up_id, {"Completed": True})
        return {"success": True, "message": "Follow-up marked as completed"}
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Complete follow-up failed:\n{tb}")
        return {"success": False, "message": f"Exception: {str(e)}"}

@app.get("/offers")
async def get_offers():
    try:
        offers = at.get(OFFERS_TABLE)
        return {"offers": [{"id": o["id"], "name": o["fields"].get("Name", "")} for o in offers]}
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Offers retrieval failed:\n{tb}")
        return {"offers": []}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(f"Global exception caught:\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": f"Unhandled error: {str(exc)}"}
    )
