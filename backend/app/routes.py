"""API for the Praxia Marketing tool."""
from __future__ import annotations

import csv
import io
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, Response

from . import ai, firsttouch, mailer, sales, sourcing
from .config import get_settings
from .db import get_conn

log = logging.getLogger("praxia.mkt")
router = APIRouter(prefix="/api")

LEAD_FIELDS = ["name", "org", "org_type", "country", "title", "email",
               "linkedin_url", "phone", "source", "status", "notes"]
FUNNEL = ["new", "queued", "contacted", "opened", "clicked", "replied", "meeting", "won", "lost"]


def _row(r) -> dict:
    return {k: r[k] for k in r.keys()}


@router.get("/config")
async def config():
    s = get_settings()
    return {
        "openai_ready": s.openai_ready,
        "smtp_ready": s.smtp_ready,
        "from_name": s.from_name,
        "public_email": s.public_email,
        "whatsapp": s.whatsapp,
        "booking_link": s.booking_link,
        "sender": s.smtp_user,
        "sender_name": s.sender_name,
        "youtube_demo": s.youtube_demo,
        "daily_send_cap": s.daily_send_cap,
    }


@router.get("/firsttouch/{lead_id}")
def firsttouch_for(lead_id: int):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not r:
            raise HTTPException(404, "Lead not found.")
        lead = _row(r)
    finally:
        conn.close()
    return firsttouch.build_first_touch(lead)


@router.post("/firsttouch/send-all")
def firsttouch_send_all():
    """Send the fixed first-touch email (with the overview PDF attached) to every accepted lead
    still in status 'new'. Each send is logged to messages + events so replies stay tracked."""
    s = get_settings()
    if not s.smtp_ready:
        raise HTTPException(400, "Email is not configured. Add SMTP_USER and SMTP_APP_PASSWORD in backend/.env.")
    attachments = s.first_touch_attachments()
    attach_names = ", ".join(os.path.basename(p) for p in attachments)
    conn = get_conn()
    try:
        leads = [_row(r) for r in conn.execute("SELECT * FROM leads WHERE status='new' AND email!=''")]
    finally:
        conn.close()
    sent, failed = 0, 0
    for lead in leads:
        msg = firsttouch.build_first_touch(lead)
        try:
            mailer.send_email(lead["email"], msg["subject"], msg["body"], attachments=attachments)
        except Exception:  # noqa: BLE001
            failed += 1
            continue
        conn = get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO messages(lead_id,channel,subject,body,status) VALUES (?, 'email', ?, ?, 'sent')",
                (lead["id"], msg["subject"], msg["body"]),
            )
            conn.execute("INSERT INTO events(lead_id,message_id,type,meta) VALUES (?,?, 'sent', ?)",
                         (lead["id"], cur.lastrowid, f"first-touch; attached: {attach_names or 'none'}"))
            conn.execute("UPDATE leads SET status='contacted' WHERE id=?", (lead["id"],))
            conn.commit()
        finally:
            conn.close()
        sent += 1
    return {"sent": sent, "failed": failed, "total": len(leads),
            "attached": [os.path.basename(p) for p in attachments]}


@router.get("/stats")
async def stats():
    conn = get_conn()
    try:
        by_status = {s: 0 for s in FUNNEL}
        for r in conn.execute("SELECT status, COUNT(*) c FROM leads GROUP BY status"):
            by_status[r["status"]] = r["c"]
        total = conn.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
        sent = conn.execute("SELECT COUNT(*) c FROM messages WHERE status='sent'").fetchone()["c"]
        today = conn.execute(
            "SELECT COUNT(*) c FROM messages WHERE status='sent' AND date(sent_at)=date('now')"
        ).fetchone()["c"]
        by_country = {r["country"]: r["c"] for r in
                      conn.execute("SELECT country, COUNT(*) c FROM leads GROUP BY country")}
        by_type = {r["org_type"]: r["c"] for r in
                   conn.execute("SELECT org_type, COUNT(*) c FROM leads GROUP BY org_type")}
        contacted = sum(by_status[s] for s in ["contacted", "opened", "clicked", "replied", "meeting", "won"])
        by_cat = {"warm": 0, "soso": 0, "cold": 0}
        for r in conn.execute("SELECT category, COUNT(*) c FROM leads WHERE category IN ('warm','soso','cold') GROUP BY category"):
            by_cat[r["category"]] = r["c"]
        new_replies = conn.execute("SELECT COUNT(*) c FROM replies WHERE handled=0").fetchone()["c"]
        return {
            "total": total, "sent": sent, "sent_today": today,
            "by_status": by_status, "by_country": by_country, "by_type": by_type,
            "by_category": by_cat, "new_replies": new_replies,
            "funnel": {
                "leads": total, "contacted": contacted,
                "replied": by_status["replied"] + by_status["meeting"] + by_status["won"],
                "meeting": by_status["meeting"] + by_status["won"],
                "won": by_status["won"],
            },
        }
    finally:
        conn.close()


