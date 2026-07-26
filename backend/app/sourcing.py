"""Lead sourcing: harvest PUBLIC business emails from institution websites, a built-in
directory of targets, and a best-effort web search. No LinkedIn, no paid API keys.

Only collects publicly published business contact emails. Be polite: few pages, timeouts,
a real User-Agent. Always human-reviewed before any outreach."""
from __future__ import annotations

import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

# A normal browser UA harvests far more than a bot UA (many sites block unknown agents).
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# pages most likely to list public contact emails (fetched concurrently, so keep the useful ones)
PATHS = ["", "/contact", "/contact-us", "/contactus", "/about", "/about-us",
         "/faculty", "/people", "/staff", "/team", "/leadership", "/departments"]

# search-engine / social / aggregator / blog / directory domains we never harvest as "leads".
# These return listicles and template pages, not real organisation contacts.
_SKIP_DOMAINS = (
    "duckduckgo.com", "duck.co", "google.", "bing.", "yahoo.", "yandex.",
    "wikipedia.org", "facebook.com", "linkedin.com", "youtube.com", "twitter.com", "x.com",
    "instagram.com", "pinterest.", "reddit.com", "quora.com", "medium.com", "wordpress.",
    "blogspot.", "tumblr.com", "substack.com", "github.com", "gitlab.com", "slideshare.",
    "scribd.com", "issuu.com", "glassdoor.", "indeed.", "naukri.", "monster.", "shine.com",
    "ambitionbox.", "crunchbase.", "clutch.co", "g2.com", "capterra.", "getapp.",
    "trustpilot.", "justdial.", "sulekha.", "yelp.", "tripadvisor.", "amazon.", "flipkart.",
    "eventbrite.", "meetup.com", "coursera.org", "udemy.com", "edx.org", "wix.com",
    "squarespace.com", "godaddy.com", "sentry.io", "mysite.com", "example.com",
    "urbanpro.", "techbehemoths.", "sortlist.", "designrush.", "goodfirms.", "shiksha.com",
    "collegedunia.", "careers360.", "3.basecamp",
    # infra / CDN / tracking hosts that appear as links but are never leads
    "googleapis.com", "gstatic.com", "googletagmanager.", "google-analytics.", "doubleclick.",
    "gravatar.com", "w3.org", "schema.org", "cdnjs.", "jsdelivr.", "cloudflare.", "jquery.",
    "unpkg.com", "bootstrapcdn.", "gmpg.org", "wp.com", "wordpress.org", "whatsapp.com",
    "wa.me", "t.me", "goo.gl", "bit.ly", "apple.com", "microsoft.com", "adobe.com", "vimeo.com",
    "website-files.com", "flipboard.com", "vk.com", "ok.ru", "cloudfront.net", "akamai",
    "typekit.net", "fontawesome.com", "hotjar.com", "hubspot.com", "calendly.com",
)

# second-level ccTLDs so we collapse sub.org.co.in to org.co.in, not co.in
_TWO_PART_TLDS = {"co.in", "org.in", "net.in", "ac.in", "edu.in", "gov.in", "res.in",
                  "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "edu.au", "gov.au",
                  "co.nz", "com.sg", "edu.sg", "co.za", "com.br", "co.jp", "com.my"}

# junk / non-lead substrings (checked anywhere in the address)
BAD_SUBSTR = ("noreply", "no-reply", "donotreply", "do-not-reply", "postmaster",
              "mailer-daemon", "sentry", "wixpress", "@2x", "@sentry", "u003",
              "webmaster@", "abuse@", "hostmaster@")
BAD_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")

# obvious template / placeholder addresses that appear on unfinished or demo sites
PLACEHOLDER_LOCALS = {"example", "email", "e-mail", "user", "username", "name", "firstname",
                      "lastname", "yourname", "your-name", "test", "demo", "sample", "john",
                      "jane", "johndoe", "janedoe", "abc", "xyz", "domain", "company",
                      "yourcompany", "someone", "mail", "youremail", "your-email", "info@example"}
PLACEHOLDER_DOMAINS = ("example.com", "example.org", "example.net", "mysite.com", "yoursite.com",
                       "yourdomain.com", "domain.com", "email.com", "test.com", "company.com",
                       "yourcompany.com", "sentry.wixpress.com", "wixpress.com", "wix.com",
                       "godaddy.com", "squarespace.com", "placeholder.com")

# role addresses that are genuinely useful for L&D / training outreach (ranked first)
GOOD_ROLES = ("training", "learning", "lnd", "l&d", "talent", "development", "corporate",
              "hr", "people", "academy", "education", "programs", "programmes", "info",
              "contact", "hello", "connect", "enquiry", "enquiries", "admissions", "outreach")

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


