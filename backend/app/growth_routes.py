"""API for Growth Studio (the social presence engine). Mounted under /api/growth."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException

from . import autopilot, growth, social
from .config import get_settings
from .db import get_conn

log = logging.getLogger("praxia.growth")
router = APIRouter(prefix="/api/growth")

POST_FIELDS = ["platform", "product", "format", "theme", "hook", "caption", "hashtags",
               "title", "script", "image_prompt", "image_path", "best_time", "status",
               "scheduled_at", "external_url", "notes", "boosted"]


def _row(r) -> dict:
    return {k: r[k] for k in r.keys()}


@router.get("/config")
def growth_config():
    s = get_settings()
    return {
        "openai_ready": s.openai_ready,
        "website": s.website,
        "brand_handle": s.brand_handle,
        "products": [{"key": k, "name": v["name"], "tagline": v["tagline"],
                      "options": v["options"]} for k, v in growth.PRODUCTS.items()],
        "platforms": social.platform_status(),
        "cloudinary_ready": s.cloudinary_ready,
        "pexels_ready": s.pexels_ready,
    }


# ------------------------------------------------------------- autopilot ----
@router.post("/autopilot/run")
def autopilot_run(payload: dict | None = None):
    return autopilot.run_today(force=bool((payload or {}).get("force")))


@router.get("/autopilot/status")
def autopilot_status():
    s = get_settings()
    return {
        "posted_today": autopilot.already_posted_today(),
        "platforms": social.platform_status(),
        "cloudinary_ready": s.cloudinary_ready,
        "pexels_ready": s.pexels_ready,
        "ready_to_post": s.instagram_ready or s.youtube_ready,
    }


@router.get("/autopilot/runs")
def autopilot_runs():
    conn = get_conn()
    try:
        return [{k: r[k] for k in r.keys() if k != "log"}
                for r in conn.execute("SELECT * FROM autopilot_runs ORDER BY id DESC LIMIT 20")]
    finally:
        conn.close()


@router.get("/autopilot/runs/{run_id}")
def autopilot_run_detail(run_id: int):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM autopilot_runs WHERE id=?", (run_id,)).fetchone()
        if not r:
            raise HTTPException(404, "Run not found.")
        d = {k: r[k] for k in r.keys()}
        d["log"] = json.loads(d.get("log") or "[]")
        return d
    finally:
        conn.close()


# ------------------------------------------------------------------ strategy --
@router.post("/strategy")
def make_strategy(payload: dict):
    goal = (payload.get("goal") or "").strip()
    products = payload.get("products") or list(growth.PRODUCTS.keys())
    days = max(1, min(30, int(payload.get("days") or 7)))
    per_day = max(1, min(4, int(payload.get("per_day") or 2)))
    try:
        plan = growth.strategist_plan(goal, products, days, per_day)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Strategy failed: {e}")
    slots = plan.get("slots") or []
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO campaigns(name,goal,products,days,per_day,plan_json) VALUES (?,?,?,?,?,?)",
            (f"Campaign · {days}d", goal, ",".join(products), days, per_day,
             json.dumps(plan.get("themes") or [])),
        )
        cid = cur.lastrowid
        for sl in slots:
            conn.execute(
                "INSERT INTO posts(campaign_id,day,slot,platform,product,format,theme,best_time,notes,status) "
                "VALUES (?,?,?,?,?,?,?,?,?, 'idea')",
                (cid, int(sl.get("day") or 1), int(sl.get("slot") or 1),
                 sl.get("platform") or "instagram", sl.get("product") or products[0],
                 sl.get("format") or "reel", sl.get("pillar") or "",
                 sl.get("best_time") or "", sl.get("hook_angle") or ""),
            )
        conn.commit()
    finally:
        conn.close()
    return {"campaign_id": cid, "themes": plan.get("themes") or [], "slots": len(slots)}


@router.get("/campaigns")
def campaigns():
    conn = get_conn()
    try:
        out = []
        for r in conn.execute("SELECT * FROM campaigns ORDER BY id DESC"):
            c = _row(r)
            c["themes"] = json.loads(c.get("plan_json") or "[]")
            counts = {row["status"]: row["c"] for row in conn.execute(
                "SELECT status, COUNT(*) c FROM posts WHERE campaign_id=? GROUP BY status", (c["id"],))}
            c["counts"] = counts
            out.append(c)
        return out
    finally:
        conn.close()


# --------------------------------------------------------------------- posts --
@router.get("/posts")
def list_posts(campaign_id: int | None = None, status: str | None = None, platform: str | None = None):
    conn = get_conn()
    try:
        q, args = "SELECT * FROM posts", []
        cond = []
        if campaign_id:
            cond.append("campaign_id=?"); args.append(campaign_id)
        if status:
            cond.append("status=?"); args.append(status)
        if platform:
            cond.append("platform=?"); args.append(platform)
        if cond:
            q += " WHERE " + " AND ".join(cond)
        q += " ORDER BY day, slot, id"
        return [_row(r) for r in conn.execute(q, args)]
    finally:
        conn.close()


@router.post("/posts/generate")
def generate_posts(payload: dict):
    """Run Content Creator + SEO agents to fully draft posts. Accepts explicit ids, else all
    'idea' posts of a campaign (optionally capped by limit)."""
    ids = payload.get("ids")
    conn = get_conn()
    try:
        if ids:
            rows = [conn.execute("SELECT * FROM posts WHERE id=?", (i,)).fetchone() for i in ids]
            rows = [r for r in rows if r]
        else:
            cid = payload.get("campaign_id")
            limit = int(payload.get("limit") or 6)
            q = "SELECT * FROM posts WHERE status='idea'"
            a = []
            if cid:
                q += " AND campaign_id=?"; a.append(cid)
            q += " ORDER BY day, slot LIMIT ?"; a.append(limit)
            rows = conn.execute(q, a).fetchall()
        posts = [_row(r) for r in rows]
    finally:
        conn.close()
    done, failed = 0, 0
    for p in posts:
        try:
            c = growth.create_post(p["platform"], p["format"], p["product"],
                                   p.get("theme") or "", p.get("notes") or "")
            seo = growth.seo_optimize(p["platform"], p["product"], c.get("hook", ""),
                                      c.get("caption", ""))
            notes = f"keywords: {seo.get('keywords','')} · boost: {seo.get('boost_tip','')}"
            conn = get_conn()
            try:
                conn.execute(
                    "UPDATE posts SET title=?, hook=?, script=?, caption=?, image_prompt=?, "
                    "hashtags=?, best_time=COALESCE(NULLIF(?,''), best_time), notes=?, status='drafted' WHERE id=?",
                    (c.get("title", ""), c.get("hook", ""), c.get("script", ""), c.get("caption", ""),
                     c.get("image_prompt", ""), seo.get("hashtags", ""), seo.get("best_time", ""),
                     notes, p["id"]),
                )
                conn.commit()
            finally:
                conn.close()
            done += 1
        except Exception as e:  # noqa: BLE001
            log.warning("generate post %s failed: %s", p.get("id"), e)
            failed += 1
    return {"drafted": done, "failed": failed}


@router.post("/posts/{pid}/image")
def make_image(pid: int):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "Post not found.")
        p = _row(r)
    finally:
        conn.close()
    prompt = p.get("image_prompt") or p.get("hook") or p.get("theme") or "Praxia AI studio"
    try:
        path = growth.generate_image(prompt, p.get("format") or "reel", slug=f"p{pid}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Image failed: {e}")
    conn = get_conn()
    try:
        conn.execute("UPDATE posts SET image_path=? WHERE id=?", (path, pid))
        conn.commit()
    finally:
        conn.close()
    return {"image_path": path}


@router.patch("/posts/{pid}")
def update_post(pid: int, payload: dict):
    fields = {k: v for k, v in payload.items() if k in POST_FIELDS}
    if not fields:
        raise HTTPException(400, "No updatable fields.")
    conn = get_conn()
    try:
        sets = ",".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE posts SET {sets} WHERE id=?", [*fields.values(), pid])
        conn.commit()
        r = conn.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "Post not found.")
        return _row(r)
    finally:
        conn.close()


@router.delete("/posts/{pid}")
def delete_post(pid: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM posts WHERE id=?", (pid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/posts/{pid}/publish")
def publish_post(pid: int):
    """Publish now. Uses a connected platform if available, else returns a manual-post pack."""
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "Post not found.")
        p = _row(r)
    finally:
        conn.close()
    caption = (p.get("caption") or "").strip()
    tags = (p.get("hashtags") or "").strip()
    full_caption = (caption + ("\n\n" + tags if tags else "")).strip()
    result = {"ok": False, "manual": True}
    if p["platform"] == "instagram":
        st = social.publish_instagram(full_caption, p.get("image_path") or "")
        result = st
    elif p["platform"] == "youtube":
        st = social.publish_youtube(p.get("title") or caption[:80], full_caption,
                                    p.get("notes_video_path") or "", tags.split())
        result = st
    if result.get("ok"):
        conn = get_conn()
        try:
            conn.execute("UPDATE posts SET status='posted', posted_at=datetime('now'), external_url=? WHERE id=?",
                         (result.get("external_url", ""), pid))
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "posted": True, "external_url": result.get("external_url", "")}
    # not connected / failed -> manual pack for one-tap posting
    return {"ok": False, "manual": True, "reason": result.get("error", "platform not connected"),
            "caption": full_caption, "image_path": p.get("image_path", ""),
            "title": p.get("title", ""), "platform": p["platform"]}


@router.post("/posts/{pid}/posted")
def mark_posted(pid: int, payload: dict):
    """User posted it by hand: record it so tracking + analytics stay complete."""
    url = (payload.get("external_url") or "").strip()
    conn = get_conn()
    try:
        conn.execute("UPDATE posts SET status='posted', posted_at=datetime('now'), external_url=? WHERE id=?",
                     (url, pid))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


# ------------------------------------------------------------------- metrics --
@router.post("/posts/{pid}/metrics")
def record_metrics(pid: int, payload: dict):
    keys = ["impressions", "reach", "likes", "comments", "shares", "saves", "views", "followers_delta"]
    vals = {k: int(payload.get(k) or 0) for k in keys}
    conn = get_conn()
    try:
        pr = conn.execute("SELECT platform FROM posts WHERE id=?", (pid,)).fetchone()
        plat = pr["platform"] if pr else ""
        conn.execute(
            "INSERT INTO post_metrics(post_id,platform,impressions,reach,likes,comments,shares,saves,views,followers_delta) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pid, plat, vals["impressions"], vals["reach"], vals["likes"], vals["comments"],
             vals["shares"], vals["saves"], vals["views"], vals["followers_delta"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.get("/stats")
def growth_stats():
    conn = get_conn()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(reach),0) reach, COALESCE(SUM(impressions),0) impressions, "
            "COALESCE(SUM(likes),0) likes, COALESCE(SUM(shares),0) shares, COALESCE(SUM(saves),0) saves, "
            "COALESCE(SUM(views),0) views, COALESCE(SUM(followers_delta),0) followers FROM post_metrics"
        ).fetchone()
        posted = conn.execute("SELECT COUNT(*) c FROM posts WHERE status='posted'").fetchone()["c"]
        scheduled = conn.execute("SELECT COUNT(*) c FROM posts WHERE status='scheduled'").fetchone()["c"]
        drafted = conn.execute("SELECT COUNT(*) c FROM posts WHERE status IN ('drafted','approved')").fetchone()["c"]
        ideas = conn.execute("SELECT COUNT(*) c FROM posts WHERE status='idea'").fetchone()["c"]
        return {"totals": _row(totals), "posted": posted, "scheduled": scheduled,
                "drafted": drafted, "ideas": ideas}
    finally:
        conn.close()


# --------------------------------------------------------------------- adapt --
@router.post("/adapt")
def adapt(payload: dict):
    """Growth Analyst reviews reach and recommends next moves; can seed the winning next ideas."""
    cid = payload.get("campaign_id")
    conn = get_conn()
    try:
        q = ("SELECT p.id post_id, p.platform, p.product, p.theme pillar, p.hook, "
             "COALESCE(SUM(m.impressions),0) impressions, COALESCE(SUM(m.reach),0) reach, "
             "COALESCE(SUM(m.likes),0) likes, COALESCE(SUM(m.comments),0) comments, "
             "COALESCE(SUM(m.shares),0) shares, COALESCE(SUM(m.saves),0) saves, "
             "COALESCE(SUM(m.views),0) views "
             "FROM posts p LEFT JOIN post_metrics m ON m.post_id=p.id WHERE p.status='posted'")
        a = []
        if cid:
            q += " AND p.campaign_id=?"; a.append(cid)
        q += " GROUP BY p.id ORDER BY reach DESC LIMIT 40"
        rows = [_row(r) for r in conn.execute(q, a)]
    finally:
        conn.close()
    if not rows:
        raise HTTPException(400, "No posted content with metrics yet. Post some, add reach numbers, then adapt.")
    try:
        review = growth.analyst_review(rows)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Adapt failed: {e}")
    # seed next ideas as fresh idea-posts on the campaign so the loop continues
    seeded = 0
    if payload.get("seed_next") and review.get("next_ideas"):
        conn = get_conn()
        try:
            if not cid:
                row = conn.execute("SELECT id FROM campaigns ORDER BY id DESC LIMIT 1").fetchone()
                target_cid = row["id"] if row else None
            else:
                target_cid = cid
            if target_cid:
                for idea in review["next_ideas"][:8]:
                    conn.execute(
                        "INSERT INTO posts(campaign_id,day,slot,platform,product,format,theme,notes,status) "
                        "VALUES (?,?,?,?,?,?,?,?, 'idea')",
                        (target_cid, 99, seeded + 1, idea.get("platform") or "instagram",
                         idea.get("product") or "course_factory", idea.get("format") or "reel",
                         idea.get("pillar") or "", idea.get("hook_angle") or ""),
                    )
                    seeded += 1
                conn.commit()
        finally:
            conn.close()
    review["seeded_ideas"] = seeded
    return review
