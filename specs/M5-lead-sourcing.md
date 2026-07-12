# M5 — Public lead sourcing

**Goal:** stop relying only on manual/CSV leads — *find* prospects from **public** sources
and drop them into a review queue. Compliant (public/business data only; no LinkedIn scraping).

## Sources (pluggable "finders")
1. **Directory finder** — public institution lists: UGC (ugc.gov.in) recognized universities,
   AICTE approved institutions, state university lists. Parse name + city + website.
2. **Site contact finder** — for a given institution website, fetch public pages likely to hold
   L&D / training contacts: search the site for "faculty development", "e-learning", "instructional
   design", "training & development", "CTL/teaching-learning centre"; extract public emails +
   `mailto:` + names/titles near them.
3. **Email finder** — Hunter.io free API (~25/mo) or Apollo free credits; fallback to pattern
   guess `first.last@domain` + optional MX/SMTP verify. Store `confidence`.
4. **Search finder** — Google Programmable Search API (free 100/day): queries like
   `"L&D head" OR "training manager" <company> email` → candidate org pages to enrich.

## Rules
- Obey **robots.txt**; rate-limit (e.g. 1 req/2s/domain); real User-Agent; cache fetched pages.
- Only **public, business** contacts. No LinkedIn. No private data.
- Everything lands in a **review queue** — nothing is contacted automatically.

## Data
- New table `candidates` (or `leads` with `status='review'`): name, org, org_type, country,
  title, email, domain, source, confidence, raw_meta (json), created_at.
- Dedup on `email` (or `domain`+`name`) against existing leads + candidates.

## API
- `POST /api/source/run` `{finder, params}` → `{added}` (runs a finder, inserts candidates).
- `GET /api/candidates?source=&country=` → list.
- `POST /api/candidates/{id}/accept` → move to `leads` (status `new`).
- `POST /api/candidates/{id}/reject`.
- `POST /api/candidates/accept-bulk` `{ids}`.

## Backend deps (new)
- `httpx` (already in venv), **`beautifulsoup4`** (install), optional `dnspython` for MX verify.
- `.env`: `HUNTER_API_KEY`, `APOLLO_API_KEY`, `GOOGLE_CSE_KEY`, `GOOGLE_CSE_CX` (all optional; finders degrade gracefully if absent).

## UI (static/index.html)
- New **"Sourcing"** tab: pick a finder + params (e.g. state, keyword, domain) → **Run** →
  candidates table with confidence → **Accept / Reject / Bulk accept** → accepted become leads.

## Acceptance criteria
- Run the directory finder for a state → candidates appear.
- Run the site contact finder on one institution domain → emails/titles extracted.
- Accept a candidate → it becomes a lead in the pipeline.

## Effort & risk
~1–2 days. Scraping is inherently **fragile** (site changes/blocks) and email accuracy varies —
always human-review before outreach. Treat finders as best-effort assistants, not guarantees.
