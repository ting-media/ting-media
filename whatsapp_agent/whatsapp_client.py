"""
WhatsApp Business API Client
"""
import requests
from typing import List, Dict, Optional
from datetime import datetime
import json

from config import WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_BUSINESS_ACCOUNT_ID

class WhatsAppClient:
    BASE_URL = "https://graph.instagram.com/v18.0"

    def __init__(self):
        self.token = WHATSAPP_API_TOKEN
        self.phone_number_id = WHATSAPP_PHONE_NUMBER_ID
        self.business_account_id = WHATSAPP_BUSINESS_ACCOUNT_ID

        if not all([self.token, self.phone_number_id, self.business_account_id]):
            raise ValueError(
                "WhatsApp credentials not configured. "
                "Set WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_BUSINESS_ACCOUNT_ID"
            )

    def _get_headers(self) -> Dict:
        """Get request headers with auth"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def get_messages(self, group_id: str, limit: int = 100) -> List[Dict]:
        """
        Fetch recent messages from a WhatsApp group

        Args:
            group_id: WhatsApp group phone number ID
            limit: Max messages to fetch

        Returns:
            List of message dicts
        """
        try:
            # Note: WhatsApp Business API doesn't have direct "get messages" endpoint
            # You need to use webhooks for incoming messages or use a conversation API
            # This is a placeholder that would work with proper setup

            url = f"{self.BASE_URL}/{group_id}/messages"
            params = {
                "access_token": self.token,
                "limit": limit
            }

            response = requests.get(url, params=params, headers=self._get_headers())
            response.raise_for_status()

            data = response.json()
            messages = data.get('data', [])

            # Parse messages
            parsed = []
            for msg in messages:
                parsed.append({
                    'id': msg.get('id'),
                    'from': msg.get('from', {}).get('phone_number_id'),
                    'timestamp': msg.get('timestamp'),
                    'type': msg.get('type'),  # text, image, document, etc
                    'text': msg.get('text', {}).get('body') if msg.get('type') == 'text' else '',
                    'sender': msg.get('from', {}).get('display_phone_number'),
                })

            return parsed

        except requests.RequestException as e:
            print(f"Error fetching WhatsApp messages: {e}")
            return []

    def get_group_info(self, group_id: str) -> Optional[Dict]:
        """Get WhatsApp group info"""
        try:
            url = f"{self.BASE_URL}/{group_id}"
            params = {"access_token": self.token}

            response = requests.get(url, params=params, headers=self._get_headers())
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            print(f"Error fetching group info: {e}")
            return None

    def send_message(self, recipient_id: str, message_text: str) -> Optional[str]:
        """
        Send a text message to WhatsApp

        Args:
            recipient_id: Recipient phone number ID or group ID
            message_text: Message content

        Returns:
            Message ID if successful
        """
        try:
            url = f"{self.BASE_URL}/{self.phone_number_id}/messages"

            payload = {
                "messaging_product": "whatsapp",
                "to": recipient_id,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": message_text
                }
            }

            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers()
            )
            response.raise_for_status()

            data = response.json()
            msg_id = data.get('messages', [{}])[0].get('id')
            print(f"✓ Message sent: {msg_id}")

            return msg_id

        except requests.RequestException as e:
            print(f"Error sending message: {e}")
            return None

    def send_message_to_group(self, group_id: str, message_text: str) -> Optional[str]:
        """Send message to a WhatsApp group"""
        return self.send_message(group_id, message_text)

    def mark_message_as_read(self, message_id: str) -> bool:
        """Mark a message as read"""
        try:
            url = f"{self.BASE_URL}/{self.phone_number_id}/messages"

            payload = {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id
            }

            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers()
            )
            response.raise_for_status()

            return True

        except requests.RequestException as e:
            print(f"Error marking message as read: {e}")
            return False

    def get_media_url(self, media_id: str) -> Optional[str]:
        """Get media download URL"""
        try:
            url = f"{self.BASE_URL}/{media_id}"
            params = {"access_token": self.token}

            response = requests.get(url, params=params, headers=self._get_headers())
            response.raise_for_status()

            data = response.json()
            return data.get('url')

        except requests.RequestException as e:
            print(f"Error getting media URL: {e}")
            return None
