"""Publish connectors for Growth Studio.

Instagram (Graph API) and YouTube (Data API) auto-publish are GATED behind credentials in
backend/.env. Until those are present, every post stays in the calendar ready for one-tap manual
posting (the UI shows a copy-ready caption + the generated image to download). This keeps the app
fully useful today, and flips to real auto-posting the moment tokens are added, no code change.

Instagram publish needs a PUBLIC image URL the Graph API can fetch, so it also requires
PUBLIC_BASE_URL to point at this app over the internet (a tunnel or host).
"""
from __future__ import annotations

import time
from pathlib import Path

import httpx

from .config import get_settings

GRAPH_FB = "https://graph.facebook.com/v21.0"
GRAPH_IG = "https://graph.instagram.com/v21.0"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _graph() -> str:
    """Base URL for Instagram calls: graph.instagram.com (Instagram Login, no Page) or
    graph.facebook.com (Facebook Login, IG linked to a Page)."""
    return GRAPH_IG if get_settings().ig_api == "instagram" else GRAPH_FB


def platform_status() -> dict:
    s = get_settings()
    return {
        "instagram": {
            "connected": s.instagram_ready,
            "needs": [] if s.instagram_ready else ["IG_USER_ID", "IG_ACCESS_TOKEN"],
            "public_url": bool(s.public_base_url),
        },
        "youtube": {
            "connected": s.youtube_ready,
            "needs": [] if s.youtube_ready else ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"],
        },
        "auto_post": s.auto_post,
    }


def _public_image_url(image_web_path: str) -> str:
    s = get_settings()
    base = (s.public_base_url or "").rstrip("/")
    return f"{base}{image_web_path}"


def refresh_instagram_token() -> bool:
    """Extend the long-lived Instagram-Login token another ~60 days. Best-effort: keeps the token
    alive as long as the app is used at least monthly, so credentials never need redoing."""
    s = get_settings()
    if s.ig_api != "instagram" or not s.ig_access_token:
        return False
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get("https://graph.instagram.com/refresh_access_token",
                      params={"grant_type": "ig_refresh_token", "access_token": s.ig_access_token})
        tok = (r.json() or {}).get("access_token") if r.status_code == 200 else None
        if not tok:
            return False
        from .setup_ig import _write_env
        _write_env({"IG_ACCESS_TOKEN": tok})
        s.ig_access_token = tok          # update the cached settings in-process too
        return True
    except Exception:  # noqa: BLE001
        return False


def publish_instagram(caption: str, image_web_path: str) -> dict:
    """Publish a single image post to an Instagram Business account via the Graph API."""
    s = get_settings()
    if not s.instagram_ready:
        return {"ok": False, "error": "Instagram not connected. Add IG_USER_ID and IG_ACCESS_TOKEN."}
    if not s.public_base_url:
        return {"ok": False, "error": "Set PUBLIC_BASE_URL so Instagram can fetch the image."}
    if not image_web_path:
        return {"ok": False, "error": "This post has no image yet. Generate one first."}
    img_url = _public_image_url(image_web_path)
    try:
        with httpx.Client(timeout=90) as c:
            create = c.post(f"{_graph()}/{s.ig_user_id}/media",
                            data={"image_url": img_url, "caption": caption,
                                  "access_token": s.ig_access_token})
            create.raise_for_status()
            container = create.json().get("id")
            if not container:
                return {"ok": False, "error": f"No media container: {create.text}"}
            pub = c.post(f"{_graph()}/{s.ig_user_id}/media_publish",
                         data={"creation_id": container, "access_token": s.ig_access_token})
            pub.raise_for_status()
            media_id = pub.json().get("id")
        return {"ok": True, "external_url": f"https://www.instagram.com/p/{media_id}", "id": media_id}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"Instagram API: {e.response.text[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def publish_reel(caption: str, video_url: str) -> dict:
    """Publish a Reel to Instagram from a PUBLIC video URL (the throwaway Cloudinary link).
    Creates a REELS container, waits for Instagram to finish processing, then publishes."""
    s = get_settings()
    if not s.instagram_ready:
        return {"ok": False, "error": "Instagram not connected."}
    if not video_url:
        return {"ok": False, "error": "No public video URL to publish."}
    try:
        with httpx.Client(timeout=120) as c:
            create = c.post(f"{_graph()}/{s.ig_user_id}/media",
                            data={"media_type": "REELS", "video_url": video_url,
                                  "caption": caption, "share_to_feed": "true",
                                  "access_token": s.ig_access_token})
            create.raise_for_status()
            container = create.json().get("id")
            if not container:
                return {"ok": False, "error": f"No container: {create.text[:300]}"}
            # poll until Instagram finishes ingesting the video
            for _ in range(30):  # up to ~5 min
                time.sleep(10)
                st = c.get(f"{_graph()}/{container}",
                           params={"fields": "status_code,status", "access_token": s.ig_access_token})
                code = (st.json() or {}).get("status_code")
                if code == "FINISHED":
                    break
                if code == "ERROR":
                    return {"ok": False, "error": f"Instagram processing error: {st.text[:300]}"}
            pub = c.post(f"{_graph()}/{s.ig_user_id}/media_publish",
                         data={"creation_id": container, "access_token": s.ig_access_token})
            pub.raise_for_status()
            media_id = pub.json().get("id")
        return {"ok": True, "media_id": media_id,
                "external_url": f"https://www.instagram.com/reel/{media_id}"}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"Instagram API: {e.response.text[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _yt_access_token() -> str | None:
    s = get_settings()
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post("https://oauth2.googleapis.com/token", data={
                "client_id": s.yt_client_id, "client_secret": s.yt_client_secret,
                "refresh_token": s.yt_refresh_token, "grant_type": "refresh_token"})
            r.raise_for_status()
            return r.json().get("access_token")
    except Exception:
        return None


def publish_youtube(title: str, description: str, video_path: str, tags: list[str] | None = None) -> dict:
    """Upload a local video file to YouTube (unlisted->public) via a resumable upload."""
    s = get_settings()
    if not s.youtube_ready:
        return {"ok": False, "error": "YouTube not connected. Add YT_CLIENT_ID/SECRET/REFRESH_TOKEN."}
    if not video_path or not Path(video_path).exists():
        return {"ok": False, "error": "No local video file to upload for this post."}
    token = _yt_access_token()
    if not token:
        return {"ok": False, "error": "Could not refresh YouTube access token."}
    meta = {"snippet": {"title": title[:100], "description": description[:4900],
                        "tags": (tags or [])[:15], "categoryId": "27"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    data = Path(video_path).read_bytes()
    try:
        with httpx.Client(timeout=None) as c:
            init = c.post(
                "https://www.googleapis.com/upload/youtube/v3/videos",
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers={"Authorization": f"Bearer {token}", "X-Upload-Content-Type": "video/*"},
                json=meta)
            init.raise_for_status()
            up = init.headers["location"]
            r = c.put(up, headers={"Authorization": f"Bearer {token}", "Content-Type": "video/*"},
                      content=data)
            r.raise_for_status()
            vid = r.json().get("id")
        return {"ok": True, "external_url": f"https://youtu.be/{vid}", "id": vid}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"YouTube API: {e.response.text[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
