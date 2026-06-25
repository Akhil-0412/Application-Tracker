"""AI-powered email classification using Groq with model fallback and phrase fallback."""

import json
import re
from dataclasses import dataclass
from typing import Optional

from .config import GROQ_API_KEY


@dataclass
class ClassificationResult:
    """Result of email classification."""
    company: str
    role: str
    status: str  # Applied, Assessment, Interview, Offer, Rejected
    confidence: float  # 0.0 - 1.0
    reasoning: str
    source: str  # "ai" or "phrases"
    action_link: Optional[str] = None


class AIClassifier:
    """Groq-powered email classifier with model + phrase fallback."""

    # Best → worst (practical)
    MODELS = [
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        "qwen/qwen3-32b",
        "llama-3.1-8b-instant",
    ]

    CLASSIFICATION_PROMPT = """Analyze this job application email and extract information.

EXISTING TRACKED APPLICATIONS (from the user's tracking sheet):
{existing_apps}

EMAIL TO CLASSIFY:
Subject: {subject}
From: {sender}
Sender Domain: {sender_domain}
Body:
{body}

COMPANY NAME EXTRACTION (CRITICAL - follow this order strictly):
1. FIRST check the "From" header above. The display name before the email address usually
   contains the company name (e.g. "Motorola Solutions - Workday" → company is "Motorola Solutions",
   "Resolutiion Hiring Team" → company is "Resolutiion"). Strip suffixes like "Hiring Team",
   "Careers", "Talent", "HR", "- Workday", "Recruiting".
2. If the From header is generic (e.g. "no-reply"), check the email body for phrases like
   "at [Company]", "here at [Company]", "joining [Company]", "interest in [Company]".
3. If still unclear, use the sender domain "{sender_domain}" as the company name.
4. NEVER use random phrases from the email body as a company name. The company must be a
   proper noun / actual organization name.

ROLE EXTRACTION:
- Look for explicit job titles in the email (e.g. "AI Engineer", "Software Engineer, Frontend").
- Use the EXACT title as written in the email, not a paraphrase.

EXISTING APPLICATION MATCHING:
1. If this email is a status update for one of the EXISTING APPLICATIONS listed above,
   return the EXACT company and role from that existing entry. Set "matched_existing" to true.
2. If this is a NEW application, extract company and role as described above.
   Set "matched_existing" to false.

STATUS - choose exactly one of: Applied | Assessment | Interview | Offer | Rejected
- Applied = application received / confirmed / submitted
- Assessment = coding challenge / test / take-home assignment
- Interview = interview scheduled / phone screen / video call
- Offer = job offer extended / congratulations on being selected
- Rejected = not moving forward / unfortunately / regret / another candidate

Return ONLY valid JSON (no markdown, no explanation):
{{"company": "exact company name", "role": "exact job title", "status": "Applied|Assessment|Interview|Offer|Rejected", "confidence": 0.9, "reasoning": "brief reason", "matched_existing": true, "matched_index": null}}"""

    def __init__(self):
        self.client = None
        self._init_client()

    def _init_client(self):
        if not GROQ_API_KEY:
            print("No GROQ_API_KEY found, falling back to phrase matching")
            return

        try:
            from groq import Groq
            self.client = Groq(api_key=GROQ_API_KEY)
        except ImportError as e:
            print(f"Failed to import Groq client: {e}")
            self.client = None

    def classify(self, email: dict, existing_apps: list = None) -> ClassificationResult:
        if self.client:
            try:
                result = self._ai_classify(email, existing_apps=existing_apps)
                if result:
                    return result
            except Exception as e:
                print(f"Groq classification failed: {e}")

        return self._phrase_classify(email)

    def _ai_classify(self, email: dict, existing_apps: list = None) -> Optional[ClassificationResult]:
        body = email.get("body", "")[:5000]
        subject = email.get("subject", "")
        sender = email.get("from", "")
        sender_domain = email.get("sender_domain", "")

        # Format existing applications for the prompt
        if existing_apps:
            # Limit to last 90 days and max 30 entries to control token usage
            apps_text = "\n".join(
                f"  - ID {app.get('id', '?')}: {app.get('company', '?')} | {app.get('role', '?')} | Status: {app.get('status', '?')} | Applied: {app.get('applied_date', '?')}"
                for i, app in enumerate(existing_apps[:30])
            )
        else:
            apps_text = "  (No existing applications available)"

        prompt = self.CLASSIFICATION_PROMPT.format(
            subject=subject,
            sender=sender,
            sender_domain=sender_domain,
            body=body,
            existing_apps=apps_text
        )

        for model in self.MODELS:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a job application email classifier. Extract job application details and match to existing tracked applications when possible. Return ONLY valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    max_tokens=400,
                )

                content = response.choices[0].message.content
                if not content:
                    continue

                data = self._parse_json(content)
                if not data:
                    continue

                return self._build_result(data, email, model)

            except Exception as e:
                print(f"[Groq] Model failed: {model} → {e}")
                continue

        return None

    def _parse_json(self, content: str) -> Optional[dict]:
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if not match:
                return None
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None

    # Words that are never valid company names - the LLM sometimes picks random phrases
    GARBAGE_COMPANY_NAMES = {
        "the", "a", "an", "our", "your", "hey", "hi", "dear", "us", "me", "we",
        "any updates", "the next", "about what", "your application", "us within",
        "the team", "our team", "the company", "the role", "the position",
        "unknown", "n/a", "none", "unknown company", "no company",
        "update", "status", "application", "confirmation", "notification",
        "hiring team", "talent team", "recruiting", "careers",
    }

    def _is_garbage_company(self, name: str) -> bool:
        """Check if extracted company name is a garbage phrase, not a real company."""
        if not name:
            return True
        lower = name.lower().strip()
        if lower in self.GARBAGE_COMPANY_NAMES:
            return True
        # If it's all lowercase common English words (not a proper noun), likely garbage
        common_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "up", "about", "into", "over", "after",
            "is", "are", "was", "were", "be", "been", "being", "have", "has",
            "had", "do", "does", "did", "will", "would", "could", "should",
            "may", "might", "can", "shall", "not", "no", "yes", "any", "all",
            "your", "our", "their", "my", "his", "her", "its", "us", "we",
            "what", "which", "who", "when", "where", "why", "how", "next",
            "within", "updates", "update", "application", "status", "team",
        }
        words = lower.split()
        if all(w in common_words for w in words):
            return True
        return False

    def _extract_company_from_subject(self, subject: str) -> str:
        """Extract company name from subject line using structured patterns."""
        if not subject:
            return ""
        patterns = [
            # "Visa - Application Update" / "RAC - Your application for..."
            r'^([A-Z][A-Za-z0-9\s&\'.\.\-]{1,30}?)\s*[-–]\s*(?:Application|Interview|Your|An update|Thanks|Thank)',
            # "Thank you for your application | Lendable"
            r'\|\s*([A-Z][A-Za-z0-9\s&\'.\.\-]{2,30}?)\s*$',
            # "Thank you for your application to Flatiron Health!" / "applying to Captur"
            r'(?:application to|applying to|interest in)\s+([A-Z][A-Za-z0-9\s&\'.\.\-]{2,40}?)(?:\s*[!,.\n]|$)',
            # "An update on your bet365 application" / "your MUBI application"
            r'(?:your|the)\s+([A-Z][A-Za-z0-9&\'.\.\-]{2,30}?)\s+application\b',
            # "Allica Bank - Thanks for your application!"
            r'^([A-Z][A-Za-z0-9\s&\'.\.\-]{2,30}?)\s*[-–]\s+(?:Thanks|Thank you|We)',
        ]
        for pattern in patterns:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                company = match.group(1).strip().rstrip('!')
                if company and not self._is_garbage_company(company):
                    return company
        return ""

    def _extract_company_from_sender(self, from_header: str) -> str:
        """Extract company name from the From header display name."""
        if not from_header:
            return ""
        # Extract display name (before the <email> part)
        match = re.match(r'^(.+?)\s*<', from_header)
        display_name = match.group(1).strip() if match else from_header.strip()
        if not display_name or '@' in display_name:
            return ""
        # Remove common suffixes
        suffixes_to_strip = [
            r'\s*-\s*Workday$', r'\s*-\s*Greenhouse$', r'\s*-\s*Lever$',
            r'\s*Hiring\s*Team$', r'\s*Careers?$', r'\s*Talent\s*(Acquisition)?$',
            r'\s*Recruiting$', r'\s*HR$', r'\s*People$', r'\s*Jobs?$',
            r'\s*Notifications?$', r'\s*via\s+\w+$',
        ]
        for suffix in suffixes_to_strip:
            display_name = re.sub(suffix, '', display_name, flags=re.IGNORECASE).strip()
        # Filter out generic names
        generic = {"no-reply", "noreply", "notifications", "mailer", "support", "info", "admin"}
        if display_name.lower() in generic:
            return ""
        return display_name

    def _build_result(self, data: dict, email: dict, model: str) -> ClassificationResult:
        company = str(data.get("company", "")).strip()
        role = str(data.get("role", "")).strip()
        status = str(data.get("status", "Applied")).strip()

        # Validate company name - fall back through sender name → subject → domain
        if self._is_garbage_company(company):
            # 1. Try From header display name
            sender_company = self._extract_company_from_sender(email.get("from", ""))
            if sender_company:
                company = sender_company
            else:
                # 2. Try subject line patterns
                subject_company = self._extract_company_from_subject(email.get("subject", ""))
                if subject_company:
                    company = subject_company
                else:
                    company = email.get("sender_domain", "Unknown")

        if status not in {"Applied", "Assessment", "Interview", "Offer", "Rejected"}:
            status = "Applied"

        if not role or role.lower() in {"unknown", "n/a", "none", ""}:
            role = self._extract_role_from_body(
                email.get("body", ""),
                email.get("subject", "")
            )

        # Get action links from email
        action_links = email.get("action_links", [])
        best_link = action_links[0] if action_links else None

        return ClassificationResult(
            company=company,
            role=role if role else "Unknown Position",
            status=status,
            confidence=float(data.get("confidence", 0.8)),
            reasoning=f"{data.get('reasoning', 'Groq classification')} (model={model})",
            source="ai",
            action_link=best_link
        )


    def _extract_role_from_body(self, body: str, subject: str) -> str:
        content = f"{subject} {body}"

        patterns = [
            r"position of\s+([A-Za-z\s\-\(\)]+?)(?:\s+at|\s+with|\.|,|\n)",
            r"application for (?:the\s+)?([A-Za-z\s\-\(\)]+?)(?:\s+position|\s+role|\s+at|\.|,|\n)",
            r"for the ([A-Za-z\s\-\(\)]+?)\s+position",
            r"([A-Za-z\s\-]+(?:Engineer|Developer|Scientist|Analyst|Manager|Intern|Designer|Architect)[A-Za-z\s\-\(\)]*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                role = re.sub(r"\s+", " ", match.group(1).strip())
                if 5 < len(role) < 80:
                    return role.title() if role.islower() else role

        return ""

    def _phrase_classify(self, email: dict) -> ClassificationResult:
        from .phrase_classifier import PhraseClassifier
        return PhraseClassifier().classify(email)
