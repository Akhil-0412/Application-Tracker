import sys
import io
import os
from datetime import datetime

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from src.sheets_client import SheetsClient

def test_update():
    print("="*50)
    print("TESTING SHEET UPDATE (ROW 2)")
    print("="*50)
    
    client = SheetsClient()
    print(f"SPREADSHEET_ID: {client.spreadsheet_id}")
    
    company = "TEST_DETERMINISTIC_123"
    role = "Test Role"
    status = "Rejected"
    
    print(f"\n[ACTION] Adding application: {company}")
    success = client.add_application(
        company=company,
        role=role,
        status=status,
        applied_date=datetime.now(),
        email_subject="Test Subject",
        detection_reason="Manual Test"
    )
    
    if success:
        print("[SUCCESS] add_application returned True")
    else:
        print("[FAILURE] add_application returned False")

if __name__ == "__main__":
    test_update()
