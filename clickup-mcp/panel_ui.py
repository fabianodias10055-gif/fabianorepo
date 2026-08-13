#!/usr/bin/env python3
"""LocoDev Operations Panel UI: turns one panel.py scan into panel.html.

Split from panel.py so the data pipeline (scan/suggest/reply/serve) and the
presentation can evolve separately. Everything in here is string assembly:
no disk access, no network, no state. The page itself keeps zero state too;
the vault is the only source of truth and the page only renders it.

Design follows the app-shell mockup: sidebar navigation, KPI tiles with real
sparklines (fed by Panel/history.json, which starts flat and grows with use),
an Incoming questions table with search + filters + expandable Suggest/Reply
rows, and a right rail with Gaps, Priority queue and Documentation coverage.
"""

from html import escape

PAGE = 8  # question rows shown before "View all questions"

CH_COLORS = {
    "discord": "#5865f2",
    "youtube": "#e5332a",
    "patreon": "#ff424d",
    "email": "#3fd39c",
}

_ICONS = {
    "home": '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    "chat": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "check": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/>',
    "book": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
    "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "video": '<polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
    "bell": '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
    "refresh": '<path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    "filter": '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "flame": '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "alert": '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    "flag": '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
    "sparkle": '<path d="M12 3l1.9 5.9L20 10l-6.1 1.6L12 18l-1.9-6.4L4 10l6.1-1.1z"/>',
    "replyic": '<polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/>',
    "external": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14L21 3"/>',
    "eye": '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
}


def _icon(name: str, size: int = 16) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{_ICONS[name]}</svg>'
    )


def _spark(vals: list, color: str, w: int = 96, h: int = 30) -> str:
    """Real trend line from history.json. With a single point it renders flat:
    honest, it grows into a curve as history accumulates."""
    vals = list(vals) or [0]
    if len(vals) == 1:
        vals = vals * 2
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = 2 + i * (w - 4) / (n - 1)
        y = (h - 4) - (v - lo) * (h - 8) / span
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    area = f"2,{h - 2} {poly} {w - 2},{h - 2}"
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f'<polygon points="{area}" fill="{color}" opacity="0.12"></polygon>'
        f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"></polyline></svg>'
    )


def _hue(name: str) -> int:
    import hashlib
    return int(hashlib.sha1(name.encode()).hexdigest()[:6], 16) % 360


def _avatar(who: str) -> str:
    initial = escape((who.lstrip("@")[:1] or "?").upper())
    return f'<span class="av" style="background:hsl({_hue(who)} 60% 45%)">{initial}</span>'


def _st_class(status: str) -> str:
    import re
    return "st-" + re.sub(r"[^a-z0-9]+", "-", status.lower()).strip("-")


def _pill(status: str) -> str:
    return f'<span class="pill {_st_class(status)}">{escape(status)}</span>'


def _chn(channel: str) -> str:
    color = CH_COLORS.get(channel, "var(--ink3)")
    return (f'<span class="chn"><span class="cd" style="background:{color}"></span>'
            f'{escape(channel)}</span>')


# --------------------------------------------------------------------------
# Style: light like the mockup, with a dark variant via prefers-color-scheme.
# --------------------------------------------------------------------------