@router.get("/leads")
async def list_leads(status: str | None = None, country: str | None = None):
    conn = get_conn()
    try:
        q = "SELECT * FROM leads"
        cond, args = [], []
        if status:
            cond.append("status=?"); args.append(status)
        if country:
            cond.append("country=?"); args.append(country)
        if cond:
            q += " WHERE " + " AND ".join(cond)
        q += " ORDER BY id DESC"
        return [_row(r) for r in conn.execute(q, args)]
    finally:
        conn.close()


@router.post("/leads")
async def create_lead(payload: dict):
    data = {k: (payload.get(k) or "") for k in LEAD_FIELDS}
    if not data.get("status"):
        data["status"] = "new"
    if not (data["email"] or data["org"] or data["name"]):
        raise HTTPException(400, "Provide at least a name, org, or email.")
    conn = get_conn()
    try:
        cols = ",".join(LEAD_FIELDS)
        ph = ",".join("?" for _ in LEAD_FIELDS)
        cur = conn.execute(f"INSERT INTO leads({cols}) VALUES ({ph})", [data[k] for k in LEAD_FIELDS])
        conn.commit()
        return {"id": cur.lastrowid, **data}
    finally:
        conn.close()


def _pick(low: dict, *keys: str) -> str:
    for k in keys:
        if low.get(k):
            return low[k]
    return ""


