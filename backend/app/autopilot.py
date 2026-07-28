"""One-button daily autopilot.

On each run it: (1) refreshes ALL-time analytics from Instagram + YouTube, (2) lets the Growth
Analyst study the whole history and choose today's angle, (3) scripts + builds one vertical Reel with
voiceover, AI + real visuals and captions, (4) QA-gates it end to end (audio not cutting, coherent,
no price, no em dash), (5) posts it to Instagram (Reel) and YouTube (Short), then (6) deletes every
local and throwaway-cloud file. No copies are kept.

Runs in a background thread; the UI polls the run row for the live log.
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import threading
from pathlib import Path

from . import growth, insights, media, qa, social
from .config import get_settings
from .db import get_conn

log = logging.getLogger("praxia.autopilot")
_lock = threading.Lock()
_running = False

PRODUCT_ROTATION = ["course_factory", "automation_consultancy", "automation_training"]


def _pick_variety():
    """Choose a topic, visual style, transition and meme-avoid-set that differ from recent posts."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT topic, style, meme_id FROM posts WHERE status='posted' ORDER BY id DESC LIMIT 8"
        ).fetchall()
    finally:
        conn.close()
    recent_topics = {r["topic"] for r in rows if r["topic"]}
    recent_styles = [r["style"] for r in rows if r["style"]]
    used_memes = {r["meme_id"] for r in rows if r["meme_id"]}
    posted = len(rows)
    topics = [t for t in growth.AUTOMATION_TOPICS if t["key"] not in recent_topics] or growth.AUTOMATION_TOPICS
    topic = topics[posted % len(topics)]
    style = growth.VISUAL_STYLES[posted % len(growth.VISUAL_STYLES)]
    if style in recent_styles[:2] and len(growth.VISUAL_STYLES) > 1:
        style = growth.VISUAL_STYLES[(posted + 1) % len(growth.VISUAL_STYLES)]
    transition = growth.TRANSITIONS[posted % len(growth.TRANSITIONS)]
    return topic, style, transition, used_memes, posted


# ------------------------------------------------------------------ run row --
def _new_run() -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO autopilot_runs(run_date,status,log) VALUES (date('now'),'running','[]')")
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _log(run_id: int, msg: str, level: str = "info") -> None:
    log.info("[run %s] %s", run_id, msg)
    conn = get_conn()
    try:
        r = conn.execute("SELECT log FROM autopilot_runs WHERE id=?", (run_id,)).fetchone()
        entries = json.loads(r["log"] or "[]") if r else []
        entries.append({"t": _now(), "level": level, "msg": msg})
        conn.execute("UPDATE autopilot_runs SET log=? WHERE id=?", (json.dumps(entries), run_id))
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    conn = get_conn()
    try:
        return conn.execute("SELECT strftime('%H:%M:%S','now','localtime') t").fetchone()["t"]
    finally:
        conn.close()


def _finish(run_id: int, status: str, ig_post=None, yt_post=None) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE autopilot_runs SET status=?, ig_post_id=?, yt_post_id=? WHERE id=?",
                     (status, ig_post, yt_post, run_id))
        conn.commit()
    finally:
        conn.close()


def already_posted_today() -> bool:
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT COUNT(*) c FROM autopilot_runs WHERE run_date=date('now') AND status='posted'"
        ).fetchone()
        return r["c"] > 0
    finally:
        conn.close()


