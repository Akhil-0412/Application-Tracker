"""Junk memory filter for Application Tracker."""

import json
from pathlib import Path
from src.config import CREDENTIALS_DIR

JUNK_FILE_PATH = CREDENTIALS_DIR / "junk_memory.json"

class JunkFilter:
    """Manages the junk memory to filter out non-application emails."""

    @staticmethod
    def _load_junk() -> dict:
        if not JUNK_FILE_PATH.exists():
            return {"threads": [], "senders": []}
        try:
            with open(JUNK_FILE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {"threads": [], "senders": []}

    @staticmethod
    def _save_junk(data: dict):
        JUNK_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(JUNK_FILE_PATH, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def add_junk(cls, thread_id: str = "", sender_email: str = ""):
        """Add a thread or sender to the junk memory."""
        data = cls._load_junk()
        
        if thread_id and thread_id not in data["threads"]:
            data["threads"].append(thread_id)
            
        if sender_email and sender_email not in data["senders"]:
            data["senders"].append(sender_email)
            
        cls._save_junk(data)

    @classmethod
    def is_junk(cls, thread_id: str, sender_email: str) -> bool:
        """Check if an email is flagged as junk."""
        data = cls._load_junk()
        if thread_id and thread_id in data["threads"]:
            return True
        if sender_email and sender_email in data["senders"]:
            return True
        return False