@router.post("/leads/import")
async def import_leads(payload: dict):
    """Universal importer for Apollo / LeadVault / SphereScout / LinkedIn CSV exports.
    Maps their columns to our rich B2B lead fields, dedups by email, tags with the current vertical."""
    from . import sales
    text = payload.get("csv") or ""
    if not text.strip():
        raise HTTPException(400, "Paste CSV text with a header row.")
    country = payload.get("country") or "USA"
    icp = sales.get_icp()
    reader = csv.DictReader(io.StringIO(text))
    conn = get_conn()
    added = 0
    try:
        existing = {r["email"].lower() for r in conn.execute("SELECT email FROM leads WHERE email!=''")}
        for row in reader:
            low = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            first = _pick(low, "first name", "first_name", "firstname")
            last = _pick(low, "last name", "last_name", "lastname")
            name = _pick(low, "name", "full name", "contact") or (first + " " + last).strip()
            email = _pick(low, "email", "email address", "work email", "primary email").lower()
            if email and email in existing:
                continue
            org = _pick(low, "company", "company name", "org", "organization", "account name", "employer")
            if not (email or org or name):
                continue
            data = {
                "name": name, "decision_maker": name,
                "org": org, "org_type": "corporate",
                "country": country,
                "title": _pick(low, "title", "job title", "designation", "position"),
                "email": email,
                "linkedin_url": _pick(low, "person linkedin url", "linkedin url", "linkedin", "linkedin_url"),
                "phone": _pick(low, "direct phone", "mobile phone", "company phone", "phone", "work direct phone"),
                "website": _pick(low, "website", "company website", "domain", "company domain url"),
                "company_size": _pick(low, "# employees", "employees", "company size", "employee count", "headcount"),
                "vertical": icp["key"], "source": _pick(low, "source") or "import",
                "status": "new", "stage": "new",
                "notes": _pick(low, "notes", "industry", "department", "seniority"),
            }
            if email:
                existing.add(email)
            cols = list(data.keys())
            conn.execute(f"INSERT INTO leads({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                         [data[k] for k in cols])
            added += 1
        conn.commit()
    finally:
        conn.close()
    return {"added": added, "vertical": icp["name"]}


@router.patch("/leads/{lead_id}")
async def update_lead(lead_id: int, payload: dict):
    fields = {k: v for k, v in payload.items() if k in LEAD_FIELDS}
    if not fields:
        raise HTTPException(400, "No updatable fields.")
    conn = get_conn()
    try:
        sets = ",".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE leads SET {sets} WHERE id=?", [*fields.values(), lead_id])
        if "status" in fields:
            conn.execute("INSERT INTO events(lead_id,type,meta) VALUES (?,?,?)",
                         (lead_id, "status", fields["status"]))
        conn.commit()
        r = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not r:
            raise HTTPException(404, "Lead not found.")
        return _row(r)
    finally:
        conn.close()


@router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM leads WHERE id=?", (lead_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.get("/templates")
async def templates():
    conn = get_conn()
    try:
        return [_row(r) for r in conn.execute("SELECT * FROM templates ORDER BY id")]
    finally:
        conn.close()


@router.post("/draft")
async def draft(payload: dict):
    lead_id = payload.get("lead_id")
    conn = get_conn()
    try:
        lr = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not lr:
            raise HTTPException(404, "Lead not found.")
        lead = _row(lr)
        tpl = None
        if payload.get("template_id"):
            tr = conn.execute("SELECT * FROM templates WHERE id=?", (payload["template_id"],)).fetchone()
            tpl = _row(tr) if tr else None
    finally:
        conn.close()
    try:
        return ai.personalize(lead, tpl)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Draft failed: {e}")


@router.post("/send")
async def send(payload: dict):
    lead_id = payload.get("lead_id")
    subject = (payload.get("subject") or "").strip()
    body = (payload.get("body") or "").strip()
    if not subject or not body:
        raise HTTPException(400, "Subject and body are required.")
    conn = get_conn()
    try:
        lr = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not lr:
            raise HTTPException(404, "Lead not found.")
        lead = _row(lr)
    finally:
        conn.close()
    if not lead["email"]:
        raise HTTPException(400, "This lead has no email address.")
    try:
        mailer.send_email(lead["email"], subject, body)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Send failed: {e}")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO messages(lead_id,channel,subject,body,status) VALUES (?,?,?,?, 'sent')",
            (lead_id, "email", subject, body),
        )
        conn.execute("INSERT INTO events(lead_id,message_id,type) VALUES (?,?, 'sent')",
                     (lead_id, cur.lastrowid))
        if lead["status"] in ("new", "queued"):
            conn.execute("UPDATE leads SET status='contacted' WHERE id=?", (lead_id,))
        conn.commit()
        return {"ok": True, "message_id": cur.lastrowid}
    finally:
        conn.close()


# --- lead sourcing (public email harvesting; no LinkedIn, no paid keys) ---
def _existing_emails(conn) -> set:
    e = set()
    for r in conn.execute("SELECT email FROM leads WHERE email!=''"):
        e.add(r["email"].lower())
    for r in conn.execute("SELECT email FROM candidates WHERE email!=''"):
        e.add(r["email"].lower())
    return e


def _add_candidates(rows: list[dict], org: str, org_type: str, country: str, source: str) -> int:
    conn = get_conn()
    added = 0
    try:
        existing = _existing_emails(conn)
        for row in rows:
            em = (row.get("email") or "").lower()
            if not em or em in existing:
                continue
            existing.add(em)
            conn.execute(
                "INSERT INTO candidates(name,org,org_type,country,email,domain,source,source_url) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("", org or sourcing.org_from_domain(row.get("domain", "")), org_type, country,
                 em, row.get("domain", ""), source, row.get("source_url", "")),
            )
            added += 1
        conn.commit()
    finally:
        conn.close()
    return added


