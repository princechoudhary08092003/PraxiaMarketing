"""Growth Studio — a team of AI marketing agents that build Praxia's social presence.

Roles (each is a focused prompt / function):
  1. Strategist      -> a multi-day campaign plan across the 3 products (themes + cadence)
  2. Content Creator -> a full post: hook, caption, script/storyboard, image brief
  3. SEO Specialist  -> hashtags, keywords, title, best posting time
  4. Social Manager  -> platform-specific variants + scheduling (handled in routes)
  5. Growth Analyst  -> reads reach metrics, scores, recommends (change / boost / double down)

House rules enforced in every prompt:
  - Never state Praxia's selling price. Reference the MARKET price rivals charge, then our
    "fraction of the time and cost" + hard impact numbers.
  - No em dashes. Use commas or periods.
  - Sound human and specific, never generic or AI-ish. Hooks must earn the scroll-stop.
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

from openai import OpenAI

from .config import get_settings

ASSETS_DIR = Path(__file__).resolve().parent / "static" / "assets" / "posts"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- products ----
PRODUCTS = {
    "course_factory": {
        "name": "Praxia AI Course Factory",
        "tagline": "Your whole training catalog, built and owned by you.",
        "what": (
            "A product (not courses for sale): it builds full courses from a single title, turns live "
            "session recordings and transcripts into polished videos, and turns Scribe docs into "
            "narrated videos. Comes with a fully custom LMS you own for life, one-time setup, at a "
            "small fraction of the usual cost."
        ),
        "options": [
            "Full course from a single title.",
            "Videos from your live sessions and transcripts.",
            "Courses from a Scribe doc.",
            "A custom LMS you own for life, one-time setup.",
        ],
        "market_price": "Agencies charge $500 to $6,000 per course, and LMS platforms bill thousands per year forever.",
        "impact": "Weeks to an afternoon, and you own the platform instead of renting it.",
        "audience": "L&D teams, training companies, universities, MSPs, edtech.",
    },
    "automation_consultancy": {
        "name": "Praxia AI Automation",
        "tagline": "Find your worst bottleneck. We automate it end to end.",
        "what": (
            "End-to-end automation consultancy. We start with a FREE assessment call where we diagnose "
            "the real bottlenecks in your SOPs and processes, then build the full automated system for "
            "you: whatever the workflow needs, wired into your tools."
        ),
        "options": [
            "Free assessment call to find the bottleneck.",
            "End-to-end custom automation, built and delivered.",
            "Measured before and after: hours and cost cut.",
        ],
        "market_price": "Automation consultancies bill $5,000 to $50,000 per engagement over months.",
        "impact": "Manual hours cut sharply, errors down, payback in weeks. Starts with a free call.",
        "audience": "Ops leads, founders, MSP owners, finance, HR and support teams.",
    },
    "automation_training": {
        "name": "Praxia Automation Training",
        "tagline": "Teach your team to automate the boring work.",
        "what": (
            "Hands-on training that teaches teams to automate real work: L&D processes, finance and "
            "Excel, invoice generation, billing, reporting and more. Practical, build-along, immediately usable."
        ),
        "options": [
            "Automate L&D processes.",
            "Automate finance, Excel, invoicing and billing.",
            "Team upskilling that produces working automations, not notes.",
        ],
        "market_price": "Corporate automation training runs $2,000 to $20,000 per cohort.",
        "impact": "Teams walk out having automated a real task, not just watched slides.",
        "audience": "Ops, finance, HR and L&D teams; agencies; founders.",
    },
}

# Big rotating pool of automation problems for the daily build-in-public reel. Each becomes a
# convincing mockup + a meme hook. The variety engine avoids repeating recent ones.
AUTOMATION_TOPICS = [
    {"key": "invoice", "title": "Invoice Automation", "pain": "typing invoices by hand from emails"},
    {"key": "payroll", "title": "Payroll Runs", "pain": "running payroll in spreadsheets every month"},
    {"key": "hr_onboarding", "title": "HR Onboarding", "pain": "chasing paperwork for every new hire"},
    {"key": "billing", "title": "Billing & Dunning", "pain": "sending payment reminders one by one"},
    {"key": "finance_excel", "title": "Finance Reporting", "pain": "rebuilding the same Excel report weekly"},
    {"key": "expense", "title": "Expense Approvals", "pain": "approving expense claims from a messy inbox"},
    {"key": "attendance", "title": "Attendance & Rosters", "pain": "reconciling attendance sheets by hand"},
    {"key": "data_entry", "title": "Data Entry", "pain": "copy pasting between systems all day"},
    {"key": "captioning", "title": "Auto Captioning", "pain": "captioning and tagging video by hand"},
    {"key": "email_triage", "title": "Email Triage", "pain": "sorting and routing hundreds of emails"},
    {"key": "reporting", "title": "Weekly Reporting", "pain": "stitching dashboards together every Monday"},
    {"key": "lead_routing", "title": "Lead Routing", "pain": "assigning leads manually from a form"},
    {"key": "support_tickets", "title": "Support Triage", "pain": "tagging and routing support tickets"},
    {"key": "contract_review", "title": "Contract Intake", "pain": "reading every contract for key dates"},
    {"key": "inventory", "title": "Inventory Reorder", "pain": "checking stock and reordering by hand"},
    {"key": "compliance", "title": "Compliance Checks", "pain": "chasing compliance sign-offs on a checklist"},
]

VISUAL_STYLES = ["cinematic", "stock", "bold_type", "duotone"]   # rotated for variety
TRANSITIONS = ["fadeblack", "slideleft", "zoompunch", "whippan"]  # rotated for variety

POSITIONING = """POSITIONING RULES (follow strictly):
- NEVER state our own selling price or any discount. If value must be anchored, cite the MARKET price
  that competitors charge, then contrast with "a fraction of the time and cost".
