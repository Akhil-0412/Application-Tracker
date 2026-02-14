"""Gmail API client for fetching job application emails."""

import base64
import re
from datetime import datetime, timedelta
from typing import Optional
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import (
    ALL_SCOPES,
    TOKEN_PATH,
    CREDENTIALS_PATH,
    IGNORED_SENDERS,
    NEGATIVE_SUBJECTS,
    POSITIVE_PHRASES,
    JOB_EMAIL_QUERY,
)


class GmailClient:
    """Client for interacting with Gmail API."""

    def __init__(self):
        self.service = None
        self.creds = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Gmail API using OAuth2."""
        if TOKEN_PATH.exists():
            self.creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), ALL_SCOPES)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not CREDENTIALS_PATH.exists():
                    raise FileNotFoundError(
                        f"credentials.json not found at {CREDENTIALS_PATH}. "
                        "Please download from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_PATH), ALL_SCOPES
                )
                self.creds = flow.run_local_server(port=0)

            # Save credentials for future runs
            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_PATH, "w") as token:
                token.write(self.creds.to_json())

        self.service = build("gmail", "v1", credentials=self.creds)

    def _check_email(self, sender_email: str, subject: str, body: str = "") -> tuple[bool, str]:
        """
        Smart filtering logic that returns (should_keep, detection_reason).
        
        Returns:
            (True, reason) if email should be KEPT
            (False, reason) if email should be BLOCKED
        """
        sender_lower = sender_email.lower()
        subject_lower = subject.lower()
        body_lower = body.lower()
        combined = f"{subject_lower} {body_lower}"
        
        # Check ignored senders FIRST (these are always blocked)
        for ignored in IGNORED_SENDERS:
            if ignored in sender_lower:
                return (False, f"Blocked sender: {ignored}")
        
        # Check negative subjects
        for phrase in NEGATIVE_SUBJECTS:
            if phrase in subject_lower:
                # Check if a positive phrase overrides
                for pos_phrase in POSITIVE_PHRASES:
                    if pos_phrase in combined:
                        return (True, f"Kept: '{pos_phrase}' (overrode '{phrase}')")
                return (False, f"Blocked subject: {phrase}")
        
        # Check for POSITIVE phrases
        for phrase in POSITIVE_PHRASES:
            if phrase in combined:
                return (True, f"Matched: {phrase}")
        
        # Default: BLOCK if no positive signal found (strict filtering)
        return (False, "Blocked: no positive job signal")


    def get_messages(
        self,
        days_back: int = 7,
        max_results: int = 500,  # Increased from 100 to capture more emails
        after_date: Optional[datetime] = None
    ) -> list[dict]:
        """
        Fetch job application emails using JOB_EMAIL_QUERY from config.
        """
        # Build date query
        if after_date:
            date_cutoff = after_date.strftime('%Y/%m/%d')
        else:
            date_cutoff = (datetime.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')

        # Use the query from config.py (not hardcoded)
        query = f'after:{date_cutoff} {JOB_EMAIL_QUERY}'

        try:
            results = self.service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results
            ).execute()

            messages = results.get("messages", [])
            all_emails = []
            
            for msg in messages:
                email_data = self.get_message_details(msg["id"])
                if email_data:
                    # Smart filter: returns (should_keep, detection_reason)
                    should_keep, detection_reason = self._check_email(
                        email_data.get("sender_email", ""),
                        email_data.get("subject", ""),
                        email_data.get("body", "")
                    )
                    if should_keep:
                        email_data["detection_reason"] = detection_reason
                        all_emails.append(email_data)
                    
            return all_emails

        except Exception as e:
            print(f"Error fetching messages: {e}")
            return []

    def get_message_details(self, message_id: str) -> dict:
        """Get full details of a specific email."""
        try:
            message = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="full"
            ).execute()

            headers = message.get("payload", {}).get("headers", [])
            header_dict = {h["name"].lower(): h["value"] for h in headers}

            # Parse date
            date_str = header_dict.get("date", "")
            try:
                email_date = parsedate_to_datetime(date_str)
            except Exception:
                email_date = datetime.now()

            # Extract body and links using robust BS4 method
            body, action_links = self._extract_body_and_links(message.get("payload", {}))


            # Extract sender info
            from_header = header_dict.get("from", "")
            sender_email = self._extract_email(from_header)
            sender_domain = self._extract_domain(sender_email)

            return {
                "id": message_id,
                "subject": header_dict.get("subject", ""),
                "from": from_header,
                "sender_email": sender_email,
                "sender_domain": sender_domain,
                "date": email_date,
                "body": body,
                "action_links": action_links,
                "snippet": message.get("snippet", ""),

            }

        except Exception as e:
            print(f"Error getting message details: {e}")
            return {}

    def _extract_body_and_links(self, payload: dict) -> tuple[str, list[str]]:
        """
        Robustly extract text and ACTION LINKS from HTML/plain emails.
        Returns: (clean_text, list_of_urls)
        """
        def decode_part(part):
            if 'data' not in part.get('body', {}):
                return ""
            data = part['body']['data'].replace('-', '+').replace('_', '/')
            try:
                return base64.b64decode(data).decode('utf-8', errors='ignore')
            except Exception:
                return ""
        
        text = ""
        links = []

        # Helper to extract links from HTML
        def extract_action_links(html_content):
            found_links = []
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    text_content = a.get_text().strip().lower()
                    
                    # Keywords for action links
                    keywords = [
                        "start test", "start assessment", "take the test", "take test",
                        "coding challenge", "hackerrank", "codility", "codesignal",
                        "schedule interview", "schedule a call", "book a time",
                        "view application", "check status", "accept offer", "sign offer"
                    ]
                    
                    if any(k in text_content for k in keywords):
                        found_links.append(href)
            except Exception:
                pass
            return found_links

        # Try parts first
        if 'parts' in payload:
            for part in payload['parts']:
                mime = part.get('mimeType', '')
                if mime == 'text/plain':
                    text += decode_part(part) + "\n"
                elif mime == 'text/html':
                    html = decode_part(part)
                    if html:
                        # Extract links BEFORE stripping
                        links.extend(extract_action_links(html))
                        
                        # Strip HTML tags + clean whitespace
                        try:
                            soup = BeautifulSoup(html, 'html.parser')
                            text += ' '.join(soup.get_text().split()) + "\n"
                        except Exception:
                            text += self._html_to_text(html) + "\n"
        
        # Fallback to body if no parts or empty text
        if not text and 'body' in payload and 'data' in payload['body']:
            content = decode_part(payload)
            # If it looks like HTML, clean it
            if '<html' in content.lower() or '<body' in content.lower() or '<div' in content.lower():
                links.extend(extract_action_links(content))
                try:
                    soup = BeautifulSoup(content, 'html.parser')
                    text = ' '.join(soup.get_text().split())
                except Exception:
                    text = self._html_to_text(content)
            else:
                text = content
        
        return text.strip(), list(set(links))  # Dedup links

    def _extract_body(self, payload: dict) -> str:
        """Legacy wrapper for backward compatibility."""
        text, _ = self._extract_body_and_links(payload)
        return text


    def _html_to_text(self, html: str) -> str:
        """Simple HTML to text conversion (fallback)."""
        # Remove scripts and styles
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Replace br and p tags with newlines
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
        # Remove all other tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        # Decode HTML entities
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        return text

    def _extract_email(self, from_header: str) -> str:
        """Extract email address from From header."""
        match = re.search(r"<(.+?)>", from_header)
        if match:
            return match.group(1)
        if "@" in from_header:
            return from_header.strip()
        return ""

    def _extract_domain(self, email: str) -> str:
        """Extract domain from email address."""
        if "@" in email:
            return email.split("@")[1].split(".")[0].title()
        return ""

    def get_history_id(self) -> str:
        """Get current history ID for tracking new messages."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return profile.get("historyId", "")
        except Exception as e:
            print(f"Error getting history ID: {e}")
            return ""
