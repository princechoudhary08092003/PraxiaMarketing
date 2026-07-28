"""B2B outreach engine for a chosen ICP (Ideal Customer Profile).

Implements the process: cold email first (one problem, one result, one CTA) -> a multi-step
follow-up sequence -> call scripts -> AI strategy review. Messaging is tuned to the ICP set in the
`settings` table. Uses the same OpenAI client as the Growth Studio.
"""
from __future__ import annotations

import json

from .config import get_settings
from .db import get_conn
from .growth import _client

# --- ICP profiles: the whole engine focuses on ONE at a time (set in settings.icp) ---
ICP_PROFILES = {
    "us_corporate_ld": {
        "name": "US Corporate L&D (500+ employees)",
        "buyer": "Director of L&D, VP Learning, Chief Learning Officer, Head of Enablement, Training Manager",
        "pain": ("their team spends weeks and heavy budget building and updating employee training, "
                 "slides, videos, quizzes and LMS packages, and can never keep up with demand"),
        "result": ("course creation drops from weeks to under an hour: slides, narrated video, quizzes, "
                   "assessments and an LMS-ready package generated automatically, plus a custom LMS they own"),
        "currency": "USD",
        "product": "course_factory",
    },
    "msp_us": {
        "name": "US MSPs",
        "buyer": "Owner, President, VP Operations, Director of Service Delivery",
        "pain": ("they must deliver security and compliance training to clients and onboard staff, "
                 "and they drown in manual, repeatable ops work"),
        "result": ("ready-to-sell training built in an afternoon plus custom automations that cut manual "
                   "ops hours, a new margin line they can resell to their own clients"),
        "currency": "USD",
        "product": "automation_consultancy",
    },
    "cert_bodies": {
        "name": "Professional certification providers",
        "buyer": "Director of Education, Head of Content, VP Programs",
        "pain": "they must constantly produce and re-version large volumes of course content on a deadline",
        "result": "whole course catalogs generated and kept current in a fraction of the time and cost",
        "currency": "USD",
        "product": "course_factory",
    },
    "healthcare_compliance": {
        "name": "Healthcare and compliance training",
        "buyer": "Director of L&D, Compliance Lead, Director of Clinical Education",
        "pain": "mandatory recurring compliance training is high-volume, deadline-driven and expensive to keep current",
        "result": "compliance courses built and updated automatically, LMS-ready, at a fraction of the cost",
        "currency": "USD",
        "product": "course_factory",
    },
}
DEFAULT_ICP = "us_corporate_ld"

# 4-step cadence (days are guidance shown to the user; sending stays manual/approved)
SEQUENCE = [
    {"step": 0, "day": 0, "kind": "cold", "goal": "First cold email: one problem, one result, one CTA (a 20-min demo)."},
    {"step": 1, "day": 3, "kind": "bump", "goal": "Short bump on the same thread: no guilt, add one concrete proof point, re-offer the demo."},
    {"step": 2, "day": 7, "kind": "value", "goal": "Deliver value: a specific before/after or a free sample offer, lower the ask to 15 minutes."},
    {"step": 3, "day": 12, "kind": "breakup", "goal": "Polite breakup: last email, leave the door open, ask for the right person if not them."},
]


def get_icp() -> dict:
    conn = get_conn()
    try:
        r = conn.execute("SELECT value FROM settings WHERE key='icp'").fetchone()
        key = r["value"] if r and r["value"] in ICP_PROFILES else DEFAULT_ICP
    finally:
        conn.close()
    return {"key": key, **ICP_PROFILES[key]}


def set_icp(key: str) -> dict:
    key = key if key in ICP_PROFILES else DEFAULT_ICP
    conn = get_conn()
    try:
        conn.execute("INSERT INTO settings(key,value) VALUES ('icp',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=?", (key, key))
        conn.commit()
    finally:
        conn.close()
    return get_icp()


