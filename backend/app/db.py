"""SQLite storage for the marketing tool (stdlib sqlite3 — no extra deps).
A new connection per call keeps it thread-safe under uvicorn."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "marketing.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT DEFAULT '', org TEXT DEFAULT '', org_type TEXT DEFAULT 'university',
  country TEXT DEFAULT 'India', title TEXT DEFAULT '', email TEXT DEFAULT '',
  linkedin_url TEXT DEFAULT '', phone TEXT DEFAULT '', source TEXT DEFAULT 'manual',
  status TEXT DEFAULT 'new', notes TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, channel TEXT DEFAULT 'email',
  region TEXT DEFAULT 'India', subject TEXT DEFAULT '', body TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER, channel TEXT DEFAULT 'email',
  subject TEXT DEFAULT '', body TEXT DEFAULT '', status TEXT DEFAULT 'sent',
  sent_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER, message_id INTEGER,
  type TEXT, meta TEXT DEFAULT '', ts TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT DEFAULT '', org TEXT DEFAULT '',
  org_type TEXT DEFAULT 'university', country TEXT DEFAULT 'India', title TEXT DEFAULT '',
  email TEXT DEFAULT '', domain TEXT DEFAULT '', source TEXT DEFAULT 'harvest',
  source_url TEXT DEFAULT '', confidence TEXT DEFAULT 'medium',
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS replies (
  id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER, from_email TEXT DEFAULT '',
  subject TEXT DEFAULT '', body TEXT DEFAULT '', category TEXT DEFAULT '', reason TEXT DEFAULT '',
  message_id TEXT DEFAULT '', received_at TEXT DEFAULT '', handled INTEGER DEFAULT 0,
  followup_subject TEXT DEFAULT '', followup_body TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now'))
);
"""

# columns added after the initial release (safe idempotent migration)
MIGRATIONS = {
    "leads": [("category", "TEXT DEFAULT ''"), ("last_reply_at", "TEXT DEFAULT ''")],
}

TEMPLATES_SEED = [
    ("Intro — India", "email", "India",
     "AI-built, LMS-ready courses for {org}",
     "Angle: outcome-led. Praxia turns one title into a complete, published course — "
     "curriculum, teaching slides, narrated video, interactive H5P, assessments, and one-click "
     "Moodle publishing. Compliance-ready (UGC/NEP). Price framing in INR. Close with a call/email."),
    ("Intro — Global", "email", "Global",
     "Turn your expertise into complete, published courses",
     "Angle: outcome-led. Praxia turns one title into a complete, published course — "
     "curriculum, slides, narrated video, interactive H5P, assessments, LMS publishing. "
     "Price framing in USD. Close with a call/email."),
]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        for table, cols in MIGRATIONS.items():
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        if conn.execute("SELECT COUNT(*) c FROM templates").fetchone()["c"] == 0:
            conn.executemany(
                "INSERT INTO templates(name,channel,region,subject,body) VALUES (?,?,?,?,?)",
                TEMPLATES_SEED,
            )
        conn.commit()
    finally:
        conn.close()
