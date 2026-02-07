"""Google Sheets client for tracking job applications."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import (
    ALL_SCOPES,
    TOKEN_PATH,
    CREDENTIALS_PATH,
    PROJECT_ROOT,
    SPREADSHEET_ID,
    SPREADSHEET_NAME,
    SHEET_HEADERS,
)

# Path to store spreadsheet ID
SHEET_CONFIG_PATH = PROJECT_ROOT / "credentials" / "sheet_config.json"

# Status colors (RGB values 0-1)
STATUS_COLORS = {
    "Applied": {"red": 0.7, "green": 0.9, "blue": 0.7},      # Light Green
    "Assessment": {"red": 1.0, "green": 0.95, "blue": 0.6},  # Light Yellow
    "Interview": {"red": 0.7, "green": 0.85, "blue": 1.0},   # Light Blue
    "Rejected": {"red": 1.0, "green": 0.7, "blue": 0.7},     # Light Red
}


class SheetsClient:
    """Client for interacting with Google Sheets API."""

    def __init__(self):
        self.service = None
        self.creds = None
        self.spreadsheet_id = self._load_spreadsheet_id()
        self.sheet_id = 0  # Default sheet ID for "Applications" tab
        self._authenticate()
        self._ensure_spreadsheet()

    def _load_spreadsheet_id(self) -> str:
        """Load spreadsheet ID from config file or environment."""
        if SPREADSHEET_ID:
            return SPREADSHEET_ID
        
        if SHEET_CONFIG_PATH.exists():
            try:
                with open(SHEET_CONFIG_PATH, "r") as f:
                    config = json.load(f)
                    return config.get("spreadsheet_id", "")
            except Exception:
                pass
        
        return ""

    def _save_spreadsheet_id(self):
        """Save spreadsheet ID to config file for persistence."""
        try:
            SHEET_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(SHEET_CONFIG_PATH, "w") as f:
                json.dump({"spreadsheet_id": self.spreadsheet_id}, f)
        except Exception as e:
            print(f"Warning: Could not save spreadsheet ID: {e}")

    def _authenticate(self):
        """Authenticate with Google Sheets API using OAuth2."""
        if TOKEN_PATH.exists():
            self.creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), ALL_SCOPES)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not CREDENTIALS_PATH.exists():
                    raise FileNotFoundError(
                        f"credentials.json not found at {CREDENTIALS_PATH}. "
                        "Please download from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_PATH), ALL_SCOPES
                )
                self.creds = flow.run_local_server(port=0)

            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_PATH, "w") as token:
                token.write(self.creds.to_json())

        self.service = build("sheets", "v4", credentials=self.creds)

    def _ensure_spreadsheet(self):
        """Ensure spreadsheet exists, create if needed."""
        if self.spreadsheet_id:
            try:
                result = self.service.spreadsheets().get(
                    spreadsheetId=self.spreadsheet_id
                ).execute()
                # Get the sheet ID for the Applications tab
                for sheet in result.get("sheets", []):
                    if sheet["properties"]["title"] == "Applications":
                        self.sheet_id = sheet["properties"]["sheetId"]
                        break
                print(f"Using existing spreadsheet: https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}")
                return
            except Exception:
                print(f"Spreadsheet {self.spreadsheet_id} not found, creating new one...")

        # Create new spreadsheet
        spreadsheet = {
            "properties": {"title": SPREADSHEET_NAME},
            "sheets": [{
                "properties": {"title": "Applications", "sheetId": 0}
            }]
        }
        result = self.service.spreadsheets().create(body=spreadsheet).execute()
        self.spreadsheet_id = result["spreadsheetId"]
        self.sheet_id = 0
        
        self._save_spreadsheet_id()
        
        print(f"Created new spreadsheet: https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}")

        # Add headers and set up formatting
        self._add_headers()
        self._setup_conditional_formatting()

    def _add_headers(self):
        """Add header row to the spreadsheet."""
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range="Applications!A1",
            valueInputOption="RAW",
            body={"values": [SHEET_HEADERS]}
        ).execute()
        
        # Format header row (bold, frozen)
        requests = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": self.sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)"
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": self.sheet_id,
                        "gridProperties": {"frozenRowCount": 1}
                    },
                    "fields": "gridProperties.frozenRowCount"
                }
            }
        ]
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={"requests": requests}
        ).execute()

    def _setup_conditional_formatting(self):
        """Set up conditional formatting for status colors."""
        requests = []
        
        # Status is in column C (index 2)
        for status, color in STATUS_COLORS.items():
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": self.sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 1000,
                            "startColumnIndex": 0,
                            "endColumnIndex": 7
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": f'=$C2="{status}"'}]
                            },
                            "format": {
                                "backgroundColor": color
                            }
                        }
                    },
                    "index": 0
                }
            })
        
        if requests:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests}
            ).execute()

    def sort_by_last_updated(self):
        """Sort the sheet by Last Updated column (newest first)."""
        try:
            # Last Updated is column E (index 4)
            request = {
                "sortRange": {
                    "range": {
                        "sheetId": self.sheet_id,
                        "startRowIndex": 1,  # Skip header
                        "startColumnIndex": 0,
                        "endColumnIndex": 6
                    },
                    "sortSpecs": [{
                        "dimensionIndex": 4,  # Column E (Last Updated)
                        "sortOrder": "DESCENDING"
                    }]
                }
            }
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [request]}
            ).execute()
        except Exception as e:
            print(f"Warning: Could not sort sheet: {e}")

    def apply_row_color(self, row_index: int, status: str):
        """Apply color to a specific row based on status."""
        if status not in STATUS_COLORS:
            return
            
        color = STATUS_COLORS[status]
        try:
            request = {
                "repeatCell": {
                    "range": {
                        "sheetId": self.sheet_id,
                        "startRowIndex": row_index - 1,  # 0-indexed
                        "endRowIndex": row_index,
                        "startColumnIndex": 0,
                        "endColumnIndex": 6
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": color
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [request]}
            ).execute()
        except Exception as e:
            print(f"Warning: Could not apply color: {e}")

    def get_all_applications(self) -> list[dict]:
        """Get all existing applications from the sheet."""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range="Applications!A2:F"
            ).execute()
            values = result.get("values", [])

            applications = []
            for row in values:
                while len(row) < len(SHEET_HEADERS):
                    row.append("")
                applications.append({
                    "company": row[0],
                    "role": row[1],
                    "status": row[2],
                    "applied_date": row[3],
                    "last_updated": row[4],
                    "email_subject": row[5],

                })
            return applications
        except Exception as e:
            print(f"Error getting applications: {e}")
            return []

    def find_application(self, company: str, role: str) -> Optional[tuple[int, dict]]:
        """Find an existing application by company and role."""
        applications = self.get_all_applications()
        for i, app in enumerate(applications):
            if (app["company"].lower() == company.lower() and
                app["role"].lower() == role.lower()):
                return (i + 2, app)
        return None
    
    def find_application_by_company(self, company: str) -> Optional[tuple[int, dict]]:
        """Find an existing application by company name only."""
        applications = self.get_all_applications()
        for i, app in enumerate(applications):
            if app["company"].lower() == company.lower():
                return (i + 2, app)
        return None

    def add_application(
        self,
        company: str,
        role: str,
        status: str,
        applied_date: datetime,
        email_subject: str = "",
        detection_reason: str = ""
    ) -> bool:
        """Add a new application or update existing one."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        try:
            if hasattr(applied_date, 'tzinfo') and applied_date.tzinfo is not None:
                applied_str = applied_date.replace(tzinfo=None).strftime("%Y-%m-%d")
            else:
                applied_str = applied_date.strftime("%Y-%m-%d")
        except Exception:
            applied_str = datetime.now().strftime("%Y-%m-%d")

        existing = self.find_application(company, role)

        if existing:
            row_index, app = existing
            return self.update_application(
                row_index, status, now, email_subject
            )

        # Add new row with detection reason
        try:
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range="Applications!A:G",
                valueInputOption="RAW",
                body={"values": [[
                    company,
                    role,
                    status,
                    applied_str,
                    now,
                    email_subject,
                    detection_reason
                ]]}
            ).execute()
            return True
        except Exception as e:
            print(f"Error adding application: {e}")
            return False

    def update_application(
        self,
        row_index: int,
        status: str,
        last_updated: str,
        email_subject: str = ""
    ) -> bool:
        """Update an existing application row."""
        try:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"Applications!C{row_index}:F{row_index}",
                valueInputOption="RAW",
                body={"values": [[status, "", last_updated, email_subject]]}
            ).execute()
            return True
        except Exception as e:
            print(f"Error updating sheet: {e}")
            return False

    def clear_sheet(self) -> bool:
        """Clear all application data from the sheet (keeps headers)."""
        try:
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range="Applications!A2:Z"
            ).execute()
            print("Server data cleared successfully.")
            return True
        except Exception as e:
            print(f"Error clearing sheet: {e}")
            return False

    def get_spreadsheet_url(self) -> str:
        """Get the URL to the spreadsheet."""
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
