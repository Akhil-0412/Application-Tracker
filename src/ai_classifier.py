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
    status: str  # Applied, Assessment, Interview, Rejected
    confidence: float  # 0.0 - 1.0
    reasoning: str
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

EXTRACT CAREFULLY:
1. COMPANY: The actual company name (not email platform like Workday, RippleHire)
2. ROLE: The EXACT job title mentioned
3. STATUS: Based on email content
4. ACTION_LINK: The most relevant action link from the email.

STATUS DETERMINATION:
- Applied = application received / confirmed
- Assessment = coding challenge / test
- Interview = interview scheduled
- Rejected = not moving forward

EMAIL:
Subject: {subject}
From: {sender}
Body:
{body}

Return ONLY valid JSON:
{{"company": "company name", "role": "exact job title", "status": "Applied|Assessment|Interview|Rejected", "confidence": 0.9, "reasoning": "brief reason", "action_link": "url"}}"""

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

    def classify(self, email: dict) -> ClassificationResult:
        if self.client:
            try:
                result = self._ai_classify(email)
                if result:
                    return result
            except Exception as e:
                print(f"Groq classification failed: {e}")

        return self._phrase_classify(email)

    def _ai_classify(self, email: dict) -> Optional[ClassificationResult]:
        body = email.get("body", "")[:3000]
        subject = email.get("subject", "")
        sender = email.get("from", "")

        prompt = self.CLASSIFICATION_PROMPT.format(
            subject=subject,
            sender=sender,
            body=body
        )

        for model in self.MODELS:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Extract job application details. Return ONLY valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    max_tokens=300,
                )

                content = response.choices[0].message.content
                if not content:
                    continue

                data = self._parse_json(content)
                if not data:
                    continue

                return self._build_result(data, email, model)

            except Exception as e:
                # Silent failover is intentional
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

        if status not in {"Applied", "Assessment", "Interview", "Rejected"}:
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
