import sys
import io
import os

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from src.sheets_client import SheetsClient

def inspect():
    print("="*50)
    print("INSPECTING GOOGLE SHEET")
    print("="*50)
    
    client = SheetsClient()
    print(f"Spreadsheet ID: {client.spreadsheet_id}")
    
    # Check sheet metadata
    try:
        meta = client.service.spreadsheets().get(spreadsheetId=client.spreadsheet_id).execute()
        titles = [s['properties']['title'] for s in meta['sheets']]
        print(f"\n[SHEETS] Available tabs: {titles}")
    except Exception as e:
        print(f"\n[ERROR] Could not fetch metadata: {e}")
        return

    print("\n[FETCH] Getting all applications...")
    apps = client.get_all_applications()
    print(f"Found {len(apps)} total applications.")
    
    target_company = "TEST_COMPANY_123"
    companies = [app.get('company', '').lower() for app in apps]
    
    matched = [c for c in companies if target_company.lower() in c]
    
    if matched:
        print(f"\n[SUCCESS] FOUND IT! Matches: {matched}")
    else:
        print(f"\n[FAILURE] NOT FOUND. Searched for '{target_company}'")
        print(f"Sample companies (first 5): {companies[:5]}")

if __name__ == "__main__":
    inspect()