@router.get("/seed")
def seed():
    return [{"name": n, "domain": d, "country": c, "org_type": t} for (n, d, c, t) in sourcing.SEED]


def _harvest_jobs(jobs: list[dict]) -> int:
    """Harvest every job's domain CONCURRENTLY, then add the candidates (DB writes stay serial)."""
    results: dict[int, list] = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(sourcing.harvest_domain, j["domain"]): i for i, j in enumerate(jobs)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception:
                results[i] = []
    added = 0
    for i, j in enumerate(jobs):
        rows = results.get(i) or []
        if rows:
            added += _add_candidates(rows, j.get("name", ""), j["org_type"], j["country"], j["source"])
    return added


@router.post("/source/harvest")
def source_harvest(payload: dict):
    raw = payload.get("input", "") or ""
    country = payload.get("country") or "India"
    org_type = payload.get("org_type") or "university"
    domains = [x for x in re.split(r"[\s,]+", raw) if x.strip()]
    if not domains:
        raise HTTPException(400, "Paste at least one website or domain.")
    jobs = [{"domain": d, "name": "", "org_type": org_type, "country": country, "source": "harvest"}
            for d in domains[:40]]
    added = _harvest_jobs(jobs)
    return {"added": added, "scanned": len(jobs)}


@router.post("/source/seed")
def source_seed(payload: dict):
    country = payload.get("country")
    org_type = payload.get("org_type")
    limit = int(payload.get("limit") or 10)
    seeds = [s for s in sourcing.SEED
             if (not country or s[2] == country) and (not org_type or s[3] == org_type)][:limit]
    jobs = [{"domain": domain, "name": name, "org_type": t, "country": c, "source": "directory"}
            for (name, domain, c, t) in seeds]
    added = _harvest_jobs(jobs)
    return {"added": added, "scanned": len(seeds)}


@router.post("/source/search")
def source_search(payload: dict):
    q = (payload.get("query") or "").strip()
    if not q:
        raise HTTPException(400, "Enter a search query.")
    country = payload.get("country") or "India"
    org_type = payload.get("org_type") or "university"
    domains = sourcing.discover_domains(q, limit=int(payload.get("limit") or 24))
    jobs = [{"domain": d, "name": "", "org_type": org_type, "country": country, "source": "search"}
            for d in domains]
    added = _harvest_jobs(jobs)
    return {"urls": domains, "added": added}


@router.get("/candidates")
def candidates():
    conn = get_conn()
    try:
        return [_row(r) for r in conn.execute("SELECT * FROM candidates ORDER BY id DESC")]
    finally:
        conn.close()


@router.post("/candidates/accept")
def candidates_accept(payload: dict):
    ids = payload.get("ids") or []
    conn = get_conn()
    moved = 0
    try:
        for cid in ids:
            r = conn.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
            if not r:
                continue
            c = _row(r)
            conn.execute(
                "INSERT INTO leads(name,org,org_type,country,email,source,status) VALUES (?,?,?,?,?,?, 'new')",
                (c["name"], c["org"], c["org_type"], c["country"], c["email"], "sourced:" + (c["source"] or "")),
            )
            conn.execute("DELETE FROM candidates WHERE id=?", (cid,))
            moved += 1
        conn.commit()
    finally:
        conn.close()
    return {"accepted": moved}


@router.post("/candidates/reject")
def candidates_reject(payload: dict):
    ids = payload.get("ids") or []
    conn = get_conn()
    try:
        conn.executemany("DELETE FROM candidates WHERE id=?", [(i,) for i in ids])
        conn.commit()
    finally:
        conn.close()
    return {"rejected": len(ids)}


