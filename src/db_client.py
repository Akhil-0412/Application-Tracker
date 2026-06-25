"""SQLite database client for tracking job applications."""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import PROJECT_ROOT, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN

DB_PATH = PROJECT_ROOT / "tracker.db"

class DBClient:
    """Handles all interactions with the local SQLite database.
    
    Replaces the previous SheetsClient to provide ACID guarantees and 
    prevent row decoupling.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def get_connection(self):
        """Get a configured connection (Turso if configured, else SQLite)."""
        if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
            from .turso_client import TursoConnection
            return TursoConnection(TURSO_DATABASE_URL, TURSO_AUTH_TOKEN)
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for concurrent read/writes between script and dashboard
            conn.execute("PRAGMA journal_mode=WAL;")
            return conn

    def _init_db(self):
        """Ensure the applications table exists."""
        with self.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    applied_date TEXT,
                    last_updated TEXT,
                    email_subject TEXT,
                    detection_reason TEXT,
                    action_link TEXT,
                    thread_id TEXT,
                    interview_round TEXT,
                    timeline TEXT
                )
            ''')

    def get_all_applications(self) -> list[dict]:
        """Get all applications, sorted by last updated (newest first)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM applications ORDER BY last_updated DESC")
                rows = cursor.fetchall()
                
                applications = []
                for row in rows:
                    app = dict(row)
                    # Preserve 'row_index' alias for backwards compatibility in UI/Tracker
                    app['row_index'] = app['id']
                    applications.append(app)
                return applications
        except Exception as e:
            print(f"Error getting applications from DB: {e}")
            return []

    def add_application(
        self,
        company: str,
        role: str,
        status: str,
        applied_date: datetime,
        email_subject: str = "",
        detection_reason: str = "",
        action_link: str = "",
        thread_id: str = "",
        interview_round: str = "",
        timeline: str = "[]",
    ) -> tuple[bool, str]:
        """Add a new application to the database."""
        try:
            # Store dates as ISO 8601 strings for proper sorting
            iso_date = applied_date.isoformat(timespec='seconds')
            
            # Ensure timeline is valid JSON string
            if not isinstance(timeline, str):
                timeline = json.dumps(timeline)

            with self.get_connection() as conn:
                cursor = conn.execute('''
                    INSERT INTO applications (
                        company, role, status, applied_date, last_updated,
                        email_subject, detection_reason, action_link, thread_id,
                        interview_round, timeline
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    company, role, status, iso_date, iso_date,
                    email_subject, detection_reason, action_link, thread_id,
                    interview_round, timeline
                ))
                new_id = cursor.lastrowid
            # The row index returned is now the database ID
            return True, f"Added {company} - {role} at ID {new_id}"
        except Exception as e:
            print(f"Failed to add application: {e}")
            return False, f"Failed to add application: {e}"

    def update_application(
        self,
        row_index: int,
        status: str,
        last_updated: str,
        email_subject: str = None,
        detection_reason: str = None,
        action_link: str = None,
        company: str = None,
        role: str = None,
        thread_id: str = None,
        interview_round: str = None,
        timeline: str = None,
    ) -> tuple[bool, str]:
        """Update an existing application in the database."""
        updates = []
        params = []
        
        updates.append("status = ?")
        params.append(status)
        
        updates.append("last_updated = ?")
        params.append(last_updated)
        
        if email_subject is not None:
            updates.append("email_subject = ?")
            params.append(email_subject)
        if detection_reason is not None:
            updates.append("detection_reason = ?")
            params.append(detection_reason)
        if action_link is not None:
            updates.append("action_link = ?")
            params.append(action_link)
        if company is not None:
            updates.append("company = ?")
            params.append(company)
        if role is not None:
            updates.append("role = ?")
            params.append(role)
        if thread_id is not None:
            updates.append("thread_id = ?")
            params.append(thread_id)
        if interview_round is not None:
            updates.append("interview_round = ?")
            params.append(interview_round)
        if timeline is not None:
            if not isinstance(timeline, str):
                timeline = json.dumps(timeline)
            updates.append("timeline = ?")
            params.append(timeline)
            
        params.append(row_index) # db id
        
        query = f"UPDATE applications SET {', '.join(updates)} WHERE id = ?"
        try:
            with self.get_connection() as conn:
                conn.execute(query, params)
            return True, "Updated successfully"
        except Exception as e:
            print(f"Failed to update application: {e}")
            return False, f"Failed to update application: {e}"

    def find_application(self, company: str, role: str) -> Optional[tuple[int, dict]]:
        """Find an application by company and role."""
        applications = self.get_all_applications()

        for app in applications:
            if app["company"].lower() == company.lower():
                # If either role is unknown, treat as same application
                if (
                    app["role"].lower() == role.lower() or
                    app["role"].lower() == "unknown position" or
                    role.lower() == "unknown position"
                ):
                    return (app["id"], app)
        return None
        
    def find_application_by_company(self, company: str) -> Optional[tuple[int, dict]]:
        """Find an application strictly by company name."""
        applications = self.get_all_applications()
        for app in applications:
            if app["company"].lower() == company.lower():
                return (app["id"], app)
        return None

    def delete_application(self, db_id: int) -> bool:
        """Delete an application from the database."""
        try:
            with self.get_connection() as conn:
                conn.execute("DELETE FROM applications WHERE id = ?", (db_id,))
            return True
        except Exception as e:
            print(f"Failed to delete application {db_id}: {e}")
            return False