CSS = """
:root {
  --ground:#f2f5f9; --surface:#ffffff; --surface2:#f6f8fb;
  --line:#e4e9f2; --line2:#edf1f7;
  --ink:#0f172a; --ink2:#5b6779; --ink3:#8b96a8;
  --accent:#2563eb; --accent-bg:#e8effd;
  --ok:#16a34a; --ok-bg:#e6f6ec;
  --warn:#d97706; --warn-bg:#fbf1df;
  --crit:#dc2626; --crit-bg:#fdeaea;
  --info:#7c3aed; --info-bg:#f1eafd;
  --indigo:#6366f1;
  --mute-bg:#eef1f6;
  --shadow:0 1px 2px rgba(15,23,42,.05);
  --ui:-apple-system,"Segoe UI",system-ui,Roboto,Arial,sans-serif;
  --mono:"Cascadia Mono",Consolas,ui-monospace,monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ground:#0d1117; --surface:#151b23; --surface2:#1a222c;
    --line:#26303d; --line2:#1f2833;
    --ink:#e6edf3; --ink2:#96a1b2; --ink3:#68758a;
    --accent:#4f8ef7; --accent-bg:#16283f;
    --ok:#3fb968; --ok-bg:#12291a;
    --warn:#e5a13b; --warn-bg:#2d2213;
    --crit:#ef5350; --crit-bg:#331717;
    --info:#a78bfa; --info-bg:#241b38;
    --mute-bg:#1e2530;
    --shadow:none;
  }
}
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--ui); font-size:13.5px; line-height:1.5; }
a { color:var(--accent); }
.app { display:grid; grid-template-columns:212px minmax(0,1fr); min-height:100vh; }

/* ---- sidebar ---- */
.side { position:sticky; top:0; height:100vh; background:var(--surface);
  border-right:1px solid var(--line); display:flex; flex-direction:column;
  padding:14px 10px; gap:2px; }
.brand { display:flex; gap:10px; align-items:center; padding:4px 10px 14px; }
.brand .mark { width:32px; height:32px; border-radius:9px; flex:none;
  background:linear-gradient(135deg,#2563eb,#7c3aed); color:#fff;
  display:grid; place-items:center; font-weight:800; font-size:15px; }
.brand b { display:block; font-size:14px; line-height:1.15; }
.brand small { color:var(--ink3); font-size:10.5px; }
.nav { display:flex; flex-direction:column; gap:2px; }
.nav a { display:flex; gap:10px; align-items:center; padding:8px 11px;
  border-radius:9px; color:var(--ink2); text-decoration:none;
  font-size:13px; font-weight:570; }
.nav a svg { flex:none; }
.nav a:hover { background:var(--surface2); color:var(--ink); }
.nav a.active { background:var(--accent-bg); color:var(--accent); }
.spacer { flex:1; }
.me { display:flex; gap:9px; align-items:center; padding:10px;
  border-top:1px solid var(--line2); }
.me b { display:block; font-size:12.5px; line-height:1.2; }
.me small { color:var(--ink3); font-size:10.5px; }

/* ---- main / header ---- */
.main { padding:18px 22px 46px; min-width:0; }
.top { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:16px; }
h1 { font-size:21px; margin:0; font-weight:700; letter-spacing:-.02em; }
.chip { display:inline-flex; align-items:center; gap:7px; font-family:var(--mono);
  font-size:11px; color:var(--ink2); background:var(--surface);
  border:1px solid var(--line); border-radius:999px; padding:4px 11px; }
.chip .dot { width:7px; height:7px; border-radius:50%; background:var(--ok);
  box-shadow:0 0 0 3px var(--ok-bg); }
.chip[data-state="building"] .dot { background:var(--warn); box-shadow:0 0 0 3px var(--warn-bg); }
.chip[data-state="off"] .dot { background:var(--crit); box-shadow:0 0 0 3px var(--crit-bg); }
.search { flex:1; min-width:200px; max-width:430px; margin-left:auto; position:relative; }
.search > svg { position:absolute; left:11px; top:50%; transform:translateY(-50%); color:var(--ink3); }
.search input { width:100%; padding:8.5px 62px 8.5px 34px; border-radius:10px;
  border:1px solid var(--line); background:var(--surface); color:var(--ink);
  font:inherit; font-size:13px; }
.search input:focus { outline:2px solid var(--accent); outline-offset:-1px; }
.search kbd { position:absolute; right:9px; top:50%; transform:translateY(-50%);
  border:1px solid var(--line); border-radius:6px; padding:1px 6px;
  font-family:var(--mono); font-size:10px; color:var(--ink3); background:var(--surface2); }
.btn { display:inline-flex; gap:7px; align-items:center; padding:8px 13px;
  border-radius:9px; border:1px solid var(--line); background:var(--surface);
  color:var(--ink); font-family:var(--ui); font-size:12.5px; font-weight:600; cursor:pointer; }
.btn:hover { border-color:var(--accent); }
.btn:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.btn[disabled] { opacity:.55; cursor:default; }
.btn.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
.btn.primary:hover { filter:brightness(1.07); }
.btn.tiny { padding:4px 10px; font-size:11.5px; border-radius:7px; }
.bell { position:relative; padding:8px 10px; }
.bell .badge { position:absolute; top:-5px; right:-5px; background:var(--accent);
  color:#fff; font-size:9.5px; font-weight:700; border-radius:999px;
  padding:1.5px 5px; min-width:16px; text-align:center; }
.spin svg { animation:rot 1s linear infinite; }
@keyframes rot { to { transform:rotate(360deg); } }

/* ---- KPI tiles ---- */
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(185px,1fr));
  gap:12px; margin-bottom:14px; }
.tile { background:var(--surface); border:1px solid var(--line); border-radius:12px;
  padding:12px 14px; box-shadow:var(--shadow); }
.tile .h { display:flex; gap:9px; align-items:center; color:var(--ink2);
  font-size:12.5px; font-weight:600; }
.tile .h .tic { width:26px; height:26px; border-radius:8px; display:grid;
  place-items:center; flex:none; }
.tile .row { display:flex; align-items:flex-end; justify-content:space-between;
  gap:8px; margin-top:9px; }
.tile .v { font-size:26px; font-weight:700; letter-spacing:-.02em; line-height:1;
  font-variant-numeric:tabular-nums; }
.tile .v small { font-size:15px; color:var(--ink2); font-weight:600; }
.tile .s { color:var(--ink3); font-size:11.5px; margin-top:7px; }
.spark { width:96px; height:30px; flex:none; }
.c-blue { background:var(--accent-bg); color:var(--accent); }
.c-green { background:var(--ok-bg); color:var(--ok); }
.c-violet { background:var(--info-bg); color:var(--info); }
.c-red { background:var(--crit-bg); color:var(--crit); }
.c-indigo { background:rgba(99,102,241,.14); color:var(--indigo); }

/* ---- layout ---- */
.cols { display:grid; grid-template-columns:minmax(0,1fr) 330px; gap:14px; align-items:start; }
.card { background:var(--surface); border:1px solid var(--line); border-radius:12px;
  padding:14px 16px; box-shadow:var(--shadow); margin-bottom:14px; scroll-margin-top:12px; }
.card h2 { display:flex; align-items:center; gap:8px; font-size:14.5px;
  font-weight:650; margin:0 0 10px; }
.card h2 svg { color:var(--ink2); }
.card h2 .cnt { margin-left:auto; color:var(--ink3); font-weight:560;
  font-size:11.5px; font-family:var(--mono); }
.grid3 { display:grid; grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); gap:14px; }
.grid3 .card { margin-bottom:0; }
.hide { display:none !important; }
.linkbtn { display:block; width:100%; background:none; border:none; color:var(--accent);
  font-family:var(--ui); font-weight:600; font-size:12.5px; cursor:pointer;
  padding:9px 0 2px; text-align:center; }
.linkbtn:hover { text-decoration:underline; }

/* ---- filters ---- */
.filters { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:10px; }
.fchip { display:inline-flex; gap:6px; align-items:center; border:1px solid var(--line);
  background:var(--surface); color:var(--ink2); border-radius:8px; padding:5px 10px;
  font-family:var(--ui); font-size:12px; font-weight:600; cursor:pointer; }
.fchip .cd { width:8px; height:8px; border-radius:3px; }
.fchip.on { background:var(--accent-bg); border-color:var(--accent); color:var(--accent); }
.fsep { width:1px; height:18px; background:var(--line); margin:0 4px; }
select.fchip { appearance:auto; max-width:190px; }
.filters.flash { animation:flash 1.2s; }
@keyframes flash { 0%,60% { outline:2px solid var(--accent); outline-offset:4px;
  border-radius:6px; } 100% { outline:0 solid transparent; } }

/* ---- tables ---- */
.scroll { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; color:var(--ink3); font-family:var(--mono); font-size:10px;
  font-weight:600; letter-spacing:.06em; text-transform:uppercase;
  padding:6px 10px 8px 0; border-bottom:1px solid var(--line); white-space:nowrap; }
td { padding:9px 10px 9px 0; border-bottom:1px solid var(--line2); vertical-align:middle; }
tbody tr:last-child > td { border-bottom:0; }
td.num { font-family:var(--mono); font-size:12px; font-variant-numeric:tabular-nums;
  color:var(--ink2); white-space:nowrap; }
tr.qrow { cursor:pointer; }
tr.qrow:hover td { background:var(--surface2); }
.uc { display:flex; gap:9px; align-items:center; min-width:130px; }
.av { width:28px; height:28px; border-radius:50%; display:grid; place-items:center;
  color:#fff; font-weight:650; font-size:12px; flex:none; }
.uc .n { font-weight:600; font-size:12.5px; line-height:1.25; }
.uc .m { color:var(--ink3); font-size:10.5px; }
.pill { display:inline-block; padding:3px 9px; border-radius:7px; font-size:10.5px;
  font-weight:650; letter-spacing:.02em; white-space:nowrap; }
.st-answered { background:var(--ok-bg); color:var(--ok); }
.st-no-source { background:var(--crit-bg); color:var(--crit); }
.st-escalated { background:var(--warn-bg); color:var(--warn); }
.st-out-of-scope, .st-unknown { background:var(--mute-bg); color:var(--ink2); }
.st-ok { background:var(--ok-bg); color:var(--ok); }
.st-partial { background:var(--warn-bg); color:var(--warn); }
.st-blind { background:var(--crit-bg); color:var(--crit); }
.snip { color:var(--ink2); max-width:430px; display:-webkit-box; -webkit-line-clamp:2;
  -webkit-box-orient:vertical; overflow:hidden; }
.chn { display:inline-flex; gap:6px; align-items:center; color:var(--ink2); font-size:12.5px; }
.cd { width:8px; height:8px; border-radius:3px; flex:none; }
.acts { text-align:right; white-space:nowrap; }
.alink { display:flex; gap:6px; align-items:center; justify-content:flex-end;
  color:var(--accent); font-size:12px; font-weight:600; cursor:pointer; padding:2px 0; }
.alink:hover { text-decoration:underline; }
.alink svg { flex:none; }

/* ---- question detail ---- */
tr.qdet > td { background:var(--surface2); border-bottom:1px solid var(--line);
  padding:13px 14px; }
.det { display:grid; gap:10px; }
.det .full { font-size:13.5px; }
.det .prov { font-size:12px; color:var(--ink2); display:flex; gap:12px;
  flex-wrap:wrap; align-items:center; }
.det .prov a { color:var(--accent); text-decoration:none; display:inline-flex;
  gap:5px; align-items:center; }
.det .prov a:hover { text-decoration:underline; }
.sugout { border:1px dashed var(--line); border-radius:10px; padding:10px 12px;
  font-size:12.5px; background:var(--surface); display:none; }
.sugout .src { color:var(--ink3); font-size:11px; margin-bottom:6px; font-family:var(--mono); }
.sugout pre { margin:0 0 8px; white-space:pre-wrap; font-family:inherit; }
.qbox { width:100%; min-height:72px; border:1px solid var(--line); border-radius:10px;
  background:var(--surface); color:var(--ink); padding:9px 11px; font:inherit;
  font-size:13px; resize:vertical; }
.qbox:focus { outline:2px solid var(--accent); outline-offset:-1px; }
.detbtns { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.msg { font-size:12px; color:var(--ink2); }

/* ---- right rail ---- */
.grow { display:flex; justify-content:space-between; align-items:center; gap:8px;
  padding:7px 0; border-bottom:1px solid var(--line2); cursor:pointer; font-size:13px; }
.grow:hover { color:var(--accent); }
.grow:last-of-type { border-bottom:0; }
.grow .gcnt { background:var(--crit-bg); color:var(--crit); border-radius:7px;
  padding:2px 8px; font-size:11px; font-weight:650; font-family:var(--mono); flex:none; }
.prow { display:grid; grid-template-columns:16px minmax(0,1.15fr) 1fr 38px;
  gap:8px; align-items:center; padding:6px 0; font-size:12.5px; }
.prow .i { color:var(--ink3); font-family:var(--mono); font-size:11px; }
.prow .n { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:570; }
.pbar { height:6px; border-radius:4px; background:var(--line2); overflow:hidden; }
.pbar i { display:block; height:100%; border-radius:4px; background:var(--accent); }
.prow .pct { text-align:right; font-family:var(--mono); font-size:11px; color:var(--ink2); }
.cbar { display:inline-flex; align-items:center; gap:7px; }
.cbar .pbar { width:64px; }
.cbar .pbar i.g { background:var(--ok); }
.cbar .pbar i.a { background:var(--warn); }
.cbar .pbar i.r { background:var(--crit); }
.cbar b { font-family:var(--mono); font-size:11px; font-weight:600; color:var(--ink2); }

/* ---- videos / sources / answers ---- */
.vrow { display:flex; gap:10px; align-items:center; padding:7px 0;
  border-bottom:1px solid var(--line2); }
.vrow:last-of-type { border-bottom:0; }
.vrow img { width:64px; height:36px; object-fit:cover; border-radius:6px;
  background:var(--mute-bg); flex:none; }
.vrow .ph { width:64px; height:36px; border-radius:6px; background:var(--mute-bg);
  display:grid; place-items:center; color:var(--ink3); flex:none; }
.vrow .t { font-size:12.5px; font-weight:570; flex:1; min-width:0; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap; }
.vrow .t a { color:var(--ink); text-decoration:none; }
.vrow .t a:hover { color:var(--accent); }
.vrow .d { color:var(--ink3); font-size:11px; font-family:var(--mono); flex:none; }
.srow { display:grid; grid-template-columns:minmax(0,1fr) auto auto; gap:10px;
  align-items:center; padding:7px 0; border-bottom:1px solid var(--line2); font-size:12.5px; }
.srow:last-of-type { border-bottom:0; }
.srow .nm { font-weight:600; }
.srow .note { color:var(--ink3); font-size:11px; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap; }
.srow .vol { color:var(--ink2); font-family:var(--mono); font-size:11px; text-align:right; }
.arow { padding:9px 0; border-bottom:1px solid var(--line2); font-size:13px; }
.arow:last-of-type { border-bottom:0; }
.arow .hd { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:3px; }
.arow .hd .w { color:var(--ink3); font-family:var(--mono); font-size:11px; }
.arow .q { color:var(--ink2); font-size:12.5px; display:-webkit-box;
  -webkit-line-clamp:1; -webkit-box-orient:vertical; overflow:hidden; }
.arow .a { margin-top:3px; }
.tag { display:inline-block; background:var(--mute-bg); color:var(--ink2);
  border-radius:6px; padding:2px 7px; font-size:10px; font-weight:650; }
.tag.lead { background:var(--warn-bg); color:var(--warn); }
.tag.sub { background:var(--accent-bg); color:var(--accent); }
.empty { color:var(--ink3); font-size:12.5px; padding:8px 0; }

footer { margin-top:20px; color:var(--ink3); font-size:11.5px; font-family:var(--mono); }

@media (max-width:1180px) {
  .app { grid-template-columns:1fr; }
  .side { display:none; }
  .cols { grid-template-columns:1fr; }
}
"""

