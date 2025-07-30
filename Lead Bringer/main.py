from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date, datetime
from enum import Enum
import os
import httpx
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
AIRTABLE_API_TOKEN = os.getenv("AIRTABLE_API_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_COMPANIES_TABLE_ID = os.getenv("AIRTABLE_COMPANIES_TABLE_ID", "Company")
AIRTABLE_CALLS_TABLE_ID = os.getenv("AIRTABLE_CALLS_TABLE_ID", "Calls")
AIRTABLE_NO_CALL_TABLE_ID = os.getenv("AIRTABLE_NO_CALL_TABLE_ID", "No-Call")

if not AIRTABLE_API_TOKEN or not AIRTABLE_BASE_ID:
    raise ValueError("AIRTABLE_API_TOKEN and AIRTABLE_BASE_ID environment variables must be set")

# Airtable API configuration
AIRTABLE_BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_TOKEN}",
    "Content-Type": "application/json"
}

# Initialize FastAPI app
app = FastAPI(
    title="Lead Bringer API",
    description="Professional B2B outbound sales CRM API",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this to your specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enums for validation
class CallOutcome(str, Enum):
    NOT_A_FIT = "Not a Fit"
    PASSIVE_INTEREST = "Passive Interest"
    ACTIVE_INTEREST = "Active Interest"

class CompanyState(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    PAUSED = "paused"

class CompanyQuality(str, Enum):
    RED = "Red"
    YELLOW = "Yellow"
    GREEN = "Green"

class TimeOfDay(str, Enum):
    MORNING = "Morning"
    NOON = "Noon"
    NIGHT = "Night"

class CallMood(str, Enum):
    POSITIVE = "Positive"
    NEUTRAL = "Neutral"
    NEGATIVE = "Negative"

# Pydantic models
class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    location: Optional[str] = None
    phone: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = None
    products: Optional[str] = None
    company_notes: Optional[str] = None
    state: Optional[CompanyState] = None
    quality: Optional[CompanyQuality] = None
    source: Optional[str] = None

class CompanyResponse(CompanyCreate):
    id: str
    created_time: str

class CallCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    company_name: str = Field(..., min_length=1, description="Company name to link to")
    date: date
    am_pm: Optional[TimeOfDay] = None
    call_notes: Optional[str] = None
    outcome: CallOutcome
    next_steps: Optional[str] = None
    follow_up_date: Optional[date] = None
    spidey_sense: Optional[bool] = None
    spidey_rationale: Optional[str] = None
    mood: Optional[CallMood] = None
    lead_bringer_learnings: Optional[str] = None

    @validator('follow_up_date')
    def follow_up_date_must_be_future(cls, v, values):
        if v and v <= values.get('date'):
            raise ValueError('Follow up date must be after call date')
        return v

class CallResponse(BaseModel):
    id: str
    name: str
    company_id: str
    company_name: str
    date: str
    am_pm: Optional[str]
    call_notes: Optional[str]
    outcome: str
    next_steps: Optional[str]
    follow_up_date: Optional[str]
    spidey_sense: Optional[bool]
    spidey_rationale: Optional[str]
    mood: Optional[str]
    lead_bringer_learnings: Optional[str]
    created_time: str

class NoCallCreate(BaseModel):
    company_name: str = Field(..., min_length=1)
    phone: Optional[str] = None
    email_domain: Optional[str] = None
    reason: str = Field(..., min_length=1)
    state: Optional[str] = None

# Utility functions
async def find_company_by_name(company_name: str) -> Optional[dict]:
    """Find a company by name in Airtable"""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{AIRTABLE_BASE_URL}/{AIRTABLE_COMPANIES_TABLE_ID}"
            params = {
                "filterByFormula": f"LOWER({{Name}}) = LOWER('{company_name}')"
            }
            response = await client.get(url, headers=HEADERS, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get("records"):
                return data["records"][0]
            return None
    except Exception as e:
        logger.error(f"Error finding company {company_name}: {str(e)}")
        return None

async def create_company_in_airtable(company_data: dict) -> dict:
    """Create a new company in Airtable"""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{AIRTABLE_BASE_URL}/{AIRTABLE_COMPANIES_TABLE_ID}"
            payload = {"records": [{"fields": company_data}]}
            response = await client.post(url, headers=HEADERS, json=payload)
            response.raise_for_status()
            
            data = response.json()
            return data["records"][0]
    except Exception as e:
        logger.error(f"Error creating company: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create company: {str(e)}"
        )

# API Routes
@app.get("/")
async def root():
    return {
        "message": "Lead Bringer API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "companies": "/companies",
            "calls": "/calls",
            "no-call": "/no-call",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test Airtable connection
        async with httpx.AsyncClient() as client:
            url = f"{AIRTABLE_BASE_URL}/{AIRTABLE_COMPANIES_TABLE_ID}"
            params = {"maxRecords": 1}
            response = await client.get(url, headers=HEADERS, params=params)
            response.raise_for_status()
        
        return {"status": "healthy", "airtable": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy - Airtable connection failed"
        )

@app.post("/companies", response_model=CompanyResponse)
async def create_company(company: CompanyCreate):
    """Create a new company"""
    # Check if company already exists
    existing_company = await find_company_by_name(company.name)
    if existing_company:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Company '{company.name}' already exists"
        )
    
    # Prepare company data for Airtable
    company_data = {
        "Name": company.name,
        "Location": company.location,
        "Phone": company.phone,
        "Contact Name": company.contact_name,
        "Email": company.email,
        "Products": company.products,
        "Company Notes": company.company_notes,
        "State": company.state.value if company.state else None,
        "Quality": company.quality.value if company.quality else None,
        "Source": company.source
    }
    
    # Remove None values
    company_data = {k: v for k, v in company_data.items() if v is not None}
    
    # Create company in Airtable
    created_company = await create_company_in_airtable(company_data)
    
    return CompanyResponse(
        id=created_company["id"],
        name=created_company["fields"]["Name"],
        location=created_company["fields"].get("Location"),
        phone=created_company["fields"].get("Phone"),
        contact_name=created_company["fields"].get("Contact Name"),
        email=created_company["fields"].get("Email"),
        products=created_company["fields"].get("Products"),
        company_notes=created_company["fields"].get("Company Notes"),
        state=created_company["fields"].get("State"),
        quality=created_company["fields"].get("Quality"),
        source=created_company["fields"].get("Source"),
        created_time=created_company["createdTime"]
    )

@app.get("/companies", response_model=List[CompanyResponse])
async def get_companies(limit: int = 100):
    """Get all companies"""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{AIRTABLE_BASE_URL}/{AIRTABLE_COMPANIES_TABLE_ID}"
            params = {"maxRecords": min(limit, 100)}
            response = await client.get(url, headers=HEADERS, params=params)
            response.raise_for_status()
            
            data = response.json()
            companies = []
            
            for record in data.get("records", []):
                fields = record["fields"]
                companies.append(CompanyResponse(
                    id=record["id"],
                    name=fields.get("Name", ""),
                    location=fields.get("Location"),
                    phone=fields.get("Phone"),
                    contact_name=fields.get("Contact Name"),
                    email=fields.get("Email"),
                    products=fields.get("Products"),
                    company_notes=fields.get("Company Notes"),
                    state=fields.get("State"),
                    quality=fields.get("Quality"),
                    source=fields.get("Source"),
                    created_time=record["createdTime"]
                ))
            
            return companies
    except Exception as e:
        logger.error(f"Error fetching companies: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch companies: {str(e)}"
        )

@app.post("/calls", response_model=CallResponse)
async def create_call(call: CallCreate):
    """Create a new call record"""
    # Find or create company
    company = await find_company_by_name(call.company_name)
    
    if not company:
        # Create company automatically
        company_data = {"Name": call.company_name}
        company = await create_company_in_airtable(company_data)
    
    # Prepare call data for Airtable
    call_data = {
        "Name": call.name,
        "Lead": [company["id"]],  # Link to company
        "Date": call.date.isoformat(),
        "AM/PM": call.am_pm.value if call.am_pm else None,
        "Call Notes": call.call_notes,
        "Outcome": call.outcome.value,
        "Next Steps": call.next_steps,
        "Follow Up Date": call.follow_up_date.isoformat() if call.follow_up_date else None,
        "Spidey Sense": call.spidey_sense,
        "Spidey Rationale": call.spidey_rationale,
        "Mood": call.mood.value if call.mood else None,
        "Lead Bringer Learnings": call.lead_bringer_learnings
    }
    
    # Remove None values
    call_data = {k: v for k, v in call_data.items() if v is not None}
    
    try:
        async with httpx.AsyncClient() as client:
            url = f"{AIRTABLE_BASE_URL}/{AIRTABLE_CALLS_TABLE_ID}"
            payload = {"records": [{"fields": call_data}]}
            response = await client.post(url, headers=HEADERS, json=payload)
            response.raise_for_status()
            
            data = response.json()
            created_call = data["records"][0]
            fields = created_call["fields"]
            
            return CallResponse(
                id=created_call["id"],
                name=fields["Name"],
                company_id=company["id"],
                company_name=call.company_name,
                date=fields["Date"],
                am_pm=fields.get("AM/PM"),
                call_notes=fields.get("Call Notes"),
                outcome=fields["Outcome"],
                next_steps=fields.get("Next Steps"),
                follow_up_date=fields.get("Follow Up Date"),
                spidey_sense=fields.get("Spidey Sense"),
                spidey_rationale=fields.get("Spidey Rationale"),
                mood=fields.get("Mood"),
                lead_bringer_learnings=fields.get("Lead Bringer Learnings"),
                created_time=created_call["createdTime"]
            )
    except Exception as e:
        logger.error(f"Error creating call: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create call: {str(e)}"
        )

@app.get("/calls", response_model=List[CallResponse])
async def get_calls(limit: int = 100, company_name: Optional[str] = None):
    """Get call records, optionally filtered by company"""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{AIRTABLE_BASE_URL}/{AIRTABLE_CALLS_TABLE_ID}"
            params = {"maxRecords": min(limit, 100)}
            
            if company_name:
                # First find the company
                company = await find_company_by_name(company_name)
                if company:
                    params["filterByFormula"] = f"FIND('{company['id']}', ARRAYJOIN({{Lead}}))"
            
            response = await client.get(url, headers=HEADERS, params=params)
            response.raise_for_status()
            
            data = response.json()
            calls = []
            
            for record in data.get("records", []):
                fields = record["fields"]
                
                # Get company name if linked
                company_name_field = "Unknown Company"
                if "Lead" in fields and fields["Lead"]:
                    # Fetch company details
                    company_id = fields["Lead"][0]
                    company_url = f"{AIRTABLE_BASE_URL}/{AIRTABLE_COMPANIES_TABLE_ID}/{company_id}"
                    company_response = await client.get(company_url, headers=HEADERS)
                    if company_response.status_code == 200:
                        company_data = company_response.json()
                        company_name_field = company_data["fields"].get("Name", "Unknown Company")
                
                calls.append(CallResponse(
                    id=record["id"],
                    name=fields.get("Name", ""),
                    company_id=fields["Lead"][0] if fields.get("Lead") else "",
                    company_name=company_name_field,
                    date=fields.get("Date", ""),
                    am_pm=fields.get("AM/PM"),
                    call_notes=fields.get("Call Notes"),
                    outcome=fields.get("Outcome", ""),
                    next_steps=fields.get("Next Steps"),
                    follow_up_date=fields.get("Follow Up Date"),
                    spidey_sense=fields.get("Spidey Sense"),
                    spidey_rationale=fields.get("Spidey Rationale"),
                    mood=fields.get("Mood"),
                    lead_bringer_learnings=fields.get("Lead Bringer Learnings"),
                    created_time=record["createdTime"]
                ))
            
            return calls
    except Exception as e:
        logger.error(f"Error fetching calls: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch calls: {str(e)}"
        )

@app.post("/no-call")
async def create_no_call_entry(no_call: NoCallCreate):
    """Add a company to the no-call list"""
    # Find company
    company = await find_company_by_name(no_call.company_name)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{no_call.company_name}' not found"
        )
    
    no_call_data = {
        "Company": [company["id"]],
        "Phone": no_call.phone,
        "Email Domain": no_call.email_domain,
        "Reason": no_call.reason,
        "State": no_call.state
    }
    
    # Remove None values
    no_call_data = {k: v for k, v in no_call_data.items() if v is not None}
    
    try:
        async with httpx.AsyncClient() as client:
            url = f"{AIRTABLE_BASE_URL}/{AIRTABLE_NO_CALL_TABLE_ID}"
            payload = {"records": [{"fields": no_call_data}]}
            response = await client.post(url, headers=HEADERS, json=payload)
            response.raise_for_status()
            
            return {"message": f"Added {no_call.company_name} to no-call list", "success": True}
    except Exception as e:
        logger.error(f"Error creating no-call entry: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create no-call entry: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)