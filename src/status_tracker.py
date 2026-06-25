"""Status tracker for managing application progression.

Integrates the CorrelationEngine to resolve vague emails (especially rejections)
to existing tracked applications, preventing orphan 'Unknown' rows.
"""

from datetime import datetime
from typing import Optional

from .db_client import DBClient
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

    def __init__(self, db_client: DBClient, correlation_engine=None, thread_store=None):
        self.db = db_client
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
                    row_index=match.db_id,
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
        existing = self.db.find_application(company, role)

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
            timeline = [{"stage": status, "date": email_date.strftime("%Y-%m-%d")}]
            import json
            timeline_str = json.dumps(timeline)

            added, reason = self.db.add_application(
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
                        # We also need to add the initial timeline via update since add doesn't support the kwarg yet
                        self.sheets.update_application(row_num, status, datetime.now().strftime("%Y-%m-%d %H:%M"), timeline=timeline_str)
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


        # Compute Interview Round updates
        interview_round = existing_app.get("interview_round", "")
        if new_status == "Interview":
            import re
            
            # Extract current round (e.g. "1/1" -> current_idx=1, total_rounds=1)
            # Or if empty string, it's 1/1
            current_idx = 1
            total_rounds = 1
            if interview_round and "/" in interview_round:
                try:
                    parts = interview_round.split("/")
                    current_idx = int(parts[0])
                    total_rounds = int(parts[1])
                except ValueError:
                    pass

            if existing_status == "Interview":
                # Already in interview. Is this a new round being scheduled?
                # Look for clues of a new/next round, or assume an update is an increment.
                # E.g. Subject contains "Round 2", "Final", "Next stage"
                text = f"{email_subject}".lower()
                if any(x in text for x in ["round 2", "second", "next", "final", "further"]):
                    total_rounds += 1
                    current_idx = total_rounds
                elif "scheduled" in text or "invite" in text:
                     # A new invite when we are already in interview = next round
                     total_rounds += 1
                     current_idx = total_rounds
                # Otherwise keep same
                interview_round = f"{current_idx}/{total_rounds}"
            else:
                # First interview!
                interview_round = "1/1"

        # Compute Timeline updates
        import json
        timeline_str = existing_app.get("timeline", "[]")
        try:
            timeline = json.loads(timeline_str)
        except json.JSONDecodeError:
            timeline = []
            
        stage_name = new_status
        if new_status == "Interview":
             stage_name = f"Interview R{interview_round}"
             
        # Only append to timeline if the status/stage changed
        append_to_timeline = False
        if not timeline:
            append_to_timeline = True
        elif timeline[-1].get("stage") != stage_name:
            append_to_timeline = True

        if append_to_timeline:
            timeline.append({"stage": stage_name, "date": email_date.strftime("%Y-%m-%d")})
            timeline_str = json.dumps(timeline)
        else:
            timeline_str = None # Don't update if nothing changed

        # If email is newer, update based on status
        # Rejected and Offer statuses always takes precedence
        if new_status == "Rejected":
            success = self.db.update_application(
                row_index=row_index,
                status="Rejected",
                last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                email_subject=email_subject,
                company=updated_company,
                role=updated_role,
                action_link=action_link,
                thread_id=thread_id,
                timeline=timeline_str
            )
            return success, "Marked as Rejected"


        if new_status == "Offer":
            success = self.db.update_application(
                row_index=row_index,
                status="Offer",
                last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                email_subject=email_subject,
                company=updated_company,
                role=updated_role,
                action_link=action_link,
                thread_id=thread_id,
                interview_round=interview_round if interview_round else None,
                timeline=timeline_str
            )
            return success, "Marked as Offer"


        # Otherwise, only upgrade status
        if self._should_update_status(existing_status, new_status, action_link) or updated_company or updated_role or (new_status == "Interview" and append_to_timeline):
             # Even if status matches, if we have better metadata, update!
            target_status = new_status if self._should_update_status(existing_status, new_status, action_link) else existing_status
            
            success = self.db.update_application(
                row_index=row_index,
                status=target_status,
                last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                email_subject=email_subject,
                company=updated_company,
                role=updated_role,
                action_link=action_link,
                thread_id=thread_id,
                interview_round=interview_round if new_status == "Interview" else None,
                timeline=timeline_str
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
        applications = self.db.get_all_applications()

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
