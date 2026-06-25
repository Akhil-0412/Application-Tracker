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
from typing import Optional

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from src.gmail_client import GmailClient
from src.db_client import DBClient
from src.ai_classifier import AIClassifier
from src.status_tracker import StatusTracker
from src.thread_store import ThreadStore
from src.correlation_engine import CorrelationEngine
from src.config import POLLING_INTERVAL


def process_emails(
    gmail: GmailClient,
    classifier: AIClassifier,
    tracker: StatusTracker,
    db: DBClient,
    days: int = 30,
    after_date: Optional[datetime] = None
):
    """Process emails from the last N days or since a specific date."""
    if after_date:
        print(f"\n[EMAIL] Fetching job application emails since {after_date.strftime('%Y-%m-%d %H:%M:%S')}...")
        emails = gmail.get_messages(after_date=after_date)
    else:
        print(f"\n[EMAIL] Fetching job application emails from the last {days} days...")
        emails = gmail.get_messages(days_back=days)
        
    print(f"   Found {len(emails)} emails matching job application criteria")
    
    if not emails:
        print("   No new emails to process")
        return 0
    
    # Load existing applications once for AI context
    existing_apps = db.get_all_applications()
    
    processed = 0
    for email in emails:
        if not email:
            continue
            
        try:
            print(f"   Processing: {email.get('subject')} ({email.get('date')})")
            # Classify the email — pass existing apps for AI correlation
            result = classifier.classify(email, existing_apps=existing_apps)
            print(f"      -> Classified: {result.company} | {result.role} | {result.status}")
            
            # Track the application — pass the full email for correlation
            updated, reason = tracker.process_classification(
                result=result,
                email_date=email.get("date", datetime.now()),
                email_subject=email.get("subject", ""),
                detection_reason=email.get("detection_reason", ""),
                email=email,
            )
            print(f"      -> Tracker update: {updated} ({reason})")

            
            if updated:
                status_marker = {
                    "Applied": "[APPLIED]",
                    "Assessment": "[ASSESSMENT]",
                    "Interview": "[INTERVIEW]",
                    "Offer": "[OFFER]",
                    "Rejected": "[REJECTED]"
                }.get(result.status, "[EMAIL]")
                
                print(f"   {status_marker} {result.company} - {result.role}: {result.status}")
                processed += 1
                
        except Exception as e:
            print(f"   [WARN] Error processing email: {e}")
            continue
    
    return processed


def live_monitor(
    gmail: GmailClient,
    classifier: AIClassifier,
    tracker: StatusTracker,
    db: DBClient,
    interval: int
):
    """Run in live monitoring mode."""
    print(f"\n[LIVE] Starting live monitoring (polling every {interval} seconds)")
    print("   Press Ctrl+C to stop\n")
    
    last_check = datetime.now() - timedelta(days=1)  # Start with last 24 hours
    
    try:
        while True:
            # Fetch only new emails
            emails = gmail.get_messages(after_date=last_check, max_results=20)
            
            if emails:
                # Load existing applications for AI context
                existing_apps = db.get_all_applications()
                
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
    
    print("\n[DB] Connecting to SQLite Database...")
    db = DBClient()
    print(f"   [OK] DB ready")
    
    print("\n[AI] Initializing AI classifier...")
    classifier = AIClassifier()
    if classifier.client:
        print(f"   [OK] Using Groq with model fallback")
    else:
        print("   [INFO] Running in phrase-matching mode (no GROQ_API_KEY)")
    
    # Initialize correlation components
    print("\n[CORRELATION] Initializing correlation engine...")
    thread_store = ThreadStore(db)
    correlation_engine = CorrelationEngine(
        db_client=db,
        thread_store=thread_store,
        ai_classifier=classifier,
    )
    print("   [OK] Correlation engine ready (thread + domain + AI signals)")
    
    # Initialize tracker with correlation
    tracker = StatusTracker(
        db_client=db,
        correlation_engine=correlation_engine,
        thread_store=thread_store,
    )
    
    if args.live:
        live_monitor(gmail, classifier, tracker, db, args.interval)
    else:
        # Instead of a separate last_run_date table, we'll just process the last N days 
        # (Gmail syncs fast anyway).
        processed = process_emails(gmail, classifier, tracker, db, args.days)
        
        # Show statistics
        stats = tracker.get_statistics()
        print(f"\n[STATS] Statistics:")
        print(f"   Total applications: {stats['total']}")
        print(f"   Applied: {stats['Applied']}")
        print(f"   Assessment: {stats['Assessment']}")
        print(f"   Interview: {stats['Interview']}")
        print(f"   Offer: {stats['Offer']}")
        print(f"   Rejected: {stats['Rejected']}")
        
        print(f"\n[DONE] Processed {processed} new/updated applications")
        
        print(f"[LINK] View your tracker by running 'python dashboard/app.py'")
    
    print("\n" + "=" * 50)


if __name__ == "__main__":
    main()
