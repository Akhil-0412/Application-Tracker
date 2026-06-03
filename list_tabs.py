import sys
import io
import os

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from src.sheets_client import SheetsClient

def list_tabs():
    try:
        client = SheetsClient()
        print(f"SHEET_ID: {client.spreadsheet_id}")
        
        meta = client.service.spreadsheets().get(spreadsheetId=client.spreadsheet_id).execute()
        sheets = meta.get('sheets', [])
        
        print(f"TOTAL_TABS: {len(sheets)}")
        for s in sheets:
            title = s['properties']['title']
            sheet_id = s['properties']['sheetId']
            grid = s['properties']['gridProperties']
            row_count = grid.get('rowCount', 0)
            col_count = grid.get('columnCount', 0)
            print(f"TAB: '{title}' (ID: {sheet_id}) - Rows: {row_count}, Cols: {col_count}")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    list_tabs()