- Lead with a concrete impact number or a sharp before/after (weeks to hours, cost cut, hours saved).
- Sound like a sharp human operator, not a brand bot. No hype words (revolutionary, game-changer,
  unlock, unleash, supercharge, elevate). No "in today's fast-paced world".
- Never use em dashes. Use commas or periods.
- One idea per post. Earn the scroll-stop in the first line."""

_client_cache: OpenAI | None = None


def _client() -> OpenAI:
    global _client_cache
    s = get_settings()
    if not s.openai_ready:
        raise RuntimeError("OpenAI is not configured (set OPENAI_API_KEY in backend/.env).")
    if _client_cache is None:
        _client_cache = OpenAI(api_key=s.openai_api_key)
    return _client_cache


def _chat_json(system: str, user: str, temperature: float = 0.8) -> dict:
    s = get_settings()
    resp = _client().chat.completions.create(
        model=s.growth_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    return json.loads(resp.choices[0].message.content or "{}")


def product_line(key: str) -> str:
    p = PRODUCTS.get(key)
    if not p:
        return ""
    return (f"{p['name']} — {p['tagline']} {p['what']} Options: {' '.join(p['options'])} "
            f"Market price context: {p['market_price']} Impact: {p['impact']} Audience: {p['audience']}")


def all_products_brief() -> str:
    return "\n".join(f"[{k}] {product_line(k)}" for k in PRODUCTS)


# =============================================================== 1. STRATEGIST ==
STRATEGIST_SYSTEM = f"""You are the Head of Growth for Praxia AI Studios, a sharp performance
marketer who has grown brands from zero on Instagram and YouTube. You design content strategies
that create fast reach and turn attention into demo calls and sales.

{POSITIONING}

You output a concrete daily plan, not vague advice. Each day has content slots, each slot names a
product, a platform, a format, a hook angle, and a content pillar. Rotate the three products so all
get airtime. Mix pillars: proof/impact, before-after, myth-bust, quick tip, behind the scenes,
client outcome, bold claim with a number, fast demo. Weight formats toward Reels and Shorts (highest
reach) with some carousels for saves."""


def strategist_plan(goal: str, products: list[str], days: int, per_day: int) -> dict:
    prods = products or list(PRODUCTS.keys())
    prod_brief = "\n".join(f"[{k}] {product_line(k)}" for k in prods if k in PRODUCTS)
    user = f"""Design a {days}-day social content plan, {per_day} posts per day.

GOAL: {goal or 'Maximum reach and follower growth across Instagram and YouTube, converting to demo calls.'}

PRODUCTS TO PROMOTE (rotate across the plan):
{prod_brief}

