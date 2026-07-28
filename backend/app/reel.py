"""Vertical Reel builder v3 (1080x1920, H.264 + AAC) — brand-grade, cost-lean.

Storyboard: a designed HOOK card -> value/product beats (REAL product & site screenshots first,
free Pexels photos next, at most ONE AI image) -> a designed OUTRO/CTA card. A persistent Praxia
watermark sits on every frame. Captions are built straight from the SCRIPT text (exact match, no
transcription) and timed per beat. Everything lives in a temp workdir the orchestrator deletes.

Cost controls: >=1 AI image max (AI_IMAGE_CAP), no Whisper, screenshots + stock are free.
"""
from __future__ import annotations

import base64
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import brand, memes, mockups, pexels
from .config import get_settings
from .growth import _client

log = logging.getLogger("praxia.reel")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1080, 1920, 30
OB, GOLD, GOLDL, INK, BODY = (12, 11, 8), (201, 162, 75), (228, 203, 135), (242, 236, 221), (167, 160, 145)
FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf"
FONT_REG = r"C:\Windows\Fonts\arial.ttf"
AI_IMAGE_CAP = 1   # at most this many gpt-image-1 generations per reel (cost control)


def _run(cmd: list[str], cwd: str | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:6])}...\n{r.stderr[-800:]}")


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _audio_seconds(path: str) -> float:
    from moviepy import AudioFileClip
    a = AudioFileClip(path); d = float(a.duration or 0); a.close()
    return d


def tts(text: str, out_path: str) -> None:
    s = get_settings()
    resp = _client().audio.speech.create(model=s.tts_model, voice=s.tts_voice, input=text[:900])
    Path(out_path).write_bytes(resp.content)


# --------------------------------------------------------------- backgrounds --
def _brand_bg() -> Image.Image:
    bg = Image.new("RGB", (W, H), OB)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W // 2 - 520, -420, W // 2 + 520, 620], fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    bg = Image.composite(Image.new("RGB", (W, H), GOLD), bg, glow.point(lambda x: int(x * 0.32)))
    return bg


def _round(im: Image.Image, rad: int) -> Image.Image:
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.size[0], im.size[1]], rad, fill=255)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0)); out.paste(im, (0, 0), mask)
    return out


def _watermark(base: Image.Image) -> None:
    try:
        if brand.MARK.exists():
            m = Image.open(brand.MARK).convert("RGBA")
            mw = 66; mh = int(m.size[1] * mw / m.size[0])
            m = m.resize((mw, mh), Image.LANCZOS); base.paste(m, (52, 60), m)
        d = ImageDraw.Draw(base)
        d.text((130, 72), "PRAXIA", font=_font(FONT_BOLD, 30), fill=INK)
        d.text((132, 106), "AI STUDIOS", font=_font(FONT_BOLD, 13), fill=GOLD)
    except Exception:  # noqa: BLE001
        pass


def _wrap(d, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if d.textlength((cur + " " + w).strip(), font=font) <= maxw:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def _hook_card(dst: str, hook: str) -> None:
    """Designed opening card: eyebrow + big hook line, brand background."""
    bg = _brand_bg(); d = ImageDraw.Draw(bg)
    d.text((W / 2 - d.textlength("PRAXIA AI STUDIOS", font=_font(FONT_BOLD, 24)) / 2, H * 0.30),
           "PRAXIA AI STUDIOS", font=_font(FONT_BOLD, 24), fill=GOLD)
    hf = _font(FONT_BOLD, 92)
    lines = _wrap(d, (hook or "Watch this").upper(), hf, W - 150)[:4]
    yy = H * 0.40
    for ln in lines:
        lw = d.textlength(ln, font=hf)
        d.text(((W - lw) / 2, yy), ln, font=hf, fill=INK); yy += 104
    _watermark(bg); bg.save(dst, "PNG")


def _photo(src: str, dst: str) -> None:
    im = Image.open(src).convert("RGB")
    sw, sh = im.size; scale = max(W / sw, H / sh)
    im = im.resize((int(sw * scale + .5), int(sh * scale + .5)), Image.LANCZOS)
    left, top = (im.size[0] - W) // 2, (im.size[1] - H) // 2
    im = im.crop((left, top, left + W, top + H))
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        grad.putpixel((0, y), min(int(170 * max(0, (y - H * 0.42) / (H * 0.58))), 175))
    im = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), im, grad.resize((W, H)))
    im = Image.blend(im, Image.new("RGB", (W, H), OB), 0.12)
    _watermark(im); im.save(dst, "PNG")


