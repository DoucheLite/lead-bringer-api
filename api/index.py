from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import datetime
import os
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import json
import base64
from fastapi.responses import JSONResponse
import uuid

# Load environment variables
load_dotenv()

# Configuration
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE")
SPREADSHEET_NAME = os.getenv("Lead_Bringer_CRM", "Lead Bringer CRM")
API_KEY = os.getenv("API_KEY")

# Initialize FastAPI app
app = FastAPI(title="Lead Bringer CRM API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# Connect to Google Sheets
def get_sheets_client():
    try:
        # Decode the base64 credentials
        credentials_json = base64.b64decode(GOOGLE_CREDENTIALS_FILE).decode('utf-8')
        credentials_dict = json.loads(credentials_json)
        
        # Create credentials from the json
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]
        credentials = Credentials.from_service_account_info(
            credentials_dict, scopes=scopes
        )
        return gspread.authorize(credentials)
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        raise HTTPException(status_code=500, detail=f"Error connecting to Google Sheets: {str(e)}")

# Helper functions
def find_company_row(sheet, company_name):
    try:
        # Get all company names
        companies = sheet.col_values(1)[1:]  # Skip header row
        for i, name in enumerate(companies, start=2):  # Start from row 2 (after header)
            if name.lower() == company_name.lower():
                return i
        return None
    except Exception as e:
        print(f"Error finding company: {e}")
        return None

def get_company_data(sheet, row):
    if not row:
        return None
    
    try:
        data = sheet.row_values(row)
        # If we don't have enough columns, pad with empty strings
        data.extend([''] * (11 - len(data)))
        
        return {
            "name": data[0],
            "location": data[1],
            "contact_name": data[2],
            "phone": data[3],
            "email": data[4],
            "products": data[5],
            "notes": data[6],
            "state": data[7],
            "quality": data[8],
            "no_call": data[9].upper() == "TRUE" if data[9] else False,
            "created_at": data[10]
        }
    except Exception as e:
        print(f"Error getting company data: {e}")
        return None

def get_calls_for_company(sheet, company_name):
    try:
        # Get all calls
        all_calls = sheet.get_all_records()
        # Filter calls for this company
        company_calls = []
        for call in all_calls:
            if call.get("Company Name", "").lower() == company_name.lower():
                company_calls.append({
                    "id": call.get("ID", str(uuid.uuid4())),
                    "company_name": call.get("Company Name", ""),
                    "contact_name": call.get("Contact Name", ""),
                    "date": call.get("Date", ""),
                    "time": call.get("Time", ""),
                    "notes": call.get("Notes", ""),
                    "outcome": call.get("Outcome", ""),
                    "next_steps": call.get("Next Steps", ""),
                    "follow_up_date": call.get("Follow-up Date", ""),
                    "completed": call.get("Completed", "").upper() == "TRUE"
                })
        return company_calls
    except Exception as e:
        print(f"Error getting calls for company: {e}")
        return []

# API Key Authentication
def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return x_api_key

# Health check endpoint
@app.get("/")
async def health_check():
    return {"status": "healthy", "message": "Lead Bringer CRM API is running with Google Sheets"}

# Log a call
@app.post("/log-call", dependencies=[Depends(verify_api_key)])
async def log_call(call: CallLog):
    try:
        # Connect to Google Sheets
        client = get_sheets_client()
        spreadsheet = client.open(SPREADSHEET_NAME)
        
        # Access Companies sheet
        companies_sheet = spreadsheet.worksheet("Companies")
        
        # Check if company exists
        company_row = find_company_row(companies_sheet, call.company_name)
        
        # Create company if it doesn't exist
        if not company_row:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            companies_sheet.append_row([
                call.company_name,  # Name
                "",                 # Location
                call.contact_name,  # Contact Name
                "",                 # Phone
                "",                 # Email
                "",                 # Products
                "",                 # Company Notes
                "",                 # State
                "",                 # Quality
                "FALSE",            # No-Call
                now                 # Created At
            ])
        
        # Access Calls sheet
        calls_sheet = spreadsheet.worksheet("Calls")
        
        # Generate a unique ID
        call_id = str(uuid.uuid4())
        
        # Get current date and time
        now = datetime.datetime.now()
        date = now.strftime("%Y-%m-%d")
        time = now.strftime("%H:%M:%S")
        
        # Prepare call data
        call_data = [
            call_id,            # ID
            call.company_name,  # Company Name
            call.contact_name,  # Contact Name
            date,               # Date
            time,               # Time
            call.notes,         # Notes
            "",                 # Outcome
            "",                 # Next Steps
            call.follow_up_date or "", # Follow-up Date
            "FALSE"             # Completed
        ]
        
        # Add call record
        calls_sheet.append_row(call_data)
        
        return {"success": True, "message": "Call logged successfully", "id": call_id}
    
    except Exception as e:
        print(f"Error logging call: {e}")
        return {"success": False, "message": f"Error logging call: {str(e)}"}

