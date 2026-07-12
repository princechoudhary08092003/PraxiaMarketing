# M6 — Templates, A/B, follow‑ups, reporting

**Goal:** raise reply rates and stop leads going cold — manage templates, A/B test them,
auto‑**draft** timed follow‑ups (you approve), and see what's working.

## Features
1. **Template management + A/B**
   - CRUD templates (name, channel, region, subject, body/angle).
   - A/B: a template can have 2+ variants; sending picks a variant round-robin.
   - Per-variant metrics from `events`: sent, open, click, reply, and rates.
2. **Follow-up sequences**
   - A sequence = ordered steps `{delay_days, template_id}`.
   - Assign a lead to a sequence; if no reply by `delay_days`, the tool **drafts** the next
     step into a **review queue** (never auto-sends).
   - Local trigger: a **"Generate due follow-ups"** button (and, when hosted, a daily scheduled job).
3. **Suppression list** — unsubscribes + hard bounces; never contact again. Every email includes
   an unsubscribe line → `POST /api/unsubscribe` (works when hosted/tunneled).
4. **Reporting**
   - Weekly summary: leads added, emails sent, open/click/reply rates, best template, cold leads
     needing follow-up. Exportable CSV of leads + funnel.

## Data
- `templates`: add `variant_of` (nullable), keep metrics derived from `events`.
- New: `sequences(id,name)`, `sequence_steps(id,sequence_id,step,delay_days,template_id)`,
  `lead_sequence(lead_id,sequence_id,current_step,next_due,status)`.
- New: `suppression(email, reason, ts)`.

## API
- Templates: `GET/POST/PATCH/DELETE /api/templates`.
- Sequences: `GET/POST /api/sequences`, `POST /api/leads/{id}/sequence` `{sequence_id}`.
- `GET /api/followups/due` → leads whose `next_due<=now` and no reply → returns AI-drafted next email (review queue).
- `POST /api/unsubscribe` `{email}` (or tracked link) → add to suppression, mark lead lost.
- `GET /api/report/weekly`, `GET /api/export/leads.csv`.

## UI
- **Templates** tab: list + editor + A/B variants + per-template performance bars.
- **Follow-ups** panel on Dashboard: "N follow-ups due" → review + send.
- Report card on Dashboard + "Export CSV".

## Compliance
- Suppression enforced on every send. Unsubscribe honored immediately. Follow-ups are drafted,
  not auto-sent (human approves) — keeps volume + tone under control.

## Acceptance criteria
- Create an A/B template; sends alternate variants; dashboard shows per-variant reply rate.
- Assign a lead to a sequence; after the delay with no reply, it appears in "due follow-ups" with a draft.
- Unsubscribe removes a lead from future sends.

## Effort
~1–2 days.
