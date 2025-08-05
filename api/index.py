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
import socket

# Load environment variables
load_dotenv()

# Configuration  (keep these four – nothing else)
GOOGLE_CREDENTIALS_B64 = os.getenv("GOOGLE_CREDENTIALS_B64")   # base-64 creds
SPREADSHEET_ID        = os.getenv("SPREADSHEET_ID")            # long sheet ID
SPREADSHEET_NAME      = "Lead Bringer CRM"                     # friendly name
API_KEY               = os.getenv("API_KEY")                   # header auth

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
        credentials_json = base64.b64decode(GOOGLE_CREDENTIALS_B64).decode('utf-8')
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
                    "follow_up_date": call.get("Follow-Up Date", "")
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

# Simple test endpoint - no Google Sheets access required
@app.get("/test")
async def test_endpoint():
    """Simple test endpoint that doesn't require Google Sheets."""
    return {"status": "ok", "message": "Test endpoint works!"}

# Sheets ping test endpoint
@app.get("/sheets-ping")
async def sheets_ping():
    """Quick smoke-test: writes a timestamp row to Calls sheet."""
    try:
        # Connect to Google Sheets
        client = get_sheets_client()
        spreadsheet = open_workbook()
        
        # Access Calls sheet
        calls_sheet = spreadsheet.worksheet("Calls")
        
        # Generate a timestamp
        now = datetime.datetime.now().isoformat(timespec="seconds")
        
        # Create a simple row with timestamp in the ID column and note in Notes column
        # Modified to match your actual sheet structure (9 columns, not 10)
        row = [
            now,                # ID/Name
            "Test Ping",        # Company Name
            "",                 # Contact Name
            datetime.datetime.now().strftime("%Y-%m-%d"),  # Date
            datetime.datetime.now().strftime("%H:%M:%S"),  # Time
            "sheets-ping test", # Notes
            "",                 # Outcome
            "",                 # Next Steps
            ""                  # Follow-Up Date
        ]
        
        # Add row to Calls sheet
        calls_sheet.append_row(row)
        
        return {"status": "wrote row", "timestamp": now}
    except Exception as e:
        error_message = str(e)
        print(f"Sheets ping failed: {error_message}")
        return {"success": False, "message": f"Sheets ping failed: {error_message}"}

# List all API routes - useful for debugging
@app.get("/routes")
async def list_routes():
    """List all registered API routes."""
    routes = []
    for route in app.routes:
        routes.append({
            "path": route.path,
            "name": route.name,
            "methods": list(route.methods) if route.methods else []
        })
    return {"routes": routes}

# ---- NEW DEBUGGING ENDPOINTS ----

@app.get("/check-credentials")
async def check_credentials():
    """Check if credentials can be decoded."""
    try:
        # Just try to decode the credentials
        credentials_json = base64.b64decode(GOOGLE_CREDENTIALS_B64).decode('utf-8')
        credentials_dict = json.loads(credentials_json)
        
        # Return a sanitized version without the private key
        safe_creds = {k: v for k, v in credentials_dict.items() if k != 'private_key'}
        return {
            "success": True,
            "client_email": credentials_dict.get("client_email", "Not found"),
            "project_id": credentials_dict.get("project_id", "Not found"),
            "credentials_details": safe_creds
        }
    except Exception as e:
        return {"success": False, "message": f"Error checking credentials: {str(e)}"}

@app.get("/simple-sheets-test")
async def simple_sheets_test():
    """Try a very basic Google Sheets API connection without opening a specific sheet."""
    try:
        # Just try to authenticate
        credentials_json = base64.b64decode(GOOGLE_CREDENTIALS_B64).decode('utf-8')
        credentials_dict = json.loads(credentials_json)
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]
        credentials = Credentials.from_service_account_info(
            credentials_dict, scopes=scopes
        )
        
        # Create the client but don't do anything with it yet
        client = gspread.authorize(credentials)
        
        # Just list available spreadsheets to test the connection
        try:
            available_sheets = [sheet.title for sheet in client.openall()]
            return {
                "success": True,
                "message": "Successfully connected to Google Sheets API",
                "available_sheets": available_sheets
            }
        except Exception as sheet_error:
            return {
                "success": False,
                "message": "Authentication successful but error listing sheets",
                "error": str(sheet_error)
            }
    except Exception as e:
        return {"success": False, "message": f"Simple sheets test failed: {str(e)}"}

