"""Throwaway pass-through host (Cloudinary). Instagram can only ingest media from a public URL, so
the reel/image is uploaded here for the ~60s publish window, then deleted. Nothing is retained:
call upload() -> publish to Instagram -> destroy(). YouTube needs no host (direct file upload)."""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import httpx

from .config import get_settings

log = logging.getLogger("praxia.media")


def _sign(params: dict, secret: str) -> str:
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha1((to_sign + secret).encode()).hexdigest()  # noqa: S324 (Cloudinary spec)


def upload(local_path: str, resource_type: str = "video") -> dict:
    """Upload a local file; return {ok, url, public_id, resource_type}."""
    s = get_settings()
    if not s.cloudinary_ready:
        return {"ok": False, "error": "Cloudinary not configured (throwaway host for IG)."}
    ts = int(time.time())
    public_id = f"praxia_tmp/{Path(local_path).stem}_{ts}"
    sign_params = {"public_id": public_id, "timestamp": ts}
    signature = _sign(sign_params, s.cloudinary_secret)
    url = f"https://api.cloudinary.com/v1_1/{s.cloudinary_cloud}/{resource_type}/upload"
    try:
        with open(local_path, "rb") as f:
            with httpx.Client(timeout=180) as c:
                r = c.post(url, data={"public_id": public_id, "timestamp": ts,
                                      "api_key": s.cloudinary_key, "signature": signature},
                           files={"file": (Path(local_path).name, f)})
        r.raise_for_status()
        j = r.json()
        return {"ok": True, "url": j.get("secure_url"), "public_id": j.get("public_id"),
                "resource_type": resource_type}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"Cloudinary upload: {e.response.text[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def destroy(public_id: str, resource_type: str = "video") -> bool:
    """Delete the throwaway asset so no copy is kept in the cloud."""
    s = get_settings()
    if not (s.cloudinary_ready and public_id):
        return False
    ts = int(time.time())
    signature = _sign({"public_id": public_id, "timestamp": ts}, s.cloudinary_secret)
    url = f"https://api.cloudinary.com/v1_1/{s.cloudinary_cloud}/{resource_type}/destroy"
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(url, data={"public_id": public_id, "timestamp": ts,
                                  "api_key": s.cloudinary_key, "signature": signature})
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001
        log.warning("cloudinary destroy failed: %s", e)
        return False
