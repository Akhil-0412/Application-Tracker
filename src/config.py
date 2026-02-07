"""Configuration management for Application Tracker."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
TOKEN_PATH = CREDENTIALS_DIR / "token.json"
CREDENTIALS_PATH = CREDENTIALS_DIR / "credentials.json"

# Gmail API scopes
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
ALL_SCOPES = GMAIL_SCOPES + SHEETS_SCOPES

# LLM Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Monitoring Configuration
POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "60"))

# Google Sheets Configuration
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "Job Application Tracker")

# Sheet headers
SHEET_HEADERS = [
    "Company",
    "Role",
    "Status",
    "Applied Date",
    "Last Updated",
    "Email Subject",
    "Detection Reason",
]

# Senders to ALWAYS IGNORE (marketing/alerts, never job apps)
IGNORED_SENDERS = [
    "glassdoor",
    "linkedin",
    "indeed",
    "monster",
    "ziprecruiter",
    "dice",
    "careerbuilder",
    "noreply@github.com",
    "hello@github.com",
    "noreply@google.com",  # Google product updates
    "targetjobs",
    "fivesurveys",
    "5surveys",
    "apple.com",
    "icloud",
    "accounts.google",  # Google security alerts
]

# NEGATIVE phrases: Subjects containing these are BLOCKED
# These are checked BEFORE positive phrases
NEGATIVE_SUBJECTS = [
    # Job alerts / marketing
    "job alert",
    "jobs for you",
    "new jobs",
    "hiring now",
    "openings nearby",
    "don't miss these opportunities",
    "latest update from",
    "added today:",
    "earn double",
    "earn rewards",
    "playing games",
    "refer a friend",
    "refer and earn",
    
    # Security / verification (NOT job events)
    "security alert",
    "security code",
    "confirm your identity",
    "verify your candidate",
    "verify your account",
    "verify your email",
    "verification code",
    
    # Surveys (post-process, not application updates)
    "candidate experience survey",
    "survey",
    
    # Incomplete applications (reminders, not confirmations)
    "complete your application",
    "finish your application",
    "don't forget to complete",
    
    # Product updates (not hiring)
    "product update",
    "[product update]",
    
    # Storage / account
    "icloud storage",
    "storage is full",
    
    # Teaching marketing
    "get into teaching",
    "initial teaching training",
]

# POSITIVE phrases: STRICT ALLOW-LIST
# Email MUST contain one of these to be tracked (default = BLOCK)
POSITIVE_PHRASES = [
    # Application confirmation (explicit)
    "thank you for applying",
    "thank you for your application",
    "thanks for applying",
    "application received",
    "we received your application",
    "we have received your application",
    "we've received your application",
    "we have received your resume",
    "we've received your resume",
    "successfully submitted",
    "application confirmed",
    "application has been submitted",
    
    # Interview signals (explicit)
    "invite you to interview",
    "invitation to interview",
    "interview invitation",
    "schedule an interview",
    "schedule a call",
    "phone screen",
    "video interview",
    "technical interview",
    "prescreen interview",
    
    # Assessment signals (explicit)
    "coding challenge",
    "take-home assignment",
    "online assessment",
    "complete this assessment",
    "hackerrank",
    "codility",
    "codesignal",
    
    # Rejection signals (we want to track these)
    "unsuccessful application",
    "unfortunately",
    "we regret to inform",
    "not moving forward",
    "decided not to move forward",
    "will not be proceeding",
    "not be proceeding",
    "position has been filled",
    "decided to pursue other candidates",
    "not selected",
    "another candidate",
    
    # Offer signals (explicit)
    "pleased to offer you",
    "offer of employment",
    "job offer",
    "extend an offer",
]

# Job application email query - STRICT: ATS senders AND job subjects
JOB_EMAIL_QUERY = """
(from:noreply OR from:no-reply OR from:careers OR from:recruiting OR 
from:talent OR from:jobs OR from:hiring OR from:hr OR from:applications OR
from:workday OR from:myworkday OR from:greenhouse OR from:lever OR from:icims OR from:taleo OR
from:smartrecruiters OR from:jobvite OR from:ripplehire OR from:applytojob OR from:ashby OR from:breezy OR
from:successfactors OR from:avature)
subject:(application OR applied OR interview OR assessment OR position OR role OR 
confirmed OR received OR resume OR thank OR opportunity OR update OR unfortunately OR regret)
"""

# Clean up the query
JOB_EMAIL_QUERY = " ".join(JOB_EMAIL_QUERY.split())