# --------------------------------------------------------------------------
# Behavior. Placeholders __EPOCH__ / __LIVE__ / __PAGE__ are substituted at
# render time; everything else is static. No page state survives a reload,
# by design: the vault is the only state there is.
# --------------------------------------------------------------------------

JS = """
var EPOCH = __EPOCH__, LIVE = __LIVE__, PAGE = __PAGE__;
function $(s, r) { return (r || document).querySelector(s); }
function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }

/* ---- live status ---- */
function agoText() {
  var s = Math.max(0, Math.floor(Date.now() / 1000 - EPOCH));
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return Math.floor(s / 86400) + "d ago";
}
function tickAgo() {
  var el = $("#chiptxt");
  var chip = $("#chip");
  if (!el || !LIVE) return;
  if (chip.dataset.state === "live") el.textContent = "live \\u00b7 updated " + agoText();
}
tickAgo();
setInterval(tickAgo, 30000);

var holdUntil = 0;  /* keep a just-shown reply message readable before reload */
function setChip(state, text) {
  var chip = $("#chip");
  if (!chip) return;
  chip.dataset.state = state;
  if (text) $("#chiptxt").textContent = text; else tickAgo();
}
function poll() {
  fetch("/status.json", { cache: "no-store" }).then(function (r) { return r.json(); })
    .then(function (s) {
      if (s.building) { setChip("building", "rebuilding..."); return; }
      if (s.epoch && s.epoch !== EPOCH) {
        if (Date.now() < holdUntil) return;
        location.reload();
        return;
      }
      setChip("live", null);
    })
    .catch(function () { setChip("off", "server gone \\u00b7 static view"); });
}
if (LIVE) setInterval(poll, 3000);

$("#updbtn").addEventListener("click", function () {
  if (!LIVE) { setChip("off", "static file: run panel.py --watch"); return; }
  var b = $("#updbtn");
  b.disabled = true;
  b.classList.add("spin");
  fetch("/rebuild", { method: "POST" }).catch(function () {});
  /* the epoch poll reloads the page when the rebuild lands */
});

/* ---- filters + search ---- */
var state = { ch: "all", st: "all", sys: "all", q: "" };
var shown = PAGE;
function match(r) {
  if (state.ch !== "all" && r.dataset.ch !== state.ch) return false;
  if (state.st !== "all" && r.dataset.st !== state.st) return false;
  if (state.sys !== "all" && r.dataset.sys !== state.sys) return false;
  if (state.q && r.dataset.txt.indexOf(state.q) === -1) return false;
  return true;
}
function apply() {
  var rows = $$("#qtbody tr.qrow");
  var kept = 0, total = 0;
  rows.forEach(function (r) {
    var m = match(r);
    if (m) total++;
    var vis = m && kept < shown;
    if (vis) kept++;
    r.classList.toggle("hide", !vis);
    var det = r.nextElementSibling;
    if (det && det.classList.contains("qdet"))
      det.classList.toggle("hide", !vis || !det.classList.contains("open"));
  });
  $("#qcount").textContent = kept + " of " + total;
  $("#morebtn").classList.toggle("hide", kept >= total);
}
function setGroup(k, v) {
  state[k] = v;
  $$('.fchip[data-k="' + k + '"]').forEach(function (c) {
    c.classList.toggle("on", c.dataset.v === v);
  });
}
$$(".fchip[data-k]").forEach(function (c) {
  c.addEventListener("click", function () {
    setGroup(c.dataset.k, c.dataset.v);
    shown = PAGE;
    apply();
  });
});
$("#sysSel").addEventListener("change", function () {
  state.sys = this.value;
  shown = PAGE;
  apply();
});
$("#q").addEventListener("input", function () {
  state.q = this.value.trim().toLowerCase();
  shown = PAGE;
  apply();
});
$("#morebtn").addEventListener("click", function () {
  shown = 1e9;
  apply();
});
document.addEventListener("keydown", function (e) {
  var tag = (document.activeElement || {}).tagName;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault(); $("#q").focus(); $("#q").select();
  } else if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA") {
    e.preventDefault(); $("#q").focus();
  } else if (e.key === "Escape" && document.activeElement === $("#q")) {
    $("#q").value = ""; state.q = ""; apply();
  }
});

/* ---- expandable rows + suggest/reply ---- */
function detOf(el) {
  var row = el.closest("tr.qrow");
  return row ? row.nextElementSibling : el.closest("tr.qdet");
}
function toggleDet(row, focus) {
  var det = row.nextElementSibling;
  if (!det || !det.classList.contains("qdet")) return;
  var open = !det.classList.contains("open");
  det.classList.toggle("open", open);
  det.classList.toggle("hide", !open);
  if (open && focus === "box") det.querySelector(".qbox").focus();
}
$$("#qtbody tr.qrow").forEach(function (r) {
  r.addEventListener("click", function (e) {
    if (e.target.closest("a, button, textarea, .alink")) return;
    toggleDet(r);
  });
});
function runSuggest(det) {
  var out = det.querySelector(".sugout");
  out.style.display = "block";
  out.textContent = "Searching your notes...";
  if (!LIVE) { out.textContent = "Static file: suggestions need the live server (panel.py --watch)."; return; }
  fetch("/suggest", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: det.dataset.id }) })
    .then(function (r) { return r.json(); })
    .then(function (s) {
      if (s.ok && s.text) {
        out.textContent = "";
        var src = document.createElement("div");
        src.className = "src";
        src.textContent = "from " + s.source;
        var pre = document.createElement("pre");
        pre.textContent = s.text;
        var use = document.createElement("button");
        use.className = "btn tiny";
        use.textContent = "Use as draft";
        use.addEventListener("click", function () {
          det.querySelector(".qbox").value = s.text;
          det.querySelector(".qbox").focus();
        });
        out.appendChild(src); out.appendChild(pre); out.appendChild(use);
      } else {
        out.textContent = "Nothing in your notes matches this yet. Real gap: type the "
          + "answer below, then paste it into the system's notes so the next one is automatic.";
      }
    })
    .catch(function () { out.textContent = "Could not reach the panel server."; });
}
function runReply(det) {
  var box = det.querySelector(".qbox");
  var msg = det.querySelector(".msg");
  var btn = det.querySelector(".replybtn");
  var text = box.value.trim();
  if (!text) { msg.textContent = "Type the reply first."; return; }
  if (!LIVE) { msg.textContent = "Static file: replying needs the live server (panel.py --watch)."; return; }
  btn.disabled = true;
  msg.textContent = "Updating the vault...";
  fetch("/reply", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: det.dataset.id, text: text }) })
    .then(function (r) { return r.json(); })
    .then(function (s) {
      if (s.ok) {
        holdUntil = Date.now() + 6000;
        msg.textContent = "Vault updated. " + (s.platform_message || "");
        var row = det.previousElementSibling;
        var pill = row.querySelector(".pill");
        pill.className = "pill st-answered";
        pill.textContent = "answered";
        row.dataset.st = "answered";
      } else {
        msg.textContent = "Failed: " + (s.error || "unknown error");
        btn.disabled = false;
      }
    })
    .catch(function () {
      msg.textContent = "Could not reach the panel server.";
      btn.disabled = false;
    });
}
$$("[data-act]").forEach(function (el) {
  el.addEventListener("click", function (e) {
    e.stopPropagation();
    var row = el.closest("tr.qrow");
    var det = detOf(el);
    if (!det) return;
    if (row && !det.classList.contains("open")) toggleDet(row);
    if (el.dataset.act === "suggest") runSuggest(det);
    else det.querySelector(".qbox").focus();
  });
});
$$("[data-suggest]").forEach(function (b) {
  b.addEventListener("click", function () { runSuggest(b.closest("tr.qdet")); });
});
$$("[data-reply]").forEach(function (b) {
  b.addEventListener("click", function () { runReply(b.closest("tr.qdet")); });
});

/* ---- gaps drill into the question table ---- */
$$(".grow").forEach(function (g) {
  g.addEventListener("click", function () {
    var sel = $("#sysSel");
    var has = Array.prototype.some.call(sel.options, function (o) { return o.value === g.dataset.sys; });
    state.sys = has ? g.dataset.sys : "all";
    sel.value = state.sys;
    setGroup("st", "no-source");
    shown = PAGE;
    apply();
    location.hash = "#questions";
  });
});

/* ---- view-all toggles ---- */
$$("[data-viewall]").forEach(function (b) {
  b.addEventListener("click", function () {
    var card = b.closest(".card");
    $$(".xtra", card).forEach(function (x) { x.classList.remove("hide"); });
    b.classList.add("hide");
  });
});

/* ---- header shortcuts ---- */
$("#filtbtn").addEventListener("click", function () {
  location.hash = "#questions";
  var f = $("#filters");
  f.classList.remove("flash");
  void f.offsetWidth;
  f.classList.add("flash");
});
$("#bellbtn").addEventListener("click", function () { location.hash = "#questions"; });

/* ---- sidebar active state ---- */
var links = {};
$$(".nav a").forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
var io = new IntersectionObserver(function (es) {
  es.forEach(function (en) {
    if (!en.isIntersecting) return;
    $$(".nav a").forEach(function (a) { a.classList.remove("active"); });
    var l = links[en.target.id];
    if (l) l.classList.add("active");
  });
}, { rootMargin: "-20% 0px -70% 0px" });
$$("section[id]").forEach(function (s) { io.observe(s); });

apply();
"""


