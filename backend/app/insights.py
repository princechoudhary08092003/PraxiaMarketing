"""Pull real analytics for every post we have published, so the Analyst learns from the full
history (not just yesterday). Instagram via Graph API insights, YouTube via Data API statistics.
A fresh metrics snapshot row is inserted per post per pull, so trends over time are preserved."""
from __future__ import annotations

import logging

import httpx

from . import social
from .config import get_settings
from .db import get_conn

log = logging.getLogger("praxia.insights")


def _posted_with_media():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, platform, media_id, format FROM posts "
            "WHERE status='posted' AND media_id!=''").fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]
    finally:
        conn.close()


def _save(post_id: int, platform: str, m: dict) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO post_metrics(post_id,platform,impressions,reach,likes,comments,shares,"
            "saves,views,plays,followers_delta) VALUES (?,?,?,?,?,?,?,?,?,?,0)",
            (post_id, platform, m.get("impressions", 0), m.get("reach", 0), m.get("likes", 0),
             m.get("comments", 0), m.get("shares", 0), m.get("saves", 0), m.get("views", 0),
             m.get("plays", 0)))
        conn.commit()
    finally:
        conn.close()


def _ig_media_insights(media_id: str, is_reel: bool, token: str) -> dict:
    metrics = "plays,reach,likes,comments,shares,saved,total_interactions" if is_reel \
        else "impressions,reach,likes,comments,shares,saved"
    out = {}
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{social._graph()}/{media_id}/insights",
                      params={"metric": metrics, "access_token": token})
            data = (r.json() or {}).get("data", [])
            vals = {d["name"]: (d.get("values") or [{}])[0].get("value", 0) for d in data}
        out = {
            "reach": vals.get("reach", 0), "impressions": vals.get("impressions", 0),
            "likes": vals.get("likes", 0), "comments": vals.get("comments", 0),
            "shares": vals.get("shares", 0), "saves": vals.get("saved", 0),
            "plays": vals.get("plays", 0), "views": vals.get("plays", 0),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("IG insights %s failed: %s", media_id, e)
    return out


def _yt_stats(video_id: str) -> dict:
    token = social._yt_access_token()
    if not token:
        return {}
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get("https://www.googleapis.com/youtube/v3/videos",
                      params={"part": "statistics", "id": video_id},
                      headers={"Authorization": f"Bearer {token}"})
            items = (r.json() or {}).get("items", [])
            if not items:
                return {}
            st = items[0].get("statistics", {})
        return {"views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0))}
    except Exception as e:  # noqa: BLE001
        log.warning("YT stats %s failed: %s", video_id, e)
        return {}


def sync_all() -> dict:
    """Refresh analytics for every posted item. Returns a small summary."""
    s = get_settings()
    posts = _posted_with_media()
    ig = yt = 0
    for p in posts:
        if p["platform"] == "instagram" and s.instagram_ready:
            m = _ig_media_insights(p["media_id"], (p.get("format") in ("reel", "short")),
                                   s.ig_access_token)
            if m:
                _save(p["id"], "instagram", m); ig += 1
        elif p["platform"] == "youtube" and s.youtube_ready:
            m = _yt_stats(p["media_id"])
            if m:
                _save(p["id"], "youtube", m); yt += 1
    return {"instagram_synced": ig, "youtube_synced": yt, "total_posts": len(posts)}
