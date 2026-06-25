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
        "graduate scheme", "placement year", "placement student", "year in industry",
        "apprentice", "trainee", "associate",
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
        """Extract company name from email, prioritizing sender display name then subject."""
        
        # Extensive blacklist of generic terms often mistaken for company names
        blacklist = {
            "the", "a", "an", "our", "your", "hey", "hi", "dear", "us", "me", "we",
            "hire", "hiring", "careers", "recruiting", "talent", "hr", "people",
            "team", "staff", "admin", "support", "info", "contact", "email",
            "application", "position", "role", "job", "vacancy", "opportunity",
            "update", "status", "notification", "alert", "digest", "newsletter",
            "verify", "security", "code", "password", "login", "account",
            "unknown", "company", "client", "employer", "organization", "firm",
            "received", "confirmed", "submitted", "successful", "unsuccessful",
            "applytojob", "myworkday", "workday", "successfactors", "avature",
            "icims", "jobvite", "smartrecruiters", "breezy", "ashby", "via",
            "e", "fivesurveys", "growthassistant", "targetjobs", "getintoteaching",
            "welcome", "confirm", "receipt", "order", "invoice", "payment",
            "subscription", "noreply", "no-reply", "mailer", "service", "system", "auto",
            # Common English words the regex picks up
            "any", "next", "what", "about", "within", "all", "how", "now",
            "this", "that", "these", "those", "here", "there",
        }
        
        # Common words that should never form a company name on their own
        common_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "up", "about", "into", "over", "after",
            "is", "are", "was", "were", "be", "been", "have", "has", "had",
            "do", "does", "did", "will", "would", "could", "should", "may",
            "might", "can", "shall", "not", "no", "yes", "any", "all",
            "your", "our", "their", "my", "his", "her", "its", "us", "we",
            "what", "which", "who", "when", "where", "why", "how", "next",
            "within", "updates", "update", "application", "status", "team",
        }
        
        def is_valid_company(name: str) -> bool:
            if not name or len(name) < 2:
                return False
            if name.lower() in blacklist:
                return False
            # Reject if ALL words are common English words
            words = name.lower().split()
            if all(w in common_words for w in words):
                return False
            return True
        
        # ─── 1. Sender Display Name (most reliable) ──────────────────────────────
        sender_match = re.match(r'^(.+?)\s*<', from_addr)
        if sender_match:
            display_name = sender_match.group(1).strip()
            if display_name and '@' not in display_name:
                # Strip ATS/platform suffixes
                suffixes = [
                    r'\s*-\s*Workday$', r'\s*-\s*Greenhouse$', r'\s*-\s*Lever$',
                    r'\s*Hiring\s*Team$', r'\s*Careers?$', r'\s*Talent\s*(Acquisition)?$',
                    r'\s*Recruiting$', r'\s*HR$', r'\s*People$', r'\s*Jobs?$',
                    r'\s*Notifications?$', r'\s*via\s+\w+$',
                ]
                for suffix in suffixes:
                    display_name = re.sub(suffix, '', display_name, flags=re.IGNORECASE).strip()
                generic_names = {"no-reply", "noreply", "notifications", "mailer", "support", "info", "admin"}
                if display_name.lower() not in generic_names and is_valid_company(display_name):
                    return display_name
        
        # ─── 2. Subject Line (rich, structured — check BEFORE body) ──────────────
        # These patterns directly address the errors.md failures:
        subject_patterns = [
            # "Visa - Application Update" / "RAC - Your application for..."
            r'^([A-Z][A-Za-z0-9\s&\'\.\-]{1,30}?)\s*[-–]\s*(?:Application|Interview|Your|An update|Thanks|Thank)',
            # "Thank you for your application | Lendable"
            r'\|\s*([A-Z][A-Za-z0-9\s&\'\.\-]{2,30}?)\s*$',
            # "Thank you for your application to Flatiron Health!" / "applying to Captur"
            r'(?:application to|applying to|interest in)\s+([A-Z][A-Za-z0-9\s&\'\.\-]{2,40}?)(?:\s*[!,.\n]|$)',
            # "An update on your bet365 application" / "An update on your MUBI application"
            r'(?:your|the)\s+([A-Z][A-Za-z0-9&\'\.\-]{2,30}?)\s+application\b',
            # "Allica Bank - Thanks for your application!"
            r'^([A-Z][A-Za-z0-9\s&\'\.\-]{2,30}?)\s*[-–]\s+(?:Thanks|Thank you|We)',
            # "application to / for CompanyName"
            r'application\s+(?:to|for)\s+([A-Z][A-Za-z0-9\s&\'\.\-]{2,30}?)(?:\s*[!,.\n]|$)',
        ]
        for pattern in subject_patterns:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                company = match.group(1).strip().rstrip('!')
                if is_valid_company(company):
                    return company

        # ─── 3. Body patterns (uppercased proper-noun check) ──────────────────────
        body_patterns = [
            r'(?:joining|interest in|here at|welcome to)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,3})',
            r'(?:at|with)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})(?:\s*[,.]|\s+we\b)',
            r'([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})\s+(?:team|talent|careers|recruiting)',
        ]
        for pattern in body_patterns:
            match = re.search(pattern, body)
            if match:
                company = match.group(1).strip()
                if is_valid_company(company):
                    return company
        
        # ─── 4. Email domain fallback ──────────────────────────────────────────────
        match = re.search(r'@([^.]+)\.', from_addr)
        if match:
            domain = match.group(1)
            ignored = {"gmail", "yahoo", "outlook", "hotmail", "mail", "no-reply", "noreply", 
                       "workday", "greenhouse", "lever", "icims", "taleo", "ripplehire",
                       "smartrecruiters", "jobvite", "applytojob", "breezy", "ashby", "myworkday", 
                       "via", "successfactors", "avature", "hire", "recruiting", "careers", "jobs",
                       "e", "fivesurveys", "growthassistant", "targetjobs", "getintoteaching",
                       "oscar-tech", "involved-solutions", "deel"}
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
            r"([A-Za-z\s\-]+(?:Engineer|Developer|Scientist|Analyst|Manager|Intern|Designer|Architect|Scheme|Apprentice|Trainee)[A-Za-z\s\-\(\)]*)",
        ]
        
        for pattern in position_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                role = match.group(1).strip()
                role = re.sub(r'\s+', ' ', role)
                if 5 < len(role) < 80:
                    # Accept if it contains a job-related word
                    role_lower = role.lower()
                    job_words = ["engineer", "developer", "scientist", "analyst", "manager", 
                                "intern", "designer", "architect", "lead", "senior", "junior",
                                "graduate", "scheme", "placement", "apprentice", "trainee",
                                "associate", "consultant", "coordinator", "specialist"]
                    if any(word in role_lower for word in job_words):
                        return role.title() if role.islower() else role
        
        # Secondary: accept role-like patterns even without strict job_words
        # (e.g., "Graduate Scheme", "Year in Industry")
        secondary_patterns = [
            r"for the\s+([A-Za-z\s\-\(\)]{5,60}?)\s+(?:position|role|opportunity)",
            r"position of\s+([A-Za-z\s\-\(\)]{5,60}?)(?:\s+at|\.|,|\n)",
            r"application for (?:the\s+)?([A-Za-z\s\-\(\)]{5,60}?)(?:\s+at|\.|,|\n)",
        ]
        for pattern in secondary_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                role = re.sub(r'\s+', ' ', match.group(1).strip())
                if 5 < len(role) < 60:
                    return role.title() if role.islower() else role
        
        # Fallback: look for known job titles
        content_lower = content.lower()
        for title in self.JOB_TITLES:
            if title.lower() in content_lower:
                return title.title()
        
        return ""