def _product_frame(src: str, dst: str, label: str) -> None:
    bg = _brand_bg()
    shot = Image.open(src).convert("RGB")
    tw = 960; th = min(int(shot.size[1] * tw / shot.size[0]), 1160)
    shot = shot.resize((tw, int(shot.size[1] * tw / shot.size[0])), Image.LANCZOS).crop((0, 0, tw, th))
    framed = _round(shot, 26)
    bd = Image.new("RGBA", (tw + 4, th + 4), (0, 0, 0, 0))
    ImageDraw.Draw(bd).rounded_rectangle([0, 0, tw + 3, th + 3], 28, outline=GOLD + (180,), width=2)
    x = (W - tw) // 2; y = int(H * 0.29)
    bg.paste(framed, (x, y), framed); bg.paste(bd, (x - 2, y - 2), bd)
    d = ImageDraw.Draw(bg); lab = (label or "PRAXIA").upper()[:36]
    d.text(((W - d.textlength(lab, font=_font(FONT_BOLD, 30))) / 2, y - 74), lab,
           font=_font(FONT_BOLD, 30), fill=GOLDL)
    _watermark(bg); bg.save(dst, "PNG")


def _cta_card(dst: str, headline: str, url: str) -> None:
    bg = _brand_bg(); d = ImageDraw.Draw(bg)
    if brand.LOGO_FULL.exists():
        lg = Image.open(brand.LOGO_FULL).convert("RGBA")
        lw = 440; lh = int(lg.size[1] * lw / lg.size[0])
        lg = lg.resize((lw, lh), Image.LANCZOS); bg.paste(lg, ((W - lw) // 2, int(H * 0.24)), lg)
    hf = _font(FONT_BOLD, 64)
    yy = int(H * 0.50)
    for ln in _wrap(d, headline or "Build it with Praxia", hf, W - 170)[:3]:
        d.text(((W - d.textlength(ln, font=hf)) / 2, yy), ln, font=hf, fill=INK); yy += 80
    uf = _font(FONT_BOLD, 46); uw = d.textlength(url, font=uf)
    px, py = (W - uw) / 2 - 36, yy + 44
    d.rounded_rectangle([px, py, px + uw + 72, py + 88], 44, fill=GOLD)
    d.text(((W - uw) / 2, py + 19), url, font=uf, fill=OB)
    sf = _font(FONT_REG, 30); sub = "Book a demo. DM us or visit the site."
    d.text(((W - d.textlength(sub, font=sf)) / 2, py + 124), sub, font=sf, fill=BODY)
    _watermark(bg); bg.save(dst, "PNG")


def _ai_image(prompt: str, out_path: str) -> None:
    s = get_settings()
    styled = (f"{prompt}. Cinematic vertical photograph, deep obsidian near-black background, warm "
              f"gold accent light, premium editorial, high detail. No text, no watermark, no logos.")
    try:
        r = _client().images.generate(model=s.image_model, prompt=styled, size="1024x1536", n=1)
        b64 = r.data[0].b64_json
    except Exception:
        r = _client().images.generate(model="dall-e-3", prompt=styled, size="1024x1792", n=1,
                                       response_format="b64_json")
        b64 = r.data[0].b64_json
    Path(out_path).write_bytes(base64.b64decode(b64))


# ---------------------------------------------------- visual plan (cost-aware) --
def brand_label(product: str) -> str:
    from .growth import PRODUCTS
    return PRODUCTS.get(product, {}).get("name", "Praxia AI Studios")


def _plan_visuals(segs: list[dict], product: str, shots: list[str]) -> list[tuple]:
    """Decide each beat's visual up front, capping AI. Returns [(kind, arg, motion)]."""
    last = len(segs) - 1
    plan, ai_used, si = [], 0, 0
    for i, seg in enumerate(segs):
        vt = (seg.get("visual_type") or "stock").lower()
        label = seg.get("on_screen") or brand_label(product)
        if i == 0:
            plan.append(("hook", seg.get("on_screen") or seg.get("narration", ""), False))
        elif i == last:
            plan.append(("cta", label, False))
        elif vt == "product" and shots:
            plan.append(("product", (shots[si % len(shots)], label), False)); si += 1
        elif vt == "ai" and ai_used < AI_IMAGE_CAP:
            plan.append(("ai", seg.get("visual_query") or label, True)); ai_used += 1
        else:
            plan.append(("stock", seg.get("visual_query") or label, True))
    return plan


def _make_visual(kind: str, arg, dst: str, url: str) -> None:
    if kind == "hook":
        _hook_card(dst, arg)
    elif kind == "cta":
        _cta_card(dst, arg, url)
    elif kind == "product":
        _product_frame(arg[0], dst, arg[1])
    elif kind == "ai":
        raw = dst + ".raw"; _ai_image(arg, raw); _photo(raw, dst); Path(raw).unlink(missing_ok=True)
    else:  # stock (free); fall back to a hook-style brand card if Pexels misses
        raw = dst + ".raw"
        if pexels.fetch_photo(arg, raw, "portrait"):
            _photo(raw, dst); Path(raw).unlink(missing_ok=True)
        else:
            _hook_card(dst, arg)


# ------------------------------------------------------------- captions (ASS) --
def _ass_time(t: float) -> str:
    cs = int(round(t * 100)); h, cs = divmod(cs, 360000); m, cs = divmod(cs, 6000); s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _captions_ass(timing: list[tuple], path: str, primary: str = "&H00FFFFFF") -> bool:
    """Build captions from the SCRIPT text (exact), timed within each beat's speech window.
    timing: [(start_sec, speech_sec, narration_text)]. primary = ASS colour (BGR hex)."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap, Arial, 44, {primary}, &H00000000, &H64000000, -1, 3, 1, 2, 120, 120, 230, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def esc(t):
        return t.replace("\\", "").replace("{", "").replace("}", "").strip()
    events = []
    for start, secs, text in timing:
        words = [w for w in (text or "").split() if w]
        if not words or secs <= 0:
            continue
        chunks = [words[i:i + 2] for i in range(0, len(words), 2)]
        total = sum(len(" ".join(c)) for c in chunks) or 1
        t = start
        for c in chunks:
            dur = max(0.5, secs * (len(" ".join(c)) / total))
            events.append(f"Dialogue: 0,{_ass_time(t)},{_ass_time(t + dur)},Cap,,0,0,0,,{esc(' '.join(c)).upper()}")
            t += dur
    if not events:
        return False
    Path(path).write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return True


# --------------------------------------------------------------- per segment --
def _segment_clip(idx: int, img: str, audio: str, seconds: float, motion: bool, wd: str) -> str:
    dur = round(seconds + 0.35, 2); frames = int(dur * FPS); out = f"seg{idx}.mp4"
    if motion:
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"zoompan=z='min(zoom+0.0011,1.10)':d={frames}:s={W}x{H}:fps={FPS},setsar=1")
    else:
        vf = f"scale={W}:{H},setsar=1,fps={FPS}"
    _run([FFMPEG, "-y", "-loop", "1", "-i", Path(img).name, "-i", Path(audio).name,
          "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "160k", "-t", str(dur), out], cwd=wd)
    return out


# ------------------------------------------------------------------- build ---
def build_reel(spec: dict, workdir: str) -> dict:
    wd = Path(workdir); wd.mkdir(parents=True, exist_ok=True)
    brand.ensure_assets()
    shots = brand.product_shots()
    product = spec.get("product", "course_factory")
    url = get_settings().website

    segs = [s for s in (spec.get("segments") or []) if (s.get("narration") or "").strip()]
    if not segs:
        raise RuntimeError("Reel script has no segments.")
    plan = _plan_visuals(segs, product, shots)

    def _assets(item):
        i, (seg, (kind, arg, motion)) = item
        img = str(wd / f"img{i}.png"); aud = str(wd / f"aud{i}.mp3")
        _make_visual(kind, arg, img, url)
        tts((seg.get("narration") or "").strip(), aud)
        return i, img, aud, _audio_seconds(aud), motion

    with ThreadPoolExecutor(max_workers=4) as ex:
        assets = sorted(ex.map(_assets, list(enumerate(zip(segs, plan)))), key=lambda a: a[0])

    clips, total, narration, timing, cursor = [], 0.0, [], [], 0.0
    for (i, img, aud, secs, motion), seg in zip(assets, segs):
        text = (seg.get("narration") or "").strip()
        narration.append(text)
        timing.append((cursor, secs, text))
        clips.append(_segment_clip(i, img, aud, secs, motion, str(wd)))
        seg_len = round(secs + 0.35, 2); total += seg_len; cursor += seg_len

    (wd / "list.txt").write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
    _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "160k", "body.mp4"], cwd=str(wd))

    final = "body.mp4"
    if _captions_ass(timing, str(wd / "subs.ass")):
        try:
            _run([FFMPEG, "-y", "-i", "body.mp4", "-vf", "ass=subs.ass",
                  "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                  "-c:a", "copy", "-movflags", "+faststart", "reel.mp4"], cwd=str(wd))
            final = "reel.mp4"
        except Exception as e:  # noqa: BLE001
            log.warning("caption burn failed (%s); posting without captions", e)
    return {"path": str(wd / final), "seconds": round(total, 1), "segments": len(clips),
            "narration": " ".join(narration)}


# ==================================================== FACELESS BUILD-REEL (v4) ==
STYLE_CAPTION = {"cinematic": "&H00FFFFFF", "stock": "&H00FFFFFF",
                 "bold_type": "&H0087CBE4", "duotone": "&H00FFFFFF"}  # BGR; gold for bold_type


def _meme_segment(meme: dict, dst: str, used_ids, seed: int) -> dict:
    """Render a real captioned meme centered on black, with a small watermark. Returns meme info."""
    tmp = dst + ".meme.png"
    info = memes.render_meme(meme.get("top", ""), meme.get("bottom", ""), tmp,
                             used_ids=used_ids, seed=seed)
    if not info.get("ok"):
        # network blip / no template: fall back to a bold text hook so the opener is never blank
        hook_txt = (meme.get("top", "") + " " + meme.get("bottom", "")).strip() or "Stop doing this by hand"
        _hook_card(dst, hook_txt)
        return info
    m = Image.open(tmp).convert("RGB")
    tw = W - 40
    th = int(m.size[1] * tw / m.size[0])
    m = m.resize((tw, th), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), (8, 8, 8))
    canvas.paste(m, ((W - tw) // 2, (H - th) // 2))
    Path(tmp).unlink(missing_ok=True)
    _watermark(canvas)
    canvas.save(dst, "PNG")
    return info


def _result_card(dst: str, big: str, label: str) -> None:
    bg = _brand_bg(); d = ImageDraw.Draw(bg)
    nf = _font(FONT_BOLD, 300)
    big = (big or "10x")[:6]
    d.text(((W - d.textlength(big, font=nf)) / 2, H * 0.30), big, font=nf, fill=GOLD)
    lf = _font(FONT_BOLD, 54)
    for i, ln in enumerate(_wrap(d, (label or "faster").upper(), lf, W - 160)[:2]):
        d.text(((W - d.textlength(ln, font=lf)) / 2, H * 0.56 + i * 64), ln, font=lf, fill=INK)
    _watermark(bg); bg.save(dst, "PNG")


def _mockup_frame(spec: dict, dst: str, label: str, wd: str) -> None:
    shot = str(Path(wd) / "mock.png")
    r = mockups.render_mockup(spec, shot)
    if r.get("ok"):
        _product_frame(shot, dst, label)
        Path(shot).unlink(missing_ok=True)
    else:
        _hook_card(dst, label)


def _motion_vf(transition: str, frames: int) -> str:
    base = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
    z = {"zoompunch": "zoompan=z='min(zoom+0.0025,1.20)'",
         "slideleft": "zoompan=z=1.14:x='iw/2-(iw/zoom/2)+(on/%d)*120'" % max(frames, 1),
         "whippan":   "zoompan=z=1.12:y='ih/2-(ih/zoom/2)+(on/%d)*120'" % max(frames, 1),
         "fadeblack": "zoompan=z='min(zoom+0.0009,1.06)'"}.get(transition, "zoompan=z='min(zoom+0.0011,1.10)'")
    return base + z + f":d={frames}:s={W}x{H}:fps={FPS},setsar=1,fade=t=in:st=0:d=0.25"


def _content_clip(idx, img, aud, secs, motion, transition, wd, min_dur=0.0) -> str:
    dur = round(max(secs + 0.35, min_dur), 2); frames = int(dur * FPS); out = f"seg{idx}.mp4"
    if motion:
        vf = _motion_vf(transition, frames)
    else:
        vf = f"scale={W}:{H},setsar=1,fps={FPS},fade=t=in:st=0:d=0.25"
    _run([FFMPEG, "-y", "-loop", "1", "-i", Path(img).name, "-i", Path(aud).name,
          "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "160k", "-t", str(dur), out], cwd=wd)
    return out


def build_content_reel(spec: dict, workdir: str, used_meme_ids=None, seed: int = 0) -> dict:
    """Faceless build reel: meme hook -> problem -> mockup build -> result -> CTA.
    Returns path/seconds/narration + meme_id used (for variety tracking)."""
    wd = Path(workdir); wd.mkdir(parents=True, exist_ok=True)
    brand.ensure_assets()
    style = spec.get("style", "cinematic")
    transition = spec.get("transition", "fadeblack")
    url = get_settings().website
    segs = spec.get("segments") or []
    meme_info = {"template_id": ""}

    def _visual_for(i, seg):
        role = seg.get("role", "")
        dst = str(wd / f"img{i}.png")
        if role == "hook":
            info = _meme_segment(spec.get("meme", {}), dst, used_meme_ids, seed)
            meme_info.update(info)
            return dst, False
        if role == "build":
            _mockup_frame(spec.get("mockup", {}), dst, spec.get("mockup", {}).get("title", "Automation"), str(wd))
            return dst, False
        if role == "result":
            big = _first_number(seg.get("on_screen", "") + " " + seg.get("narration", "")) or "10x"
            _result_card(dst, big, seg.get("on_screen", "faster"))
            return dst, False
        if role == "cta":
            _cta_card(dst, seg.get("on_screen") or PRODUCT_TAG(spec.get("product")), url)
            return dst, False
        # problem beat: visual per style
        q = seg.get("on_screen") or spec.get("topic") or "office work"
        raw = dst + ".raw"
        if style == "stock" and pexels.fetch_photo(q, raw, "portrait"):
            _photo(raw, dst); Path(raw).unlink(missing_ok=True)
        elif style == "bold_type":
            _hook_card(dst, seg.get("on_screen") or "Doing it by hand")
        else:
            _ai_image(q + " frustrated office worker, moody", raw); _photo(raw, dst); Path(raw).unlink(missing_ok=True)
        return dst, True

    def _assets(item):
        i, seg = item
        img, motion = _visual_for(i, seg)
        aud = str(wd / f"aud{i}.mp3")
        tts((seg.get("narration") or "").strip(), aud)
        return i, img, aud, _audio_seconds(aud), motion

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        assets = sorted(ex.map(_assets, list(enumerate(segs))), key=lambda a: a[0])

    clips, total, narration, timing, cursor = [], 0.0, [], [], 0.0
    for (i, img, aud, secs, motion), seg in zip(assets, segs):
        text = (seg.get("narration") or "").strip()
        narration.append(text)
        is_hook = seg.get("role") == "hook"
        min_dur = 4.2 if is_hook else 0.0   # let the meme breathe so people can read it
        # no caption over the meme (it already has big text)
        if not is_hook:
            timing.append((cursor, secs, text))
        clips.append(_content_clip(i, img, aud, secs, motion, transition, str(wd), min_dur=min_dur))
        seg_len = round(max(secs + 0.35, min_dur), 2); total += seg_len; cursor += seg_len

    (wd / "list.txt").write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
    _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "160k", "body.mp4"], cwd=str(wd))

    final = "body.mp4"
    color = STYLE_CAPTION.get(style, "&H00FFFFFF")
    if _captions_ass(timing, str(wd / "subs.ass"), primary=color):
        try:
            _run([FFMPEG, "-y", "-i", "body.mp4", "-vf", "ass=subs.ass",
                  "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                  "-c:a", "copy", "-movflags", "+faststart", "reel.mp4"], cwd=str(wd))
            final = "reel.mp4"
        except Exception as e:  # noqa: BLE001
            log.warning("caption burn failed (%s)", e)
    return {"path": str(wd / final), "seconds": round(total, 1), "segments": len(clips),
            "narration": " ".join(narration), "meme_id": meme_info.get("template_id", ""),
            "meme_name": meme_info.get("template_name", "")}


def _first_number(text: str) -> str:
    import re
    m = re.search(r"(\d+\.?\d*\s*(?:x|%|s|hrs|hours|min|k)?)", text or "", re.I)
    return (m.group(1).replace(" ", "") if m else "")


def PRODUCT_TAG(product: str) -> str:
    from .growth import PRODUCTS
    return PRODUCTS.get(product, {}).get("tagline", "Automate it with Praxia")


# ============================================================ STATIC FEED CARD ==
def build_static_card(spec: dict, out_path: str) -> None:
    """Minimal 1080x1350 (4:5) product feed image: mark + eyebrow + big headline + subline + url.
    Deliberately little text so nothing floods."""
    CW, CH = 1080, 1350
    bg = Image.new("RGB", (CW, CH), OB)
    glow = Image.new("L", (CW, CH), 0)
    ImageDraw.Draw(glow).ellipse([CW // 2 - 520, -360, CW // 2 + 520, 560], fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(170))
    bg = Image.composite(Image.new("RGB", (CW, CH), GOLD), bg, glow.point(lambda x: int(x * 0.30)))
    d = ImageDraw.Draw(bg)
    # mark + wordmark top-left
    try:
        if brand.MARK.exists():
            m = Image.open(brand.MARK).convert("RGBA"); mw = 74
            m = m.resize((mw, int(m.size[1] * mw / m.size[0])), Image.LANCZOS)
            bg.paste(m, (64, 66), m)
        d.text((150, 78), "PRAXIA", font=_font(FONT_BOLD, 34), fill=INK)
        d.text((152, 118), "AI STUDIOS", font=_font(FONT_BOLD, 15), fill=GOLD)
    except Exception:  # noqa: BLE001
        pass
    eyebrow = (spec.get("product_name") or "PRAXIA").upper()
    d.text((66, CH * 0.34), eyebrow, font=_font(FONT_BOLD, 26), fill=GOLDL)
    # headline (big, wrapped, max 3 lines)
    hf = _font(FONT_BOLD, 92)
    yy = CH * 0.40
    for ln in _wrap(d, (spec.get("headline") or "").upper(), hf, CW - 130)[:3]:
        d.text((66, yy), ln, font=hf, fill=INK); yy += 100
    # subline
    if spec.get("subline"):
        sf = _font(FONT_REG, 40)
        for ln in _wrap(d, spec["subline"], sf, CW - 160)[:2]:
            d.text((66, yy + 20), ln, font=sf, fill=BODY); yy += 52
    # url pill bottom-left
    url = get_settings().website
    uf = _font(FONT_BOLD, 40); uw = d.textlength(url, font=uf)
    d.rounded_rectangle([66, CH - 150, 66 + uw + 60, CH - 80], 38, fill=GOLD)
    d.text((96, CH - 137), url, font=uf, fill=OB)
    bg.save(out_path, "PNG")
