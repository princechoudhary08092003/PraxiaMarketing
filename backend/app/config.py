"""Config for the Praxia Marketing tool (local). Loads backend/.env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env", override=True)


class Settings:
    def __init__(self) -> None:
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("MARKETING_MODEL", "gpt-4o-mini")
        # Gmail send via SMTP + App Password (Google account -> Security -> App passwords)
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_app_password = os.getenv("SMTP_APP_PASSWORD", "").replace(" ", "")
        self.from_name = os.getenv("FROM_NAME", "Praxia AI Studios")
        # outreach CTA
        self.booking_link = os.getenv("BOOKING_LINK", "")
        self.whatsapp = os.getenv("WHATSAPP", "+91 88277 69501")
        self.public_email = os.getenv("PUBLIC_EMAIL", "") or self.smtp_user or "praxiaaistudios@gmail.com"
        self.demo_video = os.getenv("DEMO_VIDEO", "")
        self.youtube_demo = os.getenv("YOUTUBE_DEMO", "")          # YouTube demo link for emails
        self.sender_name = os.getenv("SENDER_NAME", "Prince Choudhary")
        self.daily_send_cap = int(os.getenv("DAILY_SEND_CAP", "200") or 200)

    @property
    def openai_ready(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def smtp_ready(self) -> bool:
        return bool(self.smtp_user and self.smtp_app_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
