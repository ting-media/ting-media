"""
Config for WhatsApp + Gmail Agent
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
DATABASE_DIR = BASE_DIR / "database"
STATE_DIR = BASE_DIR / "state"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Create dirs if not exist
STATE_DIR.mkdir(exist_ok=True)
DATABASE_DIR.mkdir(exist_ok=True)

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
GMAIL_CREDENTIALS_JSON = os.getenv("GMAIL_CREDENTIALS_JSON", str(BASE_DIR / "gmail_credentials.json"))

# Configuration
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))
SCHEDULER_INTERVAL_MINUTES = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", 60))

# WhatsApp Groups to monitor (comma-separated phone IDs)
MONITORED_WHATSAPP_GROUPS = os.getenv("MONITORED_WHATSAPP_GROUPS", "").split(",")
MONITORED_WHATSAPP_GROUPS = [g.strip() for g in MONITORED_WHATSAPP_GROUPS if g.strip()]

# Gmail labels/filters to monitor
MONITORED_GMAIL_LABELS = os.getenv("MONITORED_GMAIL_LABELS", "INBOX").split(",")
MONITORED_GMAIL_LABELS = [l.strip() for l in MONITORED_GMAIL_LABELS if l.strip()]

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_DIR}/agent.db")
USE_SQLITE = DATABASE_URL.startswith("sqlite")

# Claude Model
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")

# Task keywords to identify in messages
TASK_KEYWORDS = [
    "משימה", "TODO", "TASK", "צריך", "חובה", "עד",
    "דחוף", "urgent", "priority", "deadline",
    "בקשה", "request", "צורך", "need"
]

# Debug
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# print(f"✓ Config loaded: {CLAUDE_MODEL}, DB: {DATABASE_URL}")