For EACH slot return: day (1..{days}), slot (1..{per_day}), platform (instagram | youtube),
format (reel | short | carousel | image | long_video), product (one of {prods}),
pillar (short label), hook_angle (one specific line describing the scroll-stopping angle),
best_time (e.g. "8:30 PM IST").

Also return a short "themes" array: one content pillar theme per day (a phrase).
Return JSON: {{"themes": ["..."], "slots": [{{"day":1,"slot":1,"platform":"instagram","format":"reel","product":"course_factory","pillar":"impact proof","hook_angle":"...","best_time":"..."}}]}}"""
    data = _chat_json(STRATEGIST_SYSTEM, user, temperature=0.85)
    return data


# ============================================================ 2. CONTENT CREATOR ==
CREATOR_SYSTEM = f"""You are a viral short-form content creator and copywriter for Praxia AI Studios.
You write Instagram Reels, YouTube Shorts, carousels and captions that stop the scroll and get shares
and saves. You know hooks are everything: the first line must create curiosity, tension, or a bold
promise with a number.

{POSITIONING}

You also write a tight shot-by-shot script (for video) or slide-by-slide text (for carousels), and a
vivid IMAGE BRIEF for a designer: a single striking visual concept, on-brand for a premium dark,
gold-accented tech studio (obsidian background, warm gold #C9A24B accent, cinematic, no cheesy stock,
no literal robots). The image must contain little or no text (text is added later)."""


def create_post(platform: str, fmt: str, product: str, pillar: str, hook_angle: str) -> dict:
    p = PRODUCTS.get(product, {})
    fmt_guide = {
        "reel": "Instagram Reel, 20-40s. 5-7 fast shots. Punchy on-screen captions.",
        "short": "YouTube Short, vertical, under 60s. Hook in 2s, one payoff.",
        "carousel": "Instagram carousel, 6-8 slides. Slide 1 is the hook, last slide is the CTA.",
        "image": "Single Instagram feed image with a strong one-line hook.",
        "long_video": "YouTube video, 3-6 min. Title, hook, 4-6 beat outline, CTA.",
    }.get(fmt, "Short social video.")
    user = f"""Write ONE {platform} {fmt} for this product.

PRODUCT: {p.get('name','')} — {p.get('what','')}
OPTIONS: {' '.join(p.get('options', []))}
MARKET PRICE CONTEXT (use to anchor value, never our price): {p.get('market_price','')}
IMPACT ANGLE: {p.get('impact','')}
CONTENT PILLAR: {pillar}
HOOK ANGLE TO EXECUTE: {hook_angle}
FORMAT: {fmt_guide}

Return JSON:
{{
  "title": "for YouTube: a click-worthy title <= 70 chars; for IG: a 3-5 word internal label",
  "hook": "the first line / first 2 seconds, must stop the scroll",
  "script": "shot-by-shot (video) or slide-by-slide (carousel) with on-screen text; use \\n between beats",
  "caption": "the post caption, 2-5 short lines, human, one CTA at the end (visit {get_settings().website} or DM). No hashtags here.",
  "image_prompt": "one vivid visual concept for the designer, on-brand dark+gold cinematic, minimal/no text"
}}"""
    return _chat_json(CREATOR_SYSTEM, user, temperature=0.9)


# ============================================================ 2b. REEL SCRIPT ==
REEL_SYSTEM = f"""You are a senior short-form performance marketer and video director for Praxia
AI Studios. You script vertical Reels/Shorts (22 to 38 seconds) engineered to stop the scroll, hold
attention, and drive profile taps + demo requests. Narration is spoken by an AI voice: write it to be
SPOKEN, short, punchy, natural, no lists, no symbols, no reading of URLs mid-script.

{POSITIONING}

PROVEN STRUCTURE (follow it):
1. HOOK (beat 1): a pattern interrupt in the first 2 seconds. A bold number, a sharp question, or a
   painful truth for the target buyer. Not a greeting, not the brand name.
2. PROBLEM (beat 2): the expensive, slow, painful status quo (name the market cost/time).
3. PRODUCT (beats 3 to 5): show the ACTUAL Praxia product and what it literally does, concretely.
   These beats MUST use visual_type "product" (real screenshots of the tool/site are shown here).
4. PROOF/IMPACT (beat before last): the before/after or the hard result.
5. CTA (LAST beat): tell them to book a demo / DM / visit the site. Keep it short and confident.