# ------------------------------------------------------------- angle picker --
def _todays_angle(run_id: int) -> dict:
    """Study all history; return {product, pillar, hook_angle}."""
    conn = get_conn()
    try:
        rows = [{k: r[k] for k in r.keys()} for r in conn.execute(
            "SELECT p.id post_id, p.platform, p.product, p.theme pillar, p.hook, "
            "COALESCE(SUM(m.reach),0) reach, COALESCE(SUM(m.plays),0) plays, "
            "COALESCE(SUM(m.likes),0) likes, COALESCE(SUM(m.shares),0) shares, "
            "COALESCE(SUM(m.saves),0) saves, COALESCE(SUM(m.comments),0) comments "
            "FROM posts p LEFT JOIN post_metrics m ON m.post_id=p.id "
            "WHERE p.status='posted' GROUP BY p.id ORDER BY reach DESC LIMIT 60")]
        posted_count = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE status='posted' AND platform='instagram'").fetchone()["c"]
    finally:
        conn.close()

    default_product = PRODUCT_ROTATION[posted_count % len(PRODUCT_ROTATION)]
    try:
        brief = growth.growth_brief(rows, default_product)
        report = brief.get("report", "")
        if report:
            _log(run_id, "Mastermind: " + report)
        if brief.get("focus"):
            _log(run_id, "Today's growth focus: " + brief["focus"])
        reel = brief.get("reel") or {}
        demo = brief.get("demo") or {}
        return {
            "report": report, "focus": brief.get("focus", ""),
            "reel": {"product": reel.get("product") or default_product,
                     "pillar": reel.get("pillar") or "impact proof",
                     "hook_angle": reel.get("hook_angle") or ""},
            "demo": {"product": demo.get("product") or default_product,
                     "topic": demo.get("topic") or "How Praxia works",
                     "angle": demo.get("angle") or ""},
        }
    except Exception as e:  # noqa: BLE001
        _log(run_id, f"Mastermind skipped ({e}); rotating to {default_product}.", "warn")
        return {"report": "", "focus": "",
                "reel": {"product": default_product, "pillar": "impact proof", "hook_angle": ""},
                "demo": {"product": default_product, "topic": "How Praxia works", "angle": ""}}


