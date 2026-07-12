"""The fixed first-touch email sent to every new lead (personalized with first name).
No em dashes. Product = 'Praxia AI Course Factory' (brand = Praxia AI Studios)."""
from __future__ import annotations

from .config import get_settings

SUBJECT = "A quick look at Praxia AI Course Factory, following our call"

BODY = """Hi {first_name},

Thank you for taking my call earlier. As promised, here is a quick look at Praxia AI Course Factory.

Praxia AI Course Factory turns a single course title into a complete, ready-to-publish course. It builds the full curriculum, professionally designed slides, narrated video lessons, interactive knowledge checks, and auto-graded assessments, then publishes the whole course straight into your LMS. One person can do it in a single afternoon, with no production team and no manual uploading.

A course that normally costs ₹50,000 to ₹5,00,000 and takes weeks to produce, Praxia AI Course Factory delivers at a small fraction of the cost, with your academic or compliance standards built in from the start.

Here is a short demo so you can see it in action:
Watch the demo: {youtube}

I have also attached a one-page overview. If it looks useful, I would be glad to give you a quick 20-minute walkthrough. Just reply to this email, or reach me at {email} or on WhatsApp at {whatsapp}.

If you would prefer not to hear from me, reply "no" and I will not follow up.

Best regards,
{sender}
Praxia AI Studios"""


def build_first_touch(lead: dict) -> dict:
    s = get_settings()
    name = (lead.get("name") or "").strip()
    first = name.split()[0] if name else "there"
    youtube = s.youtube_demo or "[your YouTube link]"
    body = BODY.format(
        first_name=first, youtube=youtube, email=s.public_email,
        whatsapp=s.whatsapp, sender=s.sender_name,
    )
    return {"subject": SUBJECT, "body": body}