VISUALS per beat:
- "product": show the real Praxia app/website (use for the PRODUCT beats). visual_query = a short
  label of what is on screen.
- "ai": a cinematic dark+gold brand shot (give a vivid prompt). Good for HOOK/PROBLEM/emotion.
- "stock": a real photo (give a plain 2-4 word search query). Good for human/context shots.
on_screen = a punchy 2 to 5 word caption for that beat (used as the beat label, not the subtitles)."""


def reel_script(product: str, pillar: str, hook_angle: str) -> dict:
    p = PRODUCTS.get(product, {})
    s = get_settings()
    user = f"""Write ONE vertical Reel/Short that markets this Praxia product and gets leads.

PRODUCT: {p.get('name','')} — {p.get('what','')}
WHAT IT LITERALLY DOES (options): {' '.join(p.get('options', []))}
MARKET PRICE CONTEXT (anchor value, never OUR price): {p.get('market_price','')}
IMPACT / BEFORE-AFTER: {p.get('impact','')}
TARGET BUYER: {p.get('audience','')}
CONTENT PILLAR: {pillar}
HOOK ANGLE TO EXECUTE: {hook_angle}
WEBSITE (for the CTA): {s.website}

Return JSON:
{{
  "yt_title": "YouTube Shorts title <= 70 chars, punchy, keyworded for this product",
  "caption": "Instagram caption: a strong first line, 2-3 short value lines, then TWO CTAs: 'Follow {get_settings().brand_handle} for more' and a lead CTA ending with '{s.website}'. Human, specific, no hype, no em dashes. Write to earn saves, shares and follows, not likes.",
  "hashtags": "12-16 space-separated hashtags, ordered big -> niche, each starting with #, relevant to this product and audience",
  "segments": [
    {{"narration":"spoken line, 7 to 14 words", "on_screen":"2-5 word caption", "visual_type":"product|ai|stock", "visual_query":"label or search query or AI prompt"}}
  ]
}}
Give EXACTLY 6 beats in this order: 1 HOOK, 2 PROBLEM, 3 PRODUCT, 4 PRODUCT, 5 PROOF/IMPACT, 6 CTA.
Beats 3 and 4 MUST be visual_type "product" (the real tool is shown). Beat 1 is the hook, beat 6 is
the CTA. Use visual_type "stock" for problem/proof beats and "ai" for at most one emotional beat."""
    data = _chat_json(REEL_SYSTEM, user, temperature=0.85)
    segs = data.get("segments") or []
    data["segments"] = segs[:6]
    data["product"] = product
    return data


# =============================================================== 3. SEO SPECIALIST ==
SEO_SYSTEM = """You are a social SEO and discovery specialist. You pick hashtags and keywords that
maximize reach for a small but growing account: a mix of a few large tags (reach), several mid-size
tags (findability), and a few niche tags (relevance and ranking). You know YouTube Shorts and IG
Reels ranking basics. No banned or spammy tags. Never use em dashes."""


def seo_optimize(platform: str, product: str, hook: str, caption: str) -> dict:
    p = PRODUCTS.get(product, {})
    user = f"""Optimize discovery for this {platform} post about {p.get('name','')}.

HOOK: {hook}
CAPTION: {caption}
AUDIENCE: {p.get('audience','')}

Return JSON:
{{
  "hashtags": "12-18 hashtags as one space-separated string, ordered big -> niche, each starting with #",
  "keywords": "5-8 comma-separated SEO keywords to weave into title/caption",
  "best_time": "one ideal posting time in IST for this audience, e.g. '8:30 PM IST'",
  "boost_tip": "one line: the single strongest lever to boost reach on this specific post"
}}"""
    return _chat_json(SEO_SYSTEM, user, temperature=0.5)


# ============================================================= GROWTH MASTERMIND ==
MASTERMIND_SYSTEM = f"""You are a world-class growth + sales strategist running Praxia AI Studios'
social channels. You obsess over FOLLOWERS and LEADS (DMs, site visits, demo bookings), not vanity
likes. You read the numbers honestly and decide the day's move.

Hard truths you operate by:
- New accounts get near-zero reach for weeks. Growth compounds from consistency, strong hooks,
  saves + shares (not likes), YouTube search/SEO, and clear "follow + DM" calls to action.