# --------------------------------------------------------------------------
# Section builders
# --------------------------------------------------------------------------

def _tiles(d: dict, n_systems: int) -> str:
    hist = d.get("history") or []

    def series(key):
        return [p.get(key, 0) for p in hist][-60:]

    pct = d["written"] * 100 // d["total_facets"] if d["total_facets"] else 0
    tiles = [
        ("chat", "c-blue", "Open questions", str(d["open_q"]),
         "waiting on you", _spark(series("open"), "#2563eb")),
        ("check", "c-green", "Answered", f"{d['answer_rate']}%",
         f"of {len(d['questions'])} logged", _spark(series("rate"), "#16a34a")),
        ("book", "c-violet", "Catalog coverage", f"{pct}%",
         f"{d['written']} of {d['total_facets']} notes", _spark(series("cov"), "#7c3aed")),
        ("alert", "c-red", "Critical systems", str(d["critical"]),
         f"{d['urgent']} more urgent", _spark(series("crit"), "#dc2626")),
        ("flag", "c-indigo", "Complete",
         f"{d['complete']} <small>of {n_systems}</small>",
         "systems", _spark(series("complete"), "#6366f1")),
    ]
    cells = []
    for icon, color, label, value, sub, spark in tiles:
        cells.append(
            f'<div class="tile"><div class="h"><span class="tic {color}">{_icon(icon, 14)}</span>'
            f'{label}</div><div class="row"><div class="v">{value}</div>{spark}</div>'
            f'<div class="s">{sub}</div></div>'
        )
    return f'<section id="overview"><div class="tiles">{"".join(cells)}</div></section>'


