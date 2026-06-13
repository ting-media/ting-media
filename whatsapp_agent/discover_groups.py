#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discover WhatsApp groups/conversations using the Business API
"""
import sys
import io
import requests
import json
from config import WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_BUSINESS_ACCOUNT_ID

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def discover_conversations():
    """Fetch conversations from WhatsApp API"""
    print("🔍 Discovering WhatsApp conversations...")
    print(f"   Phone Number ID: {WHATSAPP_PHONE_NUMBER_ID}")
    print(f"   Business Account ID: {WHATSAPP_BUSINESS_ACCOUNT_ID}\n")

    headers = {
        "Authorization": f"Bearer {WHATSAPP_API_TOKEN}",
        "Content-Type": "application/json"
    }

    # Try to get conversations from phone number
    urls_to_try = [
        f"https://graph.instagram.com/v18.0/{WHATSAPP_PHONE_NUMBER_ID}/conversations",
        f"https://graph.instagram.com/v18.0/{WHATSAPP_BUSINESS_ACCOUNT_ID}/conversations",
        f"https://graph.instagram.com/v18.0/{WHATSAPP_PHONE_NUMBER_ID}/messages",
    ]

    for url in urls_to_try:
        try:
            print(f"🔗 Trying: {url}")
            response = requests.get(url, headers=headers, timeout=5)
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Success!")
                print(json.dumps(data, indent=2, ensure_ascii=False)[:500])
                return data
            else:
                print(f"   Error: {response.text[:200]}")
        except Exception as e:
            print(f"   Exception: {e}")

    print("\n⚠️  Could not discover conversations automatically.")
    print("\nManual Setup Required:")
    print("1. Open WhatsApp Web or WhatsApp Business app")
    print("2. Find your group(s)")
    print("3. Right-click group → Group Info → Copy group ID")
    print("4. Add to .env: MONITORED_WHATSAPP_GROUPS=group_id_1,group_id_2")
    print("\nGroup ID format typically looks like: 120363xxx@g.us")

if __name__ == '__main__':
    discover_conversations()