- Reels via API cannot use trending audio, so we win on HOOKS, PACE, VALUE, and YouTube discovery.
- Every post must earn a follow and a lead. Trend-aware and meme-style hooks are welcome when they
  fit the brand (premium, sharp, never cringe).

{POSITIONING}

You pick: today's short-form REEL angle, and today's 3 to 5 minute YOUTUBE DEMO topic (a deeper,
search-friendly walkthrough of one product). Rotate products over time."""


def growth_brief(rows: list[dict], rotation_product: str) -> dict:
    """The one-call mastermind: diagnose + decide the day's reel + demo. rows may be empty."""
    prod_keys = list(PRODUCTS.keys())
    data = json.dumps(rows, ensure_ascii=False)[:5000] if rows else "No posts with metrics yet."
    user = f"""Here is all-time performance for our posts (JSON):
{data}

Products (rotate): {prod_keys}
If there is no data yet, default the reel + demo to product '{rotation_product}'.

Decide today's plan. Return JSON:
{{
  "report": "2-4 sentences: honest reach diagnosis and the ONE thing to improve next",
  "focus": "the single growth lever to push today (e.g. stronger hooks, YouTube SEO, a save-worthy tip)",
  "reel": {{"product":"one of {prod_keys}", "pillar":"short label", "hook_angle":"a specific scroll-stopping, trend/meme-aware angle that earns a follow"}},
  "demo": {{"product":"one of {prod_keys}", "topic":"a searchable 3-5 min demo topic", "angle":"what the walkthrough proves"}}
}}"""
    return _chat_json(MASTERMIND_SYSTEM, user, temperature=0.8)


# ================================================================= LONG DEMO ==
DEMO_SYSTEM = f"""You are a senior product marketer scripting a 3 to 5 minute YouTube demo for Praxia
AI Studios. It is a clear, engaging walkthrough that makes a buyer want a demo call. Spoken by an AI
voice: write natural, confident narration, short sentences, no symbols, no reading URLs mid-script.

Structure: strong hook (why watch), the problem + market cost, a guided walkthrough of the product
showing what it literally does step by step, the concrete output, the impact numbers, and a clear CTA
to visit the site and DM. Optimize the title + description for YouTube SEARCH.

{POSITIONING}"""


def demo_script(product: str, topic: str, angle: str) -> dict:
    p = PRODUCTS.get(product, {})
    s = get_settings()
    user = f"""Script a 3 to 5 minute YouTube demo.

PRODUCT: {p.get('name','')} — {p.get('what','')}
WHAT IT DOES (options): {' '.join(p.get('options', []))}
MARKET PRICE CONTEXT (anchor, never OUR price): {p.get('market_price','')}
IMPACT: {p.get('impact','')}
AUDIENCE: {p.get('audience','')}
DEMO TOPIC: {topic}
WHAT IT PROVES: {angle}
WEBSITE: {s.website}

Return JSON:
{{
  "yt_title": "search-optimized YouTube title <= 80 chars",
  "description": "3-5 line YouTube description with keywords and a CTA ending in {s.website}",
  "tags": "12-16 comma-separated YouTube tags",
  "sections": [
    {{"narration":"45 to 70 spoken words, 2 to 3 full sentences", "on_screen":"3-6 word label", "visual_type":"product|card|stock", "visual_query":"screenshot label / search query"}}
  ]
}}
Give 12 to 14 sections. First is an intro/hook, last is the CTA. Most middle sections must be
visual_type "product" (show the real tool). IMPORTANT: each section's narration must be 45 to 70
spoken words, and the TOTAL across all sections must be 550 to 800 words so the video runs 3 to 5
minutes. Do not write short one-line sections."""
    data = _chat_json(DEMO_SYSTEM, user, temperature=0.8)
    data["segments"] = (data.get("sections") or [])[:13]
    data["product"] = product
    return data