# Get company history
@app.get("/get-company-history", dependencies=[Depends(verify_api_key)])
async def get_company_history(company_name: str):
    try:
        # Connect to Google Sheets
        client = get_sheets_client()
        spreadsheet = client.open(SPREADSHEET_NAME)
        
        # Access Companies sheet
        companies_sheet = spreadsheet.worksheet("Companies")
        
        # Check if company exists
        company_row = find_company_row(companies_sheet, company_name)
        if not company_row:
            return {"success": False, "message": "Company not found"}
        
        # Get company data
        company_data = get_company_data(companies_sheet, company_row)
        
        # Access Calls sheet
        calls_sheet = spreadsheet.worksheet("Calls")
        
        # Get calls for this company
        calls = get_calls_for_company(calls_sheet, company_name)
        
        return {
            "success": True,
            "company": company_data,
            "calls": calls
        }
    
    except Exception as e:
        print(f"Error getting company history: {e}")
        return {"success": False, "message": f"Error getting company history: {str(e)}"}

# Search calls
@app.get("/search-calls", dependencies=[Depends(verify_api_key)])
async def search_calls(keyword: str, company_name: Optional[str] = None):
    try:
        # Connect to Google Sheets
        client = get_sheets_client()
        spreadsheet = client.open(SPREADSHEET_NAME)
        
        # Access Calls sheet
        calls_sheet = spreadsheet.worksheet("Calls")
        
        # Get all calls
        all_calls = calls_sheet.get_all_records()
        
        # Filter calls based on keyword and optional company name
        matching_calls = []
        for call in all_calls:
            # Check if notes contain the keyword (case insensitive)
            notes = call.get("Notes", "").lower()
            
            if keyword.lower() in notes:
                # If company_name is provided, filter by it
                if company_name and call.get("Company Name", "").lower() != company_name.lower():
                    continue
                
                # Add to matching calls
                matching_calls.append({
                    "id": call.get("ID", str(uuid.uuid4())),
                    "company_name": call.get("Company Name", ""),
                    "contact_name": call.get("Contact Name", ""),
                    "date": call.get("Date", ""),
                    "time": call.get("Time", ""),
                    "notes": call.get("Notes", ""),
                    "outcome": call.get("Outcome", ""),
                    "next_steps": call.get("Next Steps", ""),
                    "follow_up_date": call.get("Follow-up Date", ""),
                    "completed": call.get("Completed", "").upper() == "TRUE"
                })
        
        return {
            "success": True,
            "matches": len(matching_calls),
            "calls": matching_calls
        }
    
    except Exception as e:
        print(f"Error searching calls: {e}")
        return {"success": False, "message": f"Error searching calls: {str(e)}"}

# Get follow-ups
@app.get("/get-follow-ups", dependencies=[Depends(verify_api_key)])
async def get_follow_ups():
    try:
        # Connect to Google Sheets
        client = get_sheets_client()
        spreadsheet = client.open(SPREADSHEET_NAME)
        
        # Access Calls sheet
        calls_sheet = spreadsheet.worksheet("Calls")
        
        # Get all calls
        all_calls = calls_sheet.get_all_records()
        
        # Get today's date
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Filter for follow-ups
        follow_ups = []
        for call in all_calls:
            follow_up_date = call.get("Follow-up Date", "")
            completed = call.get("Completed", "").upper() == "TRUE"
            
            # Check if there's a follow-up date and it's not completed
            if follow_up_date and not completed:
                # Only include if follow-up date is today or earlier
                if follow_up_date <= today:
                    follow_ups.append({
                        "id": call.get("ID", str(uuid.uuid4())),
                        "company_name": call.get("Company Name", ""),
                        "contact_name": call.get("Contact Name", ""),
                        "date": call.get("Date", ""),
                        "time": call.get("Time", ""),
                        "notes": call.get("Notes", ""),
                        "outcome": call.get("Outcome", ""),
                        "next_steps": call.get("Next Steps", ""),
                        "follow_up_date": follow_up_date,
                        "completed": completed
                    })
        
        # Sort by follow-up date (ascending)
        follow_ups.sort(key=lambda x: x["follow_up_date"])
        
        return {
            "success": True,
            "count": len(follow_ups),
            "follow_ups": follow_ups
        }
    
    except Exception as e:
        print(f"Error getting follow-ups: {e}")
        return {"success": False, "message": f"Error getting follow-ups: {str(e)}"}

# Error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": f"An unexpected error occurred: {str(exc)}"}
    )