# ------------------------------------------------------------------ posting --
def _record_post(platform: str, fmt: str, product: str, spec: dict, seo: dict,
                 seconds: float) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO posts(platform,product,format,theme,hook,title,caption,hashtags,script,"
            "status,video_seconds,topic,style,meme_id) VALUES (?,?,?,?,?,?,?,?,?, 'drafted', ?,?,?,?)",
            (platform, product, fmt, spec.get("pillar", spec.get("topic", "")),
             (spec.get("segments") or [{}])[0].get("narration", ""),
             spec.get("yt_title", ""), spec.get("caption", ""), seo.get("hashtags", ""),
             json.dumps(spec.get("segments") or []), int(seconds),
             spec.get("topic", ""), spec.get("style", ""), spec.get("meme_id", "")))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _mark_posted(post_id: int, media_id: str, url: str) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE posts SET status='posted', posted_at=datetime('now'), media_id=?, "
                     "external_url=? WHERE id=?", (media_id, url, post_id))
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------- the run ----
def _execute(run_id: int, reels_only: bool = False) -> None:
    global _running
    s = get_settings()
    workdir = tempfile.mkdtemp(prefix="praxia_reel_")
    ig_post_id = yt_post_id = None
    posted_any = False
    try:
        # 0) keep the Instagram token alive (extends ~60 days on each use)
        if social.refresh_instagram_token():
            _log(run_id, "Instagram token refreshed (good for another ~60 days).")

        # 1) refresh ALL analytics
        if s.instagram_ready or s.youtube_ready:
            summ = insights.sync_all()
            _log(run_id, f"Analytics refreshed: {summ['instagram_synced']} IG, "
                         f"{summ['youtube_synced']} YT of {summ['total_posts']} posts.")
        else:
            _log(run_id, "No platform connected yet, skipping analytics pull (dry build).", "warn")

        # 2) MASTERMIND: diagnose + decide today's product
        plan = _todays_angle(run_id)
        product = plan["reel"]["product"]
        pname = growth.PRODUCTS.get(product, {}).get("name", product)

        # variety: a different automation topic / style / transition / meme every day
        topic, style, transition, used_memes, posted_ct = _pick_variety()
        _log(run_id, f"Today: {pname} | problem: {topic['title']} | style: {style} | transition: {transition}")

        # 3) content script (meme + mockup + narration); editorial pre-check on narration + caption
        def _narr(sp):
            return " ".join((x.get("narration") or "") for x in (sp.get("segments") or []))

        spec = growth.content_script(product, topic, style)
        spec["transition"] = transition
        for attempt in (1, 2, 3):
            ed = qa.editorial_check(_narr(spec), spec.get("caption", ""), spec.get("yt_title", ""))
            if ed["ok"]:
                break
            _log(run_id, "Editorial flagged the script: " + "; ".join(ed["issues"]) + ". Rewriting.", "warn")
            if attempt == 3:
                _log(run_id, "Script still flagged after 3 rewrites. Aborting.", "error")
                _finish(run_id, "failed")
                return
            spec = growth.content_script(product, topic, style)
            spec["transition"] = transition
        _log(run_id, "Meme + script approved. Building the reel (faceless)...")
        seo = {"hashtags": spec.get("hashtags", "")}

        # 4) build once, then TECHNICAL QA. Rebuild once on failure.
        from . import reel as reel_mod
        built = None
        for attempt in (1, 2):
            built = reel_mod.build_content_reel(spec, workdir, used_meme_ids=used_memes,
                                                seed=posted_ct + attempt)
            tech = qa.technical_check(built["path"])
            if tech["ok"]:
                _log(run_id, f"Reel built + QA passed: {tech['duration']}s, meme "
                             f"'{built.get('meme_name','')}', audio {tech['mean_volume_db']} dB.")
                break
            _log(run_id, "Technical QA failed: " + "; ".join(tech["issues"]), "warn")
            if attempt == 2:
                _log(run_id, "Video QA failed twice. Aborting.", "error")
                _finish(run_id, "failed")
                return
        spec["topic"] = topic["key"]; spec["style"] = style; spec["meme_id"] = built.get("meme_id", "")
        angle = {"product": product}  # keep downstream references working

        caption = spec.get("caption", "")
        tags = seo.get("hashtags", "")
        full_caption = (caption + ("\n\n" + tags if tags else "")).strip()

        # 5) YouTube Short (direct upload, no host needed)
        if s.youtube_ready:
            yt_post_id = _record_post("youtube", "short", angle["product"], spec, seo, built["seconds"])
            _log(run_id, "Uploading YouTube Short...")
            yt = social.publish_youtube(spec.get("yt_title", caption[:80]), full_caption,
                                        built["path"], tags.split())
            if yt.get("ok"):
                _mark_posted(yt_post_id, yt.get("id", ""), yt["external_url"])
                _log(run_id, f"YouTube Short live: {yt['external_url']}")
                posted_any = True
            else:
                _log(run_id, f"YouTube upload failed: {yt.get('error')}", "error")
        else:
            _log(run_id, "YouTube not connected, skipped.", "warn")

        # 6) Instagram Reel (needs a public URL: ephemeral Cloudinary pass-through)
        if s.instagram_ready:
            ig_post_id = _record_post("instagram", "reel", angle["product"], spec, seo, built["seconds"])
            if not s.cloudinary_ready:
                _log(run_id, "Instagram needs the Cloudinary pass-through to fetch the video. Skipped.", "warn")
            else:
                _log(run_id, "Uploading reel to throwaway host for Instagram to fetch...")
                up = media.upload(built["path"], "video")
                if not up.get("ok"):
                    _log(run_id, f"Pass-through upload failed: {up.get('error')}", "error")
                else:
                    _log(run_id, "Publishing Instagram Reel (Instagram is processing the video)...")
                    ig = social.publish_reel(full_caption, up["url"])
                    if ig.get("ok"):
                        _mark_posted(ig_post_id, ig.get("media_id", ""), ig["external_url"])
                        _log(run_id, f"Instagram Reel live: {ig['external_url']}")
                        posted_any = True
                    else:
                        _log(run_id, f"Instagram publish failed: {ig.get('error')}", "error")
                    # delete the throwaway copy no matter what
                    media.destroy(up.get("public_id", ""), "video")
                    _log(run_id, "Deleted the throwaway cloud copy.")
        else:
            _log(run_id, "Instagram not connected, skipped.", "warn")

        # 6b) STATIC product post to Instagram (minimal text, one product/day) — both modes
        if s.instagram_ready and s.cloudinary_ready:
            try:
                _static_post_ig(run_id, posted_ct)
                posted_any = True
            except Exception as e:  # noqa: BLE001
                _log(run_id, f"Static post error: {e}", "warn")

        # 7) LONG-FORM DEMO to YouTube (3-5 min walkthrough) — skipped in reels-only mode
        if not reels_only and s.youtube_ready:
            try:
                d = plan["demo"]
                dname = growth.PRODUCTS.get(d["product"], {}).get("name", d["product"])
                _log(run_id, f"Building 3-5 min YouTube demo: {dname} | {d.get('topic','')[:70]}")
                dspec = growth.demo_script(d["product"], d.get("topic", ""), d.get("angle", ""))
                from . import demo as demo_mod
                dwork = tempfile.mkdtemp(prefix="praxia_demo_")
                try:
                    dbuilt = demo_mod.build_demo(dspec, dwork)
                    dtech = qa.technical_check(dbuilt["path"])
                    if not dtech["ok"]:
                        _log(run_id, "Demo QA failed: " + "; ".join(dtech["issues"]) + " (skipping demo).", "warn")
                    else:
                        _log(run_id, f"Demo built + QA passed: {dtech['duration']}s. Uploading to YouTube...")
                        dtags = (dspec.get("tags", "") or "").replace(",", " ").split()
                        dpost = _record_post("youtube", "long_video", d["product"],
                                             {"pillar": d.get("topic", ""), "segments": dspec.get("segments"),
                                              "yt_title": dspec.get("yt_title", ""),
                                              "caption": dspec.get("description", "")},
                                             {"hashtags": dspec.get("tags", "")}, dbuilt["seconds"])
                        dyt = social.publish_youtube(dspec.get("yt_title", dname + " demo"),
                                                     dspec.get("description", ""), dbuilt["path"], dtags)
                        if dyt.get("ok"):
                            _mark_posted(dpost, dyt.get("id", ""), dyt["external_url"])
                            _log(run_id, f"YouTube demo live: {dyt['external_url']}")
                            posted_any = True
                        else:
                            _log(run_id, f"Demo upload failed: {dyt.get('error')}", "error")
                finally:
                    shutil.rmtree(dwork, ignore_errors=True)
            except Exception as e:  # noqa: BLE001
                _log(run_id, f"Demo step error: {e}", "warn")

        # 8) SELF-EVALUATION vs targets
        try:
            _self_evaluate(run_id)
        except Exception as e:  # noqa: BLE001
            _log(run_id, f"Self-eval skipped: {e}", "warn")

        _finish(run_id, "posted" if posted_any else "failed", ig_post_id, yt_post_id)
        _log(run_id, "Done." if posted_any else "Nothing was published (connect a platform).",
             "info" if posted_any else "warn")
    except Exception as e:  # noqa: BLE001
        _log(run_id, f"Autopilot error: {e}", "error")
        _finish(run_id, "failed", ig_post_id, yt_post_id)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        _log(run_id, "Cleaned up all local files. No copies kept.")
        with _lock:
            _running = False


