"""Lead sourcing: harvest PUBLIC business emails from institution websites, a built-in
directory of targets, and a best-effort web search. No LinkedIn, no paid API keys.

Only collects publicly published business contact emails. Be polite: few pages, timeouts,
a real User-Agent. Always human-reviewed before any outreach."""
from __future__ import annotations

import re
import urllib.parse

import httpx

UA = {"User-Agent": "Mozilla/5.0 (compatible; PraxiaOutreach/1.0; +mailto:praxiaaistudios@gmail.com)"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# pages most likely to list public contact emails
PATHS = ["", "/contact", "/contact-us", "/contactus", "/about", "/about-us",
         "/faculty", "/departments", "/people", "/staff", "/team", "/academics",
         "/admissions", "/training", "/executive-education", "/leadership"]

# junk / non-lead patterns to drop
BAD_SUBSTR = ("noreply", "no-reply", "donotreply", "postmaster", "mailer-daemon",
              "example.", "@example", "sentry", "wixpress", "@2x", "your-email",
              "yourname", "@sentry", "u003", "@email", "name@", "abc@")
BAD_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")

# --- built-in directory of target institutions (name, domain, country, type) ---
SEED = [
    ("IIM Bangalore", "iimb.ac.in", "India", "university"),
    ("IIM Ahmedabad", "iima.ac.in", "India", "university"),
    ("IIM Indore", "iimidr.ac.in", "India", "university"),
    ("IIM Calcutta", "iimcal.ac.in", "India", "university"),
    ("IIT Bombay", "iitb.ac.in", "India", "university"),
    ("IIT Delhi", "iitd.ac.in", "India", "university"),
    ("IIT Madras", "iitm.ac.in", "India", "university"),
    ("University of Delhi", "du.ac.in", "India", "university"),
    ("Amity University", "amity.edu", "India", "university"),
    ("Manipal Academy", "manipal.edu", "India", "university"),
    ("Christ University", "christuniversity.in", "India", "university"),
    ("Symbiosis International", "siu.edu.in", "India", "university"),
    ("Ashoka University", "ashoka.edu.in", "India", "university"),
    ("O.P. Jindal Global University", "jgu.edu.in", "India", "university"),
    ("Lovely Professional University", "lpu.in", "India", "university"),
    ("VIT", "vit.ac.in", "India", "university"),
    ("SRM Institute", "srmist.edu.in", "India", "university"),
    ("BITS Pilani", "bits-pilani.ac.in", "India", "university"),
    ("Shiv Nadar University", "snu.edu.in", "India", "university"),
    ("Great Lakes Institute", "greatlakes.edu.in", "India", "college"),
    ("NMIMS", "nmims.edu", "India", "university"),
    ("Bennett University", "bennett.edu.in", "India", "university"),
    ("Harvard University", "harvard.edu", "Global", "university"),
    ("MIT", "mit.edu", "Global", "university"),
    ("Stanford University", "stanford.edu", "Global", "university"),
    ("University of Oxford", "ox.ac.uk", "Global", "university"),
    ("University of Cambridge", "cam.ac.uk", "Global", "university"),
    ("National University of Singapore", "nus.edu.sg", "Global", "university"),
    ("University of Melbourne", "unimelb.edu.au", "Global", "university"),
    ("University of Toronto", "utoronto.ca", "Global", "university"),
]


def _clean_domain(raw: str) -> str:
    raw = raw.strip().lower()
    raw = re.sub(r"^https?://", "", raw).rstrip("/")
    raw = raw.split("/")[0]
    if raw.startswith("www."):
        raw = raw[4:]
    return raw


def _valid_email(em: str, domain: str | None) -> bool:
    em = em.lower()
    if any(b in em for b in BAD_SUBSTR):
        return False
    if em.endswith(BAD_EXT):
        return False
    if len(em) > 70 or em.count("@") != 1:
        return False
    local, _, host = em.partition("@")
    if not local or host.count(".") < 1:
        return False
    return True


def harvest_domain(domain: str, per_domain_cap: int = 20) -> list[dict]:
    """Fetch a few public pages of a domain and extract published emails."""
    domain = _clean_domain(domain)
    if not domain or "." not in domain:
        return []
    base = f"https://{domain}"
    found: dict[str, str] = {}
    try:
        client = httpx.Client(timeout=8.0, follow_redirects=True, headers=UA)
    except Exception:
        return []
    try:
        for path in PATHS:
            if len(found) >= per_domain_cap:
                break
            try:
                r = client.get(base + path)
            except Exception:
                continue
            if r.status_code >= 400 or "text" not in r.headers.get("content-type", ""):
                continue
            for em in EMAIL_RE.findall(r.text):
                em = em.strip().lower().strip(".")
                if em not in found and _valid_email(em, domain):
                    found[em] = base + path
    finally:
        client.close()
    # prefer emails on the institution's own domain first
    items = sorted(found.items(), key=lambda kv: (0 if domain in kv[0] else 1, kv[0]))
    return [{"email": e, "source_url": u, "domain": domain} for e, u in items]


def web_search(query: str, limit: int = 8) -> list[str]:
    """Best-effort: return result URLs from DuckDuckGo HTML (no API key). May be empty."""
    urls: list[str] = []
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, headers=UA) as c:
            r = c.post("https://html.duckduckgo.com/html/", data={"q": query})
        for m in re.findall(r'uddg=([^"&]+)', r.text):
            try:
                u = urllib.parse.unquote(m)
                if u.startswith("http"):
                    urls.append(u)
            except Exception:
                continue
    except Exception:
        return []
    # dedupe by domain
    seen, out = set(), []
    for u in urls:
        d = _clean_domain(u)
        if d and d not in seen:
            seen.add(d)
            out.append(u)
        if len(out) >= limit:
            break
    return out


def org_from_domain(domain: str) -> str:
    core = _clean_domain(domain).split(".")[0]
    return core.upper() if len(core) <= 4 else core.capitalize()
