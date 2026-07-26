"""Send email from the configured Gmail via SMTP + App Password."""
from __future__ import annotations

import os
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid

from .config import get_settings


def send_email(to: str, subject: str, body: str, in_reply_to: str | None = None,
               attachments: list[str] | None = None) -> bool:
    s = get_settings()
    if not s.smtp_ready:
        raise RuntimeError(
            "Email is not configured. Set SMTP_USER and SMTP_APP_PASSWORD in backend/.env "
            "(create a Gmail App Password: Google Account → Security → 2-Step Verification → App passwords)."
        )
    if not to:
        raise RuntimeError("Lead has no email address.")

    root = MIMEMultipart("mixed")
    root["Subject"] = subject
    root["From"] = f"{s.from_name} <{s.smtp_user}>"
    root["To"] = to
    root["Message-ID"] = make_msgid()
    if in_reply_to:
        root["In-Reply-To"] = in_reply_to
        root["References"] = in_reply_to

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body, "plain", "utf-8"))
    html = (
        "<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;"
        "color:#1a1a1a;white-space:pre-wrap\">" + body.replace("\n", "<br>") + "</div>"
    )
    alt.attach(MIMEText(html, "html", "utf-8"))
    root.attach(alt)

    for path in (attachments or []):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue  # skip a missing attachment rather than failing the whole send
        part = MIMEBase("application", "octet-stream")
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
        root.attach(part)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as srv:
        srv.login(s.smtp_user, s.smtp_app_password)
        srv.sendmail(s.smtp_user, [to], root.as_string())
    return True