def reel_build(spec: dict, workdir: str) -> dict:
    # isolated import so a missing ffmpeg/moviepy surfaces only when actually building
    from . import reel
    return reel.build_reel(spec, workdir)


def _static_post_ig(run_id: int, posted_ct: int) -> None:
    """Build + post a minimal static product card to Instagram, rotating one product per day."""
    from . import reel as reel_mod
    product = PRODUCT_ROTATION[posted_ct % len(PRODUCT_ROTATION)]
    pname = growth.PRODUCTS.get(product, {}).get("name", product)
    sp = growth.static_post(product)
    _log(run_id, f"Static post: {pname} (minimal text).")
    tmp = tempfile.mkdtemp(prefix="praxia_static_")
    try:
        img = str(Path(tmp) / "card.png")
        reel_mod.build_static_card({"headline": sp.get("headline", pname),
                                    "subline": sp.get("subline", ""),
                                    "product_name": pname}, img)
        up = media.upload(img, "image")
        if not up.get("ok"):
            _log(run_id, f"Static image upload failed: {up.get('error')}", "warn"); return
        cap = (sp.get("caption", "") + "\n\n" + sp.get("hashtags", "")).strip()
        r = social.publish_image_url(cap, up["url"])
        media.destroy(up.get("public_id", ""), "image")
        if r.get("ok"):
            conn = get_conn()
            try:
                conn.execute(
                    "INSERT INTO posts(platform,product,format,caption,hashtags,status,posted_at,media_id,external_url) "
                    "VALUES ('instagram',?, 'image', ?, ?, 'posted', datetime('now'), ?, ?)",
                    (product, sp.get("caption", ""), sp.get("hashtags", ""),
                     r.get("media_id", ""), r["external_url"]))
                conn.commit()
            finally:
                conn.close()
            _log(run_id, f"Static post live: {r['external_url']}")
        else:
            _log(run_id, f"Static post failed: {r.get('error')}", "warn")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def get_targets() -> dict:
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM targets ORDER BY id DESC LIMIT 1").fetchone()
        if not r:
            conn.execute("INSERT INTO targets DEFAULT VALUES"); conn.commit()
            r = conn.execute("SELECT * FROM targets ORDER BY id DESC LIMIT 1").fetchone()
        return {k: r[k] for k in r.keys()}
    finally:
        conn.close()


