# Booking + public landing

**Goal:** give prospects an easy way to **book a call** (your primary CTA), and — when you're
ready to host — a public landing page with the demo video + brochures + a capture form.

## Booking (available now)
- Set `BOOKING_LINK` in `.env`. The AI email CTA already includes it when present, alongside
  email + WhatsApp.
- Free scheduler options: **Cal.com** (free, open-source), **Google Calendar appointment
  schedules** (free with any Google account), Calendly (free tier). Recommend Cal.com or the
  Google appointment schedule since you already use Gmail.
- No build needed — it's a config value that flows into every draft.

## Public landing page (later — needs hosting)
Not built while local-only (localhost isn't public). When hosted / tunneled:
- Static page served at `/landing`: Praxia hero, **demo video** embed, **both brochures**
  (India ₹ / Global $), a "**Book a call**" button (`BOOKING_LINK`), and a lead‑capture form.
- Form `POST /api/leads` with `source='inbound'`, `status='new'` → lands in the pipeline
  (inbound leads are your warmest).
- Host the demo video on **YouTube (unlisted)** or S3/CloudFront; brochures as static files or links.
- `.env`: `DEMO_VIDEO` (public URL), reuse brochures from Downloads or host them.

## Assets checklist
- Demo video hosted (YouTube unlisted recommended — free, reliable embeds).
- India + Global brochures reachable by link (host the PDFs).
- Booking link chosen + set in `.env`.

## Acceptance criteria
- With `BOOKING_LINK` set, generated emails include the booking link in the CTA.
- When hosted: `/landing` shows video + brochures + booking; the form creates an inbound lead.

## Effort
Booking: minutes (config). Landing page: ~0.5 day, only once hosting exists.