def _registrable(domain: str) -> str:
    """Collapse a host to its registrable domain (login.edstellar.com -> edstellar.com,
    hindi.inventiva.co.in -> inventiva.co.in) so subdomains don't create duplicate leads."""
    parts = domain.split(".")
    if len(parts) <= 2:
        return domain
    if ".".join(parts[-2:]) in _TWO_PART_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


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
    # drop template / placeholder addresses (example@mysite.com, name@yourdomain.com, ...)
    if local in PLACEHOLDER_LOCALS:
        return False
    if host in PLACEHOLDER_DOMAINS or any(host == d or host.endswith("." + d) for d in PLACEHOLDER_DOMAINS):
        return False
    if any(s in host for s in _SKIP_DOMAINS):
        return False
    return True


def _rank(email: str, domain: str) -> tuple:
    """Sort key: same-domain first, then useful role addresses, then alphabetical."""
    local = email.partition("@")[0]
    on_domain = 0 if domain and domain in email else 1
    is_role = 0 if any(r in local for r in GOOD_ROLES) else 1
    return (on_domain, is_role, email)


def _fetch_text(client: httpx.Client, url: str) -> str:
    try:
        r = client.get(url)
    except Exception:
        return ""
    if r.status_code >= 400 or "text" not in r.headers.get("content-type", ""):
        return ""
    return r.text


def harvest_domain(domain: str, per_domain_cap: int = 20) -> list[dict]:
    """Fetch a domain's public pages CONCURRENTLY and extract published emails.
    Concurrency + a short timeout keeps this to a few seconds per site instead of ~1 min."""
    domain = _clean_domain(domain)
    if not domain or "." not in domain:
        return []
    base = f"https://{domain}"
    found: dict[str, str] = {}
    urls = [base + p for p in PATHS]
    timeout = httpx.Timeout(6.0, connect=5.0)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=UA, verify=False) as client:
            with ThreadPoolExecutor(max_workers=6) as ex:
                futs = {ex.submit(_fetch_text, client, u): u for u in urls}
                for fut in as_completed(futs):
                    text = fut.result()
                    if not text:
                        continue
                    src = futs[fut]
                    for em in EMAIL_RE.findall(text):
                        em = em.strip().lower().strip(".")
                        if em not in found and _valid_email(em, domain):
                            found[em] = src
    except Exception:
        return []
    # own-domain first, then useful role addresses, then alphabetical
    items = sorted(found.items(), key=lambda kv: _rank(kv[0], domain))
    return [{"email": e, "source_url": u, "domain": domain} for e, u in items][:per_domain_cap]


def web_search(query: str, limit: int = 8) -> list[str]:
    """Return result URLs from DuckDuckGo Lite (no API key). The old html endpoint stopped
    returning parseable links; the lite endpoint still exposes plain result hrefs."""
    cands: list[str] = []
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, headers=UA) as c:
            r = c.post("https://lite.duckduckgo.com/lite/", data={"q": query})
        # lite results are plain https hrefs
        cands.extend(re.findall(r'href="(https?://[^"]+)"', r.text))
        # fallback: legacy uddg-encoded links if present
        for m in re.findall(r'uddg=([^"&]+)', r.text):
            u = urllib.parse.unquote(m)
            if u.startswith("http"):
                cands.append(u)
    except Exception:
        return []
    seen, out = set(), []
    for u in cands:
        d = _clean_domain(u)
        if not d or d in seen:
            continue
        if any(b in d for b in _SKIP_DOMAINS):
            continue
        seen.add(d)
        out.append(u)
        if len(out) >= limit:
            break
    return out


def _page_domains(client: httpx.Client, url: str) -> list[str]:
    """A result page's own domain PLUS the external company domains it links to.
    Turns a 'top 10 training companies' listicle into the actual companies to harvest."""
    rd = _clean_domain(url)
    out = [rd] if rd and "." in rd else []
    text = _fetch_text(client, url)
    if text:
        for m in re.findall(r'href=["\'](https?://[^"\'> ]+)', text):
            d = _clean_domain(m)
            if d and "." in d and d != rd and not any(s in d for s in _SKIP_DOMAINS):
                out.append(d)
    return out


def discover_domains(query: str, limit: int = 20) -> list[str]:
    """Search, then expand each result page into the real organisation domains it references.
    This finds far more relevant targets than harvesting the search-result pages themselves."""
    result_urls = web_search(query, limit=10)
    if not result_urls:
        return []
    seen: set[str] = set()
    domains: list[str] = []
    timeout = httpx.Timeout(8.0, connect=5.0)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=UA, verify=False) as client:
            with ThreadPoolExecutor(max_workers=6) as ex:
                futs = [ex.submit(_page_domains, client, u) for u in result_urls]
                for fut in as_completed(futs):
                    try:
                        found = fut.result()
                    except Exception:
                        found = []
                    for d in found:
                        d = _registrable(d)
                        if d in seen or any(s in d for s in _SKIP_DOMAINS):
                            continue
                        seen.add(d)
                        domains.append(d)
    except Exception:
        # fall back to the plain result domains
        return [_clean_domain(u) for u in result_urls][:limit]
    return domains[:limit]


def org_from_domain(domain: str) -> str:
    core = _clean_domain(domain).split(".")[0]
    return core.upper() if len(core) <= 4 else core.capitalize()