# --- replies: capture from Gmail, AI-classify, draft & send follow-ups ---
@router.post("/inbox/sync")
def inbox_sync():
    from . import inbox
    conn = get_conn()
    try:
        rows = conn.execute("SELECT id,email,org,country FROM leads WHERE email!=''").fetchall()
        lead_by_email = {r["email"].lower(): _row(r) for r in rows}
        seen = {r["message_id"] for r in conn.execute("SELECT message_id FROM replies WHERE message_id!=''")}
    finally:
        conn.close()
    if not lead_by_email:
        return {"new": 0, "scanned": 0, "note": "No leads with emails yet."}
    try:
        msgs = inbox.fetch_replies(set(lead_by_email.keys()))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Gmail sync failed: {e}")
    new = 0
    for m in msgs:
        if m["message_id"] and m["message_id"] in seen:
            continue
        lead = lead_by_email.get(m["from_email"])
        if not lead:
            continue
        cls = ai.classify_reply(m["body"], lead)
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO replies(lead_id,from_email,subject,body,category,reason,message_id,received_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (lead["id"], m["from_email"], m["subject"], m["body"], cls["category"], cls["reason"],
                 m["message_id"], m["received_at"]),
            )
            conn.execute("UPDATE leads SET status='replied', category=?, last_reply_at=? WHERE id=?",
                         (cls["category"], m["received_at"], lead["id"]))
            conn.execute("INSERT INTO events(lead_id,type,meta) VALUES (?, 'reply', ?)",
                         (lead["id"], cls["category"]))
            conn.commit()
        finally:
            conn.close()
        if m["message_id"]:
            seen.add(m["message_id"])
        new += 1
    return {"new": new, "scanned": len(msgs)}


@router.get("/replies")
def replies(category: str | None = None):
    conn = get_conn()
    try:
        q = ("SELECT r.*, l.org AS lead_org, l.email AS lead_email, l.country AS lead_country "
             "FROM replies r LEFT JOIN leads l ON l.id=r.lead_id")
        args = []
        if category:
            q += " WHERE r.category=?"
            args.append(category)
        q += " ORDER BY r.handled ASC, r.id DESC"
        return [_row(r) for r in conn.execute(q, args)]
    finally:
        conn.close()


@router.post("/replies/{rid}/followup")
def reply_followup(rid: int):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM replies WHERE id=?", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "Reply not found.")
        reply = _row(r)
        lr = conn.execute("SELECT * FROM leads WHERE id=?", (reply["lead_id"],)).fetchone()
        lead = _row(lr) if lr else {}
    finally:
        conn.close()
    try:
        d = ai.followup(reply, lead, reply.get("category") or "soso")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Follow-up draft failed: {e}")
    conn = get_conn()
    try:
        conn.execute("UPDATE replies SET followup_subject=?, followup_body=? WHERE id=?",
                     (d["subject"], d["body"], rid))
        conn.commit()
    finally:
        conn.close()
    return d


@router.post("/replies/{rid}/send")
def reply_send(rid: int, payload: dict):
    subject = (payload.get("subject") or "").strip()
    body = (payload.get("body") or "").strip()
    if not subject or not body:
        raise HTTPException(400, "Subject and body are required.")
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM replies WHERE id=?", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "Reply not found.")
        reply = _row(r)
        lr = conn.execute("SELECT * FROM leads WHERE id=?", (reply["lead_id"],)).fetchone()
        lead = _row(lr) if lr else {}
    finally:
        conn.close()
    if not lead.get("email"):
        raise HTTPException(400, "Lead has no email address.")
    try:
        mailer.send_email(lead["email"], subject, body, in_reply_to=reply.get("message_id") or None)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Send failed: {e}")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO messages(lead_id,channel,subject,body,status) VALUES (?, 'email', ?, ?, 'sent')",
            (reply["lead_id"], subject, body),
        )
        conn.execute("UPDATE replies SET handled=1, followup_subject=?, followup_body=? WHERE id=?",
                     (subject, body, rid))
        conn.execute("INSERT INTO events(lead_id,message_id,type,meta) VALUES (?,?, 'followup', ?)",
                     (reply["lead_id"], cur.lastrowid, reply.get("category") or ""))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


# --- tracking (works when the app is reachable by the recipient, e.g. via a tunnel/host) ---
_PIXEL = bytes.fromhex("47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b")


