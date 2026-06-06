import sys
import io
import json
from src.sheets_client import SheetsClient

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def check_sheet():
    sheets = SheetsClient()
    apps = sheets.get_all_applications()
    print(f"Total apps in sheet: {len(apps)}")
    if apps:
        print("First app:", apps[0])

if __name__ == "__main__":
    check_sheet()
