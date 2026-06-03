"""Status tracker for managing application progression.

Integrates the CorrelationEngine to resolve vague emails (especially rejections)
to existing tracked applications, preventing orphan 'Unknown' rows.
"""

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

    def __init__(self, sheets_client: SheetsClient, correlation_engine=None, thread_store=None):
        self.sheets = sheets_client
        self.correlation_engine = correlation_engine
        self.thread_store = thread_store
        self._cache = {}  # Cache of known applications

    def process_classification(
        self,
        result: ClassificationResult,
        email_date: datetime,
        email_subject: str,
        detection_reason: str = "",
        force_update: bool = False,
        email: dict = None,
    ) -> tuple[bool, str]:
        """
        Process a classification result and update the sheet if needed.

        Args:
            result: Classification result from AI or phrase classifier
            email_date: Date of the email
            email_subject: Subject line of the email
            detection_reason: Why this email was detected as an application
            force_update: If True, skip date-based deduplication
            email: The full email dict (for correlation — contains thread_id, sender_domain, etc.)

        Returns:
            (success, reason)
        """

        company = result.company
        role = result.role
        status = result.status
        action_link = result.action_link or ""
        thread_id = email.get("thread_id", "") if email else ""

        # ─── CORRELATION LOGIC ───────────────────────────────────────────
        # If company or role is unknown/vague, try to correlate to an
        # existing application using multiple signals before creating
        # a new row.
        is_unknown_company = company.lower() in ("unknown", "unknown company", "")
        is_unknown_role = role.lower() in ("unknown", "unknown position", "")

        correlated = False
        if (is_unknown_company or is_unknown_role) and self.correlation_engine and email:
            match = self.correlation_engine.correlate(
                email=email,
                classification_company=company,
                classification_role=role,
            )
            if match and match.confidence >= 0.6:
                # Override with correlated values
                company = match.company
                role = match.role
                correlated = True
                detection_reason = (
                    f"Correlated via {match.signal} (conf={match.confidence:.2f}): "
                    f"{match.reasoning}"
                )
                print(f"      [CORRELATED] {match.signal}: {company} | {role} (conf={match.confidence:.2f})")

                # Directly update the matched row
                return self._handle_update(
                    row_index=match.row_index,
                    existing_app={"company": company, "role": role, "status": ""},
                    new_status=status,
                    email_date=email_date,
                    email_subject=email_subject,
                    new_company=company if is_unknown_company else None,
                    new_role=role if is_unknown_role else None,
                    action_link=action_link,
                    force_update=force_update,
                    thread_id=thread_id,
                )

        # ─── STANDARD LOGIC (unchanged) ──────────────────────────────────
        # Check if this is a new application or update
        existing = self.sheets.find_application(company, role)

        if existing:
            row_index, app = existing
            success, reason = self._handle_update(
                row_index, app, status, email_date, email_subject, company, role, action_link, force_update, thread_id=thread_id
            )
            # Register thread ID mapping for successful updates
            if success and thread_id and self.thread_store:
                self.thread_store.register(thread_id, company, role, row_index)
            return success, reason
        else:
            # New application — check if it's an unmatched rejection
            if (is_unknown_company and is_unknown_role) and status == "Rejected":
                # Flag as unmatched rather than creating an orphan row
                print(f"      [WARN] ⚠️ Unmatched rejection: '{email_subject}' — skipping orphan row")
                return False, "⚠️ Unmatched rejection (no correlation found, skipped orphan row)"

            # Create new application
            added, reason = self.sheets.add_application(
                company=company,
                role=role,
                status=status,
                applied_date=email_date,
                email_subject=email_subject,
                detection_reason=detection_reason,
                action_link=action_link,
                thread_id=thread_id,
            )
            if added:
                # Register thread ID for the new application
                if thread_id and self.thread_store:
                    # Parse the row number from the reason string
                    try:
                        row_num = int(reason.split("row ")[1])
                        self.thread_store.register(thread_id, company, role, row_num)
                    except (IndexError, ValueError):
                        pass
                return True, "Created new application"
            return False, f"Failed to create application: {reason}"
        
    def _handle_update(
        self,
        row_index: int,
        existing_app: dict,
        new_status: str,
        email_date: datetime,
        email_subject: str,
        new_company: str = None, 
        new_role: str = None,
        action_link: str = "",
        force_update: bool = False,
        thread_id: str = ""
    ) -> tuple[bool, str]:


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

        # If this email is older, skip (unless forced)
        if not force_update and email_date_naive < existing_date:
            return False, f"Email older than last update ({existing_date})"


        # Check if we should refine Company/Role
        updated_company = None
        updated_role = None
        
        if new_company and "unknown" in existing_app.get("company", "").lower() and "unknown" not in new_company.lower():
            updated_company = new_company
            
        if new_role and "unknown" in existing_app.get("role", "").lower() and "unknown" not in new_role.lower():
            updated_role = new_role


        # If email is newer, update based on status
        # Rejected and Offer statuses always takes precedence
        if new_status == "Rejected":
            success = self.sheets.update_application(
                row_index=row_index,
                status="Rejected",
                last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                email_subject=email_subject,
                company=updated_company,
                role=updated_role,
                action_link=action_link,
                thread_id=thread_id
            )
            return success, "Marked as Rejected"


        if new_status == "Offer":
            success = self.sheets.update_application(
                row_index=row_index,
                status="Offer",
                last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                email_subject=email_subject,
                company=updated_company,
                role=updated_role,
                action_link=action_link,
                thread_id=thread_id
            )
            return success, "Marked as Offer"


        # Otherwise, only upgrade status
        if self._should_update_status(existing_status, new_status, action_link) or updated_company or updated_role:
             # Even if status matches, if we have better metadata, update!
            target_status = new_status if self._should_update_status(existing_status, new_status, action_link) else existing_status
            
            success = self.sheets.update_application(
                row_index=row_index,
                status=target_status,
                last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                email_subject=email_subject,
                company=updated_company,
                role=updated_role,
                action_link=action_link,
                thread_id=thread_id
            )
            return success, f"Updated status to {target_status}"




        return False, "No status update needed"


    def _should_update_status(self, current: str, new: str, action_link: str = "") -> bool:
        """Determine if we should update from current to new status."""
        current_priority = self.STATUS_PRIORITY.get(current, 0)
        new_priority = self.STATUS_PRIORITY.get(new, 0)

        # Always update if new is higher priority
        # Also update if current is Rejected but new is Interview/Offer (re-engagement/mistake correction)
        # Note: Rejected is 0, so any status > 0 updates it IF the email is newer (handled in _handle_update logic check above? No, wait)
        
        # logic in _handle_update: if new_status == "Rejected" OR should_update_status...
        # Here we just compare priorities.
        if action_link:
             return True # If there's a link, we want to update it
        
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
