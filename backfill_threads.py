import sys
import io
import os
from datetime import datetime, timedelta

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from src.sheets_client import SheetsClient
from src.gmail_client import GmailClient

def backfill():
    print("="*60)
    print("BACKFILLING MISSING GMAIL THREAD IDS")
    print("="*60)
    
    sheets = SheetsClient()
    gmail = GmailClient()
    
    print("\n[SHEETS] Fetching all applications from sheet...")
    apps = sheets.get_all_applications()
    print(f"   Found {len(apps)} total applications.")
    
    # Identify rows that need backfilling
    # Row index in Google Sheets starts at 2 (row 1 is header)
    needs_backfill = []
    for i, app in enumerate(apps):
        row_num = i + 2
        if not app.get("thread_id"):
            needs_backfill.append((row_num, app))
            
    print(f"   {len(needs_backfill)} applications are missing Thread IDs.")
    if not needs_backfill:
        print("   All applications already have Thread IDs. Nothing to do!")
        return
        
    # Fetch emails from Gmail
    lookback_days = 120
    print(f"\n[GMAIL] Fetching emails from the last {lookback_days} days...")
    emails = gmail.get_messages(days_back=lookback_days)
    print(f"   Retrieved {len(emails)} potential job emails.")
    
    # Match and collect updates
    updates = []
    matched_count = 0
    
    # Index our needs_backfill by company name for faster matching
    # Map lowercase company name -> list of (row_num, app)
    company_map = {}
    for row_num, app in needs_backfill:
        comp_clean = app["company"].lower().strip()
        if comp_clean:
            company_map.setdefault(comp_clean, []).append((row_num, app))
            
    for email in emails:
        if not email:
            continue
            
        email_company = email.get("sender_domain", "").lower().strip()
        email_subject = email.get("subject", "").lower()
        thread_id = email.get("thread_id", "")
        
        if not thread_id:
            continue
            
        # Find matching company
        matched_rows = []
        
        # Heuristic 1: Exact or substring match on company name
        for comp_name, rows in company_map.items():
            # If email domain is in sheet company name, or sheet company name is in email domain
            if email_company and (email_company in comp_name or comp_name in email_company):
                matched_rows.extend(rows)
            # Or if company name is mentioned in the subject line
            elif comp_name in email_subject:
                matched_rows.extend(rows)
                
        # Remove duplicates from matches using row_num as key
        deduped = {}
        for r_num, r_app in matched_rows:
            deduped[r_num] = r_app
        matched_rows = list(deduped.items())
        
        if matched_rows:
            # We match to the row. If there are multiple rows for the same company,
            # we can try to match by role or select the most recent one.
            for row_num, app in matched_rows:
                # Basic role matching if available
                app_role = app.get("role", "").lower().strip()
                # If roles match, or if it's the only matched row, backfill it
                if len(matched_rows) == 1 or not app_role or "unknown" in app_role:
                    updates.append((row_num, thread_id, app["company"], app.get("role")))
                    matched_count += 1
                    # Remove from map so we don't match it again with an older email
                    comp_clean = app["company"].lower().strip()
                    if comp_clean in company_map:
                        company_map[comp_clean] = [r for r in company_map[comp_clean] if r[0] != row_num]
                    break
                    
    print(f"\n[MATCH] Matched {matched_count} applications to Gmail threads.")
    
    if not updates:
        print("   No matches found to backfill.")
        return
        
    # Execute batch update on Google Sheets
    print(f"\n[SHEETS] Writing Thread IDs to Google Sheet...")
    
    # We will write to Column I (index 9) for each row
    data = []
    for row_num, thread_id, company, role in updates:
        print(f"   Row {row_num}: {company} | {role} -> Thread ID: {thread_id}")
        data.append({
            "range": f"Applications!I{row_num}",
            "values": [[thread_id]]
        })
        
    try:
        sheets.service.spreadsheets().values().batchUpdate(
            spreadsheetId=sheets.spreadsheet_id,
            body={
                "valueInputOption": "RAW",
                "data": data
            }
        ).execute()
        print(f"\n[SUCCESS] Successfully backfilled {len(updates)} Thread IDs in Google Sheets!")
    except Exception as e:
        print(f"\n[ERROR] Failed to update Google Sheets: {e}")

if __name__ == "__main__":
    backfill()
