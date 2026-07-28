"""Meme-hook engine. Pulls REAL viral meme templates (Imgflip's public library, no auth) and captions
them with top/bottom impact text written to set up the automation punchline. A different template is
used each day (variety tracked by the caller). This is the standard meme-maker approach; note that
"today's #1 trending in India" is not exposed by any API, so we rotate the viral library instead.
"""
from __future__ import annotations

import logging
from pathlib import Path

import json
import time

import httpx
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("praxia.memes")
GET_MEMES = "https://api.imgflip.com/get_memes"
CACHE_FILE = Path(__file__).resolve().parent / "static" / "brand" / "meme_templates.json"
# Drop your own meme template images here (jpg/png) to work even when imgflip is blocked.
LOCAL_DIR = Path(__file__).resolve().parent / "static" / "brand" / "memes"


def _local_templates() -> list[dict]:
    if not LOCAL_DIR.exists():
        return []
    out = []
    for f in sorted(LOCAL_DIR.glob("*")):
        if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            out.append({"id": f.stem, "name": f.stem, "url": str(f)})
    return out
IMPACT = r"C:\Windows\Fonts\impact.ttf"
ARIALBD = r"C:\Windows\Fonts\arialbd.ttf"

# Popular templates that read well with plain TOP / BOTTOM impact captions (avoids the multi-box
# ones like Drake/Distracted Boyfriend that need special placement).
TOP_BOTTOM_FRIENDLY = {
    "Waiting Skeleton", "Bernie I Am Once Again Asking For Your Support", "Disaster Girl",
    "One Does Not Simply", "Batman Slapping Robin", "Ancient Aliens", "Futurama Fry",
    "The Rock Driving", "Roll Safe Think About It", "Success Kid", "Hide the Pain Harold",
    "Leonardo Dicaprio Cheers", "Sad Pablo Escobar", "Grandma Finds The Internet",
    "Oprah You Get A", "Mugatu So Hot Right Now", "Yao Ming", "First World Problems",
    "Hard To Swallow Pills", "Buff Doge vs. Cheems", "Two Buttons", "Left Exit 12 Off Ramp",
    "Monkey Puppet", "This Is Fine", "Panik Kalm Panik",
}

_cache: list[dict] | None = None


def templates() -> list[dict]:
    global _cache
    if _cache:
        return _cache
    # try the API a few times (transient resets happen)
    for attempt in range(3):
        try:
            r = httpx.get(GET_MEMES, timeout=20)
            memes = (r.json() or {}).get("data", {}).get("memes", [])
            friendly = [m for m in memes if m["name"] in TOP_BOTTOM_FRIENDLY]
            _cache = friendly or memes[:20]
            if _cache:
                try:
                    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    CACHE_FILE.write_text(json.dumps(_cache), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
                return _cache
        except Exception as e:  # noqa: BLE001
            log.warning("imgflip fetch failed (try %s): %s", attempt + 1, e)
            time.sleep(1.5)
    # fall back to the on-disk cache from a previous successful fetch
    if CACHE_FILE.exists():
        try:
            _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            log.info("using cached meme templates (%s)", len(_cache))
            if _cache:
                return _cache
        except Exception:  # noqa: BLE001
            pass
    # last resort: local meme images the user dropped in static/brand/memes
    local = _local_templates()
    if local:
        log.info("using %s local meme templates", len(local))
        _cache = local
    return _cache or []


def pick_template(used_ids: set[str] | None = None, seed: int = 0) -> dict | None:
    ts = templates()
    if not ts:
        return None
    used = used_ids or set()
    fresh = [t for t in ts if t["id"] not in used] or ts
    return fresh[seed % len(fresh)]


def _fit_font(draw, text, font_path, max_w, start=96, min_size=44):
    size = start
    while size > min_size:
        f = ImageFont.truetype(font_path, size)
        # wrap to lines that fit
        words, lines, cur = text.split(), [], ""
        for w in words:
            if draw.textlength((cur + " " + w).strip(), font=f) <= max_w:
                cur = (cur + " " + w).strip()
            else:
                lines.append(cur); cur = w
        if cur:
            lines.append(cur)
        if len(lines) <= 3:
            return f, lines
        size -= 6
    f = ImageFont.truetype(font_path, min_size)
    return f, [text]


def _draw_impact(img: Image.Image, text: str, top: bool) -> None:
    if not text:
        return
    d = ImageDraw.Draw(img)
    W, Hh = img.size
    font_path = IMPACT if Path(IMPACT).exists() else ARIALBD
    f, lines = _fit_font(d, text.upper(), font_path, W - 40, start=int(W * 0.11))
    lh = (f.size + 8)
    block = lh * len(lines)
    y = 14 if top else Hh - block - 18
    for ln in lines:
        lw = d.textlength(ln, font=f)
        x = (W - lw) / 2
        # thick black outline
        for dx in (-3, -2, 0, 2, 3):
            for dy in (-3, -2, 0, 2, 3):
                d.text((x + dx, y + dy), ln, font=f, fill=(0, 0, 0))
        d.text((x, y), ln, font=f, fill=(255, 255, 255))
        y += lh


def render_meme(top: str, bottom: str, out_path: str, template: dict | None = None,
                used_ids: set[str] | None = None, seed: int = 0) -> dict:
    """Caption a real viral template with top/bottom text. Returns {ok, template_id, template_name, path}."""
    t = template or pick_template(used_ids, seed)
    if not t:
        return {"ok": False, "error": "No meme templates available (imgflip unreachable)."}
    try:
        src = t["url"]
        if Path(src).exists():                       # local template image
            img = Image.open(src).convert("RGB")
        else:                                        # imgflip URL
            raw = httpx.get(src, timeout=25).content
            Path(out_path + ".src").write_bytes(raw)
            img = Image.open(out_path + ".src").convert("RGB")
        _draw_impact(img, top, top=True)
        _draw_impact(img, bottom, top=False)
        img.save(out_path, "PNG")
        Path(out_path + ".src").unlink(missing_ok=True)
        return {"ok": True, "template_id": t["id"], "template_name": t["name"], "path": out_path}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
