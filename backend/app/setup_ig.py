"""One-shot Instagram self-configuration. Works for BOTH connection methods.

Set IG_API in backend/.env:
  IG_API=instagram   -> Instagram Login (NO Facebook Page). Paste FB_APP_SECRET (your app's secret)
                        and IG_ACCESS_TOKEN (the token from Instagram product -> API setup with
                        Instagram login -> Generate token). Run this: it swaps in a ~60-day token
                        and fills IG_USER_ID from your Instagram account.
  IG_API=facebook    -> Facebook Login. Paste FB_APP_ID + FB_APP_SECRET + a short-lived
                        IG_ACCESS_TOKEN (Graph API Explorer). It finds your Page + linked IG.

Run:  python -m app.setup_ig    (never prints the token value)
"""
from __future__ import annotations

import re
import sys

import httpx

from .config import BACKEND_DIR, get_settings

GRAPH_FB = "https://graph.facebook.com/v21.0"
GRAPH_IG = "https://graph.instagram.com"


def _write_env(updates: dict) -> None:
    env = BACKEND_DIR / ".env"
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    for key, val in updates.items():
        line = f"{key}={val}"
        if re.search(rf"(?m)^{key}=.*$", text):
            text = re.sub(rf"(?m)^{key}=.*$", line, text)
        else:
            text = text.rstrip() + "\n" + line + "\n"
    env.write_text(text, encoding="utf-8")


def _instagram_login(s) -> int:
    """Instagram Login path: no Facebook Page needed."""
    if not (s.fb_app_secret and s.ig_access_token):
        print("Need FB_APP_SECRET (your app secret) and IG_ACCESS_TOKEN in backend/.env.")
        return 1
    long_token = s.ig_access_token
    with httpx.Client(timeout=30) as c:
        # short-lived -> long-lived (~60 days). If it's already long-lived this is harmless/fails soft.
        ex = c.get(f"{GRAPH_IG}/access_token", params={
            "grant_type": "ig_exchange_token", "client_secret": s.fb_app_secret,
            "access_token": s.ig_access_token})
        if ex.status_code == 200 and ex.json().get("access_token"):
            long_token = ex.json()["access_token"]
            print("Got a long-lived Instagram token (~60 days).")
        else:
            print("Note: could not exchange for a long-lived token (using the token as-is).")
        me = c.get(f"{GRAPH_IG}/me", params={"fields": "user_id,username", "access_token": long_token})
        if me.status_code != 200:
            print("Could not read your Instagram account:", me.text[:300]); return 1
        j = me.json()
        ig_id = j.get("user_id") or j.get("id")
        if not ig_id:
            print("No Instagram user id returned. Is the token from Instagram Login with the "
                  "content-publish permission?"); return 1
        print(f"Connected Instagram account @{j.get('username','?')} (id {ig_id}).")
    _write_env({"IG_ACCESS_TOKEN": long_token, "IG_USER_ID": ig_id, "IG_API": "instagram"})
    return 0


def _facebook_login(s) -> int:
    """Facebook Login path: IG linked to a Facebook Page."""
    if not (s.fb_app_id and s.fb_app_secret and s.ig_access_token):
        print("Need FB_APP_ID, FB_APP_SECRET, and IG_ACCESS_TOKEN in backend/.env.")
        return 1
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{GRAPH_FB}/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": s.fb_app_id,
            "client_secret": s.fb_app_secret, "fb_exchange_token": s.ig_access_token})
        if r.status_code != 200 or not r.json().get("access_token"):
            print("Token exchange failed:", r.text[:300]); return 1
        long_token = r.json()["access_token"]
        print("Got a long-lived token (~60 days).")
        pages = c.get(f"{GRAPH_FB}/me/accounts",
                      params={"access_token": long_token, "fields": "id,name,instagram_business_account"})
        data = (pages.json() or {}).get("data", [])
        ig_id = None
        for pg in data:
            iba = pg.get("instagram_business_account")
            if iba and iba.get("id"):
                ig_id = iba["id"]; print(f"Found Page '{pg.get('name')}' linked to IG {ig_id}."); break
        if not ig_id:
            print("No Page with a linked Instagram Business account found. Link them first.")
            return 1
    _write_env({"IG_ACCESS_TOKEN": long_token, "IG_USER_ID": ig_id, "IG_API": "facebook"})
    return 0


def main() -> int:
    s = get_settings()
    rc = _facebook_login(s) if s.ig_api == "facebook" else _instagram_login(s)
    if rc == 0:
        print("\nDone. Wrote IG_ACCESS_TOKEN (long-lived) and IG_USER_ID into backend/.env.")
        print("Restart the app; Instagram will show as connected.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
