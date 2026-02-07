"""Flask Dashboard for Application Tracker.

Run with: python -m dashboard.app
Or: python dashboard/app.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, jsonify
from src.sheets_client import SheetsClient
from src.status_tracker import StatusTracker

app = Flask(__name__)

# Initialize clients once
sheets = None
tracker = None


def get_clients():
    """Lazy initialization of clients."""
    global sheets, tracker
    if sheets is None:
        sheets = SheetsClient()
        tracker = StatusTracker(sheets)
    return sheets, tracker


@app.route("/")
def index():
    """Dashboard home page."""
    return render_template("index.html")


@app.route("/api/applications")
def api_applications():
    """API endpoint for applications data."""
    sheets, _ = get_clients()
    applications = sheets.get_all_applications()
    return jsonify(applications)


@app.route("/api/stats")
def api_stats():
    """API endpoint for statistics."""
    _, tracker = get_clients()
    stats = tracker.get_statistics()
    return jsonify(stats)


@app.route("/api/refresh")
def api_refresh():
    """Trigger a manual refresh (fetch new emails)."""
    from src.gmail_client import GmailClient
    from src.ai_classifier import AIClassifier
    from datetime import datetime, timedelta
    
    sheets, tracker = get_clients()
    gmail = GmailClient()
    classifier = AIClassifier()
    
    # Fetch emails from last 24 hours
    emails = gmail.get_messages(days_back=1)
    processed = 0
    
    for email in emails:
        if not email:
            continue
        try:
            result = classifier.classify(email)
            updated = tracker.process_classification(
                result=result,
                email_date=email.get("date", datetime.now()),
                email_subject=email.get("subject", ""),
                detection_reason=email.get("detection_reason", "")
            )
            if updated:
                processed += 1
        except Exception:
            continue
    
    return jsonify({"processed": processed, "status": "ok"})


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("APPLICATION TRACKER DASHBOARD")
    print("=" * 50)
    print("\nStarting server at http://localhost:5000")
    print("Press Ctrl+C to stop\n")
    
    app.run(debug=True, host="0.0.0.0", port=5000)
