# Tracking + hosting (opens / clicks / replies)

**Goal:** turn on real engagement tracking (opens, clicks, replies) so the funnel reflects
reality — and make the tool reachable when needed.

## Why it's off locally
Open/click tracking needs a URL the **recipient's** email client can reach. `localhost:8020`
is not reachable from outside, so the pixel/redirect never fire. Reply detection works via
Gmail regardless. So local mode tracks **sent → replied → (manual) status**; opens/clicks turn
on once the app is reachable.

## Make it reachable (pick one)
- **Free tunnel (fastest):** `cloudflared tunnel --url http://localhost:8020` → gives a public
  `https://…trycloudflare.com`. Set `PUBLIC_BASE_URL` to it in `.env`.
- **Host it** (Render/Fly/VPS) → set `PUBLIC_BASE_URL` to the public domain.

## Wiring (backend)
- `.env`: add `PUBLIC_BASE_URL` (blank = tracking disabled; sends still work, no pixel/links rewritten).
- **On send (mailer.py):**
  - Append an open pixel: `<img src="{PUBLIC_BASE_URL}/api/t/o.gif?l={lead_id}&m={msg_id}" width="1" height="1">`.
  - Rewrite outbound links to `…/api/t/c?u=<encoded>&l={lead_id}&m={msg_id}` (redirects + logs click).
  - Append an unsubscribe line → `…/api/unsubscribe?e=<email>`.
- Endpoints `/api/t/o.gif` and `/api/t/c` already exist and advance lead status; they just need a
  reachable base URL + the send-time injection above.

## Reply detection (Gmail IMAP)
- Poll Gmail via `imaplib` + the same App Password: read INBOX, match `From:` against lead emails,
  mark those leads `replied` + write an event. Run on a timer (or a "Check replies" button locally).
- `.env`: reuse `SMTP_USER` / `SMTP_APP_PASSWORD` (IMAP host `imap.gmail.com:993`).

## Deliverability (do before volume)
- SPF/DKIM/DMARC — automatic for `@gmail.com`; required if you move to a custom domain.
- Warm up: low volume, ramp slowly; personalize; always include unsubscribe + a physical address
  (CAN-SPAM) for US recipients; get consent basis for EU (GDPR).
- For scale, use a **separate sending domain** so a spam hit never harms your main domain.

## Acceptance criteria
- With a tunnel + `PUBLIC_BASE_URL` set: sending injects pixel + tracked links; opening the email
  registers an `open`; clicking a link registers a `click` and advances status.
- "Check replies" marks a lead `replied` when they respond.

## Effort
~0.5–1 day (send-time injection + IMAP poll).
