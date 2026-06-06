import sys
import io
import re
from src.sheets_client import SheetsClient
from src.gmail_client import GmailClient

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def fix_thread_ids():
    print("="*60)
    print("FIXING & RE-MATCHING GMAIL THREAD IDS")
    print("="*60)
    
    sheets = SheetsClient()
    gmail = GmailClient()
    
    print("\n[SHEETS] Fetching all applications from sheet...")
    apps = sheets.get_all_applications()
    print(f"   Found {len(apps)} total applications.")
    
    # Identify all rows
    needs_backfill = []
    for i, app in enumerate(apps):
        row_num = i + 2
        needs_backfill.append((row_num, app))
            
    # Fetch emails from Gmail
    lookback_days = 180
    print(f"\n[GMAIL] Fetching emails from the last {lookback_days} days...")
    emails = gmail.get_messages(days_back=lookback_days)
    print(f"   Retrieved {len(emails)} potential job emails.")
    
    updates = []
    matched_count = 0
    
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
        sender_email = email.get("sender_email", "").lower()
        thread_id = email.get("thread_id", "")
        
        if not thread_id:
            continue
            
        matched_rows = []
        
        for comp_name, rows in company_map.items():
            if len(comp_name) < 3:
                # Too short, exact match only
                if comp_name == email_company:
                    matched_rows.extend(rows)
            else:
                # 1. Exact match on domain extraction
                if email_company == comp_name:
                    matched_rows.extend(rows)
                # 2. Domain is substring of company or vice-versa (only if long enough to avoid false positives)
                elif len(comp_name) > 4 and (email_company in comp_name or comp_name in email_company):
                    matched_rows.extend(rows)
                # 3. Company name is a distinct word in the subject
                elif re.search(r'\b' + re.escape(comp_name) + r'\b', email_subject):
                    matched_rows.extend(rows)
                # 4. Company name is a distinct word in the sender email name
                elif re.search(r'\b' + re.escape(comp_name) + r'\b', sender_email.split('@')[0]):
                    matched_rows.extend(rows)
                
        deduped = {}
        for r_num, r_app in matched_rows:
            deduped[r_num] = r_app
        matched_rows = list(deduped.items())
        
        if matched_rows:
            for row_num, app in matched_rows:
                # If matched, assign thread_id.
                updates.append((row_num, thread_id, app["company"]))
                matched_count += 1
                comp_clean = app["company"].lower().strip()
                if comp_clean in company_map:
                    company_map[comp_clean] = [r for r in company_map[comp_clean] if r[0] != row_num]
                break

    print(f"\n[MATCH] Matched {matched_count} applications to Gmail threads with improved accuracy.")
    
    # Execute batch update on Google Sheets to CLEAR and WRITE
    print(f"\n[SHEETS] Clearing old Thread IDs and writing new ones...")
    
    data = []
    # 1. Clear column I (Thread IDs)
    data.append({
        "range": "Applications!I2:I",
        "values": [[""] for _ in range(max(1000, len(apps) + 10))]
    })
    
    # 2. Write new Thread IDs
    for row_num, thread_id, company in updates:
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
        print(f"\n[SUCCESS] Successfully matched and updated {len(updates)} Thread IDs!")
    except Exception as e:
        print(f"\n[ERROR] Failed to update Google Sheets: {e}")

if __name__ == "__main__":
    fix_thread_ids()
