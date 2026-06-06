"""Flask Dashboard for Application Tracker.

Run with: python -m dashboard.app
Or: python dashboard/app.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, jsonify, request
from src.sheets_client import SheetsClient
from src.junk_filter import JunkFilter
from src.status_tracker import StatusTracker
from src.thread_store import ThreadStore
from src.correlation_engine import CorrelationEngine
from src.ai_classifier import AIClassifier

app = Flask(__name__)

# Initialize clients once
sheets = None
tracker = None
classifier_global = None


def get_clients():
    """Lazy initialization of clients."""
    global sheets, tracker, classifier_global
    if sheets is None:
        sheets = SheetsClient()
        classifier_global = AIClassifier()
        thread_store = ThreadStore(sheets)
        correlation_engine = CorrelationEngine(
            sheets_client=sheets,
            thread_store=thread_store,
            ai_classifier=classifier_global,
        )
        tracker = StatusTracker(
            sheets_client=sheets,
            correlation_engine=correlation_engine,
            thread_store=thread_store,
        )
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


@app.route("/api/email/<thread_id>")
def api_email_html(thread_id):
    """API endpoint to get the HTML content of an email thread."""
    from src.gmail_client import GmailClient
    gmail = GmailClient()
    html_content = gmail.get_thread_html(thread_id)
    return html_content


@app.route("/api/applications/<int:row_index>/status", methods=["POST"])
def api_update_status(row_index):
    """API endpoint to manually override application status."""
    data = request.json
    new_status = data.get("status")
    if not new_status:
        return jsonify({"error": "Missing status"}), 400
        
    sheets, _ = get_clients()
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    success, msg = sheets.update_application(
        row_index=row_index,
        status=new_status,
        last_updated=now
    )
    
    if success:
        return jsonify({"success": True, "message": msg})
    else:
        return jsonify({"error": msg}), 500


@app.route("/api/applications/<int:row_index>/junk", methods=["POST"])
def api_junk_application(row_index):
    """API endpoint to mark an application as junk and delete it from sheets."""
    data = request.json
    thread_id = data.get("thread_id", "")
    sender_email = data.get("sender_email", "")
    
    # 1. Add to Junk Memory
    if thread_id or sender_email:
        JunkFilter.add_junk(thread_id, sender_email)
        
    # 2. Completely delete the row from Google Sheet
    try:
        sheets, _ = get_clients()
        sheets.delete_application(row_index)
    except Exception as e:
        print(f"Failed to delete junk row {row_index}: {e}")
        
    return jsonify({"success": True, "message": "Marked as junk and completely removed from sheet"})


@app.route("/api/refresh")
def api_refresh():
    """Trigger a manual refresh (fetch new emails)."""
    from src.gmail_client import GmailClient
    from datetime import datetime, timedelta
    
    sheets, tracker = get_clients()
    gmail = GmailClient()
    classifier = classifier_global or AIClassifier()
    
    # Fetch emails from last 24 hours
    emails = gmail.get_messages(days_back=1)
    existing_apps = sheets.get_all_applications()
    processed = 0
    
    for email in emails:
        if not email:
            continue
        try:
            result = classifier.classify(email, existing_apps=existing_apps)
            updated, reason = tracker.process_classification(
                result=result,
                email_date=email.get("date", datetime.now()),
                email_subject=email.get("subject", ""),
                detection_reason=email.get("detection_reason", ""),
                email=email,
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
