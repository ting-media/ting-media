#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick start script - checks setup and starts the agent
"""
import sys
import io
from pathlib import Path

# Fix terminal encoding on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
from dotenv import load_dotenv

# Load .env
load_dotenv(verbose=True)

# Manual .env loading as fallback
env_file = Path(".env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip()

def check_setup():
    """Check if basic setup is complete"""
    print("\n" + "="*70)
    print("  🚀 WhatsApp + Gmail Agent - Startup Check")
    print("="*70 + "\n")

    issues = []

    # Check Gmail credentials
    gmail_creds = Path("gmail_credentials.json")
    if gmail_creds.exists():
        print("✅ Gmail credentials (gmail_credentials.json) - FOUND")
    else:
        print("❌ Gmail credentials (gmail_credentials.json) - MISSING")
        issues.append("Gmail credentials")

    # Check Anthropic API Key (force reload from .env)
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                _, value = line.split("=", 1)
                os.environ["ANTHROPIC_API_KEY"] = value.strip()
                break

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if api_key and api_key.startswith("sk-ant-"):
        print("✅ Anthropic API Key - CONFIGURED")
    else:
        print("❌ Anthropic API Key - NOT SET")
        issues.append("Anthropic API Key")

    # Check .env exists
    env_file = Path(".env")
    if env_file.exists():
        print("✅ .env file - FOUND")
    else:
        print("❌ .env file - MISSING")
        issues.append(".env file")

    print("\n" + "-"*70)

    if issues:
        print(f"\n⚠️  Setup incomplete. Missing:")
        for issue in issues:
            print(f"   • {issue}")

        if "Anthropic API Key" in issues:
            print("\n📌 How to fix:")
            print("   1. Get your API key from: https://console.anthropic.com/api/keys")
            print("   2. Run: python setup_api_key.py")
            print("   3. Try again: python start.py")
            return False

        return False

    print("\n✅ All checks passed! Starting agent...\n")
    return True

def main():
    """Main entry point"""
    if not check_setup():
        print("\n❌ Cannot start agent. Fix the issues above.")
        sys.exit(1)

    print("="*70)
    print("  Starting WhatsApp + Gmail Agent...")
    print("="*70 + "\n")
    print("📊 Dashboard: http://localhost:5000")
    print("📋 Logs: Check the output below\n")
    print("-"*70 + "\n")

    # Start main.py
    try:
        from main import app
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=True,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\n\n✋ Agent stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error starting agent: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
