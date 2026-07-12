"""AI personalization: write a concise, specific outreach email for a lead."""
from __future__ import annotations

import json

from openai import OpenAI

from .config import get_settings

SYSTEM = """You are a senior B2B outreach copywriter for Praxia AI Studios. You write SHORT,
warm, specific cold emails that get replies from universities, colleges, L&D teams and
corporates. No hype, no buzzwords, no "I hope this finds you well". Lead with the outcome.
Sound human and considered. 90-140 words max. One clear call to action at the end.
Never use em dashes (—); use commas or periods instead. Refer to the product as
"Praxia AI Course Factory" (the company is Praxia AI Studios). Do not mention any underlying
technology or vendors; describe only the outcome and value."""

PRODUCT = (
    "Praxia AI Course Factory builds complete, published courses from a single title: full "
    "curriculum, professional teaching slides, a narrated HD video, interactive in-lesson "
    "questions, and assessments (pre-test, quizzes, final exam), then publishes the whole course "
    "straight into the client's LMS in one click. It is compliance-ready (aligned to academic or "
    "corporate standards). A course that normally costs a lot and takes weeks now takes one "
    "person an afternoon, at a small fraction of the cost."
)


def build_cta(s) -> str:
    parts = []
    if s.booking_link:
        parts.append(f"book a quick demo call: {s.booking_link}")
    parts.append(f"reply to this email or write to {s.public_email}")
    if s.whatsapp:
        parts.append(f"WhatsApp {s.whatsapp}")
    return " — or ".join(parts)


def personalize(lead: dict, template: dict | None) -> dict:
    s = get_settings()
    if not s.openai_ready:
        raise RuntimeError("OpenAI is not configured (set OPENAI_API_KEY in backend/.env).")
    client = OpenAI(api_key=s.openai_api_key)

    region = (lead.get("country") or "India").strip()
    price_hint = (
        "If pricing comes up, frame value in Indian Rupees." if region == "India"
        else "If pricing comes up, frame value in US Dollars."
    )
    angle = (template or {}).get("body", "") or "Outcome-led introduction."
    cta = build_cta(s)

    user = f"""Write a cold outreach email.

RECIPIENT:
- Name: {lead.get('name') or '(unknown — use a warm generic greeting)'}
- Title: {lead.get('title') or ''}
- Organization: {lead.get('org') or ''}
- Type: {lead.get('org_type') or ''}
- Region: {region}

PRODUCT (do not list everything — pick what's most relevant to THIS recipient):
{PRODUCT}

ANGLE / TEMPLATE NOTES: {angle}
{price_hint}

RULES:
- Personalize to their organization and role; reference what a {lead.get('org_type') or 'team'} would care about.
- 90-140 words. Plain, human, specific. No markdown, no bullet dumps.
- End with a clear call to action that EXPLICITLY includes these contact options, verbatim
  (do not paraphrase or omit them): {cta}.
- Sign off as "{s.from_name}".

Return JSON: {{"subject": "...", "body": "..."}}"""

    resp = client.chat.completions.create(
        model=s.openai_model,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    return {"subject": (data.get("subject") or "").strip(), "body": (data.get("body") or "").strip()}


CLASSIFY_SYSTEM = """You classify replies to a B2B sales outreach email into exactly one category:
- "warm": interested / positive / wants a demo or call / asks to proceed / enthusiastic.
- "soso": unsure, 50-50, "maybe later", asking about price/details, mild hesitation, needs convincing.
- "cold": not interested / declines / "no thanks" / unsubscribe / wrong person / hostile.
Return JSON: {"category": "warm|soso|cold", "reason": "one short phrase"}."""


def classify_reply(reply_text: str, lead: dict) -> dict:
    s = get_settings()
    if not s.openai_ready:
        return {"category": "soso", "reason": "AI not configured"}
    client = OpenAI(api_key=s.openai_api_key)
    user = f"Lead org: {lead.get('org') or ''}. Their reply:\n\"\"\"\n{reply_text[:1500]}\n\"\"\"\nClassify it."
    try:
        resp = client.chat.completions.create(
            model=s.openai_model,
            messages=[{"role": "system", "content": CLASSIFY_SYSTEM}, {"role": "user", "content": user}],
            response_format={"type": "json_object"}, temperature=0,
        )
        d = json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        return {"category": "soso", "reason": "classification failed"}
    cat = (d.get("category") or "soso").lower().strip()
    if cat not in ("warm", "soso", "cold"):
        cat = "soso"
    return {"category": cat, "reason": (d.get("reason") or "").strip()}


FOLLOWUP_GUIDE = {
    "warm": ("They're interested. Be warm and move fast. Thank them, then PROPOSE A DEMO — offer "
             "2-3 concrete time options this/next week and share the booking + contact options. Keep momentum."),
    "soso": ("They're unsure / on the fence. Acknowledge their specific point, reinforce 1-2 concrete "
             "outcomes, remove risk (offer a short 15-minute no-obligation demo), and gently nudge for a yes."),
    "cold": ("They declined or aren't interested. Be gracious, brief, no pressure. Thank them, leave the "
             "door open, and offer a useful resource (the demo video / brochure) they can revisit later."),
}


def followup(reply: dict, lead: dict, category: str) -> dict:
    s = get_settings()
    if not s.openai_ready:
        raise RuntimeError("OpenAI is not configured.")
    client = OpenAI(api_key=s.openai_api_key)
    region = (lead.get("country") or "India").strip()
    cta = build_cta(s)
    guide = FOLLOWUP_GUIDE.get(category, FOLLOWUP_GUIDE["soso"])
    their_subject = reply.get("subject") or "our conversation"

    user = f"""Write a follow-up REPLY email to this prospect.

THEIR REPLY:
\"\"\"
{(reply.get('body') or '')[:1500]}
\"\"\"

CONTEXT:
- Organization: {lead.get('org') or ''}  |  Region: {region}
- Classified as: {category.upper()}. {guide}

PRODUCT (use only what's relevant): {PRODUCT}
CTA / contact options to weave in where appropriate: {cta}
{"Frame value in INR." if region == "India" else "Frame value in USD."}

RULES:
- 70-130 words, warm, human, specific to what they wrote. No markdown.
- Subject must be a reply subject: "Re: {their_subject}".
- Sign off as "{s.from_name}".

Return JSON: {{"subject": "...", "body": "..."}}"""
    resp = client.chat.completions.create(
        model=s.openai_model,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        response_format={"type": "json_object"}, temperature=0.6,
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    subj = (data.get("subject") or f"Re: {their_subject}").strip()
    return {"subject": subj, "body": (data.get("body") or "").strip()}
