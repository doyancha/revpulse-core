"""
Configuration settings for RevPulse AI Engine.
"""

from typing import Optional
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME: str = os.getenv("MODEL_NAME", "gemini-3.6-flash")
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'revpulse.db'}")
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Live Sandbox & Webhook Verification Settings
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
STRIPE_SECRET_KEY: Optional[str] = os.getenv("STRIPE_SECRET_KEY", None)
STRIPE_WEBHOOK_SECRET: Optional[str] = os.getenv("STRIPE_WEBHOOK_SECRET", None)
TWILIO_ACCOUNT_SID: Optional[str] = os.getenv("TWILIO_ACCOUNT_SID", None)
TWILIO_AUTH_TOKEN: Optional[str] = os.getenv("TWILIO_AUTH_TOKEN", None)
TWILIO_WHATSAPP_NUMBER: str = os.getenv("TWILIO_WHATSAPP_NUMBER", "+17572508054")

