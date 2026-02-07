"""Status tracker for managing application progression."""

from datetime import datetime
from typing import Optional

from .sheets_client import SheetsClient
from .ai_classifier import ClassificationResult


class StatusTracker:
    """Tracks application status progression based on latest email."""

    # Status priority for comparison (higher = more advanced)
    STATUS_PRIORITY = {
        "Applied": 1,
        "Assessment": 2,
        "Interview": 3,
        "Offer": 4,     # Highest positive status
        "Rejected": 0,  # Rejected is final but lower priority for updates (handled specially)
    }

    def __init__(self, sheets_client: SheetsClient):
        self.sheets = sheets_client
        self._cache = {}  # Cache of known applications

    def process_classification(
        self,
        result: ClassificationResult,
        email_date: datetime,
        email_subject: str,
        detection_reason: str = ""
    ) -> bool:
        """
        Process a classification result and update the sheet if needed.

        Args:
            result: Classification result from AI or phrase classifier
            email_date: Date of the email
            email_subject: Subject line of the email
            detection_reason: Why this email was detected as an application

        Returns:
            True if application was added/updated
        """
        company = result.company
        role = result.role
        status = result.status

        # Check if this is a new application or update
        existing = self.sheets.find_application(company, role)

        if existing:
            row_index, app = existing
            return self._handle_update(
                row_index, app, status, email_date, email_subject
            )
        else:
            # New application
            return self.sheets.add_application(
                company=company,
                role=role,
                status=status,
                applied_date=email_date,
                email_subject=email_subject,
                detection_reason=detection_reason
            )

    def _handle_update(
        self,
        row_index: int,
        existing_app: dict,
        new_status: str,
        email_date: datetime,
        email_subject: str
    ) -> bool:
        """Handle updating an existing application."""
        existing_status = existing_app.get("status", "")
        last_updated_str = existing_app.get("last_updated", "")

        # Parse existing date
        try:
            existing_date = datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M")
        except Exception:
            existing_date = datetime.min

        # Normalize email_date to naive datetime for comparison
        try:
            if hasattr(email_date, 'tzinfo') and email_date.tzinfo is not None:
                email_date_naive = email_date.replace(tzinfo=None)
            else:
                email_date_naive = email_date
        except Exception:
            email_date_naive = datetime.now()

        # If this email is older, skip
        if email_date_naive < existing_date:
            return False

        # If email is newer, update based on status
        # Rejected and Offer statuses always takes precedence (it's final)
        # Rejection ALWAYS overrides if email is newer
        if new_status == "Rejected":
            return self.sheets.update_application(
                row_index=row_index,
                status="Rejected",
                last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                email_subject=email_subject
            )

        # Otherwise, only upgrade status
        if self._should_update_status(existing_status, new_status):
            return self.sheets.update_application(
                row_index=row_index,
                status=new_status,
                last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                email_subject=email_subject
            )


        return False

    def _should_update_status(self, current: str, new: str) -> bool:
        """Determine if we should update from current to new status."""
        current_priority = self.STATUS_PRIORITY.get(current, 0)
        new_priority = self.STATUS_PRIORITY.get(new, 0)

        # Always update if new is higher priority
        # Also update if current is Rejected but new is Interview/Offer (re-engagement/mistake correction)
        # Note: Rejected is 0, so any status > 0 updates it IF the email is newer (handled in _handle_update logic check above? No, wait)
        
        # logic in _handle_update: if new_status == "Rejected" OR should_update_status...
        # Here we just compare priorities.
        return new_priority >= current_priority

    def get_statistics(self) -> dict:
        """Get application statistics."""
        applications = self.sheets.get_all_applications()

        stats = {
            "total": len(applications),
            "Applied": 0,
            "Assessment": 0,
            "Interview": 0,
            "Offer": 0,
            "Rejected": 0,
        }

        for app in applications:
            status = app.get("status", "Applied")
            if status in stats:
                stats[status] += 1

        return stats