@app.get("/network-test")
async def network_test():
    """Test basic internet connectivity."""
    hosts_to_check = [
        ("sheets.googleapis.com", 443),
        ("www.googleapis.com", 443),
        ("accounts.google.com", 443)
    ]
    
    results = {}
    
    for host, port in hosts_to_check:
        try:
            # Try to create a socket connection
            sock = socket.create_connection((host, port), timeout=5)
            sock.close()
            results[host] = "Success"
        except Exception as e:
            results[host] = f"Failed: {str(e)}"
    
    return {"success": True, "connectivity_tests": results}

@app.get("/sheets-debug")
async def sheets_debug():
    """Detailed debugging of Google Sheets connection."""
    try:
        # Connect to Google Sheets
        print("Attempting to get sheets client...")
        client = get_sheets_client()
        print("Got sheets client successfully!")
        
        print(f"Opening spreadsheet: {SPREADSHEET_NAME}")
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        print(f"Opened spreadsheet!")
        
        # List all worksheets
        worksheets = spreadsheet.worksheets()
        worksheet_names = [ws.title for ws in worksheets]
        print(f"Available worksheets: {worksheet_names}")
        
        # Try to access the Calls sheet
        print(f"Trying to access 'Calls' worksheet...")
        try:
            calls_sheet = spreadsheet.worksheet("Calls")
            print("Successfully accessed 'Calls' worksheet")
            
            # Get the header row
            headers = calls_sheet.row_values(1)
            print(f"Headers in 'Calls' sheet: {headers}")
            
            return {
                "success": True,
                "spreadsheet_name": SPREADSHEET_NAME,
                "worksheets": worksheet_names,
                "calls_headers": headers
            }
        except Exception as e:
            print(f"Error accessing 'Calls' worksheet: {str(e)}")
            return {
                "success": False,
                "spreadsheet_name": SPREADSHEET_NAME,
                "worksheets": worksheet_names,
                "error": f"Error accessing 'Calls' worksheet: {str(e)}"
            }
        
    except Exception as e:
        error_message = str(e)
        print(f"Sheets debug failed: {error_message}")
        return {"success": False, "message": f"Sheets debug failed: {error_message}"}

# ---- END OF NEW DEBUGGING ENDPOINTS ----

# Log a call
@app.post("/log-call", dependencies=[Depends(verify_api_key)])
async def log_call(call: CallLog):
    try:
        # Connect to Google Sheets
        client = get_sheets_client()
        spreadsheet = open_workbook()
        
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
            call.follow_up_date or "" # Follow-up Date
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
        spreadsheet = open_workbook()
        
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
        spreadsheet = open_workbook()
        
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
                    "follow_up_date": call.get("Follow-Up Date", "")
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
        spreadsheet = open_workbook()
        
        # Access Calls sheet
        calls_sheet = spreadsheet.worksheet("Calls")
        
        # Get all calls
        all_calls = calls_sheet.get_all_records()
        
        # Get today's date
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Filter for follow-ups
        follow_ups = []
        for call in all_calls:
            follow_up_date = call.get("Follow-Up Date", "")
            
            # Check if there's a follow-up date
            if follow_up_date:
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
                        "follow_up_date": follow_up_date
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

# Monkey-patch to use sheets_adapter
from . import sheets_adapter      # ← relative import from the same folder
get_sheets_client = sheets_adapter.get_sheets_client
open_workbook = sheets_adapter.open_workbook

from fastapi.routing import APIRoute

@app.get("/list-routes")
async def list_routes():
    routes = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes.append({
                "path": route.path,
                "methods": list(route.methods),
                "name": route.name
            })
    return {"routes": routes}