def _filters(questions: list) -> str:
    channels = sorted({q["channel"] for q in questions})
    statuses = [s for s in ("answered", "escalated", "no-source", "out-of-scope", "unknown")
                if any(q["status"] == s for q in questions)]

    sys_counts: dict[str, int] = {}
    sys_names: dict[str, str] = {}
    for q in questions:
        if q["system"] == "-":
            continue
        sys_counts[q["system"]] = sys_counts.get(q["system"], 0) + 1
        sys_names[q["system"]] = q["system_name"]

    parts = ['<div class="filters" id="filters">',
             '<span class="fchip on" data-k="ch" data-v="all">All channels</span>']
    for ch in channels:
        dot = (f'<span class="cd" style="background:{CH_COLORS[ch]}"></span>'
               if ch in CH_COLORS else "")
        parts.append(f'<span class="fchip" data-k="ch" data-v="{escape(ch, quote=True)}">'
                     f'{dot}{escape(ch)}</span>')
    parts.append('<span class="fsep"></span>')
    parts.append('<span class="fchip on" data-k="st" data-v="all">All statuses</span>')
    for st in statuses:
        parts.append(f'<span class="fchip" data-k="st" data-v="{escape(st, quote=True)}">'
                     f'{escape(st)}</span>')
    parts.append('<span class="fsep"></span>')
    parts.append('<select id="sysSel" class="fchip"><option value="all">All systems</option>'
                 '<option value="-">catalog wide</option>')
    for slug in sorted(sys_counts, key=lambda s: -sys_counts[s]):
        parts.append(f'<option value="{escape(slug, quote=True)}">'
                     f'{escape(sys_names[slug])} ({sys_counts[slug]})</option>')
    parts.append('</select></div>')
    return "".join(parts)


