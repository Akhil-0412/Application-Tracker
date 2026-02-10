# Application Tracker Deployment Guide

## Vercel Dashboard Deployment

### Step 1: Push to GitHub
```bash
cd c:\Users\AKHILESHWAR\Scripts_UoS\Projects\ApplicationTracker
git init
git add .
git commit -m "Add Application Tracker with Vercel deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/application-tracker.git
git push -u origin main
```

### Step 2: Deploy to Vercel
1. Go to [vercel.com](https://vercel.com) and sign in with GitHub
2. Click "Add New Project" → Import your repository
3. Configure Environment Variables:

| Variable | Value |
|----------|-------|
| `SPREADSHEET_ID` | Your Google Sheets ID (from URL) |
| `GOOGLE_CREDENTIALS` | Contents of `credentials/credentials.json` (as single-line JSON) |

4. Deploy!

---

## GitHub Actions Monitor Setup

### Step 1: Add Repository Secrets
Go to: Repository → Settings → Secrets and variables → Actions → New repository secret

| Secret Name | Value |
|-------------|-------|
| `SPREADSHEET_ID` | `1mQ9Qjb9kZ1-I8Mra6VDlI-Sgm01auOnySTg7-_7gnY0` |
| `GROQ_API_KEY` | Your Groq API key |
| `GOOGLE_CREDENTIALS` | Contents of `credentials/credentials.json` |
| `GOOGLE_TOKEN` | Contents of `credentials/token.json` |

### Step 2: Enable Workflow
The workflow runs automatically every 15 minutes. You can also trigger it manually from the Actions tab.

---

## Important Files

| File | Purpose |
|------|---------|
| `vercel.json` | Vercel deployment config |

## Deployment Log
- **Last Triggered**: 2026-02-10 (Verify Vercel Connection)