def achieved() -> dict:
    """Best-so-far numbers: totals + best single-post reach/likes, plus posted count."""
    conn = get_conn()
    try:
        t = conn.execute(
            "SELECT COALESCE(SUM(reach),0) reach, COALESCE(SUM(likes),0) likes, "
            "COALESCE(SUM(impressions),0)+COALESCE(SUM(plays),0) impressions, "
            "COALESCE(SUM(followers_delta),0) followers, COALESCE(MAX(reach),0) best_reach, "
            "COALESCE(MAX(likes),0) best_likes FROM post_metrics").fetchone()
        posted = conn.execute("SELECT COUNT(*) c FROM posts WHERE status='posted'").fetchone()["c"]
        return {**{k: t[k] for k in t.keys()}, "posted": posted}
    finally:
        conn.close()


def _self_evaluate(run_id: int) -> None:
    tg = get_targets(); ac = achieved()
    parts = []
    for label, got, want in [
        ("reach/post", ac["best_reach"], tg["reach_per_post"]),
        ("likes/post", ac["best_likes"], tg["likes_per_post"]),
        ("followers", ac["followers"], tg["followers_per_day"]),
    ]:
        hit = "on track" if got >= want else f"short ({got}/{want})"
        parts.append(f"{label}: {hit}")
    behind = ac["best_reach"] < tg["reach_per_post"]
    verdict = ("Below target so far. New accounts need consistent daily posting for weeks; "
               "the engine will keep varying hooks, memes and topics to find what lands."
               if behind else "Hitting targets. Keep the cadence.")
    _log(run_id, "Self-eval vs targets: " + " | ".join(parts))
    _log(run_id, verdict)


def cleanup_orphans() -> None:
    """Remove any reel temp dirs left by a hard crash (normal runs self-clean)."""
    import glob
    for pat in ("praxia_reel_*", "praxia_demo_*", "praxia_static_*"):
        for d in glob.glob(str(Path(tempfile.gettempdir()) / pat)):
            shutil.rmtree(d, ignore_errors=True)


def run_today(force: bool = False, reels_only: bool = False) -> dict:
    global _running
    with _lock:
        if _running:
            return {"ok": False, "error": "Autopilot is already running. Watch the log."}
        if already_posted_today() and not force:
            return {"ok": False, "error": "Already posted today. Come back tomorrow, or force a run."}
        _running = True
    run_id = _new_run()
    threading.Thread(target=_execute, args=(run_id, reels_only),
                     name=f"autopilot-{run_id}", daemon=True).start()
    return {"ok": True, "run_id": run_id}