def _question_rows(questions: list) -> str:
    rows = []
    for i, q in enumerate(questions):
        hid = "" if i < PAGE else " hide"
        sys_label = q["system_name"] if q["system"] != "-" else "catalog wide"
        sub = '<span class="m">subscriber</span>' if q["subscriber"] == "yes" else ""
        txt = escape(
            " ".join((q["who"], q["text"], sys_label, q["channel"], q["status"])).lower(),
            quote=True)
        qid = escape(q["id"], quote=True)

        rows.append(
            f'<tr class="qrow{hid}" data-id="{qid}" data-ch="{escape(q["channel"], quote=True)}"'
            f' data-st="{escape(q["status"], quote=True)}"'
            f' data-sys="{escape(q["system"], quote=True)}" data-txt="{txt}">'
            f'<td><span class="uc">{_avatar(q["who"])}'
            f'<span><span class="n">{escape(q["who"])}</span><br>{sub}</span></span></td>'
            f'<td>{_pill(q["status"])}</td>'
            f'<td><div class="snip">{escape(q["text"][:230])}</div></td>'
            f'<td>{escape(sys_label)}</td>'
            f'<td>{_chn(q["channel"])}</td>'
            f'<td class="num">{q["date"]}</td>'
            f'<td class="acts">'
            f'<span class="alink" data-act="suggest">{_icon("sparkle", 13)}Suggest answer</span>'
            f'<span class="alink" data-act="reply">{_icon("replyic", 13)}Reply</span>'
            f'</td></tr>'
        )

        prov = [f'{_chn(q["channel"])}', f'<span class="num">{q["date"]}</span>']
        if q.get("video") and q.get("video_url"):
            prov.append(
                f'<a href="{escape(q["video_url"], quote=True)}" target="_blank" rel="noopener">'
                f'from: {escape(q["video"])} {_icon("external", 12)}</a>')
        elif q.get("video"):
            prov.append(f'<span>from: {escape(q["video"])}</span>')
        if q.get("source"):
            prov.append(f'<span class="num">{escape(q["source"])}</span>')

        rows.append(
            f'<tr class="qdet hide" data-id="{qid}"><td colspan="7"><div class="det">'
            f'<div class="full">{escape(q["text"])}</div>'
            f'<div class="prov">{" ".join(prov)}</div>'
            f'<div class="detbtns"><button class="btn tiny" data-suggest>'
            f'{_icon("sparkle", 13)}Suggest answer</button></div>'
            f'<div class="sugout"></div>'
            f'<textarea class="qbox" placeholder="Type the reply. Reply always updates the '
            f'vault; posting to YouTube for real needs the one-time OAuth setup."></textarea>'
            f'<div class="detbtns"><button class="btn tiny primary replybtn" data-reply>'
            f'{_icon("replyic", 13)}Reply</button><span class="msg"></span></div>'
            f'</div></td></tr>'
        )
    return "".join(rows)


