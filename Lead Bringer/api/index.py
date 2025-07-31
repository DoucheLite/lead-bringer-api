from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import datetime
import pytz
from dotenv import load_dotenv
import airtable
from fastapi.responses import JSONResponse

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Lead Bringer CRM API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Airtable configuration
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
CALLS_TABLE = os.getenv("CALLS_TABLE", "Calls")
COMPANIES_TABLE = os.getenv("COMPANIES_TABLE", "Companies")
OFFERS_TABLE = os.getenv("OFFERS_TABLE", "Offers")
NO_CALL_TABLE = os.getenv("NO_CALL_TABLE", "No-Call List")

# Connect to Airtable
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

# Health check endpoint
@app.get("/")
async def health_check():
    return {"status": "healthy", "message": "Lead Bringer CRM API is running"}

# Log a call
@app.post("/log-call")
async def log_call(call: CallLog):
    try:
        # Check if company exists
        companies = at.get(COMPANIES_TABLE, filter_by_formula=f"{{Name}}='{call.company_name}'")
        
        company_id = None
        # Create company if it doesn't exist
        if not companies:
            company_data = {
                "Name": call.company_name,
                "Contact Name": call.contact_name
            }
            company_response = at.create(COMPANIES_TABLE, company_data)
            company_id = company_response["id"]
        else:
            company_id = companies[0]["id"]
        
        # Prepare call data
        now = datetime.datetime.now(pytz.timezone('UTC'))
        call_data = {
            "Company": [company_id],
            "Contact Name": call.contact_name,
            "Notes": call.notes,
            "Call Date": now.strftime("%Y-%m-%d"),
            "Call Time": now.strftime("%H:%M:%S")
        }
        
        # Add follow-up date if provided
        if call.follow_up_date:
            call_data["Follow-up Date"] = call.follow_up_date
            
        # Add offer if provided
        if call.offer_made:
            offers = at.get(OFFERS_TABLE, filter_by_formula=f"{{Name}}='{call.offer_made}'")
            if offers:
                offer_id = offers[0]["id"]
                call_data["Offer"] = [offer_id]
        
        # Create call record
        response = at.create(CALLS_TABLE, call_data)
        
        return {"success": True, "message": "Call logged successfully", "id": response["id"]}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error logging call: {str(e)}")

# Get follow-ups
@app.get("/follow-ups", response_model=List[FollowUp])
async def get_follow_ups():
    try:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        # Get all follow-ups scheduled for today or earlier
        formula = f"AND(NOT({{Completed}}), {{Follow-up Date}}<='{today}')"
        calls = at.get(CALLS_TABLE, filter_by_formula=formula)
        
        follow_ups = []
        for call in calls:
            fields = call["fields"]
            # Get company name
            company_name = ""
            if "Company" in fields and fields["Company"]:
                company_id = fields["Company"][0]
                company = at.get(COMPANIES_TABLE, record_id=company_id)
                if company:
                    company_name = company["fields"].get("Name", "")
            
            follow_up = FollowUp(
                id=call["id"],
                company_name=company_name,
                contact_name=fields.get("Contact Name", ""),
                follow_up_date=fields.get("Follow-up Date", ""),
                notes=fields.get("Notes", "")
            )
            follow_ups.append(follow_up)
        
        return follow_ups
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving follow-ups: {str(e)}")

# Mark follow-up as completed
@app.post("/complete-follow-up/{follow_up_id}")
async def complete_follow_up(follow_up_id: str):
    try:
        # Update the follow-up record
        at.update(CALLS_TABLE, follow_up_id, {"Completed": True})
        return {"success": True, "message": "Follow-up marked as completed"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error completing follow-up: {str(e)}")

# Add company to no-call list
@app.post("/add-to-no-call")
async def add_to_no_call(company: Company):
    try:
        # Check if already in no-call list
        existing = at.get(NO_CALL_TABLE, filter_by_formula=f"{{Name}}='{company.name}'")
        if existing:
            return {"success": True, "message": "Company already in no-call list"}
        
        # Add to no-call list
        company_data = {
            "Name": company.name,
            "Contact Name": company.contact_name or "",
            "Phone": company.phone or "",
            "Email": company.email or "",
            "Website": company.website or "",
            "Date Added": datetime.datetime.now().strftime("%Y-%m-%d")
        }
        
        at.create(NO_CALL_TABLE, company_data)
        return {"success": True, "message": "Company added to no-call list"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding to no-call list: {str(e)}")

# Check if company is in no-call list
@app.get("/check-no-call/{company_name}")
async def check_no_call(company_name: str):
    try:
        companies = at.get(NO_CALL_TABLE, filter_by_formula=f"{{Name}}='{company_name}'")
        if companies:
            return {"in_no_call_list": True}
        return {"in_no_call_list": False}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking no-call list: {str(e)}")

# Get available offers
@app.get("/offers")
async def get_offers():
    try:
        offers = at.get(OFFERS_TABLE)
        return {"offers": [{"id": offer["id"], "name": offer["fields"].get("Name", "")} for offer in offers]}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving offers: {str(e)}")

# Error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": f"An unexpected error occurred: {str(exc)}"}
    )