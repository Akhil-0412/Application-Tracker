"""Correlation engine for matching vague emails to existing tracked applications.

When a rejection (or status update) email arrives without a clear company/role,
this engine uses multiple signals to find the correct existing application:

Signal 1: Thread ID Match (highest confidence — exact correlation)
Signal 2: Sender Domain Match (high confidence if unique company)
Signal 3: AI Cross-Reference (medium confidence — uses LLM to match)
Signal 4: Temporal Proximity (tiebreaker — recent applications score higher)
"""

import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional


@dataclass
class CorrelationMatch:
    """Result of a correlation attempt."""
    row_index: int
    company: str
    role: str
    confidence: float  # 0.0 - 1.0
    signal: str  # Which signal produced the match
    reasoning: str


class CorrelationEngine:
    """Multi-signal engine for correlating emails to existing applications."""

    def __init__(self, sheets_client, thread_store, ai_classifier=None):
        self.sheets = sheets_client
        self.thread_store = thread_store
        self.ai_classifier = ai_classifier

    def correlate(
        self,
        email: dict,
        classification_company: str,
        classification_role: str,
    ) -> Optional[CorrelationMatch]:
        """Attempt to correlate an email to an existing tracked application.

        Tries signals in priority order:
        1. Thread ID match (instant, exact)
        2. Sender domain match
        3. AI cross-reference
        4. Temporal proximity (tiebreaker for domain matches)

        Args:
            email: The full email dict (with thread_id, sender_domain, body, etc.)
            classification_company: Company extracted by classifier (may be "Unknown")
            classification_role: Role extracted by classifier (may be "Unknown")

        Returns:
            CorrelationMatch if a match is found, else None.
        """
        thread_id = email.get("thread_id", "")
        sender_domain = email.get("sender_domain", "")
        sender_email = email.get("sender_email", "")

        # Signal 1: Thread ID Match
        match = self._match_by_thread(thread_id)
        if match:
            return match

        # Get all existing applications for subsequent signals
        existing_apps = self.sheets.get_all_applications()
        if not existing_apps:
            return None

        # Signal 2: Sender Domain Match
        match = self._match_by_domain(
            sender_domain, sender_email, existing_apps, email
        )
        if match:
            return match

        # Signal 3: AI Cross-Reference (only if AI classifier is available)
        match = self._match_by_ai(email, existing_apps)
        if match:
            return match

        return None

    def _match_by_thread(self, thread_id: str) -> Optional[CorrelationMatch]:
        """Signal 1: Exact thread ID match."""
        if not thread_id:
            return None

        thread_match = self.thread_store.lookup(thread_id)
        if thread_match:
            return CorrelationMatch(
                row_index=thread_match["row"],
                company=thread_match["company"],
                role=thread_match["role"],
                confidence=1.0,
                signal="thread_id",
                reasoning=f"Exact thread match (threadId={thread_id[:12]}...)",
            )
        return None

    def _match_by_domain(
        self,
        sender_domain: str,
        sender_email: str,
        existing_apps: list,
        email: dict,
    ) -> Optional[CorrelationMatch]:
        """Signal 2: Match by sender email domain against known companies."""
        if not sender_domain and not sender_email:
            return None

        # Extract the raw domain from sender email for matching
        raw_domain = ""
        if sender_email and "@" in sender_email:
            raw_domain = sender_email.split("@")[1].lower()

        sender_domain_lower = sender_domain.lower() if sender_domain else ""

        # Find all applications whose company name could match this domain
        candidates = []
        for i, app in enumerate(existing_apps):
            company = app.get("company", "").strip()
            if not company or company.lower() in ("unknown", "unknown company"):
                continue

            company_lower = company.lower()
            row = i + 2  # 1-indexed, skip header

            # Check if company name appears in the domain
            # e.g., company="Amazon" matches domain="amazon.com"
            # or company="J&J" and domain contains "jnj"
            company_normalized = re.sub(r'[^a-z0-9]', '', company_lower)
            domain_normalized = re.sub(r'[^a-z0-9]', '', raw_domain)

            if (
                company_normalized in domain_normalized
                or domain_normalized.startswith(company_normalized)
                or sender_domain_lower == company_lower
            ):
                candidates.append((row, app))

        if not candidates:
            return None

        if len(candidates) == 1:
            row, app = candidates[0]
            return CorrelationMatch(
                row_index=row,
                company=app["company"],
                role=app["role"],
                confidence=0.85,
                signal="domain_unique",
                reasoning=f"Sender domain '{raw_domain}' matches unique company '{app['company']}'",
            )

        # Multiple candidates at the same company — use temporal proximity
        # A rejection 1-4 weeks after applying is most likely
        best = self._pick_best_by_time(candidates, email)
        if best:
            row, app = best
            return CorrelationMatch(
                row_index=row,
                company=app["company"],
                role=app["role"],
                confidence=0.7,
                signal="domain_temporal",
                reasoning=f"Best temporal match among {len(candidates)} apps at '{app['company']}'",
            )

        return None

    def _pick_best_by_time(
        self, candidates: list[tuple[int, dict]], email: dict
    ) -> Optional[tuple[int, dict]]:
        """Pick the most likely candidate using temporal proximity.

        Rejections typically arrive 1-6 weeks after applying.
        Applications that are already 'Rejected' are deprioritized.
        """
        email_date = email.get("date", datetime.now())
        if hasattr(email_date, "tzinfo") and email_date.tzinfo is not None:
            email_date = email_date.replace(tzinfo=None)

        scored = []
        for row, app in candidates:
            # Skip already rejected apps
            if app.get("status", "").lower() == "rejected":
                continue

            # Parse applied date
            applied_str = app.get("applied_date", "")
            try:
                applied_date = datetime.strptime(applied_str, "%Y-%m-%d")
            except Exception:
                applied_date = datetime.min

            if applied_date == datetime.min:
                scored.append((0.1, row, app))
                continue

            # Days between application and this email
            days_diff = (email_date - applied_date).days

            # Sweet spot: 7-42 days (1-6 weeks) after applying
            if 0 <= days_diff <= 7:
                score = 0.7
            elif 7 < days_diff <= 42:
                score = 0.9
            elif 42 < days_diff <= 90:
                score = 0.6
            elif days_diff > 90:
                score = 0.3
            else:
                score = 0.1  # negative days_diff (future date?)

            scored.append((score, row, app))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_row, best_app = scored[0]
        return (best_row, best_app)

    def _match_by_ai(
        self, email: dict, existing_apps: list
    ) -> Optional[CorrelationMatch]:
        """Signal 3: Use AI to cross-reference the email against existing applications."""
        if not self.ai_classifier or not self.ai_classifier.client:
            return None

        try:
            # Build a compact list of existing apps for the AI
            apps_summary = []
            for i, app in enumerate(existing_apps):
                company = app.get("company", "Unknown")
                role = app.get("role", "Unknown")
                status = app.get("status", "")
                if company.lower() not in ("unknown", "unknown company"):
                    apps_summary.append(
                        f"Row {i+2}: {company} | {role} | {status}"
                    )

            if not apps_summary:
                return None

            # Ask the AI to match
            apps_text = "\n".join(apps_summary[:30])
            body_snippet = email.get("body", "")[:3000]
            subject = email.get("subject", "")
            sender = email.get("from", "")

            prompt = f"""Given this email and the list of tracked job applications below,
determine which application (if any) this email relates to.

EMAIL:
Subject: {subject}
From: {sender}
Body (first 3000 chars):
{body_snippet}

TRACKED APPLICATIONS:
{apps_text}

If this email is a status update (rejection, interview, assessment, offer) for one of
the tracked applications, return the row number. If it doesn't match any, return null.

Return ONLY valid JSON:
{{"matched_row": <row_number_or_null>, "company": "matched company", "role": "matched role", "confidence": 0.8, "reasoning": "brief reason"}}"""

            for model in self.ai_classifier.MODELS[:2]:  # Try only top 2 models to save API calls
                try:
                    response = self.ai_classifier.client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "Match emails to tracked job applications. Return ONLY valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.0,
                        max_tokens=200,
                    )

                    content = response.choices[0].message.content
                    if not content:
                        continue

                    data = self.ai_classifier._parse_json(content)
                    if not data:
                        continue

                    matched_row = data.get("matched_row")
                    if matched_row and isinstance(matched_row, (int, float)):
                        matched_row = int(matched_row)
                        company = str(data.get("company", "")).strip()
                        role = str(data.get("role", "")).strip()
                        conf = float(data.get("confidence", 0.7))

                        if company and role:
                            return CorrelationMatch(
                                row_index=matched_row,
                                company=company,
                                role=role,
                                confidence=min(conf, 0.8),  # Cap at 0.8 for AI matches
                                signal="ai_crossref",
                                reasoning=f"AI matched to row {matched_row}: {data.get('reasoning', '')}",
                            )
                    break  # Got a valid response (even if no match), stop trying models

                except Exception as e:
                    print(f"[CorrelationEngine] AI model {model} failed: {e}")
                    continue

        except Exception as e:
            print(f"[CorrelationEngine] AI cross-reference failed: {e}")

        return None
