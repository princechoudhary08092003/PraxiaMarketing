"""Pexels (free) real-photo fetcher. Used to blend genuine photography with AI visuals so the
feed feels human, not obviously generated. Downloads to a caller-supplied path; the caller deletes
it after the reel is posted (nothing is kept)."""
from __future__ import annotations

import logging
import random

import httpx

from .config import get_settings

log = logging.getLogger("praxia.pexels")
API = "https://api.pexels.com/v1/search"


def fetch_photo(query: str, out_path: str, orientation: str = "portrait") -> bool:
    """Download one relevant real photo for `query` to out_path. Returns True on success."""
    s = get_settings()
    if not s.pexels_ready:
        return False
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(API, headers={"Authorization": s.pexels_key},
                      params={"query": query, "orientation": orientation,
                              "per_page": 15, "size": "large"})
            r.raise_for_status()
            photos = r.json().get("photos") or []
            if not photos:
                return False
            pick = random.choice(photos[:10])  # noqa: S311 (variety, not security)
            src = pick.get("src", {})
            url = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
            if not url:
                return False
            img = c.get(url, timeout=45)
            img.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(img.content)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("pexels fetch failed for %r: %s", query, e)
        return False
