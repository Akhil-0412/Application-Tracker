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

INSTRUCTIONS:
1. If this email is a status update (rejection, interview invite, assessment, offer) for one
   of the EXISTING APPLICATIONS listed above, return the EXACT company and role from that
   existing application. Set "matched_existing" to true.
2. If this is a NEW application confirmation (not matching any existing application), extract
   the company and role directly from the email. Set "matched_existing" to false.
3. If the email doesn't mention a company name, use the sender domain "{sender_domain}" as a hint
   and check if it matches any existing application's company.
4. For STATUS, choose exactly one of: Applied | Assessment | Interview | Offer | Rejected

STATUS DETERMINATION GUIDE:
- Applied = application received / confirmed / submitted
- Assessment = coding challenge / test / take-home assignment
- Interview = interview scheduled / phone screen / video call
- Offer = job offer extended / congratulations on being selected
- Rejected = not moving forward / unfortunately / regret / another candidate

Return ONLY valid JSON (no markdown, no explanation):
{{"company": "exact company name", "role": "exact job title", "status": "Applied|Assessment|Interview|Offer|Rejected", "confidence": 0.9, "reasoning": "brief reason for classification", "matched_existing": true, "matched_index": null}}"""

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
                f"  - Row {i+1}: {app.get('company', '?')} | {app.get('role', '?')} | Status: {app.get('status', '?')} | Applied: {app.get('applied_date', '?')}"
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

    def _build_result(self, data: dict, email: dict, model: str) -> ClassificationResult:
        company = str(data.get("company", "")).strip()
        role = str(data.get("role", "")).strip()
        status = str(data.get("status", "Applied")).strip()

        if not company or company.lower() in {"unknown", "n/a", "none", ""}:
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
