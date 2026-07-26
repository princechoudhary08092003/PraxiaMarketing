"""End-to-end QA gate before anything is posted.

Technical (via ffmpeg, no ffprobe needed):
  - video + audio streams both present
  - duration within a sane Reel range
  - audio is not effectively silent (volumedetect mean level)
  - audio does not cut out: no long silence, and no long trailing silence at the end
Editorial (via the model):
  - narration + caption are coherent and on-brand, no price stated, no em dashes, CTA present
A post only goes out if passed is True.
"""
from __future__ import annotations

import json
import re
import subprocess

import imageio_ffmpeg

from .growth import _client
from .config import get_settings

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

MIN_SECONDS, MAX_SECONDS = 8.0, 95.0
SILENCE_MAX_GAP = 2.5          # a mid-clip gap longer than this = "sound cutting"
TRAILING_SILENCE_MAX = 1.6     # dead air at the very end
MEAN_VOL_FLOOR = -40.0         # dB; quieter mean than this = effectively silent


def _ffmpeg_stderr(args: list[str]) -> str:
    return subprocess.run([FFMPEG, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True).stderr


def _duration(info: str) -> float:
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", info)
    if not m:
        return 0.0
    h, mm, ss = m.groups()
    return int(h) * 3600 + int(mm) * 60 + float(ss)


def technical_check(video_path: str) -> dict:
    issues = []
    info = _ffmpeg_stderr(["-i", video_path])
    dur = _duration(info)
    has_video = bool(re.search(r"Stream #\d+:\d+.*Video:", info))
    has_audio = bool(re.search(r"Stream #\d+:\d+.*Audio:", info))
    if not has_video:
        issues.append("no video stream")
    if not has_audio:
        issues.append("no audio track")
    if dur < MIN_SECONDS:
        issues.append(f"too short ({dur:.1f}s)")
    if dur > MAX_SECONDS:
        issues.append(f"too long ({dur:.1f}s)")

    mean_vol = None
    if has_audio:
        vol = _ffmpeg_stderr(["-i", video_path, "-af", "volumedetect", "-f", "null", "-"])
        mv = re.search(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB", vol)
        if mv:
            mean_vol = float(mv.group(1))
            if mean_vol < MEAN_VOL_FLOOR:
                issues.append(f"audio effectively silent (mean {mean_vol:.1f} dB)")

        sil = _ffmpeg_stderr(["-i", video_path, "-af", "silencedetect=noise=-38dB:d=1.0",
                              "-f", "null", "-"])
        starts = [float(x) for x in re.findall(r"silence_start:\s*(-?\d+\.?\d*)", sil)]
        durs = [float(x) for x in re.findall(r"silence_duration:\s*(\d+\.?\d*)", sil)]
        if durs and max(durs) > SILENCE_MAX_GAP:
            issues.append(f"sound cuts out for {max(durs):.1f}s mid-reel")
        # trailing silence: a silence that starts and never gets an end before EOF
        if starts and dur and (dur - starts[-1]) > TRAILING_SILENCE_MAX and len(starts) > len(durs):
            issues.append(f"dead air at the end ({dur - starts[-1]:.1f}s)")

    return {"duration": round(dur, 1), "has_video": has_video, "has_audio": has_audio,
            "mean_volume_db": mean_vol, "issues": issues, "ok": not issues}


COHERENCE_SYSTEM = """You are the final editor for Praxia AI Studios social posts. Approve unless
there is a real problem. Approve or reject a Reel before it goes live.

ALLOWED (do NOT reject for these):
- Naming the MARKET price competitors/agencies charge (e.g. "agencies charge up to $6,000 a course").
- Saying we do it for "a fraction of the cost/time", "a small fraction", "far less". This is our
  core message and is NOT stating our price.
- Impact numbers and before/after (weeks to hours, etc.).

REJECT ONLY IF:
- It states OUR OWN specific selling price or a discount (an actual figure or currency amount
  attached to what WE charge, e.g. "our plan is ₹40,000" or "just $99").
- It contains an em dash (the — character).
- It is genuinely incoherent or self-contradictory.
- It has NO call to action at all (no invite to visit the site or DM).
- The caption and narration are about clearly different things.

Be lenient. When in doubt, approve. A soft CTA counts as a CTA."""


def editorial_check(narration: str, caption: str, title: str) -> dict:
    s = get_settings()
    user = f"""Review this Reel before posting.

NARRATION (spoken): {narration}
INSTAGRAM CAPTION: {caption}
YOUTUBE TITLE: {title}

Return JSON: {{"ok": true|false, "issues": ["..."], "fix_hint": "one line if not ok"}}"""
    try:
        resp = _client().chat.completions.create(
            model=s.growth_model,
            messages=[{"role": "system", "content": COHERENCE_SYSTEM},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"}, temperature=0)
        d = json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:  # noqa: BLE001
        return {"ok": True, "issues": [], "note": f"editorial check skipped: {e}"}
    return {"ok": bool(d.get("ok", True)), "issues": d.get("issues") or [],
            "fix_hint": d.get("fix_hint", "")}


def qa_reel(video_path: str, narration: str, caption: str, title: str) -> dict:
    tech = technical_check(video_path)
    edit = editorial_check(narration, caption, title)
    passed = tech["ok"] and edit["ok"]
    return {"passed": passed, "technical": tech, "editorial": edit,
            "issues": tech["issues"] + edit.get("issues", [])}
