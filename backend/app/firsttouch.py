"""The fixed first-touch email sent to every new lead (personalized with first name).
No em dashes. Product = 'Praxia AI Course Factory' (brand = Praxia AI Studios)."""
from __future__ import annotations

from .config import get_settings

SUBJECT = "A quick look at Praxia AI Course Factory, following our call"

BODY = """Hi {first_name},

Thank you for taking my call earlier. As promised, here is a quick look at Praxia AI Course Factory, the platform I have built at Praxia AI Studios.

It turns a single course title into a complete, ready-to-publish course. Full curriculum, professionally designed slides, narrated video lessons, hands-on labs, interactive knowledge checks, and auto-graded assessments, published straight into your LMS. One person can do it in a single afternoon, with no production team and no manual uploading.

A course that normally costs ₹50,000 to ₹5,00,000 and takes weeks to produce, Praxia delivers at a small fraction of the cost, with your academic or compliance standards built in from the start.

I would rather show you than tell you, so here is a short demo of the real output:
Watch the demo: {youtube}

I have also attached a one-page overview.

Because I would want you to be completely sure before committing to anything, I am happy to build a short sample course on a topic of your choice, free and with no obligation, so you can judge the quality yourself first. A quick 20-minute walkthrough works too. Just reply to this email, or reach me directly at {email} or on WhatsApp at {whatsapp}.

If you would prefer not to hear from me, reply "no" and I will not follow up.

Best regards,
{sender}
Praxia AI Studios
{email} · {whatsapp}"""


_TITLES = {"dr", "prof", "mr", "ms", "mrs", "mx", "sir", "madam", "the"}


def _first_name(name: str) -> str:
    parts = [p for p in name.split() if p]
    while parts and parts[0].lower().strip(".") in _TITLES:
        parts.pop(0)
    return parts[0] if parts else "there"


def build_first_touch(lead: dict) -> dict:
    s = get_settings()
    name = (lead.get("name") or "").strip()
    first = _first_name(name)
    youtube = s.youtube_demo or "[your YouTube link]"
    body = BODY.format(
        first_name=first, youtube=youtube, email=s.public_email,
        whatsapp=s.whatsapp, sender=s.sender_name,
    )
    return {"subject": SUBJECT, "body": body}
