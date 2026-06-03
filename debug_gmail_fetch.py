import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from src.gmail_client import GmailClient
from src.config import JOB_EMAIL_QUERY

def debug():
    print("="*50)
    print("DEBUG GMAIL FETCH")
    print("="*50)
    
    print(f"\n[CONFIG] Raw Query:\n{JOB_EMAIL_QUERY}")
    
    client = GmailClient()
    print("\n[API] Fetching last 7 days...")
    
    # Manually construct query to see what happens
    from datetime import datetime, timedelta
    date_cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y/%m/%d')
    final_query = f'after:{date_cutoff} {JOB_EMAIL_QUERY}'
    print(f"\n[API] Final Query Sent:\n{final_query}")
    
    # Fetch
    messages = client.get_messages(days_back=7, max_results=10)
    print(f"\n[RESULT] Found {len(messages)} messages.")
    
    for i, msg in enumerate(messages):
        print(f"\n--- Email {i+1} ---")
        print(f"Subject: {msg.get('subject')}")
        print(f"From: {msg.get('from')}")
        print(f"Date: {msg.get('date')}")
        print(f"Prediction: {msg.get('detection_reason')}")

if __name__ == "__main__":
    debug()
