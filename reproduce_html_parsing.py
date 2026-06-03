import sys
import os
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.getcwd())

from src.gmail_client import GmailClient

# Mock BeautifulSoup to avoid dependency if not installed (though it should be)
# But we want to test ACTUAL behavior, so we assume bs4 is there.

def test_hackerrank_parsing():
    # Mock GmailClient to avoid auth
    original_init = GmailClient.__init__
    GmailClient.__init__ = lambda self: None
    
    client = GmailClient()
    # Restore init for other uses if needed (not here)
    
    # Construct a mock HackerRank HTML payload
    html_content = """
    <div style="font-family: Arial;">
        <h1>TR Labs Scientist Interns Screen (CH/UK)</h1>
        <p>Hi Akhil,</p>
        <p>Thank you for your interest in joining Thomson Reuters!</p>
        <p>Here's what you need to know:</p>
        <ul>
            <li>Timeline: 7 days</li>
        </ul>
        <div style="text-align: center;">
            <a href="https://www.hackerrank.com/test/12345" style="background-color: green; color: white; padding: 10px;">Start Test</a>
        </div>
        <p>Happy coding,<br>The Thomson Reuters Hiring Team</p>
    </div>
    """
    
    import base64
    encoded_html = base64.urlsafe_b64encode(html_content.encode('utf-8')).decode('utf-8')
    
    payload = {
        "parts": [
            {
                "mimeType": "text/html",
                "body": {
                    "data": encoded_html
                }
            }
        ]
    }
    
    print("--- Testing HTML Extraction ---")
    # extracted_text = client._extract_body(payload) # Old method
    extracted_text, links = client._extract_body_and_links(payload)
    
    print(f"Extracted Text:\n{extracted_text}")
    print(f"Extracted Links:\n{links}")
    
    print("\n--- Analysis ---")
    if "https://www.hackerrank.com/test/12345" in links:
        print("PASS: HackerRank test link extracted.")
    else:
        print("FAIL: HackerRank test link NOT extracted.")
        
    if "Start Test" in extracted_text:
        print("PASS: 'Start Test' button text preserved in body.")
    else:
        print("FAIL: 'Start Test' button text lost from body.")


if __name__ == "__main__":
    test_hackerrank_parsing()