def _questions_card(d: dict) -> str:
    body = _question_rows(d["questions"]) if d["questions"] else (
        '<tr><td colspan="7"><div class="empty">No questions logged yet. '
        'They arrive via collect_youtube.py or by hand in Inbox/00 - Questions.md.</div></td></tr>')
    return (
        f'<section class="card" id="questions">'
        f'<h2>{_icon("chat")}Incoming questions'
        f'<span class="cnt">showing <span id="qcount"></span></span></h2>'
        f'{_filters(d["questions"])}'
        f'<div class="scroll"><table><thead><tr>'
        f'<th>User</th><th>Status</th><th>Snippet</th><th>System</th>'
        f'<th>Channel</th><th>Date</th><th></th>'
        f'</tr></thead><tbody id="qtbody">{body}</tbody></table></div>'
        f'<button class="linkbtn" id="morebtn">View all questions &rarr;</button>'
        f'</section>'
    )


def _answers_card(d: dict) -> str:
    answers = d.get("answers") or []
    rows = []
    for i, a in enumerate(answers):
        hid = "" if i < 5 else " xtra hide"
        posted = ('<span class="pill st-ok">posted to youtube</span>' if a["posted"]
                  else '<span class="pill st-unknown">vault only</span>')
        rows.append(
            f'<div class="arow{hid}"><div class="hd">{_avatar(a["who"])}'
            f'<b>{escape(a["who"])}</b>{_chn(a["channel"])}{posted}'
            f'<span class="w">{escape(a["when"])}</span></div>'
            f'<div class="q">Q: {escape(a["q"])}</div>'
            f'<div class="a">{escape(a["a"])}</div></div>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(answers)} replies</button>'
            if len(answers) > 5 else "")
    body = "".join(rows) if rows else (
        '<div class="empty">No replies sent from the panel yet. Expand a question, '
        'type an answer and hit Reply: it lands here and in Inbox/02 - Answered.md.</div>')
    return (
        f'<section class="card" id="answers">'
        f'<h2>{_icon("check")}Answers sent'
        f'<span class="cnt">{len(answers)} logged</span></h2>{body}{more}</section>'
    )


def _gaps_card(d: dict) -> str:
    rows = []
    for i, g in enumerate(d["gaps"]):
        hid = "" if i < 8 else " xtra hide"
        sys_val = "-" if g["key"] == "general" else g["key"]
        rows.append(
            f'<div class="grow{hid}" data-sys="{escape(sys_val, quote=True)}">'
            f'<span>{escape(g["label"])}</span>'
            f'<span class="gcnt">{g["count"]}x</span></div>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(d["gaps"])} gaps</button>'
            if len(d["gaps"]) > 8 else "")
    body = "".join(rows) if rows else '<div class="empty">Nothing marked no-source.</div>'
    return (f'<section class="card" id="gaps"><h2>{_icon("target")}Gaps to close</h2>'
            f'{body}{more}</section>')


def _priority_card(d: dict, n_facets: int) -> str:
    queue = [s for s in d["systems"] if s["demand"] > 0 and s["done"] < n_facets]
    rows = []
    for i, s in enumerate(queue):
        hid = "" if i < 8 else " xtra hide"
        rows.append(
            f'<div class="prow{hid}"><span class="i">{i + 1}</span>'
            f'<span class="n">{escape(s["name"])}</span>'
            f'<span class="pbar"><i style="width:{s["pct"]}%"></i></span>'
            f'<span class="pct">{s["pct"]}%</span></div>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(queue)}</button>'
            if len(queue) > 8 else "")
    body = "".join(rows) if rows else '<div class="empty">No gaps with recorded demand.</div>'
    return (f'<section class="card" id="priority"><h2>{_icon("flame")}Priority queue</h2>'
            f'{body}{more}</section>')


def _coverage_card(d: dict, n_facets: int) -> str:
    rows = []
    for i, s in enumerate(d["systems"]):
        hid = "" if i < 8 else " xtra hide"
        cov = s["done"] * 100 // n_facets
        cls = "g" if cov >= 80 else ("a" if cov >= 40 else "r")
        rows.append(
            f'<tr class="{hid.strip()}"><td>{escape(s["name"])}</td>'
            f'<td class="num">{s["done"]} / {n_facets}</td>'
            f'<td class="num">{s["demand"] or "-"}</td>'
            f'<td><span class="cbar"><span class="pbar">'
            f'<i class="{cls}" style="width:{cov}%"></i></span><b>{cov}%</b></span></td></tr>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(d["systems"])} systems</button>'
            if len(d["systems"]) > 8 else "")
    return (
        f'<section class="card" id="systems"><h2>{_icon("book")}Documentation coverage</h2>'
        f'<div class="scroll"><table><thead><tr><th>System</th><th>Done</th>'
        f'<th>Asked</th><th>Coverage</th></tr></thead><tbody>{"".join(rows)}</tbody>'
        f'</table></div>{more}</section>'
    )


def _people_card(d: dict) -> str:
    rows = []
    for i, p in enumerate(d["people"]):
        hid = "" if i < 8 else " xtra hide"
        tags = ""
        if p.get("lead"):
            tags += ' <span class="tag lead">lead</span>'
        if p["subscriber"] == "yes":
            tags += ' <span class="tag sub">sub</span>'
        rows.append(
            f'<tr class="{hid.strip()}"><td><span class="uc">{_avatar(p["who"])}'
            f'<span class="n">{escape(p["who"])}{tags}</span></span></td>'
            f'<td class="num">{p["asked"]}</td><td class="num">{p["open"]}</td>'
            f'<td class="num">{p["last"]}</td></tr>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(d["people"])} users</button>'
            if len(d["people"]) > 8 else "")
    body = "".join(rows) if rows else (
        '<tr><td colspan="4"><div class="empty">Nobody logged yet.</div></td></tr>')
    return (
        f'<section class="card" id="people"><h2>{_icon("users")}Who is asking</h2>'
        f'<div class="scroll"><table><thead><tr><th>User</th><th>Asked</th>'
        f'<th>Open</th><th>Last</th></tr></thead><tbody>{body}</tbody></table></div>'
        f'{more}</section>'
    )


