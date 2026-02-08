"""Phrase-based email classification (fallback classifier)."""

import re
from .ai_classifier import ClassificationResult


class PhraseClassifier:
    """Keyword/phrase-based email classifier with priority logic."""

    # Priority-based status rules (Regex patterns)
    STATUS_RULES = {
        'Rejected': [
            r'\b(not selected|not moving forward|unfortunately|another candidate|not the right fit|wish you the best|will not be proceeding)\b',
            r'\b(thank you for your interest.*but|we regret to inform|after careful consideration)\b',
            r'\b(position has been filled|decided not to proceed|unable to offer)\b'
        ],
        'Interview': [
            r'\b(interview|schedule a call|available times|calendar invite|zoom|google meet|teams meeting)\b',
            r'\b(meet with|speak with|chat with).*?(interviewer|hiring manager|team)\b',
            r'\b(phone screen|video call|on-site|onsite|final round)\b'
        ],
        'Assessment': [
            r'\b(assessment|coding challenge|take-home|assignment|online test|hackerrank|codility)\b',
            r'\b(complete this task|technical screen|skill assessment|codesignal|leetcode)\b'
        ],
        'Applied': [
            r'\b(application received|successfully submitted|thank you for applying|we have received your application)\b',
            r'\b(application confirmation|successfully applied|job application is confirmed)\b',
            r'\b(received your resume|application for the)\b'
        ]
    }

    # Common job titles to look for
    JOB_TITLES = [
        "software engineer", "software developer", "sde", "swe",
        "machine learning engineer", "ml engineer", "mle",
        "data scientist", "data analyst", "data engineer",
        "ai engineer", "ai engineering intern", "ai research engineer", "research engineer", "research scientist",
        "frontend engineer", "frontend developer", "front-end",
        "backend engineer", "backend developer", "back-end",
        "full stack engineer", "full stack developer", "fullstack",
        "devops engineer", "sre", "site reliability",
        "product manager", "program manager", "project manager",
        "solutions architect", "cloud engineer", "cloud architect",
        "qa engineer", "test engineer", "sdet",
        "mobile developer", "ios developer", "android developer",
        "intern", "graduate", "junior", "senior", "staff", "principal", "lead",
    ]

    def classify(self, email: dict) -> ClassificationResult:
        """Classify email using priority phrase matching."""
        subject = email.get("subject", "")
        body = email.get("body", "")
        snippet = email.get("snippet", "")
        from_addr = email.get("from", "")
        
        # Combine for status matching (lowercase)
        text = f"{subject} {snippet} {body}".lower()

        # Determine status using Priority Logic
        status = "Applied" # Default
        confidence = 0.5
        reasoning = "Default status"

        # Check in order of priority: Rejected > Interview > Assessment > Applied
        # (Offer is implicitly Interview or separate, but for now we stick to these 4 statuses)
        
        detected_status = None
        matched_pattern = ""

        # 1. Rejected
        for pattern in self.STATUS_RULES['Rejected']:
            if re.search(pattern, text):
                detected_status = "Rejected"
                matched_pattern = pattern
                break
        
        # 2. Interview (if not rejected)
        if not detected_status:
           # Interview requires stronger signals or multiple signals
           interview_signals = sum(1 for p in self.STATUS_RULES['Interview'] if re.search(p, text))
           if interview_signals >= 1: # Relaxed slightly from 2 for better recall
               detected_status = "Interview"
               matched_pattern = "Interview patterns"
        
        # 3. Assessment
        if not detected_status:
            for pattern in self.STATUS_RULES['Assessment']:
                if re.search(pattern, text):
                    detected_status = "Assessment"
                    matched_pattern = pattern
                    break

        # 4. Applied
        if not detected_status:
            for pattern in self.STATUS_RULES['Applied']:
                if re.search(pattern, text):
                    detected_status = "Applied"
                    matched_pattern = pattern
                    break

        if detected_status:
            status = detected_status
            confidence = 0.8
            reasoning = f"Matched pattern for {status}"

        # Extract company
        company = self._extract_company(subject, body, from_addr)
        
        # Extract role
        role = self._extract_role(subject, body)

        # STRICTER LOGIC:
        # If Company is "Unknown" AND Role is "Unknown", downgrade confidence
        if not company and not role:
            confidence = 0.0
            reasoning = "Failed to extract Company or Role"
            status = "Applied" # Reset to default if we can't identify what it is
        
        # If we have a status match but no company/role, it might still be valid (e.g. "Status update"),
        # but if we have NO status match and NO company/role, it's definitely junk.
        if confidence < 0.6 and (not company or not role):
             confidence = 0.0
             reasoning = "Low confidence and missing metadata"

        return ClassificationResult(
            company=company or "Unknown Company",
            role=role or "Unknown Position",
            status=status,
            confidence=confidence,
            reasoning=reasoning,
            source="phrases"
        )

    def _extract_company(self, subject: str, body: str, from_addr: str) -> str:
        """Extract company name from email."""
        # Common patterns for company names in body
        patterns = [
            r"(?:at|with|from|here at)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)?)",
            r"([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)?)\s+(?:team|talent|careers|recruiting)",
            r"interest in (?:the\s+)?(?:\w+\s+)?(?:position|role)?\s*(?:at|with)\s+([A-Z][a-zA-Z0-9]+)",
        ]
        
        # Extensive blacklist of generic terms often mistaken for company names
        blacklist = [
            "the", "a", "an", "our", "your", "hey", "hi", "dear", "us", "me",
            "hire", "hiring", "careers", "recruiting", "talent", "hr", "people",
            "team", "staff", "admin", "support", "info", "contact", "email",
            "application", "position", "role", "job", "vacancy", "opportunity",
            "update", "status", "notification", "alert", "digest", "newsletter",
            "verify", "security", "code", "password", "login", "account",
            "unknown", "company", "client", "employer", "organization", "firm",
            "received", "confirmed", "submitted", "successful", "unsuccessful",
            # ATS Platforms and Noise
            "applytojob", "myworkday", "workday", "successfactors", "avature",
            "icims", "jobvite", "smartrecruiters", "breezy", "ashby", "via",
            "e", "fivesurveys", "growthassistant", "targetjobs", "getintoteaching",
            "verify", "security", "code", "password", "login", "account",
            "welcome", "confirm", "receipt", "order", "invoice", "payment",
            "subscription", "newsletter", "digest", "update", "alert",
            "notification", "support", "help", "contact", "info", "admin",
            "noreply", "no-reply", "mailer", "service", "system", "auto"
        ]

        for pattern in patterns:
            match = re.search(pattern, body)
            if match:
                company = match.group(1).strip()
                if company.lower() not in blacklist:
                    return company
        
        # Fallback: Look for "Application to [Company]" in subject
        subject_patterns = [
            r"application\s+(?:to|for)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)?)",
            r"your\s+(?:job\s+)?application\s+(?:at|with|to)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)?)",
        ]
        for pattern in subject_patterns:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                company = match.group(1).strip()
                if company.lower() not in blacklist:
                    return company

        # Try from email domain
        match = re.search(r'@([^.]+)\.', from_addr)
        if match:
            domain = match.group(1)
            # Filter out generic email providers and platforms
            ignored = ["gmail", "yahoo", "outlook", "hotmail", "mail", "no-reply", "noreply", 
                       "workday", "greenhouse", "lever", "icims", "taleo", "ripplehire",
                       "smartrecruiters", "jobvite", "applytojob", "breezy", "ashby", "myworkday", 
                       "via", "successfactors", "avature", "hire", "recruiting", "careers", "jobs",
                       "e", "fivesurveys", "growthassistant", "targetjobs", "getintoteaching",
                       "oscar-tech", "involved-solutions"]
            if domain.lower() not in ignored:
                return domain.title()
        
        return ""

    def _extract_role(self, subject: str, body: str) -> str:
        """Extract job role from email content."""
        content = f"{subject} {body}"
        
        # Look for "position of X" pattern first (most reliable)
        position_patterns = [
            r"position of\s+([A-Za-z\s\-\(\)]+?)(?:\s+at|\s+with|\.|,|\n)",
            r"for the\s+([A-Za-z\s\-\(\)]+?)\s+(?:position|role)",
            r"application for (?:the\s+)?([A-Za-z\s\-\(\)]+?)(?:\s+position|\s+role|\s+at|\.|,|\n)",
            r"([A-Za-z\s\-]+(?:Engineer|Developer|Scientist|Analyst|Manager|Intern|Designer|Architect)[A-Za-z\s\-\(\)]*)",
        ]
        
        for pattern in position_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                role = match.group(1).strip()
                role = re.sub(r'\s+', ' ', role)
                if 5 < len(role) < 80:
                    # Only use if it contains a job-related word
                    role_lower = role.lower()
                    job_words = ["engineer", "developer", "scientist", "analyst", "manager", 
                                "intern", "designer", "architect", "lead", "senior", "junior", "graduate"]
                    if any(word in role_lower for word in job_words):
                        return role.title() if role.islower() else role
        
        # Fallback: look for known job titles
        content_lower = content.lower()
        for title in self.JOB_TITLES:
            if title.lower() in content_lower:
                return title.title()
        
        return ""
