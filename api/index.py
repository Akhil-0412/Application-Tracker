"""Vercel Serverless Function Entry Point."""

import os
import sys
import json
from pathlib import Path

# Add project root to path
# On Vercel, the script runs from api/index.py, so root is parent
# However, Vercel might place files differently.
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))

from datetime import datetime

from flask import Flask, render_template, jsonify
# Try imports immediately to fail fast if they don't exist
try:
    from src.sheets_client import SheetsClient
    from src.gmail_client import GmailClient
    from src.ai_classifier import AIClassifier
    from src.status_tracker import StatusTracker
except ImportError:
    SheetsClient = None
    GmailClient = None
    AIClassifier = None
    StatusTracker = None


app = Flask(
    __name__,
    template_folder=str(project_root / "dashboard" / "templates"),
    static_folder=str(project_root / "dashboard" / "static")
)


def setup_oauth_credentials():
    """Setup OAuth credentials from environment variables."""
    # ... (same as before) ...
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
    try:
        return render_template("index.html")
    except Exception as e:
        return jsonify({"error": str(e), "path": str(project_root)}), 500


@app.route("/api/applications")
def api_applications():
    """API endpoint for applications data."""
    try:
        applications = get_applications_from_sheet()
        
        if applications is None:
            return jsonify([
                {"company": "Demo Company", "role": "Software Engineer", "status": "Applied", "applied_date": "2026-02-07", "last_updated": "2026-02-07 12:00", "detection_reason": "API returned None (Auth failed?)"}
            ])
        
        # 1. Filter out "Unknown"
        filtered_applications = []
        for app in applications:
            company = str(app.get("company", "")).lower().strip()
            role = str(app.get("role", "")).lower().strip()
            
            if (company in ["unknown", "unknown company", ""] and 
                role in ["unknown", "unknown position", "", "unspecified"]):
                continue
            filtered_applications.append(app)
        
        # 2. Sort by applied_date
        def parse_date(date_str):
            # Ensure datetime is available
            from datetime import datetime
            
            if not date_str: return datetime.min
            s = str(date_str).strip()
            formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%b %d, %Y"]
            for fmt in formats:
                try:
                    return datetime.strptime(s, fmt)
                except:
                    continue
            return datetime.min

        filtered_applications.sort(
            key=lambda x: parse_date(x.get("applied_date", "")), 
            reverse=True
        )
        
        return jsonify(filtered_applications)

    except Exception as e:
        import traceback
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc(),
            # Don't return env vars in case of secrets, just return keys
            "env_vars_keys": list(os.environ.keys())
        }), 500


@app.route("/api/stats")
def api_stats():
    """API endpoint for statistics."""
    applications = get_applications_from_sheet()
    
    if applications is None:
        return jsonify({"total": 1, "Applied": 1, "Assessment": 0, "Interview": 0, "Rejected": 0})
    
    return jsonify(get_stats_from_applications(applications))


@app.route("/api/process")
def process_emails():
    """Trigger email processing (Cron job entry point)."""
    # 1. Setup credentials
    setup_oauth_credentials()
    
    # 2. Initialize clients
    try:
        if not GmailClient:
            return jsonify({"error": "Modules not loaded"}), 500
            
        gmail = GmailClient()
        sheets = SheetsClient()
        classifier = AIClassifier()
        tracker = StatusTracker(sheets)
        
        # 3. Fetch & Process (Limit to 1 day and 20 emails to avoid timeout)
        # Vercel functions have 10s (Hobby) or 60s (Pro) limit
        days_back = 1
        max_emails = 20
        
        emails = gmail.get_messages(days_back=days_back, max_results=max_emails)
        
        processed_count = 0
        details = []
        
        for email in emails:
            if not email: continue
            
            try:
                # Classify
                result = classifier.classify(email)
                
                # Track
                updated = tracker.process_classification(
                    result=result,
                    email_date=email.get("date", datetime.now()),
                    email_subject=email.get("subject", ""),
                    detection_reason=email.get("detection_reason", "")
                )
                
                if updated:
                    processed_count += 1
                    details.append(f"{result.company} - {result.role}: {result.status}")
                    
            except Exception as e:
                print(f"Error processing email {email.get('id')}: {e}")
                continue
        
        return jsonify({
            "status": "success",
            "processed": processed_count,
            "details": details,
            "message": f"Processed {processed_count} updates from last {days_back} days"
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500



@app.route("/api/health")
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "spreadsheet_configured": bool(os.environ.get("SPREADSHEET_ID")),
        "credentials_configured": bool(os.environ.get("GOOGLE_TOKEN"))
    })

@app.route("/debug")
def debug():
    """Debug file system."""
    files = []
    
    # List files in current directory
    try:
        files.append(f"Current dir ({os.getcwd()}): {os.listdir(os.getcwd())}")
    except Exception as e:
        files.append(f"Error listing current: {e}")
        
    # List files in project root
    try:
        files.append(f"Project root ({project_root}): {os.listdir(project_root)}")
    except Exception as e:
        files.append(f"Error listing root: {e}")
        
    # Check templates dir
    try:
        tpl_dir = project_root / "dashboard" / "templates"
        files.append(f"Templates ({tpl_dir}): {os.listdir(tpl_dir)}")
    except Exception as e:
        files.append(f"Error listing templates: {window.e}")

    return jsonify({
        "files": files,
        "python_path": sys.path,
        "template_folder": app.template_folder,
        "static_folder": app.static_folder
    })


# Vercel requires this
app = app
