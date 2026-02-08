"""Vercel Serverless Function Entry Point."""

import os
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, render_template, jsonify
from datetime import datetime

app = Flask(
    __name__,
    template_folder=str(project_root / "dashboard" / "templates"),
    static_folder=str(project_root / "dashboard" / "static")
)


def setup_oauth_credentials():
    """Setup OAuth credentials from environment variables."""
    client_creds = os.environ.get("GOOGLE_CLIENT_CREDENTIALS")
    token_json = os.environ.get("GOOGLE_TOKEN")
    
    if client_creds:
        with open("/tmp/credentials.json", "w") as f:
            f.write(client_creds)
    
    if token_json:
        with open("/tmp/token.json", "w") as f:
            f.write(token_json)


def get_sheets_service():
    """Get Google Sheets service using OAuth credentials."""
    setup_oauth_credentials()
    
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not spreadsheet_id:
        return None, None
    
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        # Try to load token
        token_path = "/tmp/token.json"
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path)
            service = build("sheets", "v4", credentials=creds)
            return service, spreadsheet_id
    except Exception as e:
        print(f"Error initializing Sheets: {e}")
    
    return None, None


def get_applications_from_sheet():
    """Fetch applications directly from Google Sheets."""
    service, spreadsheet_id = get_sheets_service()
    
    if not service:
        return None
    
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="Applications!A:G"
        ).execute()
        
        values = result.get("values", [])
        if len(values) <= 1:  # No data or only headers
            return []
        
        headers = ["company", "role", "status", "applied_date", "last_updated", "email_subject", "detection_reason"]
        applications = []
        
        for row in values[1:]:  # Skip header row
            app = {}
            for i, header in enumerate(headers):
                app[header] = row[i] if i < len(row) else ""
            applications.append(app)
        
        return applications
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None


def get_stats_from_applications(applications):
    """Calculate stats from applications."""
    stats = {
        "total": len(applications),
        "Applied": 0,
        "Assessment": 0,
        "Interview": 0,
        "Offer": 0,
        "Rejected": 0
    }
    
    for app in applications:
        status = app.get("status", "Applied")
        if status in stats:
            stats[status] += 1
    
    return stats


@app.route("/")
def index():
    """Dashboard home page."""
    return render_template("index.html")


@app.route("/api/applications")
def api_applications():
    """API endpoint for applications data."""
    applications = get_applications_from_sheet()
    
    if applications is None:
        # Return sample data for demo/development
        return jsonify([
            {"company": "Demo Company", "role": "Software Engineer", "status": "Applied", "applied_date": "2026-02-07", "last_updated": "2026-02-07 12:00"}
        ])
    
    return jsonify(applications)


@app.route("/api/stats")
def api_stats():
    """API endpoint for statistics."""
    applications = get_applications_from_sheet()
    
    if applications is None:
        return jsonify({"total": 1, "Applied": 1, "Assessment": 0, "Interview": 0, "Rejected": 0})
    
    return jsonify(get_stats_from_applications(applications))


@app.route("/api/health")
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "spreadsheet_configured": bool(os.environ.get("SPREADSHEET_ID")),
        "credentials_configured": bool(os.environ.get("GOOGLE_TOKEN"))
    })


# Vercel requires this
app = app
