"""Vercel Serverless Function Entry Point."""

import os
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, render_template, jsonify, Response
from datetime import datetime

app = Flask(
    __name__,
    template_folder=str(project_root / "dashboard" / "templates"),
    static_folder=str(project_root / "dashboard" / "static")
)

# Initialize Google credentials from environment variable
def setup_credentials():
    """Setup Google credentials from environment variable."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        creds_path = "/tmp/google_credentials.json"
        with open(creds_path, "w") as f:
            f.write(creds_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path


def get_sheets_client():
    """Get SheetsClient with proper credential handling for Vercel."""
    setup_credentials()
    
    # Check if we have the environment variables
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not spreadsheet_id:
        return None
    
    try:
        from src.sheets_client import SheetsClient
        return SheetsClient()
    except Exception as e:
        print(f"Error initializing SheetsClient: {e}")
        return None


@app.route("/")
def index():
    """Dashboard home page."""
    return render_template("index.html")


@app.route("/api/applications")
def api_applications():
    """API endpoint for applications data."""
    sheets = get_sheets_client()
    if not sheets:
        # Return sample data for demo/development
        return jsonify([
            {"company": "Demo Company", "role": "Software Engineer", "status": "Applied", "applied_date": "2026-02-07", "last_updated": "2026-02-07 12:00"}
        ])
    
    try:
        applications = sheets.get_all_applications()
        return jsonify(applications)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats")
def api_stats():
    """API endpoint for statistics."""
    sheets = get_sheets_client()
    if not sheets:
        return jsonify({"total": 1, "Applied": 1, "Assessment": 0, "Interview": 0, "Rejected": 0})
    
    try:
        from src.status_tracker import StatusTracker
        tracker = StatusTracker(sheets)
        stats = tracker.get_statistics()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/health")
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "spreadsheet_configured": bool(os.environ.get("SPREADSHEET_ID"))
    })


# Vercel requires this
app = app
