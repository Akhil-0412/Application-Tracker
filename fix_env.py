import subprocess
import sys
import os

# Define variables - ENSURE NO NEWLINES
vars_to_add = {
    "SPREADSHEET_ID": "1mQ9Qjb9kZ1-I8Mra6VDlI-Sgm01auOnySTg7-_7gnY0",
    "GROQ_API_KEY": "YOUR_GROQ_API_KEY_HERE",
}

# Add credential files (read as bytes)
try:
    with open("credentials/credentials.json", "rb") as f:
        vars_to_add["GOOGLE_CREDENTIALS"] = f.read().decode().strip()
    with open("credentials/token.json", "rb") as f:
        vars_to_add["GOOGLE_TOKEN"] = f.read().decode().strip()
except Exception as e:
    print(f"Error reading credentials: {e}")
    sys.exit(1)

for key, val in vars_to_add.items():
    print(f"Adding {key}...")
    # Remove first if exists (optional, but safe)
    subprocess.run(["vercel", "env", "rm", key, "production", "-y"], capture_output=True, shell=True)
    
    # Add with explicit input
    proc = subprocess.run(
        ["vercel", "env", "add", key, "production"], 
        input=val.encode(), # No newline added here
        capture_output=True,
        shell=True
    )
    
    print(f"Stdout: {proc.stdout.decode()}")
    print(f"Stderr: {proc.stderr.decode()}")
    
    if proc.returncode != 0:
        print(f"Failed to add {key}")
