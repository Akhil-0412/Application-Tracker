# Application Tracker

Automatically tracks job applications from Gmail and logs them to Google Sheets.

## Features
- 📧 **Live Gmail Monitoring** - Polls for new job application emails
- 🤖 **AI Classification** - Uses LLM for intelligent status detection (with phrase fallback)
- 📊 **Google Sheets Integration** - Auto-updates your application tracker spreadsheet
- 🔄 **Status Progression** - Tracks changes based on latest email timestamp

## Setup

### 1. Google Cloud Console Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select existing)
3. Enable **Gmail API** and **Google Sheets API**
4. Create **OAuth 2.0 Credentials** (Desktop Application)
5. Download `credentials.json` and place in `credentials/` folder

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env with your API keys
```

### 4. Run
```bash
# First run will prompt for Google OAuth authorization
python main.py

# Live monitoring mode
python main.py --live

# Process last N days
python main.py --days 7
```

## Configuration

Edit `.env` to customize:
- `LLM_PROVIDER` - groq, openai, or openrouter
- `POLLING_INTERVAL` - Seconds between email checks (default: 60)
- `SPREADSHEET_ID` - Existing sheet ID (optional, creates new if not set)

## Sheet Structure

| Company | Role | Status | Applied Date | Last Updated | Email Subject | Notes |
|---------|------|--------|--------------|--------------|---------------|-------|
