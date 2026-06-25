"""Configuration management for Application Tracker."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"

# Check if running on Vercel
IS_VERCEL = os.environ.get("VERCEL") == "1"

if IS_VERCEL:
    # On Vercel, use /tmp for writable credentials
    TOKEN_PATH = Path("/tmp/token.json")
    CREDENTIALS_PATH = Path("/tmp/credentials.json")
else:
    # Local development
    TOKEN_PATH = CREDENTIALS_DIR / "token.json"
    CREDENTIALS_PATH = CREDENTIALS_DIR / "credentials.json"


# Gmail API scopes
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
ALL_SCOPES = GMAIL_SCOPES

# LLM Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Turso Database Configuration
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

# Monitoring Configuration
POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "60"))

# Google OAuth Token from Environment (for serverless Vercel)
GOOGLE_OAUTH_TOKEN_JSON = os.getenv("GOOGLE_OAUTH_TOKEN_JSON")



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
    "not to progress",
    "not progressing",
    
    # Offer signals (explicit)
    "pleased to offer you",
    "offer of employment",
    "job offer",
    "offer of employment",
    "job offer",
    "extend an offer",

    # Generic updates (often used for both rejections and next steps)
    "application update",
    "update on your application",
    "status of your application",
    "regarding your application",
    "about your application",
    "your application for",
    "your candidacy",

    # Additional rejection signals
    "after careful consideration",
    "after careful review",
    "gone with another candidate",
    "other candidates whose",
    "not be taking your application further",
    "will not be progressing",
    "unable to offer you",
    "we wish you all the best",
    "not successful",
    "regret to advise",

    # Offer and progression signals
    "congratulations",
    "delighted to offer",
    "we'd like to offer",
    "shortlisted",
    "next stage",
    "progressed to",
    "moved forward",
]


# Job application email query - BROAD: Keywords in subject + ATS sender domains
JOB_EMAIL_QUERY = (
    '('
    'subject:(application OR applied OR interview OR assessment OR position OR role '
    'OR confirmed OR received OR resume OR thank OR opportunity OR update '
    'OR unfortunately OR regret OR "not to progress" OR "status update" '
    'OR rejected OR congratulations OR shortlisted OR proceeding OR offer OR candidate) '
    'OR from:(workday OR greenhouse OR lever OR icims OR smartrecruiters OR jobvite '
    'OR ashby OR breezy OR ripplehire OR taleo)'
    ') -from:me'
)

# Clean up the query
JOB_EMAIL_QUERY = " ".join(JOB_EMAIL_QUERY.split())
