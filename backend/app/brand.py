"""Brand assets + real product footage for reels.

Stages the official Praxia logo/mark/product images, and captures REAL screenshots of the live
marketing site and the running Course Factory app, so reels show the actual product and site,
not random stock. Screenshots are cached (captured once) under app/static/brand/shots.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

log = logging.getLogger("praxia.brand")

BRAND_DIR = Path(__file__).resolve().parent / "static" / "brand"
SHOTS_DIR = BRAND_DIR / "shots"

# Portable: PRAXIA_WEBSITE_DIR env wins; else the praxia-studios-website repo cloned as a sibling
# of this repo; else the original dev path. Brand assets are also cached in BRAND_DIR after first run.
def _find_web_dir() -> Path:
    import os
    env = os.getenv("PRAXIA_WEBSITE_DIR")
    if env and Path(env).exists():
        return Path(env)
    repo_root = Path(__file__).resolve().parents[3]      # .../praxia-marketing
    sibling = repo_root.parent / "praxia-studios-website"
    if sibling.exists():
        return sibling
    return Path(r"C:\Users\Prince.Choudhary\praxia-studios-website")

WEB_DIR = _find_web_dir()
WEB_IMG = WEB_DIR / "assets" / "img"

MARK = BRAND_DIR / "mark.png"          # transparent spark mark (corner watermark)
LOGO_FULL = BRAND_DIR / "logo-full.png"  # full logo for the CTA card
PRODUCTS_IMG = {
    "course_factory": BRAND_DIR / "course-factory.jpg",
    "automation_sprint": BRAND_DIR / "automation-sprint.jpg",
    "ai_trainings": BRAND_DIR / "masterclass.jpg",
}


def ensure_assets() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    pairs = [(WEB_IMG / "praxia-mark.png", MARK),
             (WEB_IMG / "praxia-logo-full.png", LOGO_FULL),
             (WEB_IMG / "course-factory.jpg", PRODUCTS_IMG["course_factory"]),
             (WEB_IMG / "automation-sprint.jpg", PRODUCTS_IMG["automation_sprint"]),
             (WEB_IMG / "masterclass.jpg", PRODUCTS_IMG["ai_trainings"])]
    for src, dst in pairs:
        if src.exists() and not dst.exists():
            shutil.copy(src, dst)


def _capture_site(pg) -> int:
    n = 0
    try:
        pg.goto((WEB_DIR / "index.html").as_uri(), wait_until="networkidle")
        pg.wait_for_timeout(1200)
        for sel, name in [(".hero", "site_hero"), ("#products .product:nth-of-type(1)", "site_prod1"),
                          ("#products .product:nth-of-type(2)", "site_prod2"),
                          ("#products .product:nth-of-type(3)", "site_prod3"),
                          ("#process", "site_process")]:
            try:
                el = pg.locator(sel).first
                el.scroll_into_view_if_needed(timeout=3000)
                pg.wait_for_timeout(500)
                el.screenshot(path=str(SHOTS_DIR / f"{name}.png"))
                n += 1
            except Exception:
                continue
        for page, name in [("about.html", "site_about"), ("contact.html", "site_contact")]:
            try:
                pg.goto((WEB_DIR / page).as_uri(), wait_until="networkidle")
                pg.wait_for_timeout(900)
                pg.screenshot(path=str(SHOTS_DIR / f"{name}.png"))
                n += 1
            except Exception:
                continue
    except Exception as e:  # noqa: BLE001
        log.warning("site capture failed: %s", e)
    return n


def _capture_app(pg) -> int:
    """Best-effort screenshots of the running Course Factory app (localhost:5183)."""
    n = 0
    try:
        pg.goto("http://localhost:5183", wait_until="networkidle", timeout=8000)
        pg.wait_for_timeout(1500)
        try:
            pg.fill('input[placeholder="Your name"]', "Praxia")
            pg.get_by_role("button", name="Claim").first.click(timeout=2500)
            pg.wait_for_timeout(1500)
        except Exception:
            pass
        try:
            pg.locator("button.btn-primary").first.click(timeout=2500)
            pg.wait_for_timeout(1500)
        except Exception:
            pass
        pg.screenshot(path=str(SHOTS_DIR / "app_studio.png"))
        n += 1
    except Exception as e:  # noqa: BLE001
        log.warning("app capture skipped: %s", e)
    return n


def capture_shots(force: bool = False) -> int:
    """Capture site + app screenshots once (cached). Returns total shots available."""
    ensure_assets()
    existing = list(SHOTS_DIR.glob("*.png"))
    if existing and not force:
        return len(existing)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
            pg = ctx.new_page()
            _capture_site(pg)
            _capture_app(pg)
            b.close()
    except Exception as e:  # noqa: BLE001
        log.warning("capture_shots failed: %s", e)
    return len(list(SHOTS_DIR.glob("*.png")))


def product_shots(product: str | None = None) -> list[str]:
    """Real footage for product beats, best first: the actual app UI, then product sections, then
    hero/process. About + Contact are excluded (About reveals sensitive copy; Contact is just a form)."""
    order = ["app_studio", "site_prod1", "site_prod2", "site_prod3", "site_hero", "site_process"]
    rank = {name: i for i, name in enumerate(order)}
    shots = [p for p in SHOTS_DIR.glob("*.png") if p.stem in rank]
    shots.sort(key=lambda p: rank.get(p.stem, 99))
    if not shots:  # fallback to whatever exists if names differ
        shots = sorted(SHOTS_DIR.glob("*.png"))
    return [str(s) for s in shots]
