# Praxia Marketing — Specs Index

Detailed specs for each part of the marketing tool. High-level plan lives in
`../SPEC.md`; this folder breaks each milestone into a buildable spec.

| # | Spec | Status | Effort |
|---|---|---|---|
| M1–M3 | CRM + dashboard + AI email + Gmail send | ✅ **built** (`../SPEC.md`) | done |
| M4 | [LinkedIn / WhatsApp draft‑&‑paste assist](M4-linkedin-whatsapp-assist.md) | 📋 spec | ~0.5 day |
| M5 | [Public lead sourcing](M5-lead-sourcing.md) | 📋 spec | ~1–2 days |
| M6 | [Templates, A/B, follow‑ups, reporting](M6-optimization.md) | 📋 spec | ~1–2 days |
| — | [Tracking + hosting (opens/clicks/replies)](tracking-hosting.md) | 📋 spec | ~0.5–1 day |
| — | [Booking + public landing](booking-landing.md) | 📋 spec | ~0.5 day |

## Conventions
- **Stack:** FastAPI + stdlib sqlite3 + single-page `static/index.html` (vanilla JS, Praxia brand). Port **8020**. Runs on the course app's venv.
- **Compliance is non-negotiable:** no LinkedIn scraping / auto-DM, no WhatsApp bulk. Human-in-the-loop for those channels; email is the only automated send.
- **Free-first:** OpenAI (existing key), Gmail SMTP, free API tiers. Paid only when scale is proven.
- **Everything measured:** every action writes an `events` row so the dashboard funnel stays truthful.

## Recommended build order
M4 (assist) → tracking+hosting (turn on opens/clicks via tunnel) → M5 (sourcing) → M6 (optimize) → booking+landing (when hosted).
