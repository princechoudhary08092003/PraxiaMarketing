"""Convincing automation mockups. Renders a pixel-perfect fake-but-realistic tool/dashboard for a
given problem (via generated HTML + Playwright) so a reel can SHOW "what the automation built"
without shipping real code. On-brand (obsidian + gold). Each mockup's content differs per problem.
"""
from __future__ import annotations

import html
import logging
from pathlib import Path

log = logging.getLogger("praxia.mockups")


def _esc(s) -> str:
    return html.escape(str(s))


def _page(spec: dict) -> str:
    title = _esc(spec.get("title", "Automation"))
    subtitle = _esc(spec.get("subtitle", ""))
    accent = spec.get("accent", "#C9A24B")
    kpis = spec.get("kpis", [])[:4]
    rows = spec.get("rows", [])[:6]
    cols = spec.get("cols", ["Item", "Status", "Time"])
    badge = _esc(spec.get("badge", "AUTOMATED"))
    kpi_html = "".join(
        f'<div class="kpi"><div class="v">{_esc(k.get("value",""))}</div>'
        f'<div class="l">{_esc(k.get("label",""))}</div></div>' for k in kpis)
    head_html = "".join(f"<th>{_esc(c)}</th>" for c in cols)
    row_html = ""
    for r in rows:
        cells = r if isinstance(r, list) else [r.get(c, "") for c in cols]
        tds = ""
        for i, c in enumerate(cells):
            cls = ' class="ok"' if (i == 1 and "done" in str(c).lower() or "auto" in str(c).lower()) else ""
            tds += f"<td{cls}>{_esc(c)}</td>"
        row_html += f"<tr>{tds}</tr>"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    *{{margin:0;box-sizing:border-box;font-family:'Segoe UI',Inter,system-ui,sans-serif}}
    body{{width:1280px;height:800px;background:#0C0B08;color:#EFE9DB;padding:0;overflow:hidden}}
    .top{{display:flex;align-items:center;justify-content:space-between;padding:20px 30px;border-bottom:1px solid rgba(242,236,221,.12)}}
    .brand{{display:flex;align-items:center;gap:12px}}
    .dot{{width:34px;height:34px;border-radius:8px;background:linear-gradient(135deg,{accent},#8a6d2f)}}
    .brand b{{font-size:17px;letter-spacing:.5px}}
    .badge{{font-size:12px;letter-spacing:2px;color:#0C0B08;background:{accent};padding:6px 14px;border-radius:20px;font-weight:700}}
    .body{{padding:26px 30px}}
    h1{{font-size:30px;font-weight:700;margin-bottom:6px}}
    .sub{{color:#A7A091;font-size:15px;margin-bottom:22px}}
    .kpis{{display:grid;grid-template-columns:repeat({max(len(kpis),1)},1fr);gap:16px;margin-bottom:24px}}
    .kpi{{background:#15130E;border:1px solid rgba(242,236,221,.1);border-radius:12px;padding:18px 20px}}
    .kpi .v{{font-size:32px;font-weight:700;color:{accent}}}
    .kpi .l{{font-size:12px;color:#A7A091;text-transform:uppercase;letter-spacing:1px;margin-top:6px}}
    .panel{{background:#15130E;border:1px solid rgba(242,236,221,.1);border-radius:12px;overflow:hidden}}
    .panel .ph{{padding:14px 20px;border-bottom:1px solid rgba(242,236,221,.08);font-size:13px;letter-spacing:1px;color:#A7A091;text-transform:uppercase}}
    table{{width:100%;border-collapse:collapse}}
    th{{text-align:left;font-size:12px;color:#6B6557;text-transform:uppercase;letter-spacing:1px;padding:12px 20px}}
    td{{padding:13px 20px;border-top:1px solid rgba(242,236,221,.06);font-size:15px}}
    td.ok{{color:#93A66B;font-weight:600}}
    .flow{{display:flex;align-items:center;gap:10px;margin-top:20px;font-size:13px;color:#A7A091}}
    .step{{background:#15130E;border:1px solid rgba(201,162,75,.35);border-radius:8px;padding:8px 14px;color:#EFE9DB}}
    .arr{{color:{accent}}}
    </style></head><body>
    <div class="top"><div class="brand"><div class="dot"></div><b>Praxia Automation</b></div>
      <div class="badge">{badge}</div></div>
    <div class="body">
      <h1>{title}</h1><div class="sub">{subtitle}</div>
      <div class="kpis">{kpi_html}</div>
      <div class="panel"><div class="ph">Live activity</div>
        <table><thead><tr>{head_html}</tr></thead><tbody>{row_html}</tbody></table></div>
      <div class="flow">{''.join(f'<span class="step">{_esc(s)}</span><span class="arr">&#8594;</span>' for s in spec.get("flow", [])[:4])}<span class="step" style="border-color:#93A66B;color:#93A66B">Done</span></div>
    </div></body></html>"""


def render_mockup(spec: dict, out_path: str) -> dict:
    """Render the mockup HTML to a 1280x800 PNG. Returns {ok, path}."""
    try:
        from playwright.sync_api import sync_playwright
        html_str = _page(spec)
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2).new_page()
            pg.set_content(html_str, wait_until="networkidle")
            pg.wait_for_timeout(300)
            pg.screenshot(path=out_path)
            b.close()
        return {"ok": True, "path": out_path}
    except Exception as e:  # noqa: BLE001
        log.warning("mockup render failed: %s", e)
        return {"ok": False, "error": str(e)}
