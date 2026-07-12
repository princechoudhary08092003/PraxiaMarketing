# Praxia Marketing Tool — Build Spec

A **separate** product from the Praxia Course Studio app. Goal: a free / low‑cost,
semi‑automated **outreach + sales engine** to market Praxia to universities, colleges,
L&D teams and corporates in **India and globally**, with a **dashboard + tracking** at
its center so we can measure what works and **change the plan** when something isn't.

Location: `praxia-marketing/` (sibling of `praxia-course-factory/`). Own DB, own ports.

---

## 0. Guiding principles (decided)
- **Compliant by design.** No LinkedIn scraping / auto‑DM, no WhatsApp bulk automation
  (both violate provider terms → bans). LinkedIn/WhatsApp are handled in **"draft &
  paste" assist** mode (human sends). Email is the automated channel.
- **Free‑first.** Uses your existing OpenAI key, your Gmail (`praxiaaistudios@gmail.com`),
  SQLite, and free hosting tiers. Paid tools only when scaling is proven worth it.
- **Everything is measured.** Every stage emits a tracked event so the dashboard shows a
  real funnel — the whole point is to *see* what's failing and pivot.
- **Region‑aware.** Each lead is India or Global → drives ₹ brochure/pricing vs $ brochure.

---

## 1. Tech stack (reuse what we know)
- **Backend:** Python + FastAPI + **SQLite** (via SQLModel). Persistent (unlike the app's
  in‑memory store) — leads/campaigns/events must survive restarts.
- **Frontend:** React + Vite + Tailwind, Praxia brand system (obsidian/gold/Fraunces).
- **AI:** OpenAI (existing key) for message personalization.
- **Email:** Gmail API (OAuth) for sending; backend hosts **open pixel** + **click‑tracking
  redirects**. Daily send cap (ramp slowly).
- **Landing page:** static (demo video + both brochures + "book a demo" form), served by
  the same backend so form + tracking share one origin.
- **Lead sources:** CSV import; public directory scrapers (UGC/AICTE/university dept pages);
  optional Hunter/Apollo free‑tier email lookup; Google Programmable Search (free tier).
- **Hosting:** free (Vercel/Netlify/Render free / local + Cloudflare tunnel). Ports e.g.
  backend 8020, frontend 5193 (clear of the two course apps).

---

## 2. Data model (SQLite)
- **Lead**: id, name, org, org_type (university | college | l&d | corporate | other),
  country (India | Global), region‑derived currency, title, email, linkedin_url, phone,
  source, status (new → queued → contacted → opened → clicked → replied → meeting → won |
  lost), notes, created_at.
- **Template**: id, name, channel (email | linkedin | whatsapp), region (India | Global),
  subject, body (with `{{variables}}` + AI personalization instruction).
- **Campaign**: id, name, channel, template_id, region, status.
- **Message**: id, lead_id, campaign_id, channel, subject, body, status (draft | approved |
  sent | bounced), sent_at.
- **Event** (tracking spine): id, lead_id, message_id, type (visit | form | sent | open |
  click | reply | unsubscribe | meeting | won | lost), meta (json), ts.

---

## 3. Milestones (build order — each independently useful)

### M1 — Landing page + tracking spine  *(fast; unblocks everything)*
- Branded landing page: hero, demo video embed, **both brochures** (India ₹ / Global $),
  and a **"Book a demo"** form.
- Backend: `GET /t/o.gif` (open pixel), `GET /t/c?u=…&m=…` (click redirect + log),
  `POST /leads` (form submit → Lead + Event).
- Dashboard v0: visits, clicks, form leads.
- **Deliverable:** one public link to drop into any email/DM/message.

### M2 — CRM + dashboard  *(the tracking core)*
- CSV import + manual add of leads (name/org/email/country/type).
- Lead table with filters (status, country, org_type) + Kanban pipeline.
- **Funnel dashboard:** Source → Lead → Contacted → Opened → Clicked → Replied → Meeting →
  Won, with conversion rates, sliced by **country / org_type / template / channel**.
- Cost tracking (OpenAI spend per campaign).

### M3 — AI‑personalized email outreach
- Region‑aware templates (India → ₹ brochure/pricing; Global → $ brochure).
- Per‑lead OpenAI personalization: subject + body referencing their org, with **tracked**
  links to the landing page / brochure.
- **Review‑before‑send queue** (you approve each, or approve in bulk).
- Send via Gmail API with a daily cap; log Message + Event(sent); wire open/click events.
- Auto opt‑out link + suppression list.

### M4 — Assisted LinkedIn / WhatsApp (compliant)
- Generate personalized LinkedIn connection note + DM + WhatsApp text per lead.
- One‑click **"copy + open"**: opens the LinkedIn profile or a `wa.me` chat prefilled — you
  hit send. Logs the lead as *contacted*. No bots, no ban risk.

### M5 — Lead sourcing (public data)
- Scrapers for public directories: UGC/AICTE college lists, university L&D / e‑learning /
  training dept pages (respect robots.txt + rate‑limit).
- Optional Hunter/Apollo free‑tier email lookup; Google Programmable Search to discover orgs.
- All results land in a **review queue** before entering the pipeline.

### M6 — Optimize & report
- A/B templates with per‑template performance.
- Follow‑up sequences (auto‑draft a follow‑up after N days if no reply — you approve).
- Weekly summary (what's working / what to cut).

---

## 4. Tracking → "change the plan" (the emphasis)
The dashboard is the product's spine. Instrument every stage and slice it so you can kill
what fails and double down on what works:
- **Funnel by segment:** open/click/reply/meeting/win rates per country, org_type, template,
  channel, campaign.
- **Cohorts:** compare campaigns/templates side by side.
- **Leading indicators:** open rate (subject line), click rate (offer/landing), reply rate
  (message fit) — each tells you *which* lever to change.
- **Cost per meeting / per win** so ROI is visible.

---

## 5. Free stack + limits (honest)
| Piece | Free option | Limit / caveat |
|---|---|---|
| AI personalization | your OpenAI key | ~pennies/lead |
| Email send | Gmail API | ~500/day free (2000 Workspace); ramp slowly |
| Deliverability | SPF/DKIM/DMARC | consider a **separate sending domain** to protect main reputation |
| Email finding | Hunter / Apollo free | limited monthly credits |
| Data store | SQLite | free, local |
| Hosting | Vercel/Netlify/Render free / tunnel | fine for our volume |

## 6. Explicitly NOT built (compliance)
- ❌ LinkedIn scraping or auto‑DM
- ❌ WhatsApp bulk/automated messaging
- ✅ Replaced by compliant "draft & paste" assist

## 7. Risks & mitigations
- **Email spam/deliverability** → low volume, warm‑up, personalization, opt‑out, separate domain.
- **Free‑tier caps** → queue + daily throttle; upgrade only when justified.
- **Scraper fragility** → treat public sources as best‑effort; always human‑review before outreach.

## 8. Recommended start
**M1 (landing + tracking) → M2 (CRM + dashboard)** first — that gives you a shareable link
and the measurement backbone. Then M3 (AI email). Sourcing (M5) and assist (M4) after.
