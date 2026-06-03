"""Thread-to-application mapping store for email correlation.

Maps Gmail thread IDs to tracked applications so that follow-up emails
(rejections, interview invites, etc.) in the same thread can be instantly
correlated to the correct application — even when they don't mention the
company or role.
"""

from typing import Optional


class ThreadStore:
    """Maps Gmail threadId → (company, role, sheet_row).

    Uses an in-memory cache backed by a Google Sheet column for persistence.
    Thread IDs are stored in the "Thread ID" column (column I) of the
    Applications tab.
    """

    def __init__(self, sheets_client):
        self.sheets = sheets_client
        self._cache: dict[str, dict] = {}  # threadId → {company, role, row}
        self._loaded = False

    def _ensure_loaded(self):
        """Lazy-load all thread mappings from the sheet on first access."""
        if self._loaded:
            return

        try:
            applications = self.sheets.get_all_applications()
            for i, app in enumerate(applications):
                thread_id = app.get("thread_id", "")
                if thread_id:
                    self._cache[thread_id] = {
                        "company": app.get("company", ""),
                        "role": app.get("role", ""),
                        "row": i + 2,  # 1-indexed, skip header
                    }
        except Exception as e:
            print(f"[ThreadStore] Warning: Could not load thread mappings: {e}")

        self._loaded = True

    def lookup(self, thread_id: str) -> Optional[dict]:
        """Look up an application by Gmail thread ID.

        Returns:
            dict with keys {company, role, row} if found, else None.
        """
        if not thread_id:
            return None

        self._ensure_loaded()
        return self._cache.get(thread_id)

    def register(self, thread_id: str, company: str, role: str, row: int):
        """Register a thread ID → application mapping.

        Call this after successfully processing an Applied email.
        """
        if not thread_id:
            return

        self._cache[thread_id] = {
            "company": company,
            "role": role,
            "row": row,
        }

        # Persist to sheet (Thread ID is column I, index 9)
        try:
            self.sheets.service.spreadsheets().values().update(
                spreadsheetId=self.sheets.spreadsheet_id,
                range=f"Applications!I{row}",
                valueInputOption="RAW",
                body={"values": [[thread_id]]},
            ).execute()
        except Exception as e:
            print(f"[ThreadStore] Warning: Could not persist thread ID for row {row}: {e}")

    def invalidate(self):
        """Force re-load from sheet on next access."""
        self._cache.clear()
        self._loaded = False
