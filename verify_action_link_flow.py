import sys
import os
from unittest.mock import MagicMock
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from src.gmail_client import GmailClient
from src.ai_classifier import AIClassifier, ClassificationResult
from src.status_tracker import StatusTracker
from src.sheets_client import SheetsClient

def test_full_flow():
    print("--- Testing Full Action Link Flow ---")
    
    # 1. Mock Gmail Extraction
    # We will simulate the output of _extract_body_and_links
    mock_payload = {} # Not used because we mock the method
    
    client = GmailClient()
    # Mock the internal extraction to return a known link
    client._extract_body_and_links = MagicMock(return_value=(
        "Please complete your assessment. Start Test", 
        ["https://hackerrank.com/test/123"]
    ))
    
    # mock get_message_details to use our mocked extraction
    # Actually, let's just construct the email dict manually as if it came from get_message_details
    email_data = {
        "id": "123",
        "subject": "HackerRank Test Invitation",
        "from": "support@hackerrank.com",
        "sender_email": "support@hackerrank.com",
        "sender_domain": "HackerRank",
        "date": datetime.now(),
        "body": "Please complete your assessment. Start Test",
        "action_links": ["https://hackerrank.com/test/123"],
        "snippet": "Please complete..."
    }
    
    print(f"[1] Email Data Simulated: {email_data['action_links']}")
    
    # 2. Mock AI Classification
    # We want to verify AIClassifier picks up the link
    classifier = AIClassifier()
    
    # Mock _ai_classify to avoid API call, but we want to test _build_result logic
    # So we'll mock the internal _parse_json to return data, and let _build_result do the rest
    classifier.client = MagicMock() # Fake client
    classifier._ai_classify = MagicMock(return_value=ClassificationResult(
        company="HackerRank",
        role="Software Engineer",
        status="Assessment",
        confidence=0.9,
        reasoning="Test",
        source="ai",
        action_link="https://hackerrank.com/test/123" # This is what we expect _build_result to produce
    ))
    
    # Wait, I want to test that _build_result ACTUALLY populates it.
    # So let's test _build_result directly.
    result = classifier._build_result(
        {"company": "HackerRank", "role": "SWE", "status": "Assessment"},
        email_data,
        "mock-model"
    )
    
    print(f"[2] Classification Result Action Link: {result.action_link}")
    if result.action_link == "https://hackerrank.com/test/123":
        print("PASS: AIClassifier picked up the link.")
    else:
        print(f"FAIL: AIClassifier missed the link. Got: {result.action_link}")
        
    # 3. Mock Sheets & Status Tracker
    mock_sheets = MagicMock(spec=SheetsClient)
    tracker = StatusTracker(mock_sheets)
    
    # Mock find_application to return None (new app)
    mock_sheets.find_application.return_value = None
    
    # Run process
    tracker.process_classification(result, datetime.now(), "Subject")
    
    # Verify add_application was called with action_link
    print("\n[3] Verifying Sheets Call...")
    mock_sheets.add_application.assert_called_once()
    call_args = mock_sheets.add_application.call_args[1]
    
    print(f"Call Args: {call_args}")
    
    if call_args.get("action_link") == "https://hackerrank.com/test/123":
        print("PASS: status_tracker passed action_link to sheets_client.")
    else:
        print("FAIL: action_link NOT passed to sheets_client.")

if __name__ == "__main__":
    test_full_flow()
