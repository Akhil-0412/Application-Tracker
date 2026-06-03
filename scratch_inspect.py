import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from src.sheets_client import SheetsClient

client = SheetsClient()
apps = client.get_all_applications()
print(f"Total apps in sheet: {len(apps)}")
print("\nLast 5 applications in sheet:")
for i, app in enumerate(apps[-10:]):
    print(f"Row {len(apps) - 10 + i + 2}: Company={app['company']}, Status={app['status']}, ThreadID={app['thread_id']}")