def _videos_card(d: dict) -> str:
    videos = d["videos"]
    transcripts = sum(1 for v in videos if v["transcript"])
    rows = []
    for i, v in enumerate(videos):
        hid = "" if i < 6 else " xtra hide"
        title = escape(v["name"][11:] if len(v["name"]) > 11 else v["name"])
        if v.get("url"):
            title = (f'<a href="{escape(v["url"], quote=True)}" target="_blank" '
                     f'rel="noopener">{title}</a>')
        if v.get("video_id"):
            thumb = (f'<img loading="lazy" alt="" '
                     f'src="https://i.ytimg.com/vi/{escape(v["video_id"], quote=True)}/mqdefault.jpg" '
                     f'onerror="this.classList.add(\'hide\')">')
        else:
            thumb = f'<span class="ph">{_icon("video", 14)}</span>'
        rows.append(
            f'<div class="vrow{hid}">{thumb}<span class="t">{title}</span>'
            f'<span class="d">{escape(v["published"])}</span></div>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(videos)} videos</button>'
            if len(videos) > 6 else "")
    body = "".join(rows) if rows else '<div class="empty">No videos collected yet.</div>'
    return (
        f'<section class="card" id="videos"><h2>{_icon("video")}Videos'
        f'<span class="cnt">{len(videos)} collected &middot; {transcripts} with transcript</span>'
        f'</h2>{body}{more}</section>'
    )


def _sources_card(instrumentation: list) -> str:
    rows = []
    for source, vol, state, note in instrumentation:
        rows.append(
            f'<div class="srow"><span><span class="nm">{escape(source)}</span><br>'
            f'<span class="note" title="{escape(note, quote=True)}">{escape(note)}</span></span>'
            f'<span class="vol">{escape(vol)}</span>'
            f'<span class="pill st-{escape(state, quote=True)}">{escape(state)}</span></div>'
        )
    return (
        f'<section class="card" id="sources"><h2>{_icon("eye")}What is measured, '
        f'and what is blind</h2>{"".join(rows)}</section>'
    )


def _sidebar() -> str:
    items = [
        ("overview", "home", "Overview"),
        ("questions", "chat", "Questions"),
        ("answers", "check", "Answers"),
        ("systems", "grid", "Systems"),
        ("people", "users", "People"),
        ("videos", "video", "Videos"),
        ("sources", "database", "Sources"),
    ]
    parts = []
    for sid, icon, label in items:
        cls = ' class="active"' if sid == "overview" else ""
        parts.append(f'<a href="#{sid}"{cls}>{_icon(icon)}{label}</a>')
    nav = "".join(parts)
    return (
        '<aside class="side">'
        '<div class="brand"><span class="mark">L</span>'
        '<div><b>LocoDev</b><small>Operations</small></div></div>'
        f'<nav class="nav">{nav}</nav>'
        '<div class="spacer"></div>'
        '<div class="me"><span class="av" style="background:#2563eb">LD</span>'
        '<div><b>LocoDev</b><small>local vault</small></div></div>'
        '</aside>'
    )


def _header(d: dict, live: bool) -> str:
    if live:
        chip = ('<span class="chip" id="chip" data-state="live"><span class="dot"></span>'
                '<span id="chiptxt">live</span></span>')
    else:
        chip = (f'<span class="chip" id="chip" data-state="off"><span class="dot"></span>'
                f'<span id="chiptxt">static build {escape(d["generated_at"])}</span></span>')
    return (
        f'<div class="top"><h1>LocoDev Operations Panel</h1>{chip}'
        f'<div class="search">{_icon("search", 15)}'
        f'<input id="q" type="search" placeholder="Search questions, users, systems..." '
        f'autocomplete="off"><kbd>Ctrl K</kbd></div>'
        f'<button class="btn primary" id="updbtn">{_icon("refresh", 14)}Update now</button>'
        f'<button class="btn" id="filtbtn">{_icon("filter", 14)}Filters</button>'
        f'<button class="btn bell" id="bellbtn">{_icon("bell", 15)}'
        f'<span class="badge">{d["open_q"]}</span></button></div>'
    )


def render_html(d: dict, live: bool, facets: list, instrumentation: list) -> str:
    n_facets = len(facets)
    n_systems = len(d["systems"])

    js = (JS.replace("__EPOCH__", str(d["epoch"]))
            .replace("__LIVE__", "true" if live else "false")
            .replace("__PAGE__", str(PAGE)))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>LocoDev Operations Panel</title>
<style>{CSS}</style>
</head>
<body>
<div class="app">
{_sidebar()}
<main class="main">
{_header(d, live)}
{_tiles(d, n_systems)}
<div class="cols">
<div class="colmain">
{_questions_card(d)}
{_answers_card(d)}
</div>
<div class="rail">
{_gaps_card(d)}
{_priority_card(d, n_facets)}
{_coverage_card(d, n_facets)}
</div>
</div>
<div class="grid3">
{_people_card(d)}
{_videos_card(d)}
{_sources_card(instrumentation)}
</div>
<footer>generated {escape(d["generated_at"])} &middot; panel.py reads the vault on disk
&middot; the page keeps no state of its own: the vault is the source of truth</footer>
</main>
</div>
<script>{js}</script>
</body>
</html>
"""
