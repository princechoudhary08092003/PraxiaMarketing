"""Long-form YouTube demo builder (1920x1080, 3-5 min). A guided product walkthrough: title card ->
real app/site footage with narration + lower-third captions -> impact -> CTA card. Reuses the reel
engine's low-level helpers; layout is landscape and built for YouTube search discovery.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import brand, pexels, reel
from .config import get_settings

log = logging.getLogger("praxia.demo")
FFMPEG = reel.FFMPEG
W, H, FPS = 1920, 1080, 30
OB, GOLD, GOLDL, INK, BODY = reel.OB, reel.GOLD, reel.GOLDL, reel.INK, reel.BODY
FB, FR = reel.FONT_BOLD, reel.FONT_REG
AI_IMAGE_CAP = 1


def _bg() -> Image.Image:
    bg = Image.new("RGB", (W, H), OB)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W // 2 - 700, -520, W // 2 + 700, 620], fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(200))
    return Image.composite(Image.new("RGB", (W, H), GOLD), bg, glow.point(lambda x: int(x * 0.30)))


def _wm(base: Image.Image) -> None:
    try:
        if brand.MARK.exists():
            m = Image.open(brand.MARK).convert("RGBA")
            mw = 60; m = m.resize((mw, int(m.size[1] * mw / m.size[0])), Image.LANCZOS)
            base.paste(m, (58, 52), m)
        d = ImageDraw.Draw(base)
        d.text((128, 60), "PRAXIA", font=reel._font(FB, 28), fill=INK)
        d.text((130, 92), "AI STUDIOS", font=reel._font(FB, 12), fill=GOLD)
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


def _title_card(dst: str, title: str, sub: str = "") -> None:
    bg = _bg(); d = ImageDraw.Draw(bg)
    d.text((150, H * 0.30), "PRAXIA AI STUDIOS", font=reel._font(FB, 26), fill=GOLD)
    hf = reel._font(FB, 96); yy = H * 0.36
    for ln in _wrap(d, title.upper(), hf, W - 320)[:3]:
        d.text((150, yy), ln, font=hf, fill=INK); yy += 108
    if sub:
        for ln in _wrap(d, sub, reel._font(FR, 40), W - 340)[:2]:
            d.text((152, yy + 20), ln, font=reel._font(FR, 40), fill=BODY); yy += 52
    _wm(bg); bg.save(dst, "PNG")


def _product(dst: str, shot: str, label: str) -> None:
    bg = _bg()
    im = Image.open(shot).convert("RGB")
    tw = 1500; th = int(im.size[1] * tw / im.size[0])
    if th > 820:
        th = 820; tw = int(im.size[0] * th / im.size[1])
    im = im.resize((tw, th), Image.LANCZOS)
    framed = reel._round(im, 22)
    bd = Image.new("RGBA", (tw + 4, th + 4), (0, 0, 0, 0))
    ImageDraw.Draw(bd).rounded_rectangle([0, 0, tw + 3, th + 3], 24, outline=GOLD + (170,), width=2)
    x = (W - tw) // 2; y = int(H * 0.20)
    bg.paste(framed, (x, y), framed); bg.paste(bd, (x - 2, y - 2), bd)
    d = ImageDraw.Draw(bg); lab = (label or "PRAXIA").upper()[:48]
    d.text(((W - d.textlength(lab, font=reel._font(FB, 30))) / 2, y - 66), lab,
           font=reel._font(FB, 30), fill=GOLDL)
    _wm(bg); bg.save(dst, "PNG")


def _photo(dst: str, src: str) -> None:
    im = Image.open(src).convert("RGB")
    sw, sh = im.size; scale = max(W / sw, H / sh)
    im = im.resize((int(sw * scale + .5), int(sh * scale + .5)), Image.LANCZOS)
    left, top = (im.size[0] - W) // 2, (im.size[1] - H) // 2
    im = im.crop((left, top, left + W, top + H))
    grad = Image.new("L", (1, H), 0)
    for yy in range(H):
        grad.putpixel((0, yy), min(int(180 * max(0, (yy - H * 0.4) / (H * 0.6))), 185))
    im = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), im, grad.resize((W, H)))
    im = Image.blend(im, Image.new("RGB", (W, H), OB), 0.12)
    _wm(im); im.save(dst, "PNG")


def _cta(dst: str, url: str) -> None:
    bg = _bg(); d = ImageDraw.Draw(bg)
    if brand.LOGO_FULL.exists():
        lg = Image.open(brand.LOGO_FULL).convert("RGBA")
        lw = 380; lg = lg.resize((lw, int(lg.size[1] * lw / lg.size[0])), Image.LANCZOS)
        bg.paste(lg, ((W - lw) // 2, int(H * 0.16)), lg)
    hf = reel._font(FB, 70)
    txt = "Book a demo"
    d.text(((W - d.textlength(txt, font=hf)) / 2, H * 0.60), txt, font=hf, fill=INK)
    uf = reel._font(FB, 52); uw = d.textlength(url, font=uf)
    px, py = (W - uw) / 2 - 40, H * 0.72
    d.rounded_rectangle([px, py, px + uw + 80, py + 96], 48, fill=GOLD)
    d.text(((W - uw) / 2, py + 22), url, font=uf, fill=OB)
    _wm(bg); bg.save(dst, "PNG")


def _plan(segs, product, shots):
    last = len(segs) - 1
    plan, ai, si = [], 0, 0
    for i, seg in enumerate(segs):
        vt = (seg.get("visual_type") or "product").lower()
        label = seg.get("on_screen") or reel.brand_label(product)
        if i == 0:
            plan.append(("title", seg.get("on_screen") or seg.get("narration", "")[:60]))
        elif i == last:
            plan.append(("cta", None))
        elif vt == "product" and shots:
            plan.append(("product", (shots[si % len(shots)], label))); si += 1
        elif vt == "ai" and ai < AI_IMAGE_CAP:
            plan.append(("ai", seg.get("visual_query") or label)); ai += 1
        else:
            plan.append(("stock", seg.get("visual_query") or label))
    return plan


def _make(kind, arg, dst, url):
    if kind == "title":
        _title_card(dst, arg, "A Praxia AI Studios walkthrough")
    elif kind == "cta":
        _cta(dst, url)
    elif kind == "product":
        _product(dst, arg[0], arg[1])
    elif kind == "ai":
        raw = dst + ".raw"; reel._ai_image(arg, raw); _photo(dst, raw); Path(raw).unlink(missing_ok=True)
    else:
        raw = dst + ".raw"
        if pexels.fetch_photo(arg, raw, "landscape"):
            _photo(dst, raw); Path(raw).unlink(missing_ok=True)
        else:
            _title_card(dst, arg)


def _seg_clip(idx, img, aud, secs, motion, wd):
    dur = round(secs + 0.4, 2); frames = int(dur * FPS); out = f"d{idx}.mp4"
    if motion:
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"zoompan=z='min(zoom+0.0008,1.08)':d={frames}:s={W}x{H}:fps={FPS},setsar=1")
    else:
        vf = f"scale={W}:{H},setsar=1,fps={FPS}"
    reel._run([FFMPEG, "-y", "-loop", "1", "-i", Path(img).name, "-i", Path(aud).name,
               "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a",
               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "160k", "-t", str(dur), out], cwd=wd)
    return out


def _captions(timing, path) -> bool:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap, Arial, 46, &H00FFFFFF, &H00000000, &H64000000, -1, 5, 1, 2, 160, 160, 70, 1

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
        chunks = [words[i:i + 5] for i in range(0, len(words), 5)]
        total = sum(len(" ".join(c)) for c in chunks) or 1
        t = start
        for c in chunks:
            dur = max(0.6, secs * (len(" ".join(c)) / total))
            events.append(f"Dialogue: 0,{reel._ass_time(t)},{reel._ass_time(t + dur)},Cap,,0,0,0,,{esc(' '.join(c))}")
            t += dur
    if not events:
        return False
    Path(path).write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return True


def build_demo(spec: dict, workdir: str) -> dict:
    wd = Path(workdir); wd.mkdir(parents=True, exist_ok=True)
    brand.ensure_assets()
    shots = brand.product_shots()
    product = spec.get("product", "course_factory")
    url = get_settings().website
    segs = [s for s in (spec.get("segments") or []) if (s.get("narration") or "").strip()]
    if not segs:
        raise RuntimeError("Demo script has no sections.")
    plan = _plan(segs, product, shots)

    def _assets(item):
        i, (seg, (kind, arg)) = item
        img = str(wd / f"d{i}.png"); aud = str(wd / f"da{i}.mp3")
        _make(kind, arg, img, url)
        reel.tts((seg.get("narration") or "").strip(), aud)
        return i, img, aud, reel._audio_seconds(aud), kind not in ("title", "cta", "product")

    with ThreadPoolExecutor(max_workers=4) as ex:
        assets = sorted(ex.map(_assets, list(enumerate(zip(segs, plan)))), key=lambda a: a[0])

    clips, total, narration, timing, cursor = [], 0.0, [], [], 0.0
    for (i, img, aud, secs, motion), seg in zip(assets, segs):
        text = (seg.get("narration") or "").strip()
        narration.append(text); timing.append((cursor, secs, text))
        clips.append(_seg_clip(i, img, aud, secs, motion, str(wd)))
        seg_len = round(secs + 0.4, 2); total += seg_len; cursor += seg_len

    (wd / "dlist.txt").write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
    reel._run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", "dlist.txt",
               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "160k", "dbody.mp4"], cwd=str(wd))
    final = "dbody.mp4"
    if _captions(timing, str(wd / "dsubs.ass")):
        try:
            reel._run([FFMPEG, "-y", "-i", "dbody.mp4", "-vf", "ass=dsubs.ass",
                       "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                       "-c:a", "copy", "-movflags", "+faststart", "demo.mp4"], cwd=str(wd))
            final = "demo.mp4"
        except Exception as e:  # noqa: BLE001
            log.warning("demo caption burn failed: %s", e)
    return {"path": str(wd / final), "seconds": round(total, 1), "segments": len(clips),
            "narration": " ".join(narration)}
