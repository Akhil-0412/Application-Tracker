"""Thread-to-application mapping store for email correlation.

Maps Gmail thread IDs to tracked applications so that follow-up emails
(rejections, interview invites, etc.) in the same thread can be instantly
correlated to the correct application — even when they don't mention the
company or role.
"""

from typing import Optional


class ThreadStore:
    """Maps Gmail threadId → (company, role, db_id).

    Uses an in-memory cache backed by the SQLite database for persistence.
    """

    def __init__(self, db_client):
        self.db = db_client
        self._cache: dict[str, dict] = {}  # threadId → {company, role, db_id}
        self._loaded = False

    def _ensure_loaded(self):
        """Lazy-load all thread mappings from the database on first access."""
        if self._loaded:
            return

        try:
            applications = self.db.get_all_applications()
            for app in applications:
                thread_id = app.get("thread_id", "")
                if thread_id:
                    self._cache[thread_id] = {
                        "company": app.get("company", ""),
                        "role": app.get("role", ""),
                        "db_id": app.get("id"),
                    }
        except Exception as e:
            print(f"[ThreadStore] Warning: Could not load thread mappings: {e}")

        self._loaded = True

    def lookup(self, thread_id: str) -> Optional[dict]:
        """Look up an application by Gmail thread ID.

        Returns:
            dict with keys {company, role, db_id} if found, else None.
        """
        if not thread_id:
            return None

        self._ensure_loaded()
        return self._cache.get(thread_id)

    def register(self, thread_id: str, company: str, role: str, db_id: int):
        """Register a thread ID → application mapping.

        Call this after successfully processing an Applied email.
        Note: Database persistence of thread_id is handled by DBClient.
        """
        if not thread_id:
            return

        self._cache[thread_id] = {
            "company": company,
            "role": role,
            "db_id": db_id,
        }

    def invalidate(self):
        """Force re-load from database on next access."""
        self._cache.clear()
        self._loaded = False
