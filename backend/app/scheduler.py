"""Background auto-poster. Every minute, publishes posts whose scheduled time has arrived,
but only when AUTO_POST is on and the target platform is connected. Otherwise posts simply wait
in the calendar for a one-tap manual publish. Pure stdlib threading, no extra deps."""
from __future__ import annotations

import logging
import threading
import time

from . import social
from .config import get_settings
from .db import get_conn

log = logging.getLogger("praxia.scheduler")
_started = False


def _due_posts():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM posts WHERE status='scheduled' AND scheduled_at!='' "
            "AND scheduled_at <= datetime('now') ORDER BY scheduled_at LIMIT 20"
        ).fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]
    finally:
        conn.close()


def _publish(p: dict) -> None:
    caption = (p.get("caption") or "").strip()
    tags = (p.get("hashtags") or "").strip()
    full = (caption + ("\n\n" + tags if tags else "")).strip()
    if p["platform"] == "instagram":
        res = social.publish_instagram(full, p.get("image_path") or "")
    elif p["platform"] == "youtube":
        res = social.publish_youtube(p.get("title") or caption[:80], full, "", tags.split())
    else:
        return
    if res.get("ok"):
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE posts SET status='posted', posted_at=datetime('now'), external_url=? WHERE id=?",
                (res.get("external_url", ""), p["id"]))
            conn.commit()
        finally:
            conn.close()
        log.info("auto-posted #%s to %s -> %s", p["id"], p["platform"], res.get("external_url"))
    else:
        log.warning("auto-post #%s failed: %s", p["id"], res.get("error"))


def _loop() -> None:
    while True:
        try:
            s = get_settings()
            if s.auto_post and (s.instagram_ready or s.youtube_ready):
                for p in _due_posts():
                    connected = (p["platform"] == "instagram" and s.instagram_ready) or \
                                (p["platform"] == "youtube" and s.youtube_ready)
                    if connected:
                        _publish(p)
        except Exception as e:  # noqa: BLE001
            log.warning("scheduler tick error: %s", e)
        time.sleep(60)


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, name="growth-scheduler", daemon=True).start()
    log.info("Growth scheduler started (auto-post gated by AUTO_POST + platform credentials).")
