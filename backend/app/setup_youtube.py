"""One-shot YouTube refresh-token grabber.

Uses your YT_CLIENT_ID + YT_CLIENT_SECRET (already in backend/.env) to run the installed-app OAuth
flow: it opens your browser, you approve access to your channel once, and it writes YT_REFRESH_TOKEN
back into backend/.env. Run:  python -m app.setup_youtube
"""
from __future__ import annotations

import http.server
import socketserver
import sys
import threading
import urllib.parse
import webbrowser

import httpx

from .config import get_settings
from .setup_ig import _write_env

SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
_code = {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        q = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(q)
        _code["code"] = (params.get("code") or [None])[0]
        _code["error"] = (params.get("error") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        msg = ("Praxia: YouTube connected. You can close this tab and return to the app."
               if _code.get("code") else "Authorization failed or was cancelled.")
        self.wfile.write(f"<html><body style='font-family:sans-serif;background:#0C0B08;color:#E4CB87;"
                         f"padding:60px;text-align:center'><h2>{msg}</h2></body></html>".encode())

    def log_message(self, *a):  # silence
        return


def _exchange_code(s, code: str, redirect: str) -> int:
    tok = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code, "client_id": s.yt_client_id, "client_secret": s.yt_client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code"}, timeout=30)
    if tok.status_code != 200 or not tok.json().get("refresh_token"):
        print("Token exchange failed:", tok.text[:400])
        return 1
    _write_env({"YT_REFRESH_TOKEN": tok.json()["refresh_token"]})
    print("Done. Wrote YT_REFRESH_TOKEN to backend/.env.")
    return 0


def main() -> int:
    import os
    s = get_settings()
    if not (s.yt_client_id and s.yt_client_secret):
        print("Missing YT_CLIENT_ID / YT_CLIENT_SECRET in backend/.env.")
        return 1
    port = 8721
    redirect = f"http://localhost:{port}/"

    # Deterministic paste mode: give the code (or the full redirected URL) via YT_AUTH_CODE.
    raw = os.getenv("YT_AUTH_CODE", "").strip()
    if raw:
        if "code=" in raw:
            raw = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get("code", [""])[0]
        return _exchange_code(s, raw, redirect)
    auth = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": s.yt_client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "true"})

    httpd = socketserver.TCPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print("\nOpening your browser to authorize YouTube...")
    print("If it does not open, paste this URL into your browser:\n" + auth + "\n")
    print("NOTE: Google will warn 'Google hasn't verified this app'. Click 'Advanced' -> "
          "'Go to Praxia (unsafe)' -> then Allow. It is your own app, this is expected.\n")
    try:
        webbrowser.open(auth)
    except Exception:
        pass

    print("Waiting for you to approve in the browser...")
    import time
    for _ in range(300):  # up to 5 minutes
        if _code.get("code") or _code.get("error"):
            break
        time.sleep(1)
    httpd.shutdown()

    if _code.get("error") or not _code.get("code"):
        print("Did not get an authorization code:", _code.get("error") or "timed out")
        return 1
    tok = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": _code["code"], "client_id": s.yt_client_id, "client_secret": s.yt_client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code"}, timeout=30)
    if tok.status_code != 200 or not tok.json().get("refresh_token"):
        print("Token exchange failed:", tok.text[:400])
        return 1
    _write_env({"YT_REFRESH_TOKEN": tok.json()["refresh_token"]})
    print("\nDone. Wrote YT_REFRESH_TOKEN to backend/.env. Restart the app; YouTube is connected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