# ========================================================= FACELESS BUILD REEL ==
CONTENT_SYSTEM = f"""You are a faceless short-form creator in the style of build-in-public tech
creators (like EZsnippet): fast, funny, useful. You make daily Reels that solve ONE real work
problem with automation and show the result. No face, no personal voice, faceless brand channel.

Every reel opens with a FUNNY, RELATABLE MEME that has NOTHING to do with AI or tech, then pivots
into the automation. The meme sets up the pain in a human, everyday way (office life, Monday dread,
manual drudgery). Then you SHOW a slick tool that fixes it, give the impact, and a call to action.

BE DISRUPTIVE. The first spoken line and on-screen text must be a pattern interrupt: a bold claim, a
provocative "stop doing this", a spicy hot-take, or a shocking number. Punchy and confident, scroll-
stopping, a little controversial is good. NOT bland, NOT corporate, NOT explicit or NSFW (keep it
brand-safe for a B2B audience, edgy in wording not in content). Keep every on-screen text ULTRA short
(2 to 4 words) so nothing floods the screen.

{POSITIONING}

Optimize for FOLLOWERS + LEADS (saves, shares, DMs, free assessment calls), not likes. The product
being promoted determines the CTA:
- Course Factory: "build your whole training catalog + own your LMS" -> visit site / DM.
- Automation consultancy: "book a FREE bottleneck assessment call" -> DM / site.
- Automation training: "learn to automate this yourself" -> DM / site."""


def content_script(product: str, topic: dict, style: str, seed: int = 0) -> dict:
    """One call: meme hook text + mockup spec + narration segments + caption/hashtags for the
    faceless automation reel. topic = one AUTOMATION_TOPICS entry."""
    p = PRODUCTS.get(product, {})
    s = get_settings()
    user = f"""Make today's faceless automation Reel.

AUTOMATION PROBLEM: {topic.get('title')} (the pain: {topic.get('pain')})
PRODUCT TO PROMOTE: {p.get('name','')} — {p.get('what','')}
CTA CONTEXT: {p.get('impact','')}
MARKET PRICE ANCHOR (never OUR price): {p.get('market_price','')}
WEBSITE: {s.website}   HANDLE: {s.brand_handle}
VISUAL STYLE FOR TODAY: {style} (keep it distinct from a generic look)

Return JSON:
{{
  "meme": {{"top":"FUNNY top line, NON-AI, relatable office/work pain, all caps ok", "bottom":"FUNNY bottom line that lands the joke"}},
  "yt_title": "punchy YouTube Shorts title <= 70 chars",
  "caption": "IG caption: funny first line, 2 value lines, then 'Follow {s.brand_handle}' + a CTA ending with {s.website}. No em dashes.",
  "hashtags": "12-15 space-separated hashtags big -> niche, mixing automation, the industry, and broad reach tags",
  "mockup": {{
     "title":"the tool name for {topic.get('title')}", "subtitle":"one line: what it does",
     "badge":"AUTOMATED", "kpis":[{{"value":"e.g. 312","label":"short label"}} , 4 items with believable numbers],
     "cols":["3 column headers for a live activity table"],
     "rows":[["4-5 rows of 3 believable cells; status column should say Auto-approved/Done/Flagged"]],
     "flow":["3-4 short pipeline steps, e.g. 'Email in','Extract','Post to ERP']
  }},
  "segments": [
    {{"role":"hook","narration":"1 spoken line reading/riffing the meme, 6-12 words","on_screen":"2-4 words"}},
    {{"role":"problem","narration":"the manual pain, 8-14 words","on_screen":"2-4 words"}},
    {{"role":"build","narration":"what the automation does, 10-16 words","on_screen":"2-4 words"}},
    {{"role":"result","narration":"the impact with a number, 8-14 words","on_screen":"2-4 words"}},
    {{"role":"cta","narration":"the call to action, 6-12 words","on_screen":"2-4 words"}}
  ]
}}
Exactly these 5 segments in this order. The meme must be genuinely funny and unrelated to AI."""
    data = _chat_json(CONTENT_SYSTEM, user, temperature=0.9)
    data["product"] = product
    data["topic"] = topic.get("key")
    data["style"] = style
    # guarantee hashtags (a few broad reach tags always appended)
    tags = (data.get("hashtags") or "").strip()
    if len(tags.split()) < 6:
        tags = (tags + " " + DEFAULT_HASHTAGS).strip()
    data["hashtags"] = tags
    return data


DEFAULT_HASHTAGS = ("#automation #ai #productivity #nocode #workflow #business #tech #startup "
                    "#futureofwork #efficiency #digitaltransformation #reelsindia")


