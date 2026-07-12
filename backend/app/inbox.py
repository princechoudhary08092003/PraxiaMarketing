"""Read replies from Gmail via IMAP (same account + App Password used for sending).
Matches incoming mail to known lead emails so we only capture actual replies."""
from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parseaddr

from .config import get_settings


def _decode(s: str | None) -> str:
    if not s:
        return ""
    out = ""
    for txt, enc in decode_header(s):
        out += txt.decode(enc or "utf-8", "ignore") if isinstance(txt, bytes) else txt
    return out


def _plain_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            disp = str(part.get("Content-Disposition") or "")
            if part.get_content_type() == "text/plain" and "attachment" not in disp:
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
                except Exception:
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "ignore")
    except Exception:
        return msg.get_payload() or ""


def _strip_quotes(text: str) -> str:
    """Keep just the person's new message, dropping quoted history/signatures below."""
    lines = []
    for ln in text.splitlines():
        st = ln.strip()
        if st.startswith(">"):
            break
        if re.match(r"^On .+wrote:$", st):
            break
        if st.startswith("From:") and lines:
            break
        if st in ("--", "—") and lines:
            break
        lines.append(ln)
    return "\n".join(lines).strip()[:2000]


def fetch_replies(known_emails: set[str], days: int = 21, limit: int = 150) -> list[dict]:
    s = get_settings()
    if not s.smtp_ready:
        raise RuntimeError("Gmail is not configured (SMTP_USER + SMTP_APP_PASSWORD).")
    known = {e.lower() for e in known_emails if e}
    if not known:
        return []
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        M.login(s.smtp_user, s.smtp_app_password)
        M.select("INBOX")
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = M.search(None, f"(SINCE {since})")
        ids = data[0].split()[-limit:] if data and data[0] else []
        out = []
        for i in reversed(ids):
            typ, md = M.fetch(i, "(RFC822)")
            if not md or not md[0]:
                continue
            msg = email.message_from_bytes(md[0][1])
            frm = parseaddr(msg.get("From", ""))[1].lower()
            if frm not in known:
                continue
            out.append({
                "from_email": frm,
                "subject": _decode(msg.get("Subject", "")),
                "body": _strip_quotes(_plain_body(msg)),
                "message_id": msg.get("Message-ID", ""),
                "received_at": msg.get("Date", ""),
            })
        return out
    finally:
        try:
            M.logout()
        except Exception:
            pass
