"""Utility to wipe all application data from the Google Sheet."""

from src.sheets_client import SheetsClient


def main():
    print("[WIPE] Connecting to Google Sheets...")
    sheets = SheetsClient()

    print("[WIPE] Clearing application data (keeping headers)...")
    success = sheets.clear_sheet()

    if success:
        print("[WIPE] Sheet cleared successfully.")
        print(f"[LINK] {sheets.get_spreadsheet_url()}")
    else:
        print("[ERROR] Failed to clear sheet.")


if __name__ == "__main__":
    main()
