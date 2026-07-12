"""Send email from the configured Gmail via SMTP + App Password."""
from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid

from .config import get_settings


def send_email(to: str, subject: str, body: str, in_reply_to: str | None = None) -> bool:
    s = get_settings()
    if not s.smtp_ready:
        raise RuntimeError(
            "Email is not configured. Set SMTP_USER and SMTP_APP_PASSWORD in backend/.env "
            "(create a Gmail App Password: Google Account → Security → 2-Step Verification → App passwords)."
        )
    if not to:
        raise RuntimeError("Lead has no email address.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{s.from_name} <{s.smtp_user}>"
    msg["To"] = to
    msg["Message-ID"] = make_msgid()
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.attach(MIMEText(body, "plain", "utf-8"))
    html = (
        "<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;"
        "color:#1a1a1a;white-space:pre-wrap\">" + body.replace("\n", "<br>") + "</div>"
    )
    msg.attach(MIMEText(html, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as srv:
        srv.login(s.smtp_user, s.smtp_app_password)
        srv.sendmail(s.smtp_user, [to], msg.as_string())
    return True
