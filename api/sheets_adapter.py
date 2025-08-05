"""Runtime shim to make Lead Bringer open the workbook by ID."""
import os
import json
import base64
import gspread
from google.oauth2.service_account import Credentials

# Load environment variables
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDENTIALS_B64 = os.getenv("GOOGLE_CREDENTIALS_FILE")  # Match Claude's variable name

if not (SPREADSHEET_ID and GOOGLE_CREDENTIALS_B64):
    raise RuntimeError("Missing SPREADSHEET_ID or GOOGLE_CREDENTIALS_B64 env var")

# Create client
_creds_json = base64.b64decode(GOOGLE_CREDENTIALS_B64).decode()
_creds_dict = json.loads(_creds_json)
_client = gspread.authorize(Credentials.from_service_account_info(_creds_dict, scopes=SCOPES))

# Override get_sheets_client to return pre-authorized client
def get_sheets_client():
    return _client

# Override open_workbook to use SPREADSHEET_ID
def open_workbook():
    return _client.open_by_key(SPREADSHEET_ID)