def _chat(system: str, user: str, temperature: float = 0.6) -> dict:
    s = get_settings()
    resp = _client().chat.completions.create(
        model=s.growth_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"}, temperature=temperature)
    return json.loads(resp.choices[0].message.content or "{}")


SYSTEM = """You are a top B2B SDR writing to enterprise buyers. You write SHORT, human, specific cold
outreach. Rules: one problem, one result, one clear call to action. 60-110 words for the first email,
shorter for follow-ups. No hype, no buzzwords, no "I hope this finds you well". Never use em dashes.
Frame any money in the ICP's currency. Sound like a sharp person, not a template. Never state your
own price. If value must be anchored, cite what the market charges, then "a fraction of that"."""


def _lead_ctx(lead: dict) -> str:
    return (f"Name: {lead.get('decision_maker') or lead.get('name') or '(unknown)'}\n"
            f"Title: {lead.get('title') or ''}\nCompany: {lead.get('org') or ''}\n"
            f"Company size: {lead.get('company_size') or ''}\nCountry: {lead.get('country') or ''}")


def cold_email(lead: dict) -> dict:
    icp = get_icp(); s = get_settings()
    user = f"""Write the FIRST cold email to this {icp['name']} buyer.

LEAD:
{_lead_ctx(lead)}

THEIR PAIN: {icp['pain']}
OUR RESULT: {icp['result']}
CURRENCY: {icp['currency']}
CTA: ask for a 20-minute demo next week. Also offer a free sample built on a topic of their choice.
Sign as {s.sender_name}, Praxia AI Studios. Contact: {s.public_email}.

Return JSON: {{"subject":"short, specific, no clickbait","body":"the email, plain text, no markdown"}}"""
    d = _chat(SYSTEM, user, 0.7)
    return {"subject": (d.get("subject") or "").strip(), "body": (d.get("body") or "").strip()}


def followup(lead: dict, step: int, last_subject: str = "") -> dict:
    icp = get_icp(); s = get_settings()
    st = SEQUENCE[min(max(step, 1), len(SEQUENCE) - 1)]
    user = f"""Write follow-up step {st['step']} ({st['kind']}) to this {icp['name']} buyer.

LEAD:
{_lead_ctx(lead)}

GOAL OF THIS STEP: {st['goal']}
THEIR PAIN: {icp['pain']}
OUR RESULT: {icp['result']}
CURRENCY: {icp['currency']}
This is a reply on the existing thread. Keep it very short. Sign as {s.sender_name}.

Return JSON: {{"subject":"Re: {last_subject or 'quick idea'}","body":"the short follow-up, plain text"}}"""
    d = _chat(SYSTEM, user, 0.7)
    return {"subject": (d.get("subject") or f"Re: {last_subject}").strip(),
            "body": (d.get("body") or "").strip(), "step": st["step"], "kind": st["kind"]}


CALL_SYSTEM = """You are a B2B calling coach. You write tight, natural phone scripts for booking a
demo (not selling on the call). Conversational, confident, short lines. No em dashes."""


def call_script(lead: dict) -> dict:
    icp = get_icp(); s = get_settings()
    user = f"""Write a cold-call script for reaching this {icp['name']} buyer. Objective: book a 20-min demo.
The caller is {s.sender_name} from Praxia AI Studios. Use those real names, never bracket placeholders
like [Your Name] or [Your Company].

LEAD:
{_lead_ctx(lead)}
THEIR PAIN: {icp['pain']}
OUR RESULT: {icp['result']}

Return JSON:
{{
 "opener":"the first 2 lines after they pick up",
 "pitch":"2-3 sentence why-this-matters if they say yes",
 "objections":[{{"objection":"common pushback","response":"a short reply"}} , 3 items],
 "gatekeeper":"one line to get past a gatekeeper / find the right person",
 "voicemail":"a 15-second voicemail if they do not pick up"
}}"""
    return _chat(CALL_SYSTEM, user, 0.6)


STRATEGY_SYSTEM = """You are a head of sales reviewing an outbound campaign. Be blunt and specific.
Diagnose what is working and what to change in targeting, messaging and cadence. No fluff."""


def strategy_review(stats: dict) -> dict:
    icp = get_icp()
    user = f"""Review this outbound campaign for the ICP: {icp['name']}.

DATA (JSON): {json.dumps(stats)[:3000]}

Return JSON:
{{
 "diagnosis":"2-4 sentences, honest",
 "fix_targeting":"one concrete change to who we target",
 "fix_message":"one concrete change to the cold email",
 "fix_cadence":"one concrete change to follow-up timing/volume",
 "next_experiment":"one A/B test to run this week"
}}"""
    return _chat(STRATEGY_SYSTEM, user, 0.5)
