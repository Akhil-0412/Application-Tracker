
import os
import sys
import json
from datetime import datetime
from src.sheets_client import SheetsClient
from src.config import SPREADSHEET_ID

def test_api_logic():
    print("Fetching applications from sheet...")
    sheets = SheetsClient()
    applications = sheets.get_all_applications()
    
    print(f"\nTotal applications fetched: {len(applications)}")
    
    if not applications:
        print("No applications found in sheet.")
        return

    # 1. Filter logic test
    filtered_applications = []
    removed_count = 0
    
    print("\n--- Filtering Debug ---")
    for i, app in enumerate(applications):
        company = app.get("company", "").lower()
        role = app.get("role", "").lower()
        
        # Exact logic from api/index.py
        if (company in ["unknown", "unknown company", ""] and 
            role in ["unknown", "unknown position", "", "unspecified"]):
            print(f"Removing: Company='{app.get('company')}', Role='{app.get('role')}'")
            removed_count += 1
            continue
            
        filtered_applications.append(app)

    print(f"\nRemoved {removed_count} entries.")
    print(f"Remaining: {len(filtered_applications)}")

    # 2. Sorting logic test
    print("\n--- Sorting Debug ---")
    def parse_date(date_str):
        if not date_str: return datetime.min
        try:
            return datetime.strptime(str(date_str), "%Y-%m-%d")
        except:
            return datetime.min

    try:
        filtered_applications.sort(
            key=lambda x: parse_date(x.get("applied_date", "")), 
            reverse=True
        )
        print("Sorting successful.")
        if filtered_applications:
            print(f"Top 1: {filtered_applications[0]['applied_date']} - {filtered_applications[0]['company']}")
            print(f"Last: {filtered_applications[-1]['applied_date']} - {filtered_applications[-1]['company']}")
    except Exception as e:
        print(f"Sorting FAILED: {e}")

if __name__ == "__main__":
    test_api_logic()
