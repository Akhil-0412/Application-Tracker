import sys
import io
import os

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from src.sheets_client import SheetsClient

def verify():
    try:
        client = SheetsClient()
        print(f"SHEET_ID: {client.spreadsheet_id}")
        
        apps = client.get_all_applications()
        companies = [a.get('company', '').lower() for a in apps]
        
        rider_found = any("rider" in c or "levett" in c for c in companies)
        test_found = any("deterministic" in c for c in companies)
        
        print(f"RIDER_FOUND: {rider_found}")
        print(f"TEST_FOUND: {test_found}")
        
        print(f"TOTAL_ROWS: {len(apps)}")
        if len(apps) > 0:
            print(f"ROW 2 STATUS: {apps[0].get('status')}")
            print(f"ROW 2 LAST_UPD: {apps[0].get('last_updated')}")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    verify()
