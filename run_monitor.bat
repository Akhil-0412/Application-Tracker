@echo off
REM Application Tracker - Scheduled Monitor
REM This script fetches new emails and updates the Google Sheet
REM Schedule this in Windows Task Scheduler to run every 10-15 minutes

cd /d "%~dp0"
echo [%date% %time%] Starting monitor run... >> logs\monitor.log

REM Activate venv and run monitor
.venv\Scripts\python.exe main.py --days 1 >> logs\monitor.log 2>&1

echo [%date% %time%] Monitor run complete >> logs\monitor.log
echo. >> logs\monitor.log
