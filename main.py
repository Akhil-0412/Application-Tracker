"""Application Tracker - Main Entry Point.

Monitor Gmail for job application emails, classify them using AI,
and track everything in a Google Sheet.

Usage:
    python main.py                  # Process last 30 days
    python main.py --days 7         # Process last 7 days
    python main.py --live           # Live monitoring mode
    python main.py --live --interval 120  # Poll every 2 minutes
"""

import argparse
import time
import sys
import io
from datetime import datetime, timedelta

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from src.gmail_client import GmailClient
from src.sheets_client import SheetsClient
from src.ai_classifier import AIClassifier
from src.status_tracker import StatusTracker
from src.config import POLLING_INTERVAL


def process_emails(gmail: GmailClient, classifier: AIClassifier, tracker: StatusTracker, days: int = 30):
    """Process emails from the last N days."""
    print(f"\n[EMAIL] Fetching job application emails from the last {days} days...")
    
    emails = gmail.get_messages(days_back=days)
    print(f"   Found {len(emails)} emails matching job application criteria")
    
    if not emails:
        print("   No new emails to process")
        return 0
    
    processed = 0
    for email in emails:
        if not email:
            continue
            
        try:
            print(f"   Processing: {email.get('subject')} ({email.get('date')})")
            # Classify the email
            result = classifier.classify(email)
            print(f"      -> Classified: {result.company} | {result.role} | {result.status}")
            
            # Track the application
            updated, reason = tracker.process_classification(
                result=result,
                email_date=email.get("date", datetime.now()),
                email_subject=email.get("subject", ""),
                detection_reason=email.get("detection_reason", "")
            )
            print(f"      -> Tracker update: {updated} ({reason})")

            
            if updated:
                status_marker = {
                    "Applied": "[APPLIED]",
                    "Assessment": "[ASSESSMENT]",
                    "Interview": "[INTERVIEW]",
                    "Rejected": "[REJECTED]"
                }.get(result.status, "[EMAIL]")
                
                print(f"   {status_marker} {result.company} - {result.role}: {result.status}")
                processed += 1
                
        except Exception as e:
            print(f"   [WARN] Error processing email: {e}")
            continue
    
    return processed


def live_monitor(gmail: GmailClient, classifier: AIClassifier, tracker: StatusTracker, interval: int):
    """Run in live monitoring mode."""
    print(f"\n[LIVE] Starting live monitoring (polling every {interval} seconds)")
    print("   Press Ctrl+C to stop\n")
    
    last_check = datetime.now() - timedelta(days=1)  # Start with last 24 hours
    
    try:
        while True:
            # Fetch only new emails
            emails = gmail.get_messages(after_date=last_check, max_results=20)
            
            if emails:
                for email in emails:
                    if not email:
                        continue
                    
                    try:
                        result = classifier.classify(email)
                        updated, reason = tracker.process_classification(
                            result=result,
                            email_date=email.get("date", datetime.now()),
                            email_subject=email.get("subject", ""),
                            detection_reason=email.get("detection_reason", "")
                        )
                        
                        if updated:
                            print(f"   [NEW] {result.company} - {result.role}: {result.status} ({reason})")

                            
                    except Exception as e:
                        print(f"   [WARN] Error: {e}")
            
            last_check = datetime.now()
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n[INFO] Stopping live monitor...")


def main():
    parser = argparse.ArgumentParser(
        description="Track job applications from Gmail"
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="Number of days to look back (default: 30)"
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Enable live monitoring mode"
    )
    parser.add_argument(
        "--interval", type=int, default=POLLING_INTERVAL,
        help=f"Polling interval in seconds (default: {POLLING_INTERVAL})"
    )
    args = parser.parse_args()
    
    print("=" * 50)
    print("APPLICATION TRACKER")
    print("=" * 50)
    
    # Initialize clients
    print("\n[GMAIL] Connecting to Gmail...")
    gmail = GmailClient()
    print("   [OK] Gmail connected")
    
    print("\n[SHEETS] Connecting to Google Sheets...")
    sheets = SheetsClient()
    print(f"   [OK] Sheet ready: {sheets.get_spreadsheet_url()}")
    
    print("\n[AI] Initializing AI classifier...")
    classifier = AIClassifier()
    if classifier.client:
        print(f"   [OK] Using Groq with model fallback")
    else:
        print("   [INFO] Running in phrase-matching mode (no GROQ_API_KEY)")
    
    # Initialize tracker
    tracker = StatusTracker(sheets)
    
    if args.live:
        live_monitor(gmail, classifier, tracker, args.interval)
    else:
        processed = process_emails(gmail, classifier, tracker, args.days)
        
        # Show statistics
        stats = tracker.get_statistics()
        print(f"\n[STATS] Statistics:")
        print(f"   Total applications: {stats['total']}")
        print(f"   Applied: {stats['Applied']}")
        print(f"   Assessment: {stats['Assessment']}")
        print(f"   Interview: {stats['Interview']}")
        print(f"   Rejected: {stats['Rejected']}")
        
        print(f"\n[DONE] Processed {processed} new/updated applications")
        
        # Sort sheet by Last Updated (newest first)
        print("[SORT] Sorting by latest updates...")
        sheets.sort_by_last_updated()
        
        print(f"[LINK] View your tracker: {sheets.get_spreadsheet_url()}")
    
    print("\n" + "=" * 50)


if __name__ == "__main__":
    main()
