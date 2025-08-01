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
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Log a call - simplified for maximum reliability
@app.post("/log-call")
async def log_call(call: CallLog):
    try:
        logger.info(f"Logging call for company: {call.company_name}")
        
        # Check if company exists
        company_formula = f"LOWER({{Name}})=LOWER('{call.company_name}')"
        logger.info(f"Searching for company with formula: {company_formula}")
        companies = at.get(COMPANIES_TABLE, filter_by_formula=company_formula)
        
        company_id = None
        # Create company if it doesn't exist
        if not companies:
            logger.info(f"Company not found, creating new: {call.company_name}")
            company_data = {
                "Name": call.company_name,
                "Contact Name": call.contact_name
            }
            company_response = at.create(COMPANIES_TABLE, company_data)
            company_id = company_response["id"]
            logger.info(f"Created company with ID: {company_id}")
        else:
            company_id = companies[0]["id"]
            logger.info(f"Found existing company with ID: {company_id}")
        
        # Prepare minimal call data to ensure success
        call_data = {
            "Company": [company_id],
            "Contact Name": call.contact_name,
            "Notes": call.notes
        }
        
        # Add follow-up date if provided
        if call.follow_up_date:
            logger.info(f"Adding follow-up date: {call.follow_up_date}")
            call_data["Follow-up Date"] = call.follow_up_date
        
        # Create call record with minimal required fields
        logger.info(f"Creating call record with data: {call_data}")
        response = at.create(CALLS_TABLE, call_data)
        logger.info(f"Call record created successfully with ID: {response['id']}")
        
        return {"success": True, "message": "Call logged successfully", "id": response["id"]}
    
    except Exception as e:
        logger.error(f"Error logging call: {str(e)}", exc_info=True)
        return {"success": False, "message": f"Error details: {str(e)}"}

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
        logger.error(f"Error retrieving follow-ups: {str(e)}", exc_info=True)
        return []

# Mark follow-up as completed
@app.post("/complete-follow-up/{follow_up_id}")
async def complete_follow_up(follow_up_id: str):
    try:
        # Update the follow-up record
        at.update(CALLS_TABLE, follow_up_id, {"Completed": True})
        return {"success": True, "message": "Follow-up marked as completed"}
    
    except Exception as e:
        logger.error(f"Error completing follow-up: {str(e)}", exc_info=True)
        return {"success": False, "message": f"Error details: {str(e)}"}

# Get available offers
@app.get("/offers")
async def get_offers():
    try:
        offers = at.get(OFFERS_TABLE)
        return {"offers": [{"id": offer["id"], "name": offer["fields"].get("Name", "")} for offer in offers]}
    
    except Exception as e:
        logger.error(f"Error retrieving offers: {str(e)}", exc_info=True)
        return {"offers": []}

# Error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": f"An unexpected error occurred: {str(exc)}"}
    )
