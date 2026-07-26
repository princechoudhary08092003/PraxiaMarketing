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
        # brochure attached to the first-touch email
        self.overview_pdf = os.getenv("OVERVIEW_PDF") or os.path.expanduser(
            "~/Downloads/Praxia-Overview.pdf")

        # --- Growth Studio (social presence engine) ---
        self.growth_model = os.getenv("GROWTH_MODEL", "gpt-4o")          # copy/strategy brain
        self.image_model = os.getenv("IMAGE_MODEL", "gpt-image-1")       # post-graphic generator
        self.brand_handle = os.getenv("BRAND_HANDLE", "@praxiaaistudios")
        self.website = os.getenv("WEBSITE", "praxiaaistudios.in")
        # Instagram publishing. Two paths:
        #   "instagram" = Instagram Login (NO Facebook Page needed) via graph.instagram.com  [default]
        #   "facebook"  = Facebook Login, IG linked to a Page, via graph.facebook.com
        self.ig_api = os.getenv("IG_API", "instagram").lower().strip()
        # IG_USER_ID = the IG Business account id.
        self.ig_user_id = os.getenv("IG_USER_ID", "")
        self.ig_access_token = os.getenv("IG_ACCESS_TOKEN", "")
        # App id/secret — used only to exchange a short-lived token for a long-lived one
        self.fb_app_id = os.getenv("FB_APP_ID", "")
        self.fb_app_secret = os.getenv("FB_APP_SECRET", "")
        # YouTube Data API (OAuth). Provide a refresh token flow via env for uploads.
        self.yt_client_id = os.getenv("YT_CLIENT_ID", "")
        self.yt_client_secret = os.getenv("YT_CLIENT_SECRET", "")
        self.yt_refresh_token = os.getenv("YT_REFRESH_TOKEN", "")
        # When true, the scheduler auto-publishes scheduled posts once a platform is connected.
        self.auto_post = (os.getenv("AUTO_POST", "false").lower() in ("1", "true", "yes"))
        # public base URL the platforms can reach for image hosting (needed for IG publish)
        self.public_base_url = os.getenv("PUBLIC_BASE_URL", "")
        # Cloudinary — throwaway pass-through host so Instagram can fetch the reel/image.
        # Nothing is kept: media is uploaded, posted, then deleted from Cloudinary and disk.
        self.cloudinary_cloud = os.getenv("CLOUDINARY_CLOUD_NAME", "")
        self.cloudinary_key = os.getenv("CLOUDINARY_API_KEY", "")
        self.cloudinary_secret = os.getenv("CLOUDINARY_API_SECRET", "")
        # Pexels (free) — real stock photography blended with AI visuals.
        self.pexels_key = os.getenv("PEXELS_API_KEY", "")
        # TTS voice for reel voiceovers
        self.tts_voice = os.getenv("TTS_VOICE", "onyx")
        self.tts_model = os.getenv("TTS_MODEL", "tts-1-hd")

    @property
    def instagram_ready(self) -> bool:
        return bool(self.ig_user_id and self.ig_access_token)

    @property
    def youtube_ready(self) -> bool:
        return bool(self.yt_client_id and self.yt_client_secret and self.yt_refresh_token)

    @property
    def cloudinary_ready(self) -> bool:
        return bool(self.cloudinary_cloud and self.cloudinary_key and self.cloudinary_secret)

    @property
    def pexels_ready(self) -> bool:
        return bool(self.pexels_key)

    def first_touch_attachments(self) -> list[str]:
        """Existing files to attach to the first-touch email (skips missing ones silently)."""
        return [p for p in [self.overview_pdf] if p and os.path.exists(p)]

    @property
    def openai_ready(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def smtp_ready(self) -> bool:
        return bool(self.smtp_user and self.smtp_app_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