STATIC_SYSTEM = f"""You write ultra-minimal static social posts for a faceless premium AI studio.
One product per post. Almost no text. A punchy 3-6 word headline, a one-line subline, and a caption.
{POSITIONING}"""


def static_post(product: str) -> dict:
    """A minimal one-product static post (headline + subline + caption + hashtags)."""
    p = PRODUCTS.get(product, {})
    s = get_settings()
    user = f"""Make a minimal static post for this product.

PRODUCT: {p.get('name','')} — {p.get('what','')}
TAGLINE: {p.get('tagline','')}
IMPACT: {p.get('impact','')}
WEBSITE: {s.website}  HANDLE: {s.brand_handle}

Return JSON:
{{
  "headline": "3-6 word bold headline",
  "subline": "one short line, max 10 words",
  "caption": "2-3 short lines, end with 'Follow {s.brand_handle}' and {s.website}. No em dashes.",
  "hashtags": "10-14 space-separated hashtags"
}}"""
    d = _chat_json(STATIC_SYSTEM, user, temperature=0.75)
    tags = (d.get("hashtags") or "").strip()
    if len(tags.split()) < 6:
        tags = (tags + " " + DEFAULT_HASHTAGS).strip()
    d["hashtags"] = tags
    d["product"] = product
    return d


# =============================================================== 5. GROWTH ANALYST ==
ANALYST_SYSTEM = f"""You are a ruthless growth analyst for Praxia AI Studios. You read post performance
and decide, per post and overall, what to do next: DOUBLE DOWN on what worked, BOOST (paid) the posts
with unusually strong organic saves/shares, or KILL and REPLACE ideas that flopped. You are specific
and numeric. You never invent metrics that were not provided.

{POSITIONING}"""


def analyst_review(rows: list[dict]) -> dict:
    """rows: [{post_id, platform, product, pillar, hook, impressions, reach, likes, comments, shares, saves, views}]"""
    user = f"""Here is recent post performance (JSON). Analyze reach and engagement.

DATA:
{json.dumps(rows, ensure_ascii=False)[:6000]}

Return JSON:
{{
  "summary": "2-3 sentences: what is working, what is not, where reach is stalling",
  "verdicts": [{{"post_id": 1, "action": "double_down|boost|kill", "why": "one line with the number that drove it"}}],
  "winning_pillars": ["the pillars/angles to make more of"],
  "next_ideas": [{{"product":"course_factory","platform":"instagram","format":"reel","pillar":"...","hook_angle":"a fresh angle informed by what worked"}}],
  "boost_budget_tip": "one line on whether/where to spend a small boost budget"
}}"""
    return _chat_json(ANALYST_SYSTEM, user, temperature=0.6)


# ================================================================= IMAGE (art) ==
def _size_for(fmt: str) -> str:
    return "1024x1536" if fmt in ("reel", "short", "carousel", "long_video") else "1024x1024"


def generate_image(prompt: str, fmt: str = "reel", slug: str = "post") -> str:
    """Generate an on-brand post graphic, save as PNG under static/assets/posts, return web path."""
    s = get_settings()
    client = _client()
    styled = (
        f"{prompt}. Premium cinematic photography style, deep obsidian near-black background, "
        f"warm gold #C9A24B accent light, high contrast, elegant, editorial. No text, no watermark, "
        f"no logos, no cartoon robots. Professional brand visual for a high-end AI studio."
    )
    size = _size_for(fmt)
    b64 = None
    try:
        r = client.images.generate(model=s.image_model, prompt=styled, size=size, n=1)
        b64 = r.data[0].b64_json
        if not b64 and getattr(r.data[0], "url", None):
            import httpx
            b64 = base64.b64encode(httpx.get(r.data[0].url, timeout=60).content).decode()
    except Exception:
        # fallback to dall-e-3 (returns url unless b64 requested)
        ds = "1024x1792" if size == "1024x1536" else "1024x1024"
        r = client.images.generate(model="dall-e-3", prompt=styled, size=ds, n=1,
                                    response_format="b64_json")
        b64 = r.data[0].b64_json
    if not b64:
        raise RuntimeError("Image generation returned no data.")
    fname = f"{slug}-{int(time.time()*1000)}.png"
    (ASSETS_DIR / fname).write_bytes(base64.b64decode(b64))
    return f"/static/assets/posts/{fname}"