@router.get("/t/o.gif")
async def track_open(m: int | None = None, l: int | None = None):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO events(lead_id,message_id,type) VALUES (?,?, 'open')", (l, m))
        if l:
            conn.execute("UPDATE leads SET status='opened' WHERE id=? AND status IN ('contacted','queued','new')", (l,))
        conn.commit()
    finally:
        conn.close()
    return Response(content=_PIXEL, media_type="image/gif")


@router.get("/t/c")
async def track_click(u: str, m: int | None = None, l: int | None = None):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO events(lead_id,message_id,type,meta) VALUES (?,?, 'click', ?)", (l, m, u))
        if l:
            conn.execute("UPDATE leads SET status='clicked' WHERE id=? AND status IN ('contacted','opened','queued','new')", (l,))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(u)


# ===================================================== B2B SALES (ICP outreach) ==
def _lead(lead_id: int) -> dict:
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not r:
            raise HTTPException(404, "Lead not found.")
        return _row(r)
    finally:
        conn.close()


@router.get("/icp")
def icp_get():
    return {"current": sales.get_icp(),
            "options": [{"key": k, "name": v["name"], "buyer": v["buyer"]}
                        for k, v in sales.ICP_PROFILES.items()],
            "sequence": sales.SEQUENCE}


@router.post("/icp")
def icp_set(payload: dict):
    return {"current": sales.set_icp((payload or {}).get("key", ""))}


@router.post("/leads/{lead_id}/cold-email")
def lead_cold_email(lead_id: int):
    try:
        return sales.cold_email(_lead(lead_id))
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Cold email failed: {e}")


@router.post("/leads/{lead_id}/followup")
def lead_followup(lead_id: int, payload: dict | None = None):
    lead = _lead(lead_id)
    p = payload or {}
    step = int(p.get("step") or (lead.get("followup_step") or 0) + 1)
    try:
        return sales.followup(lead, step, p.get("last_subject", ""))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Follow-up failed: {e}")


@router.post("/leads/{lead_id}/call-script")
def lead_call_script(lead_id: int):
    try:
        return sales.call_script(_lead(lead_id))
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Call script failed: {e}")


@router.post("/leads/{lead_id}/log-call")
def lead_log_call(lead_id: int, payload: dict):
    outcome = (payload.get("outcome") or "").strip()
    notes = (payload.get("notes") or "").strip()
    conn = get_conn()
    try:
        conn.execute("INSERT INTO calls(lead_id,outcome,notes) VALUES (?,?,?)", (lead_id, outcome, notes))
        conn.execute("INSERT INTO events(lead_id,type,meta) VALUES (?, 'call', ?)", (lead_id, outcome))
        if outcome in ("booked", "demo", "meeting"):
            conn.execute("UPDATE leads SET status='meeting', stage='meeting' WHERE id=?", (lead_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/leads/{lead_id}/advance")
def lead_advance(lead_id: int, payload: dict | None = None):
    """Record that a follow-up step was sent: bump the step + timestamps."""
    conn = get_conn()
    try:
        conn.execute("UPDATE leads SET followup_step=followup_step+1, last_touch_at=datetime('now') WHERE id=?",
                     (lead_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.get("/sales/strategy")
def sales_strategy():
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
        by_stage = {r["status"]: r["c"] for r in conn.execute("SELECT status, COUNT(*) c FROM leads GROUP BY status")}
        by_cat = {r["category"]: r["c"] for r in conn.execute(
            "SELECT category, COUNT(*) c FROM leads WHERE category!='' GROUP BY category")}
        sent = conn.execute("SELECT COUNT(*) c FROM messages WHERE status='sent'").fetchone()["c"]
        replies = conn.execute("SELECT COUNT(*) c FROM replies").fetchone()["c"]
        calls = conn.execute("SELECT COUNT(*) c FROM calls").fetchone()["c"]
    finally:
        conn.close()
    stats = {"total_leads": total, "by_stage": by_stage, "reply_categories": by_cat,
             "emails_sent": sent, "replies": replies, "calls_logged": calls}
    try:
        return {"stats": stats, "review": sales.strategy_review(stats)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Strategy review failed: {e}")
