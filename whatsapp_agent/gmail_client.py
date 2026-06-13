"""
Gmail API Client for fetching emails
"""
import pickle
import os.path
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError
from googleapiclient import discovery
from googleapiclient.errors import HttpError
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import base64
from email.mime.text import MIMEText

from config import GMAIL_CREDENTIALS_JSON, BASE_DIR

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send'
]

class GmailClient:
    def __init__(self):
        self.service = None
        self.credentials = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Gmail API using OAuth2"""
        creds = None
        token_file = BASE_DIR / "token.pickle"

        # Load cached token
        if token_file.exists():
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)

        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError:
                    print("Token refresh failed, requesting new auth...")
                    creds = None

            if not creds:
                # Check if credentials file exists
                if not os.path.exists(GMAIL_CREDENTIALS_JSON):
                    raise FileNotFoundError(
                        f"Gmail credentials not found at {GMAIL_CREDENTIALS_JSON}\n"
                        "Download OAuth 2.0 credentials from Google Cloud Console"
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    GMAIL_CREDENTIALS_JSON, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save token for next run
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)

        self.credentials = creds
        self.service = discovery.build('gmail', 'v1', credentials=creds)
        print("✓ Gmail authenticated")

    def get_recent_messages(self, hours: int = 1, label_ids: Optional[List[str]] = None) -> List[Dict]:
        """
        Fetch recent messages from Gmail

        Args:
            hours: How many hours back to fetch
            label_ids: Specific labels to search (default: INBOX)

        Returns:
            List of message dicts with full content
        """
        try:
            # Build query
            since_date = datetime.now() - timedelta(hours=hours)
            query = f"after:{since_date.strftime('%Y/%m/%d')}"

            if label_ids:
                label_filter = " OR ".join([f"label:{l}" for l in label_ids])
                query += f" ({label_filter})"
            else:
                query += " label:INBOX"

            # Search
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=50
            ).execute()

            messages = results.get('messages', [])

            if not messages:
                return []

            # Fetch full content for each message
            full_messages = []
            for message in messages:
                try:
                    msg = self.service.users().messages().get(
                        userId='me',
                        id=message['id'],
                        format='full'
                    ).execute()
                    full_messages.append(msg)
                except HttpError as e:
                    print(f"Error fetching message {message['id']}: {e}")

            return full_messages

        except HttpError as e:
            print(f"Gmail API error: {e}")
            return []

    def search_messages(self, query: str) -> List[Dict]:
        """
        Search Gmail messages by query

        Examples:
            - "from:someone@example.com"
            - "subject:project"
            - "has:attachment"
        """
        try:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=50
            ).execute()

            messages = results.get('messages', [])

            # Fetch full content
            full_messages = []
            for message in messages:
                try:
                    msg = self.service.users().messages().get(
                        userId='me',
                        id=message['id'],
                        format='full'
                    ).execute()
                    full_messages.append(msg)
                except HttpError:
                    pass

            return full_messages

        except HttpError as e:
            print(f"Gmail search error: {e}")
            return []

    def get_message_details(self, msg: Dict) -> Dict:
        """Extract structured data from Gmail message"""
        headers = msg['payload']['headers']
        body = self._get_message_body(msg['payload'])

        # Extract headers
        header_dict = {h['name']: h['value'] for h in headers}

        return {
            'id': msg['id'],
            'from': header_dict.get('From', 'Unknown'),
            'to': header_dict.get('To', 'Unknown'),
            'subject': header_dict.get('Subject', '(No Subject)'),
            'date': header_dict.get('Date', ''),
            'body': body,
            'timestamp': msg.get('internalDate', ''),
            'labels': msg.get('labelIds', [])
        }

    def _get_message_body(self, payload: Dict) -> str:
        """Extract body from Gmail payload"""
        if 'parts' in payload:
            body = ""
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        data = part['body']['data']
                        body = base64.urlsafe_b64decode(data).decode('utf-8')
                        break
            return body
        elif 'body' in payload:
            if 'data' in payload['body']:
                data = payload['body']['data']
                return base64.urlsafe_b64decode(data).decode('utf-8')

        return ""

    def send_message(self, to: str, subject: str, body: str) -> Optional[str]:
        """Send an email"""
        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            send_message = {
                'raw': raw
            }

            sent = self.service.users().messages().send(
                userId='me',
                body=send_message
            ).execute()

            return sent.get('id')

        except HttpError as e:
            print(f"Failed to send message: {e}")
            return None

    def get_labels(self) -> List[Dict]:
        """Get all Gmail labels"""
        try:
            results = self.service.users().labels().list(userId='me').execute()
            return results.get('labels', [])
        except HttpError as e:
            print(f"Error fetching labels: {e}")
            return []
