#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup script to configure API keys
"""
import os
import sys
import io
from pathlib import Path

# Fix terminal encoding on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def setup_anthropic_key():
    """Guide user through setting up Anthropic API key"""
    print("\n" + "="*60)
    print("🔑 WhatsApp + Gmail Agent - API Key Setup")
    print("="*60)

    env_path = Path(__file__).parent / ".env"

    print("\n📌 You need an Anthropic API Key to use this agent.")
    print("\n📍 Get it here: https://console.anthropic.com/api/keys")
    print("\nSteps:")
    print("  1. Go to https://console.anthropic.com/api/keys")
    print("  2. Sign in with your account")
    print("  3. Click 'Create Key'")
    print("  4. Copy the key that starts with 'sk-ant-'")
    print("  5. Paste it below\n")

    api_key = input("🔓 Enter your ANTHROPIC_API_KEY (sk-ant-...): ").strip()

    if not api_key.startswith("sk-ant-"):
        print("❌ Invalid key format. Must start with 'sk-ant-'")
        return False

    # Read current .env
    if env_path.exists():
        content = env_path.read_text()
    else:
        content = ""

    # Update ANTHROPIC_API_KEY
    if "ANTHROPIC_API_KEY=" in content:
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith("ANTHROPIC_API_KEY="):
                lines[i] = f"ANTHROPIC_API_KEY={api_key}"
                break
        content = '\n'.join(lines)
    else:
        content = f"ANTHROPIC_API_KEY={api_key}\n{content}"

    # Write back
    env_path.write_text(content)

    print("\n✅ API Key saved to .env")
    print("📂 File:", env_path)

    # Ask about WhatsApp
    print("\n" + "-"*60)
    setup_whatsapp = input("\n🤖 Do you have WhatsApp Business API credentials? (y/N): ").strip().lower()

    if setup_whatsapp == 'y':
        setup_whatsapp_keys()

    print("\n✅ Setup complete!")
    print("\n🚀 Start the agent:")
    print("   python main.py")
    print("\n📊 Dashboard:")
    print("   http://localhost:5000")

    return True

def setup_whatsapp_keys():
    """Guide user through setting up WhatsApp API keys"""
    print("\n📌 WhatsApp Business API Setup")
    print("-"*60)
    print("Get keys from: https://developers.facebook.com/")
    print("  1. Create/Select a Business app")
    print("  2. Add WhatsApp product")
    print("  3. Select your phone number")

    token = input("\n🔓 WHATSAPP_API_TOKEN (EAA...): ").strip()
    phone_id = input("📱 WHATSAPP_PHONE_NUMBER_ID: ").strip()
    account_id = input("🏢 WHATSAPP_BUSINESS_ACCOUNT_ID: ").strip()

    if not (token and phone_id and account_id):
        print("⚠️ Skipping WhatsApp setup (some values missing)")
        return

    env_path = Path(__file__).parent / ".env"
    content = env_path.read_text()

    # Update values
    replacements = {
        "WHATSAPP_API_TOKEN=": f"WHATSAPP_API_TOKEN={token}",
        "WHATSAPP_PHONE_NUMBER_ID=": f"WHATSAPP_PHONE_NUMBER_ID={phone_id}",
        "WHATSAPP_BUSINESS_ACCOUNT_ID=": f"WHATSAPP_BUSINESS_ACCOUNT_ID={account_id}",
    }

    lines = content.split('\n')
    for i, line in enumerate(lines):
        for old, new in replacements.items():
            if line.startswith(old.split('=')[0]):
                lines[i] = new

    env_path.write_text('\n'.join(lines))
    print("\n✅ WhatsApp API keys saved")

if __name__ == "__main__":
    try:
        success = setup_anthropic_key()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ Setup cancelled")
        sys.exit(1)
