# M4 — LinkedIn / WhatsApp draft‑&‑paste assist

**Goal:** reach prospects on LinkedIn and WhatsApp **without** violating either platform's
terms (no bots, no bulk automation). The tool drafts a personalized message; **you** send it
with one click‑to‑open. 90% of the speed, zero ban risk.

## Scope
Per lead, generate and copy:
- **LinkedIn connection note** — ≤ 300 chars, no links (LinkedIn strips/greys them).
- **LinkedIn DM** — value + one CTA (after they connect).
- **WhatsApp message** — short, friendly, with the booking link + a one-line pitch.

Then one‑click:
- **Open LinkedIn profile** (`lead.linkedin_url`) → paste note/DM manually.
- **Open WhatsApp chat** via `https://wa.me/<digits>?text=<url-encoded message>` (prefilled) → hit send.
- **Copy** buttons for each text.
- Mark the lead **contacted** + log the channel.

## Data
Reuse existing tables:
- `messages` with `channel` in `linkedin_note | linkedin_dm | whatsapp`, `status='drafted'|'sent'`.
- `events`: `type='contacted'`, `meta=channel`.
- `leads.linkedin_url`, `leads.phone` already exist. Normalize phone to digits for `wa.me`.

## API
- `POST /api/assist` `{lead_id, channel}` → `{text}` (AI-generated; channel-specific length/format).
- `POST /api/contacted` `{lead_id, channel}` → sets status `contacted` (if earlier), writes event, stores the message row.

## AI (ai.py additions)
Add `assist(lead, channel)` with channel-specific system/user prompts:
- **linkedin_note:** ≤ 300 chars, warm, specific to their org/role, no link, ends with a soft ask to connect.
- **linkedin_dm:** ~60–90 words, one CTA (book/email), can name the demo.
- **whatsapp:** ~40–60 words, friendly, includes booking link (or email) + WhatsApp-appropriate tone.

## UI (static/index.html)
- New **"Assist"** control on each lead row (or a per-lead drawer): channel selector → **Generate** →
  shows the text with **Copy** + **Open LinkedIn** / **Open WhatsApp** buttons → **Mark contacted**.
- `wa.me` link built client-side from `lead.phone` digits + `encodeURIComponent(text)`.

## Compliance notes
- Human presses send every time. No auto-connect, no auto-DM, no queued WhatsApp blasts.
- Respect LinkedIn note char limit; don't put links in the connection note.

## Acceptance criteria
- Generate a LinkedIn note/DM and a WhatsApp text for a lead.
- "Open WhatsApp" opens a prefilled chat; "Open LinkedIn" opens the profile.
- After sending manually, "Mark contacted" advances the lead + shows in the funnel.

## Effort
~0.5 day. No new dependencies.
