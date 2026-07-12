# Praxia Marketing

A local outreach and sales tool for **Praxia AI Course Factory**. It sources leads,
writes AI-personalized emails, sends via Gmail, captures replies and auto-classifies them
(warm / so-so / cold), and drafts the right follow-up. FastAPI + SQLite + a single self-contained page.

## What it does
- **Sourcing** — harvest public business emails from institution websites, a built-in directory, or a web search.
- **Leads** — add / CSV import / pipeline (new → contacted → replied → meeting → won).
- **Compose** — a fixed first-touch email (merged with the lead's first name) or an AI-personalized draft, sent from Gmail.
- **Replies** — pull replies from Gmail, AI-sort into warm / so-so / cold, and draft category-appropriate follow-ups.
- **Dashboard** — the full funnel + reply categories.

## Run locally
1. `cd backend && cp .env.example .env` then fill in your keys.
2. Install deps: `pip install -r requirements.txt`
3. `python -m uvicorn app.main:app --port 8020`
4. Open http://127.0.0.1:8020

### Configuration (`backend/.env`)
- `OPENAI_API_KEY` — for email personalization + reply classification.
- `SMTP_USER` + `SMTP_APP_PASSWORD` — Gmail sending (create a Gmail App Password).
- `SENDER_NAME`, `PUBLIC_EMAIL`, `WHATSAPP`, `BOOKING_LINK`, `YOUTUBE_DEMO` — outreach identity + CTA.

## Compliance
No LinkedIn scraping or automated LinkedIn/WhatsApp messaging. Email only, sent through your own Gmail,
with a clear opt-out. See `SPEC.md` and `specs/` for the full design and roadmap.
