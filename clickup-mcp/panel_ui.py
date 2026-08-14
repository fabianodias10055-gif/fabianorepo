#!/usr/bin/env python3
"""LocoDev Operations Panel UI: turns one panel.py scan into panel.html.

Split from panel.py so the data pipeline (scan/suggest/reply/serve) and the
presentation can evolve separately. Everything in here is string assembly:
no disk access, no network, no state. The page keeps no vault state either;
the vault is the only source of truth and the page only renders it. The one
exception is UI preference and continuity state (theme, filters in the URL,
open rows, unsent reply drafts), which lives in the browser precisely so the
automatic reload on every rebuild never loses your place or your typing.

The visual layer is a token system, not ad-hoc values: every size, space,
radius, shadow and color resolves to a custom property defined once in
:root. Changing the product's look means editing tokens, not hunting
literals through a thousand lines of CSS.
"""

import re
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
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "copy": '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "sun": '<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "auto": '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" stroke="none"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    "menu": '<path d="M3 12h18M3 6h18M3 18h18"/>',
    "up": '<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>',
    "down": '<path d="M12 5v14"/><path d="M19 12l-7 7-7-7"/>',
    "brain": '<path d="M9.5 3a3 3 0 0 0-3 3 3 3 0 0 0-1.5 5.6A3 3 0 0 0 6 17a3 3 0 0 0 3.5 2.9V3z"/><path d="M14.5 3a3 3 0 0 1 3 3 3 3 0 0 1 1.5 5.6A3 3 0 0 1 18 17a3 3 0 0 1-3.5 2.9V3z"/>',
}

# Filled brand marks (approximations, small sizes): stroke icons read poorly
# for brands, so these bypass the stroke-based helper.
_BRAND = {
    "youtube": ('<rect x="1.5" y="5" width="21" height="14" rx="4" fill="#e5332a"/>'
                '<path d="M10 9l6 3-6 3z" fill="#fff"/>'),
    "discord": ('<ellipse cx="12" cy="12" rx="10" ry="7.5" fill="#5865f2"/>'
                '<circle cx="8.6" cy="12" r="1.6" fill="#fff"/>'
                '<circle cx="15.4" cy="12" r="1.6" fill="#fff"/>'),
}


def _icon(name: str, size: int = 16) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.9" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{_ICONS[name]}</svg>'
    )


def _brand_icon(name: str, size: int = 14) -> str:
    if name not in _BRAND:
        return ""
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'aria-hidden="true">{_BRAND[name]}</svg>')


def _fmt(n) -> str:
    """Thousands separators for every rendered number."""
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def _spark(vals: list, ident: str, color: str, w: int = 104, h: int = 34) -> str:
    """Real trend line from history.json, drawn as a gradient-filled area.

    With a single point it renders flat: honest, it grows into a curve as
    history accumulates rather than faking a trend nobody measured.
    """
    vals = list(vals) or [0]
    if len(vals) == 1:
        vals = vals * 2
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = 2 + i * (w - 4) / (n - 1)
        y = (h - 5) - (v - lo) * (h - 11) / span
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    area = f"2,{h - 1} {poly} {w - 2},{h - 1}"
    gid = f"g{ident}"
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity=".28"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        f'<polygon points="{area}" fill="url(#{gid})"></polygon>'
        f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round"></polyline></svg>'
    )


def _safe_url(url: str) -> str:
    """Only http(s) URLs may become hrefs or clipboard payloads. Vault
    fields are hand-editable; a pasted javascript: URL must render inert,
    not become a click-to-execute link inside the panel's origin."""
    u = (url or "").strip()
    return u if u.lower().startswith(("http://", "https://")) else ""


# A curated hue set instead of the full circle: random hues produced muddy
# olive and mustard avatars that fought the accent. These ten are spaced,
# saturated and all sit comfortably beside the indigo brand color.
_AV_HUES = (214, 245, 268, 292, 318, 344, 8, 26, 162, 190)


def _avatar(who: str, size: str = "") -> str:
    import hashlib
    idx = int(hashlib.sha1(who.encode()).hexdigest()[:6], 16) % len(_AV_HUES)
    hue = _AV_HUES[idx]
    initial = escape((who.lstrip("@")[:1] or "?").upper())
    cls = f"av {size}".strip()
    return (f'<span class="{cls}" style="--h:{hue}" aria-hidden="true">{initial}</span>')


def _thumb_url(video_id: str, size: str = "mqdefault") -> str:
    """YouTube's own still. Loaded straight from i.ytimg.com with a
    no-referrer policy; nothing about the vault leaves the machine."""
    vid = re.sub(r"[^A-Za-z0-9_-]", "", video_id or "")
    return f"https://i.ytimg.com/vi/{vid}/{size}.jpg" if vid else ""


def _mini_thumb(q: dict) -> str:
    """A 48x27 still in the collapsed row: which tutorial this is about is
    recognisable at a glance, which a slug in another column never is."""
    url = _thumb_url(q.get("video_id", ""), "default")
    if not url:
        return ""
    title = escape(q.get("video", ""), quote=True)
    return (f'<span class="qthumb" title="{title}">'
            f'<img loading="lazy" alt="" width="48" height="27" '
            f'referrerpolicy="no-referrer" src="{url}" '
            f'onerror="this.parentNode.classList.add(\'hide\')"></span>')


def _st_class(status: str) -> str:
    import re
    return "st-" + re.sub(r"[^a-z0-9]+", "-", status.lower()).strip("-")


# The vault stores the precise value; "no-source" states WHY it is open
# (nothing written to answer from). On screen that reads as jargon, so the
# label is plain and the original meaning moves into the tooltip.
_STATUS_LABEL = {"no-source": "unanswered"}
# An emoji carries the state at a glance and, unlike the colour alone,
# still reads for anyone who cannot separate the reds from the greens.
_STATUS_EMOJI = {
    "no-source": "📥",      # inbox tray
    "escalated": "⚠️",   # warning
    "answered": "✅",           # check
    "out-of-scope": "⏭️",
    "unknown": "❓",
    "ok": "✅", "partial": "⚠️", "blind": "🚫",
}
_DIFF_EMOJI = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}
_STATUS_TITLE = {
    "no-source": "no-source in the vault: nothing written yet to answer from",
    "escalated": "escalated: waiting on you specifically",
    "answered": "answered: a reply exists, kept in the knowledge base",
    "out-of-scope": "out of scope: not about the catalog",
}


def _pill(status: str) -> str:
    label = _STATUS_LABEL.get(status, status)
    title = _STATUS_TITLE.get(status, status)
    emoji = _STATUS_EMOJI.get(status, "")
    return (f'<span class="pill {_st_class(status)}" '
            f'title="{escape(title, quote=True)}">'
            f'<i class="pe">{emoji}</i>{escape(label)}</span>')


def _diff_pill(q: dict) -> str:
    """How much material the vault already has for this question."""
    d = q.get("difficulty")
    if not d or q.get("status") == "answered":
        return ""
    tips = {
        "easy": "easy: the vault already has a close match, Search my notes should find it",
        "medium": "medium: related material exists but nothing that answers it directly",
        "hard": "hard: nothing in the vault covers this yet, it is a documentation gap",
    }
    return (f'<span class="dpill d-{d}" title="{escape(tips[d], quote=True)}">'
            f'<i class="pe">{_DIFF_EMOJI[d]}</i>{d} '
            f'<b>{q.get("coverage", 0)}%</b></span>')


def _chn(channel: str) -> str:
    brand = _brand_icon(channel)
    if not brand:
        color = CH_COLORS.get(channel, "var(--ink3)")
        brand = f'<span class="cd" style="background:{color}"></span>'
    return f'<span class="chn">{brand}{escape(channel)}</span>'


def _delta24(hist: list, key: str) -> int:
    """Change vs the newest point at least 24h old (or the oldest point when
    history is younger than a day). Real data only; 0 when unknown."""
    if len(hist) < 2:
        return 0
    cur = hist[-1].get(key, 0)
    cutoff = hist[-1].get("t", 0) - 86400
    base = hist[0]
    for p in hist:
        if p.get("t", 0) <= cutoff:
            base = p
        else:
            break
    return cur - base.get(key, 0)


# --------------------------------------------------------------------------
# Style. A token system: sizes, spaces, radii, shadows and colors are all
# custom properties declared once. The dark token block is emitted twice,
# once under prefers-color-scheme for the "system" setting and once under
# [data-theme="dark"] so the in-page toggle wins in both directions.
# --------------------------------------------------------------------------

_DARK_TOKENS = """
    --ground:#0a0c11; --surface:#111620; --surface2:#161d29; --surface3:#1c2534;
    --line:#212a38; --line2:#1a2230;
    --ink:#e9edf4; --ink2:#98a3b5; --ink3:#838da1;
    --accent:#6c8dff; --accent-ink:#0a0c11; --accent-bg:#161f38; --accent-line:#2b3d68;
    --ok:#3ecf82; --ok-bg:#0f2a1e; --ok-line:#1c4834;
    --warn:#e9a83c; --warn-bg:#2b2113; --warn-line:#4a3a1c;
    --crit:#f2645a; --crit-bg:#2d1618; --crit-line:#502428;
    --info:#a98bfa; --info-bg:#221c39; --info-line:#3a2f60;
    --mute-bg:#1a2230;
    --av-l:33%; --av-s:52%;
    --e1:0 1px 2px rgba(0,0,0,.4);
    --e2:0 2px 10px rgba(0,0,0,.45);
    --e3:0 18px 44px rgba(0,0,0,.6);
    --skel:linear-gradient(90deg,#161d29 25%,#1e2836 37%,#161d29 63%);
    --glow-a:rgba(108,141,255,.10); --glow-b:rgba(169,139,250,.08);
"""

CSS = """
:root {
  /* ---- type scale ---- */
  --t-2xs:10px; --t-xs:11px; --t-sm:12px; --t-base:13px; --t-md:14px;
  --t-lg:15px; --t-xl:18px; --t-2xl:22px; --t-3xl:28px; --t-4xl:36px;
  /* ---- space scale, 4px base ---- */
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:20px; --s6:24px;
  --s7:28px; --s8:32px; --s10:40px;
  /* ---- radii ---- */
  --r-xs:6px; --r-sm:8px; --r-md:10px; --r-lg:14px; --r-xl:18px; --r-full:999px;
  /* ---- motion ---- */
  --dur:.16s; --ease:cubic-bezier(.2,.6,.3,1);
  /* ---- type faces ---- */
  --ui:-apple-system,"Segoe UI Variable Text","Segoe UI",system-ui,Roboto,Arial,sans-serif;
  --mono:"Cascadia Mono","SF Mono",Consolas,ui-monospace,monospace;
  /* ---- light palette ---- */
  --ground:#f6f7f9; --surface:#ffffff; --surface2:#f7f8fa; --surface3:#eef1f5;
  --line:#e5e8ee; --line2:#eef0f4;
  --ink:#101319; --ink2:#5a6373; --ink3:#636d7f;
  --accent:#365df5; --accent-ink:#ffffff; --accent-bg:#eaefff; --accent-line:#c9d6ff;
  --ok:#127c42; --ok-bg:#e7f6ed; --ok-line:#c2e6d1;
  --warn:#9a600a; --warn-bg:#fdf2df; --warn-line:#f2ddb4;
  --crit:#cc3030; --crit-bg:#fdecec; --crit-line:#f6cfcf;
  --info:#6d3cf0; --info-bg:#f0ebfe; --info-line:#dcd0fb;
  --mute-bg:#eff1f5;
  --av-l:33%; --av-s:56%;
  --e1:0 1px 2px rgba(16,19,25,.05);
  --e2:0 2px 8px rgba(16,19,25,.06),0 1px 2px rgba(16,19,25,.04);
  --e3:0 16px 40px rgba(16,19,25,.14);
  --skel:linear-gradient(90deg,#eef1f5 25%,#f6f8fa 37%,#eef1f5 63%);
  /* ---- layout ---- */
  --side-w:224px; --head-h:62px; --page-max:1640px;
  --glow-a:rgba(61,99,245,.07); --glow-b:rgba(109,60,240,.06);
  --glass:82%; --glass-blur:14px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
/*DARK*/
  }
}
:root[data-theme="dark"] {
/*DARK*/
}

* { box-sizing:border-box; }
html { scroll-behavior:smooth; -webkit-text-size-adjust:100%; }
body::before { content:""; position:fixed; inset:0; z-index:-1; pointer-events:none;
  background:
    radial-gradient(60rem 40rem at 12% -8%, var(--glow-a), transparent 60%),
    radial-gradient(52rem 36rem at 92% 4%, var(--glow-b), transparent 62%); }
body { margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--ui); font-size:var(--t-base); line-height:1.55;
  -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
  scrollbar-width:thin; scrollbar-color:var(--line) transparent; }
a { color:var(--accent); text-underline-offset:2px; }
::selection { background:var(--accent-bg); color:var(--ink); }
::-webkit-scrollbar { width:10px; height:10px; }
::-webkit-scrollbar-thumb { background:var(--line); border-radius:var(--r-full);
  border:3px solid transparent; background-clip:content-box; }
::-webkit-scrollbar-thumb:hover { background:var(--ink3); background-clip:content-box; }
::-webkit-scrollbar-track { background:transparent; }

:focus-visible { outline:2px solid var(--accent); outline-offset:2px; border-radius:var(--r-xs); }
.app { display:grid; grid-template-columns:var(--side-w) minmax(0,1fr); min-height:100vh; }

/* ================= sidebar ================= */
.side { position:sticky; top:0; height:100vh;
  background:color-mix(in srgb, var(--surface) 88%, transparent);
  backdrop-filter:blur(var(--glass-blur)) saturate(1.2);
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(1.2);
  border-right:1px solid var(--line); display:flex; flex-direction:column;
  padding:var(--s4) var(--s3); gap:var(--s1); }
.brand { display:flex; gap:var(--s3); align-items:center; padding:var(--s1) var(--s2) var(--s5); }
.brand .mark { width:34px; height:34px; border-radius:var(--r-md); flex:none;
  background:linear-gradient(140deg,var(--accent),var(--info)); color:var(--accent-ink);
  display:grid; place-items:center; font-weight:800; font-size:var(--t-lg);
  letter-spacing:-.03em; box-shadow:var(--e2); }
.brand b { display:block; font-size:var(--t-md); line-height:1.2; letter-spacing:-.01em; }
.brand small { color:var(--ink3); font-size:var(--t-2xs); letter-spacing:.09em;
  text-transform:uppercase; font-weight:600; }
.navlabel { color:var(--ink3); font-size:var(--t-2xs); font-weight:700;
  letter-spacing:.1em; text-transform:uppercase; padding:var(--s4) var(--s3) var(--s1); }
.nav { display:flex; flex-direction:column; gap:1px; }
.nav a { position:relative; display:flex; gap:var(--s3); align-items:center;
  padding:var(--s2) var(--s3); border-radius:var(--r-sm); color:var(--ink2);
  text-decoration:none; font-size:var(--t-base); font-weight:550;
  transition:background var(--dur) var(--ease), color var(--dur) var(--ease); }
.nav a svg { flex:none; opacity:.8; }
.nav a:hover { background:var(--surface2); color:var(--ink); }
.nav a.active { background:var(--accent-bg); color:var(--accent); font-weight:620; }
.nav a.active svg { opacity:1; }
.nav a.active::before { content:""; position:absolute; left:-12px;
  top:50%; transform:translateY(-50%); width:3px; height:18px;
  background:var(--accent); border-radius:0 3px 3px 0; }
.nav .navcount { margin-left:auto; font-family:var(--mono); font-size:var(--t-2xs);
  color:var(--ink3); background:var(--surface3); border-radius:var(--r-full);
  padding:1px 7px; font-weight:600; }
.nav a.active .navcount { background:var(--surface); color:var(--accent); }
.spacer { flex:1; }
.me { display:flex; gap:var(--s3); align-items:center; padding:var(--s3) var(--s2) var(--s1);
  border-top:1px solid var(--line2); }
.me b { display:block; font-size:var(--t-sm); line-height:1.25; }
.me small { color:var(--ink3); font-size:var(--t-2xs); font-family:var(--mono); }

/* ================= main + header ================= */
.main { padding:0 var(--s6) var(--s10); min-width:0; max-width:var(--page-max); }
.top { display:flex; align-items:center; gap:var(--s3); flex-wrap:wrap;
  position:sticky; top:0; z-index:40; padding:var(--s4) 0 var(--s3);
  background:var(--ground);
  background:color-mix(in srgb, var(--ground) 88%, transparent);
  backdrop-filter:saturate(1.4) blur(10px);
  -webkit-backdrop-filter:saturate(1.4) blur(10px);
  border-bottom:1px solid transparent; margin-bottom:var(--s5);
  transition:border-color var(--dur) var(--ease); }
.top.stuck { border-bottom-color:var(--line); }
h1 { font-size:var(--t-xl); margin:0; font-weight:680; letter-spacing:-.025em; }
.chip { display:inline-flex; align-items:center; gap:var(--s2); font-family:var(--mono);
  font-size:var(--t-xs); color:var(--ink2); background:var(--surface);
  border:1px solid var(--line); border-radius:var(--r-full); padding:5px 12px;
  box-shadow:var(--e1); }
.chip .dot { width:7px; height:7px; border-radius:50%; background:var(--ok);
  box-shadow:0 0 0 3px var(--ok-bg); }
.chip[data-state="live"] .dot { animation:pulse 2.4s var(--ease) infinite; }
@keyframes pulse { 0%,100% { box-shadow:0 0 0 3px var(--ok-bg); }
  50% { box-shadow:0 0 0 5px var(--ok-bg); } }
.chip[data-state="building"] .dot { background:var(--warn); box-shadow:0 0 0 3px var(--warn-bg); }
.chip[data-state="off"] .dot { background:var(--crit); box-shadow:0 0 0 3px var(--crit-bg); animation:none; }
.search { flex:1; min-width:190px; max-width:420px; margin-left:auto; position:relative; }
.search > svg { position:absolute; left:12px; top:50%; transform:translateY(-50%);
  color:var(--ink3); pointer-events:none; }
.search input { width:100%; padding:9px 66px 9px 36px; border-radius:var(--r-md);
  border:1px solid var(--line); background:var(--surface); color:var(--ink);
  font:inherit; font-size:var(--t-base); box-shadow:var(--e1);
  transition:border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease); }
.search input::placeholder { color:var(--ink3); }
.search input:focus { outline:none; border-color:var(--accent);
  box-shadow:0 0 0 3px var(--accent-bg); }
.search kbd { position:absolute; right:10px; top:50%; transform:translateY(-50%);
  border:1px solid var(--line); border-radius:var(--r-xs); padding:2px 6px;
  font-family:var(--mono); font-size:var(--t-2xs); color:var(--ink3);
  background:var(--surface2); pointer-events:none; }
.btn { display:inline-flex; gap:var(--s2); align-items:center; padding:8px 13px;
  border-radius:var(--r-md); border:1px solid var(--line); background:var(--surface);
  color:var(--ink); font-family:var(--ui); font-size:var(--t-sm); font-weight:600;
  cursor:pointer; box-shadow:var(--e1); white-space:nowrap;
  transition:background var(--dur) var(--ease), border-color var(--dur) var(--ease),
    transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease); }
.btn:hover { background:var(--surface2); border-color:var(--ink3); }
.btn:active { transform:translateY(1px); box-shadow:none; }
.btn[disabled] { opacity:.5; cursor:default; transform:none; }
.btn.primary { background:var(--accent); border-color:var(--accent); color:var(--accent-ink);
  box-shadow:var(--e2); }
.btn.primary:hover { filter:brightness(1.08); border-color:var(--accent); }
.btn.tiny { padding:5px 10px; font-size:var(--t-xs); border-radius:var(--r-sm); }
.btn.icon { padding:8px; }
.bell { position:relative; }
.bell .badge { position:absolute; top:-6px; right:-6px; background:var(--crit);
  color:var(--accent-ink); font-size:var(--t-2xs); font-weight:700; border-radius:var(--r-full);
  padding:1px 6px; min-width:18px; text-align:center; font-family:var(--mono);
  border:2px solid var(--ground); }
.spin svg { animation:rot .9s linear infinite; }
@keyframes rot { to { transform:rotate(360deg); } }

/* mobile nav, hidden on desktop */
.mnav { display:none; gap:var(--s2); overflow-x:auto; padding:0 0 var(--s4);
  scrollbar-width:none; }
.mnav::-webkit-scrollbar { display:none; }
.mnav a { flex:none; display:inline-flex; gap:var(--s2); align-items:center;
  padding:7px 13px; border-radius:var(--r-full); background:var(--surface);
  border:1px solid var(--line); color:var(--ink2); text-decoration:none;
  font-size:var(--t-sm); font-weight:600; }
.mnav a.active { background:var(--accent-bg); border-color:var(--accent-line); color:var(--accent); }

/* ================= KPI tiles ================= */
.tiles { display:grid; gap:var(--s3); margin-bottom:var(--s5);
  grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); }
@media (min-width:1180px) { .tiles { grid-template-columns:1.55fr 1fr 1fr 1fr 1fr; } }
.tile { position:relative;
  background:color-mix(in srgb, var(--surface) var(--glass), transparent);
  backdrop-filter:blur(var(--glass-blur)) saturate(1.25);
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(1.25);
  border:1px solid var(--line);
  border-radius:var(--r-lg); padding:var(--s4); box-shadow:var(--e1); overflow:hidden;
  transition:box-shadow var(--dur) var(--ease), transform var(--dur) var(--ease),
    border-color var(--dur) var(--ease); }
.tile:hover { box-shadow:var(--e2); transform:translateY(-1px); }
.tile .h { display:flex; gap:var(--s2); align-items:center; color:var(--ink2);
  font-size:var(--t-sm); font-weight:600; letter-spacing:-.005em; }
.tile .tic { width:28px; height:28px; border-radius:var(--r-sm); display:grid;
  place-items:center; flex:none; }
.tile .row { display:flex; align-items:flex-end; justify-content:space-between;
  gap:var(--s3); margin-top:var(--s3); }
.tile .v { font-size:var(--t-3xl); font-weight:700; letter-spacing:-.035em; line-height:1;
  font-variant-numeric:tabular-nums; font-feature-settings:"tnum" 1; }
.tile .v small { font-size:var(--t-lg); color:var(--ink3); font-weight:600;
  letter-spacing:-.01em; }
.tile .s { color:var(--ink3); font-size:var(--t-xs); margin-top:var(--s3);
  display:flex; align-items:center; gap:var(--s2); flex-wrap:wrap; }
.tile.hero { background:
    radial-gradient(120% 140% at 100% 0%, var(--accent-bg) 0%, transparent 62%),
    var(--surface); }
.tile.hero .v { font-size:var(--t-4xl); }
.tile.hero .h { color:var(--ink); }
.dlt { display:inline-flex; align-items:center; gap:3px; font-weight:700;
  font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r-xs);
  font-size:var(--t-2xs); }
.dlt.good { color:var(--ok); background:var(--ok-bg); }
.dlt.bad { color:var(--crit); background:var(--crit-bg); }
.dlt svg { width:10px; height:10px; }
.spark { width:104px; height:34px; flex:none; }
.c-blue { background:var(--accent-bg); color:var(--accent); }
.c-green { background:var(--ok-bg); color:var(--ok); }
.c-violet { background:var(--info-bg); color:var(--info); }
.c-red { background:var(--crit-bg); color:var(--crit); }
.c-amber { background:var(--warn-bg); color:var(--warn); }

/* ================= layout + cards ================= */
.cols { display:grid; grid-template-columns:minmax(0,1fr) 336px; gap:var(--s4);
  align-items:start; }
.card { background:color-mix(in srgb, var(--surface) var(--glass), transparent);
  backdrop-filter:blur(var(--glass-blur)) saturate(1.25);
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(1.25);
  border:1px solid var(--line); border-radius:var(--r-lg);
  padding:var(--s4) var(--s5); box-shadow:var(--e1); margin-bottom:var(--s4);
  scroll-margin-top:calc(var(--head-h) + var(--s3)); }
.card h2 { display:flex; align-items:center; gap:var(--s2); font-size:var(--t-lg);
  font-weight:660; margin:0 0 var(--s3); letter-spacing:-.015em; flex-wrap:wrap;
  padding-bottom:var(--s3); border-bottom:1px solid var(--line2); }
.card h2 > svg { color:var(--ink3); }
.card h2 .cnt { margin-left:auto; color:var(--ink3); font-weight:550;
  font-size:var(--t-xs); font-family:var(--mono); letter-spacing:0; }
.grid3 { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(340px,100%),1fr));
  gap:var(--s4); align-items:start; }
.grid3 .card { margin-bottom:0; }
.hide { display:none !important; }
.linkbtn { display:block; width:100%; background:none; border:none; color:var(--accent);
  font-family:var(--ui); font-weight:620; font-size:var(--t-sm); cursor:pointer;
  padding:var(--s3) 0 var(--s1); text-align:center; border-radius:var(--r-sm);
  transition:background var(--dur) var(--ease); }
.linkbtn:hover { background:var(--surface2); }

/* ================= filters ================= */
.filters { display:flex; flex-wrap:wrap; gap:var(--s2); align-items:center;
  margin-bottom:var(--s3); }
.fchip { display:inline-flex; gap:var(--s2); align-items:center; border:1px solid var(--line);
  background:var(--surface); color:var(--ink2); border-radius:var(--r-full);
  padding:5px 12px; font-family:var(--ui); font-size:var(--t-sm); font-weight:600;
  cursor:pointer; user-select:none;
  transition:background var(--dur) var(--ease), border-color var(--dur) var(--ease),
    color var(--dur) var(--ease); }
.fchip:hover { border-color:var(--ink3); color:var(--ink); }
.fchip .cd { width:8px; height:8px; border-radius:var(--r-full); }
.fchip .fc-n { color:var(--ink3); font-weight:650; font-size:var(--t-2xs);
  font-family:var(--mono); font-variant-numeric:tabular-nums; }
.fchip.on { background:var(--accent-bg); border-color:var(--accent-line); color:var(--accent); }
.fchip.on .fc-n { color:var(--accent); }
.fsep { width:1px; height:20px; background:var(--line); margin:0 var(--s1); }
select.fchip { appearance:none; max-width:200px; padding-right:28px;
  background-image:linear-gradient(45deg,transparent 50%,currentColor 50%),
    linear-gradient(135deg,currentColor 50%,transparent 50%);
  background-position:calc(100% - 15px) 51%,calc(100% - 11px) 51%;
  background-size:4px 4px,4px 4px; background-repeat:no-repeat; }
.fclear { margin-left:auto; color:var(--ink3); background:none; border:none;
  font-family:var(--ui); font-size:var(--t-xs); font-weight:600; cursor:pointer;
  padding:var(--s1) var(--s2); border-radius:var(--r-xs); }
.fclear:hover { color:var(--crit); background:var(--crit-bg); }
.filters.flash { animation:flash 1.1s var(--ease); }
@keyframes flash { 0%,55% { box-shadow:0 0 0 3px var(--accent); border-radius:var(--r-md); }
  100% { box-shadow:0 0 0 0 transparent; } }

/* ================= tables ================= */
.scroll { overflow-x:auto; margin:0 calc(var(--s5) * -1); padding:0 var(--s5); }
table { width:100%; border-collapse:collapse; font-size:var(--t-base); }
th { background:color-mix(in srgb, var(--surface) 94%, transparent);
  backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px);
  text-align:left; color:var(--ink3); font-family:var(--mono); font-size:var(--t-2xs);
  font-weight:600; letter-spacing:.07em; text-transform:uppercase;
  padding:var(--s2) var(--s3) var(--s2) 0; border-bottom:1px solid var(--line);
  white-space:nowrap; background:var(--surface); }
th[data-sort] { cursor:pointer; user-select:none; transition:color var(--dur) var(--ease); }
th[data-sort]:hover { color:var(--accent); }
th .sarrow { opacity:0; margin-left:3px; display:inline-block; }
th[aria-sort="ascending"] .sarrow, th[aria-sort="descending"] .sarrow { opacity:1; color:var(--accent); }
th[aria-sort="descending"] .sarrow { transform:rotate(180deg); }
td { padding:var(--s3) var(--s3) var(--s3) 0; border-bottom:1px solid var(--line2);
  vertical-align:middle; }
tbody tr:last-child > td { border-bottom:0; }
tfoot td { font-weight:700; border-top:1px solid var(--line); border-bottom:0;
  font-family:var(--mono); font-size:var(--t-xs); color:var(--ink2); }
td.num { font-family:var(--mono); font-size:var(--t-sm); font-variant-numeric:tabular-nums;
  color:var(--ink2); white-space:nowrap; }
tr.qrow { cursor:pointer; transition:background var(--dur) var(--ease); }
tr.qrow > td { transition:background var(--dur) var(--ease); }
tr.qrow:hover > td { background:var(--surface2); }
tr.qrow.kfocus > td { background:var(--accent-bg); }
tr.qrow.kfocus > td:first-child { box-shadow:inset 3px 0 0 var(--accent); }
tr.qrow[aria-expanded="true"] > td { background:var(--surface2); }
/* Expanded, the row is just the card's title bar: the snippet, system,
   channel, date and actions all reappear inside the panel below, and
   showing them twice made the card read as noise.
   The CONTENT is hidden, never the <td>: hiding a cell takes its background
   with it and punched a lighter rectangle through the row, and hiding it
   with display would change the cell count and break every other row's
   column alignment. */
tr.qrow[aria-expanded="true"] .snip,
tr.qrow[aria-expanded="true"] .qid,
tr.qrow[aria-expanded="true"] .cval,
tr.qrow[aria-expanded="true"] .chn,
tr.qrow[aria-expanded="true"] .rowacts { visibility:hidden; }
/* Title bar and panel are one surface: no rule between them, and a rounded
   accent edge marks where the card starts. */
tr.qrow[aria-expanded="true"] > td { border-bottom-color:transparent; }
tr.qrow[aria-expanded="true"] > td:first-child {
  box-shadow:inset 3px 0 0 var(--accent); }
tr.qdet.open > td { box-shadow:inset 3px 0 0 var(--accent); }
.agew { color:var(--warn); }
.agec { color:var(--crit); font-weight:650; }
.uc { display:flex; gap:var(--s2); align-items:center; min-width:132px; }
.av { width:30px; height:30px; border-radius:var(--r-full); display:grid;
  place-items:center; color:#fff; font-weight:660; font-size:var(--t-sm); flex:none;
  background:hsl(var(--h) var(--av-s) var(--av-l)); letter-spacing:-.01em;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.14); }
.av.sm { width:22px; height:22px; font-size:var(--t-2xs); }
.uc .n { font-weight:600; font-size:var(--t-sm); line-height:1.3; letter-spacing:-.005em; }
.uc .m { color:var(--ink3); font-size:var(--t-2xs); }
.pill { display:inline-flex; align-items:center; gap:4px; padding:3px 9px;
  border-radius:var(--r-full); font-size:var(--t-2xs); font-weight:680;
  letter-spacing:.01em; white-space:nowrap; border:1px solid transparent; }
.pill { gap:5px; }
.st-answered { background:var(--ok-bg); color:var(--ok); border-color:var(--ok-line); }
.st-no-source { background:var(--crit-bg); color:var(--crit); border-color:var(--crit-line); }
.st-escalated { background:var(--warn-bg); color:var(--warn); border-color:var(--warn-line); }
.st-out-of-scope, .st-unknown { background:var(--mute-bg); color:var(--ink2); border-color:var(--line); }
.st-ok { background:var(--ok-bg); color:var(--ok); border-color:var(--ok-line); }
.st-partial { background:var(--warn-bg); color:var(--warn); border-color:var(--warn-line); }
.st-blind { background:var(--crit-bg); color:var(--crit); border-color:var(--crit-line); }
.u-critical { background:var(--crit-bg); color:var(--crit); border-color:var(--crit-line); }
.u-urgent { background:var(--warn-bg); color:var(--warn); border-color:var(--warn-line); }
.qcell { display:flex; gap:var(--s3); align-items:center; }
.qthumb { flex:none; width:48px; height:27px; border-radius:var(--r-xs);
  overflow:hidden; background:var(--surface3); }
.qthumb img { width:100%; height:100%; object-fit:cover; display:block; }
.idcell { width:1%; white-space:nowrap; }
.qid { font-family:var(--mono); font-size:var(--t-xs); color:var(--ink3);
  background:var(--surface2); border:1px solid var(--line2);
  border-radius:var(--r-xs); padding:2px 7px; cursor:pointer;
  transition:color var(--dur) var(--ease), border-color var(--dur) var(--ease); }
.qid:hover { color:var(--accent); border-color:var(--accent-line); }
.stcell { white-space:nowrap; }
.dpill { display:inline-flex; align-items:center; gap:4px; margin-left:6px;
  padding:2px 7px; border-radius:var(--r-full); font-size:var(--t-2xs);
  font-weight:650; border:1px solid transparent; }
.dpill b { font-family:var(--mono); font-weight:700; opacity:.75; }
.d-easy { background:var(--ok-bg); color:var(--ok); border-color:var(--ok-line); }
.d-medium { background:var(--warn-bg); color:var(--warn); border-color:var(--warn-line); }
.d-hard { background:var(--mute-bg); color:var(--ink2); border-color:var(--line); }
.snip { color:var(--ink2); max-width:440px; display:-webkit-box; -webkit-line-clamp:2;
  -webkit-box-orient:vertical; overflow:hidden; line-height:1.45; }
/* The video still leads the expanded card: recognising which tutorial the
   comment is about is most of the work of answering it. */
.vidcard { display:flex; gap:var(--s4); align-items:center; padding:var(--s3);
  border:1px solid var(--line); border-radius:var(--r-md); background:var(--surface);
  text-decoration:none; color:inherit;
  transition:border-color var(--dur) var(--ease), background var(--dur) var(--ease); }
a.vidcard:hover { border-color:var(--accent); background:var(--accent-bg); }
.vidcard img { width:168px; height:94px; object-fit:cover; border-radius:var(--r-xs);
  flex:none; background:var(--surface3); }
.vidcard .vmeta { min-width:0; display:grid; gap:var(--s1); }
.vidcard .vmeta b { font-size:var(--t-md); font-weight:620; line-height:1.35;
  letter-spacing:-.01em; }
.vidcard .vmeta > span { display:inline-flex; align-items:center; gap:5px;
  color:var(--accent); font-size:var(--t-sm); font-weight:600; }
.vidcard.novid { color:var(--ink2); border-style:dashed; }
.vidcard.novid .vmeta b { font-size:var(--t-base); color:var(--ink2); }
.vidcard.novid .vmeta > span { color:var(--ink3); font-weight:500; }
.chn { display:inline-flex; gap:6px; align-items:center; color:var(--ink2);
  font-size:var(--t-sm); }
.cd { width:8px; height:8px; border-radius:var(--r-full); flex:none; }
.acts { text-align:right; white-space:nowrap; width:1%; }
/* Dimmed rather than hidden: replying is the point of this table, so the
   action must stay discoverable without a hover to find it. */
.rowacts { display:inline-flex; flex-direction:column; gap:3px; align-items:flex-end;
  opacity:.6; transition:opacity var(--dur) var(--ease); }
tr.qrow:hover .rowacts, tr.qrow:focus-within .rowacts,
tr.qrow.kfocus .rowacts, tr.qrow[aria-expanded="true"] .rowacts { opacity:1; }
@media (hover:none) { .rowacts { opacity:1; } }
.alink { display:inline-flex; gap:5px; align-items:center; color:var(--ink2);
  font-size:var(--t-xs); font-weight:600; cursor:pointer; padding:3px 8px;
  border-radius:var(--r-sm); border:1px solid transparent; background:none;
  white-space:nowrap;
  transition:color var(--dur) var(--ease), border-color var(--dur) var(--ease),
    background var(--dur) var(--ease); }
.alink:hover { color:var(--accent); border-color:var(--accent-line); background:var(--accent-bg); }
.pe { font-style:normal; font-size:11px; line-height:1; }
.he { font-size:16px; line-height:1; }
.alink svg { flex:none; }
.sysdrill { cursor:pointer; border-bottom:1px dashed var(--line);
  transition:color var(--dur) var(--ease), border-color var(--dur) var(--ease); }
.sysdrill:hover { color:var(--accent); border-color:var(--accent); }

/* ================= question detail ================= */
tr.qdet > td { background:var(--surface2); border-bottom:1px solid var(--line);
  padding:0 var(--s4); }
/* Entrance animation only, never a transition out of an invisible base
   state: an fr-track animation resolves to 0px inside a table cell, and an
   opacity:0 base leaves the panel permanently blank whenever frames do not
   run (background tab). Visible is the default; the keyframes are pure
   decoration on top of it. */
tr.qdet.open .detwrap { animation:detIn .18s var(--ease); }
/* Transform only, never opacity: while an animation is pending its first
   frame the browser already applies the from-state, so an opacity:0 keyframe
   renders the panel blank in a tab that is not painting. Worst case here is
   a 5px offset, never invisible content. */
@keyframes detIn { from { transform:translateY(-5px); } to { transform:none; } }
.det { display:grid; gap:var(--s3); padding:var(--s4) 0; max-width:78ch; }
.det .full { font-size:var(--t-md); line-height:1.6; color:var(--ink); }
.det .prov { font-size:var(--t-sm); color:var(--ink2); display:flex; gap:var(--s4);
  flex-wrap:wrap; align-items:center; padding:var(--s2) 0; border-top:1px solid var(--line2);
  border-bottom:1px solid var(--line2); }
.det .prov a { color:var(--accent); text-decoration:none; display:inline-flex;
  gap:5px; align-items:center; font-weight:560; }
.det .prov a:hover { text-decoration:underline; }
.det .prov .num { font-family:var(--mono); font-size:var(--t-xs); color:var(--ink3); }
.yourreply { background:var(--ok-bg); border:1px solid var(--ok-line);
  border-left:3px solid var(--ok); border-radius:var(--r-md); padding:var(--s3) var(--s4);
  font-size:var(--t-base); line-height:1.55; }
.yourreply b { color:var(--ok); display:flex; align-items:center; gap:6px;
  font-size:var(--t-xs); text-transform:uppercase; letter-spacing:.06em;
  margin-bottom:var(--s1); }
.sugout { border:1px solid var(--line); border-radius:var(--r-md); padding:var(--s3) var(--s4);
  font-size:var(--t-base); background:var(--surface); display:none; }
.sugout .src { color:var(--ink3); font-size:var(--t-xs); margin-bottom:var(--s2);
  font-family:var(--mono); display:flex; align-items:center; gap:var(--s2); flex-wrap:wrap; }
.sugout pre { margin:0 0 var(--s3); white-space:pre-wrap; font-family:inherit;
  line-height:1.55; max-height:280px; overflow:auto; }
.aiout { border:1px solid var(--info-line); border-left:3px solid var(--info);
  border-radius:var(--r-md); padding:var(--s3) var(--s4); font-size:var(--t-base);
  background:var(--surface); display:none; }
.aiout .src { color:var(--ink3); font-size:var(--t-xs); margin-bottom:var(--s2);
  font-family:var(--mono); display:flex; align-items:center; gap:var(--s2); flex-wrap:wrap; }
.aiout pre { margin:0 0 var(--s3); white-space:pre-wrap; font-family:inherit;
  line-height:1.55; }
.aimiss { background:var(--warn-bg); color:var(--warn); border-radius:var(--r-sm);
  padding:var(--s2) var(--s3); font-size:var(--t-sm); margin-bottom:var(--s2); }
.ainote { background:var(--surface2); color:var(--ink2); border-radius:var(--r-sm);
  padding:var(--s2) var(--s3); font-size:var(--t-sm); margin-bottom:var(--s2); }
.aisrc { color:var(--ink3); font-family:var(--mono); font-size:var(--t-2xs);
  margin-bottom:var(--s3); word-break:break-all; }
.regen { margin-left:auto; color:var(--accent); cursor:pointer; font-weight:600;
  font-family:var(--ui); font-size:var(--t-xs); }
.regen:hover { text-decoration:underline; }
.btn.ai { border-color:var(--info-line); color:var(--info); }
.btn.ai:hover { background:var(--info-bg); border-color:var(--info); }
.conf { display:inline-flex; gap:7px; align-items:center; font-size:var(--t-2xs);
  font-weight:700; white-space:nowrap; padding:2px 8px; border-radius:var(--r-full);
  border:1px solid currentColor; }
.conf-ok { color:var(--ok); background:var(--ok-bg); }
.conf-warn { color:var(--warn); background:var(--warn-bg); }
.conf-crit { color:var(--crit); background:var(--crit-bg); }
.confbar { width:52px; height:5px; border-radius:var(--r-full); background:rgba(127,127,127,.25);
  overflow:hidden; display:inline-block; }
.confbar i { display:block; height:100%; border-radius:var(--r-full); background:currentColor; }
.qbox { width:100%; min-height:84px; border:1px solid var(--line); border-radius:var(--r-md);
  background:var(--surface); color:var(--ink); padding:var(--s3) var(--s4); font:inherit;
  font-size:var(--t-base); line-height:1.55; resize:vertical;
  transition:border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease); }
.qbox::placeholder { color:var(--ink3); }
.qbox:focus { outline:none; border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-bg); }
.detbtns { display:flex; gap:var(--s2); align-items:center; flex-wrap:wrap; }
.msg { font-size:var(--t-sm); color:var(--ink2); }
.msg.good { color:var(--ok); font-weight:600; }
.msg.bad { color:var(--crit); font-weight:600; }

/* ================= right rail ================= */
.grow { display:flex; justify-content:space-between; align-items:center; gap:var(--s2);
  padding:var(--s2) var(--s2); margin:0 calc(var(--s2) * -1);
  border-radius:var(--r-sm); cursor:pointer; font-size:var(--t-base);
  transition:background var(--dur) var(--ease); }
.grow + .grow { border-top:1px solid var(--line2); }
.grow:hover { background:var(--surface2); color:var(--accent); }
.grow small { color:var(--ink3); font-size:var(--t-2xs); font-family:var(--mono);
  display:block; font-weight:500; }
.grow .gcnt { background:var(--crit-bg); color:var(--crit); border:1px solid var(--crit-line);
  border-radius:var(--r-full); padding:2px 9px; font-size:var(--t-xs); font-weight:700;
  font-family:var(--mono); flex:none; font-variant-numeric:tabular-nums; }
.prow { display:grid; grid-template-columns:18px minmax(0,1.1fr) 1fr 40px;
  gap:var(--s2); align-items:center; padding:var(--s2) 0; font-size:var(--t-sm); }
.prow .i { color:var(--ink3); font-family:var(--mono); font-size:var(--t-xs);
  font-variant-numeric:tabular-nums; }
.prow .n { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:570; }
.pbar { height:6px; border-radius:var(--r-full); background:var(--surface3); overflow:hidden; }
.pbar i { display:block; height:100%; border-radius:var(--r-full); background:var(--accent);
  transition:width .5s var(--ease); }
.prow .pct { text-align:right; font-family:var(--mono); font-size:var(--t-xs);
  color:var(--ink2); font-variant-numeric:tabular-nums; }
.cbar { display:inline-flex; align-items:center; gap:var(--s2); }
.cbar .pbar { width:62px; }
.cbar .pbar i.g { background:var(--ok); }
.cbar .pbar i.a { background:var(--warn); }
.cbar .pbar i.r { background:var(--crit); }
.cbar b { font-family:var(--mono); font-size:var(--t-xs); font-weight:600;
  color:var(--ink2); font-variant-numeric:tabular-nums; }

/* ================= videos / sources / answers ================= */
.vrow { display:flex; gap:var(--s3); align-items:center; padding:var(--s2) 0;
  border-bottom:1px solid var(--line2); }
.vrow:last-of-type { border-bottom:0; }
.vthumb { position:relative; width:68px; height:38px; border-radius:var(--r-xs);
  background:var(--surface3); flex:none; overflow:hidden; }
.vthumb img { width:100%; height:100%; object-fit:cover; display:block; }
.vthumb .ph { position:absolute; inset:0; display:grid; place-items:center; color:var(--ink3); }
.vrow .t { font-size:var(--t-sm); font-weight:560; flex:1; min-width:0; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap; }
.vrow .t a { color:var(--ink); text-decoration:none; }
.vrow .t a:hover { color:var(--accent); }
.vrow .d { color:var(--ink3); font-size:var(--t-xs); font-family:var(--mono); flex:none;
  font-variant-numeric:tabular-nums; }
.vtag { background:var(--mute-bg); color:var(--ink2); border-radius:var(--r-xs);
  padding:2px 7px; font-size:var(--t-2xs); font-family:var(--mono); flex:none; }
.srow { display:grid; grid-template-columns:minmax(0,1fr) auto auto; gap:var(--s3);
  align-items:center; padding:var(--s2) 0; border-bottom:1px solid var(--line2);
  font-size:var(--t-sm); }
.srow:last-of-type { border-bottom:0; }
.srow .nm { font-weight:600; font-size:var(--t-base); }
.srow .note { color:var(--ink3); font-size:var(--t-xs); overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap; }
.srow .vol { color:var(--ink2); font-family:var(--mono); font-size:var(--t-xs);
  text-align:right; font-variant-numeric:tabular-nums; }
.arow { padding:var(--s3) 0; border-bottom:1px solid var(--line2); font-size:var(--t-base); }
.arow:last-of-type { border-bottom:0; }
.arow .hd { display:flex; gap:var(--s2); align-items:center; flex-wrap:wrap;
  margin-bottom:var(--s1); }
.arow .hd b { font-size:var(--t-sm); }
.arow .hd .w { color:var(--ink3); font-family:var(--mono); font-size:var(--t-2xs);
  margin-left:auto; }
.arow .q { color:var(--ink3); font-size:var(--t-sm); display:-webkit-box;
  -webkit-line-clamp:1; -webkit-box-orient:vertical; overflow:hidden; }
.arow .a { margin-top:2px; display:-webkit-box; -webkit-line-clamp:3;
  -webkit-box-orient:vertical; overflow:hidden; line-height:1.5; }
.tag { display:inline-block; background:var(--mute-bg); color:var(--ink2);
  border-radius:var(--r-xs); padding:1px 7px; font-size:var(--t-2xs); font-weight:680; }
.tag.lead { background:var(--warn-bg); color:var(--warn); }
.tag.sub { background:var(--accent-bg); color:var(--accent); }
.tag.esc { background:var(--warn-bg); color:var(--warn); }

/* ================= empty states ================= */
.empty { color:var(--ink3); font-size:var(--t-sm); padding:var(--s3) 0; }
.emptybox { display:grid; justify-items:center; gap:var(--s2); text-align:center;
  padding:var(--s7) var(--s4); color:var(--ink3); }
.emptybox .eic { width:44px; height:44px; border-radius:var(--r-md);
  background:var(--surface3); display:grid; place-items:center; color:var(--ink3); }
.emptybox b { color:var(--ink); font-size:var(--t-md); font-weight:620; }
.emptybox p { margin:0; font-size:var(--t-sm); max-width:46ch; line-height:1.5; }

/* ================= skeletons ================= */
.skel { background:var(--skel); background-size:400% 100%;
  animation:shimmer 1.4s ease-in-out infinite; border-radius:var(--r-sm); }
@keyframes shimmer { 0% { background-position:100% 50%; } 100% { background-position:0 50%; } }
.skel-row { height:14px; margin:var(--s2) 0; }
.skel-tile { height:58px; border-radius:var(--r-md); }

/* ================= link telemetry ================= */
.admlink { display:inline-flex; gap:5px; align-items:center; margin-left:var(--s3);
  font-size:var(--t-xs); font-weight:600; text-decoration:none; }
.admlink:hover { text-decoration:underline; }
.ltk { display:grid; grid-template-columns:repeat(auto-fit,minmax(116px,1fr));
  gap:var(--s2); margin-bottom:var(--s4); }
.mk { background:var(--surface2); border:1px solid var(--line2); border-radius:var(--r-md);
  padding:var(--s3) var(--s4); }
.mk.skel { background:var(--skel); background-size:400% 100%; }
.mk .v { font-size:var(--t-2xl); font-weight:700; font-variant-numeric:tabular-nums;
  line-height:1.15; letter-spacing:-.03em; }
.mk .l { color:var(--ink3); font-size:var(--t-2xs); text-transform:uppercase;
  letter-spacing:.07em; font-weight:600; margin-top:2px; }
.ltgrid { display:grid; grid-template-columns:minmax(0,1fr) 296px; gap:var(--s6);
  align-items:start; }
@media (max-width:940px) { .ltgrid { grid-template-columns:1fr; } }
.lchart { width:100%; height:84px; margin-bottom:var(--s4); overflow:visible; }
.lchart rect { fill:var(--accent); opacity:.8; transition:opacity var(--dur) var(--ease); }
.lchart rect:hover { opacity:1; }
.lsub { color:var(--ink3); font-family:var(--mono); font-size:var(--t-2xs);
  letter-spacing:.08em; text-transform:uppercase; margin:0 0 var(--s2); font-weight:600; }
.crow { display:flex; justify-content:space-between; gap:var(--s2); padding:var(--s2) 0;
  border-bottom:1px solid var(--line2); font-size:var(--t-sm); align-items:center; }
.crow:last-child { border-bottom:0; }
.crow .n { font-family:var(--mono); font-size:var(--t-xs); color:var(--ink3);
  text-align:right; font-variant-numeric:tabular-nums; }
.slug { font-family:var(--mono); font-size:var(--t-sm); color:var(--ink); }
.host { color:var(--ink3); font-size:var(--t-xs); }
.retry { color:var(--accent); cursor:pointer; text-decoration:underline; font-weight:600; }

/* ================= toast ================= */
#toast { position:fixed; right:var(--s5); bottom:var(--s5); background:var(--surface);
  border:1px solid var(--line); border-radius:var(--r-md); padding:var(--s3) var(--s4);
  font-size:var(--t-sm); z-index:60; box-shadow:var(--e3); opacity:0;
  transform:translateY(10px) scale(.98); pointer-events:none; max-width:340px;
  display:flex; align-items:center; gap:var(--s3); font-weight:550;
  transition:opacity var(--dur) var(--ease), transform var(--dur) var(--ease); }
#toast.show { opacity:1; transform:none; }
#toast .ti { width:26px; height:26px; border-radius:var(--r-sm); flex:none;
  display:grid; place-items:center; background:var(--accent-bg); color:var(--accent); }
#toast[data-kind="good"] .ti { background:var(--ok-bg); color:var(--ok); }
#toast[data-kind="bad"] .ti { background:var(--crit-bg); color:var(--crit); }

footer { margin-top:var(--s6); padding-top:var(--s4); border-top:1px solid var(--line);
  color:var(--ink3); font-size:var(--t-xs); font-family:var(--mono); }

/* ================= responsive ================= */
@media (min-width:1500px) {
  /* the questions table fits: drop the scroll container so the sticky
     header can anchor to the viewport instead of a short scroll box */
  #questions .scroll { overflow:visible; margin:0; padding:0; }
  #questions thead th { position:sticky; top:var(--head-h); z-index:5; }
}
@media (max-width:1180px) {
  .app { grid-template-columns:1fr; }
  .side { display:none; }
  .mnav { display:flex; }
  .cols { grid-template-columns:minmax(0,1fr); }
  .main { padding:0 var(--s4) var(--s8); }
  h1 { font-size:var(--t-lg); }
  .tile.hero .v { font-size:var(--t-3xl); }
}
@media (max-width:680px) {
  .search { order:5; max-width:none; margin-left:0; }
  .top { gap:var(--s2); }
  .snip { max-width:none; }
  .card { padding:var(--s4); }
  .scroll { margin:0 calc(var(--s4) * -1); padding:0 var(--s4); }
}

@supports not ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))) {
  .card, .tile, .side, th { background:var(--surface); }
}
@media (prefers-reduced-transparency: reduce) {
  .card, .tile, .side, th { background:var(--surface); backdrop-filter:none;
    -webkit-backdrop-filter:none; }
  body::before { display:none; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior:auto; }
  *, *::before, *::after { animation-duration:.001ms !important;
    animation-iteration-count:1 !important; transition-duration:.001ms !important; }
}

@media print {
  .side, .mnav, .search, .btn, .bell, .filters, .linkbtn, .acts, .chip kbd,
  #toast, .qdet, .spark { display:none !important; }
  .app { display:block; }
  .top { position:static; backdrop-filter:none; }
  body { background:#fff; color:#000; font-size:10pt; }
  .card, .tile { break-inside:avoid; border-color:#ccc; box-shadow:none;
    background:#fff; backdrop-filter:none; -webkit-backdrop-filter:none; }
  body::before { display:none; }
  .cols, .grid3 { display:block; }
  .card { margin-bottom:12pt; }
  a[href^="http"]::after { content:" (" attr(href) ")"; font-size:8pt; color:#555; }
}
""".replace("/*DARK*/", _DARK_TOKENS)

# Applied before first paint so a stored theme choice never flashes the
# other palette; the full script at the end of body does everything else.
HEAD_JS = """
try {
  var t = localStorage.getItem("lp-theme");
  if (t === "dark" || t === "light") document.documentElement.dataset.theme = t;
} catch (e) {}
"""

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
           "viewBox='0 0 64 64'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' "
           "x2='1' y2='1'%3E%3Cstop offset='0%25' stop-color='%233d63f5'/%3E"
           "%3Cstop offset='100%25' stop-color='%236d3cf0'/%3E%3C/linearGradient%3E"
           "%3C/defs%3E%3Crect width='64' height='64' rx='16' fill='url(%23g)'/%3E"
           "%3Ctext x='32' y='45' font-size='36' font-family='Arial' "
           "font-weight='bold' fill='white' text-anchor='middle'%3EL%3C/text%3E%3C/svg%3E")

# --------------------------------------------------------------------------
# Behavior. Placeholders __EPOCH__ / __LIVE__ / __PAGE__ are substituted at
# render time. Continuity state (filters, sort, open rows, drafts, scroll)
# lives in the URL and web storage so the auto-reload on every vault rebuild
# never loses the operator's place; vault data itself never lives here.
# --------------------------------------------------------------------------

JS = """
var EPOCH = __EPOCH__, LIVE = __LIVE__, PAGE = __PAGE__;
var AI_CACHE = __AI_CACHE__;
function $(s, r) { return (r || document).querySelector(s); }
function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
function esc(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}
function fmt(n) { return Number(n).toLocaleString("en-US"); }
function debounce(fn, ms) {
  var t;
  return function () {
    var a = arguments, self = this;
    clearTimeout(t);
    t = setTimeout(function () { fn.apply(self, a); }, ms);
  };
}
var reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
function ss(k, v) { try { if (v === null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, v); } catch (e) {} }
function ssGet(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

/* ---- theme toggle: system -> dark -> light ---- */
var THEME_ICON = { system: "auto", dark: "moon", light: "sun" };
function applyTheme(mode) {
  if (mode === "dark" || mode === "light") document.documentElement.dataset.theme = mode;
  else delete document.documentElement.dataset.theme;
  var b = $("#themebtn");
  if (!b) return;
  b.querySelector(".tlabel").textContent =
    mode === "dark" ? "Dark" : mode === "light" ? "Light" : "Auto";
  $$(".ticon", b).forEach(function (i) {
    i.classList.toggle("hide", i.dataset.icon !== THEME_ICON[mode]);
  });
}
var themeMode = lsGet("lp-theme") || "system";
applyTheme(themeMode);
$("#themebtn").addEventListener("click", function () {
  themeMode = themeMode === "system" ? "dark" : themeMode === "dark" ? "light" : "system";
  if (themeMode === "system") { try { localStorage.removeItem("lp-theme"); } catch (e) {} }
  else lsSet("lp-theme", themeMode);
  applyTheme(themeMode);
});

/* ---- toast ---- */
function toast(text, kind) {
  var t = $("#toast");
  t.dataset.kind = kind || "info";
  $("#toasttxt").textContent = text;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(function () { t.classList.remove("show"); }, 5000);
}

/* ---- sticky header shadow ---- */
var topBar = $(".top");
function syncHeadH() {
  document.documentElement.style.setProperty("--head-h", topBar.offsetHeight + "px");
}
syncHeadH();
addEventListener("resize", debounce(syncHeadH, 120));
addEventListener("scroll", function () {
  topBar.classList.toggle("stuck", scrollY > 8);
}, { passive: true });

/* ---- live status ---- */
function agoText() {
  var s = Math.max(0, Math.floor(Date.now() / 1000 - EPOCH));
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return Math.floor(s / 86400) + "d ago";
}
function tickAgo() {
  var el = $("#chiptxt"), chip = $("#chip");
  if (!el || !LIVE) return;
  if (chip.dataset.state === "live") el.textContent = "live \\u00b7 updated " + agoText();
}
tickAgo();
setInterval(tickAgo, 30000);

var holdUntil = 0;
function setChip(state, text) {
  var chip = $("#chip");
  if (!chip) return;
  chip.dataset.state = state;
  if (text) $("#chiptxt").textContent = text; else tickAgo();
}
function reloadKeepingPlace() {
  ss("lp-scroll", String(Math.round(scrollY)));
  location.reload();
}
function poll() {
  fetch("/status.json", { cache: "no-store" }).then(function (r) { return r.json(); })
    .then(function (s) {
      if (s.building) { setChip("building", "rebuilding..."); return; }
      if (s.epoch && s.epoch !== EPOCH) {
        if (Date.now() < holdUntil) return;
        reloadKeepingPlace();
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
  fetch("/rebuild", { method: "POST" })
    .then(function () { toast("Rebuild requested; the page refreshes when it lands.", "info"); })
    .catch(function () {
      toast("Could not reach the panel server.", "bad");
      b.disabled = false;
      b.classList.remove("spin");
    });
});

/* ---- filter/sort state, persisted in the URL across auto-reloads ---- */
var params = new URLSearchParams(location.search);
var state = {
  ch: params.get("ch") || "all",
  st: params.get("st") || "all",
  sys: params.get("sys") || "all",
  df: params.get("df") || "all",
  q: params.get("q") || "",
  sort: params.get("sort") || "date",
  dir: params.get("dir") || "desc"
};
var shown = parseInt(ssGet("lp-shown") || PAGE, 10) || PAGE;
function syncUrl() {
  var p = new URLSearchParams();
  if (state.ch !== "all") p.set("ch", state.ch);
  if (state.st !== "all") p.set("st", state.st);
  if (state.sys !== "all") p.set("sys", state.sys);
  if (state.df !== "all") p.set("df", state.df);
  if (state.q) p.set("q", state.q);
  if (state.sort !== "date" || state.dir !== "desc") { p.set("sort", state.sort); p.set("dir", state.dir); }
  var qs = p.toString();
  try { history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash); } catch (e) {}
}

var PAIRS = $$("#qtbody tr.qrow").map(function (r) {
  return { r: r, det: r.nextElementSibling };
});
function sortRows() {
  var key = state.sort, dir = state.dir === "asc" ? 1 : -1;
  var sorted = PAIRS.slice().sort(function (a, b) {
    var av, bv;
    if (key === "who") { av = a.r.dataset.who; bv = b.r.dataset.who; }
    else if (key === "status") { av = a.r.dataset.st; bv = b.r.dataset.st; }
    else if (key === "system") { av = a.r.dataset.sys; bv = b.r.dataset.sys; }
    else { av = a.r.dataset.date; bv = b.r.dataset.date; }
    if (av < bv) return -dir;
    if (av > bv) return dir;
    return 0;
  });
  var tbody = $("#qtbody");
  sorted.forEach(function (p) { tbody.appendChild(p.r); tbody.appendChild(p.det); });
  $$("th[data-sort]").forEach(function (th) {
    th.setAttribute("aria-sort", th.dataset.sort === key
      ? (dir === 1 ? "ascending" : "descending") : "none");
  });
}
$$("th[data-sort]").forEach(function (th) {
  th.tabIndex = 0;
  th.addEventListener("click", function () {
    if (state.sort === th.dataset.sort) state.dir = state.dir === "asc" ? "desc" : "asc";
    else { state.sort = th.dataset.sort; state.dir = th.dataset.sort === "date" ? "desc" : "asc"; }
    sortRows();
    apply();
    syncUrl();
  });
});

var visRows = [];
function match(r) {
  if (state.ch !== "all" && r.dataset.ch !== state.ch) return false;
  if (state.st !== "all" && r.dataset.st !== state.st) return false;
  if (state.sys !== "all" && r.dataset.sys !== state.sys) return false;
  if (state.df !== "all" && r.dataset.df !== state.df) return false;
  if (state.q && r.dataset.txt.indexOf(state.q) === -1) return false;
  return true;
}
function apply() {
  var rows = $$("#qtbody tr.qrow");
  var kept = 0, total = 0;
  visRows = [];
  rows.forEach(function (r) {
    var m = match(r);
    if (m) total++;
    var vis = m && kept < shown;
    if (vis) { kept++; visRows.push(r); }
    r.classList.toggle("hide", !vis);
    var det = r.nextElementSibling;
    if (det && det.classList.contains("qdet"))
      det.classList.toggle("hide", !vis || !det.classList.contains("open"));
  });
  $("#qcount").textContent = kept + " of " + total;
  $("#morebtn").classList.toggle("hide", kept >= total);
  /* only when filters hid existing rows; an empty vault has its own message */
  $("#qempty").classList.toggle("hide", total !== 0 || PAIRS.length === 0);
  /* the sidebar badge stays the open-question count on purpose: it must
     agree with the bell, not drift into "rows currently matching" */
  ss("lp-shown", String(shown));
}
function setGroup(k, v) {
  state[k] = v;
  $$('.fchip[data-k="' + k + '"]').forEach(function (c) {
    var on = c.dataset.v === v;
    c.classList.toggle("on", on);
    c.setAttribute("aria-pressed", on ? "true" : "false");
  });
}
$$(".fchip[data-k]").forEach(function (c) {
  c.tabIndex = 0;
  c.setAttribute("role", "button");
  c.addEventListener("click", function () {
    setGroup(c.dataset.k, c.dataset.v);
    shown = PAGE;
    apply();
    syncUrl();
  });
});
$("#sysSel").addEventListener("change", function () {
  state.sys = this.value;
  shown = PAGE;
  apply();
  syncUrl();
});
var searchApply = debounce(function (v) {
  state.q = v.trim().toLowerCase();
  shown = PAGE;
  apply();
  syncUrl();
}, 150);
$("#q").addEventListener("input", function () { searchApply(this.value); });
function clearFilters() {
  setGroup("ch", "all");
  setGroup("st", "all");
  setGroup("df", "all");
  state.sys = "all";
  $("#sysSel").value = "all";
  state.q = "";
  $("#q").value = "";
  shown = PAGE;
  apply();
  syncUrl();
}
$("#fclear").addEventListener("click", clearFilters);
$("#qemptyclear").addEventListener("click", clearFilters);
$("#morebtn").addEventListener("click", function () { shown = 1e9; apply(); });

/* ---- expandable rows + suggest/reply, with continuity across reloads ---- */
function toggleDet(row, focus) {
  var det = row.nextElementSibling;
  if (!det || !det.classList.contains("qdet")) return;
  var open = !det.classList.contains("open");
  clearTimeout(det._t);   /* a pending close must never hide a reopened row */
  if (open) det.classList.remove("hide");
  /* Force layout instead of waiting for a frame: requestAnimationFrame does
     not fire in a background or non-compositing tab, which left restored
     rows stuck closed after an auto-reload. Reading offsetHeight flushes
     the start value so the transition still runs when frames do arrive. */
  void det.offsetHeight;
  det.classList.toggle("open", open);
  if (!open) det._t = setTimeout(function () {
    if (!det.classList.contains("open")) det.classList.add("hide");
  }, reduceMotion ? 0 : 180);
  row.setAttribute("aria-expanded", open ? "true" : "false");
  ss("lp-open:" + det.dataset.id, open ? "1" : null);
  if (open && focus === "box") det.querySelector(".qbox").focus();
}
$$("#qtbody tr.qrow").forEach(function (r) {
  r.tabIndex = 0;
  r.setAttribute("role", "button");
  r.setAttribute("aria-expanded", "false");
  r.addEventListener("click", function (e) {
    if (e.target.closest("a, button, textarea, .alink")) return;
    toggleDet(r);
  });
});
function runReply(det) {
  var box = det.querySelector(".qbox");
  var msg = det.querySelector(".msg");
  var btn = det.querySelector(".replybtn");
  var text = box.value.trim();
  msg.className = "msg";
  if (!text) { msg.textContent = "Type the reply first."; msg.classList.add("bad"); return; }
  if (!LIVE) { msg.textContent = "Static file: replying needs the live server (panel.py --watch)."; return; }
  btn.disabled = true;
  btn.classList.add("spin");
  msg.textContent = "Updating the vault...";
  fetch("/reply", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: det.dataset.id, text: text }) })
    .then(function (r) { return r.json(); })
    .then(function (s) {
      btn.classList.remove("spin");
      if (s.ok) {
        holdUntil = Date.now() + 6000;
        ss("lp-draft:" + det.dataset.id, null);
        msg.textContent = "Vault updated. " + (s.platform_message || "");
        msg.classList.add("good");
        toast("Reply saved to the vault and filed as knowledge.", "good");
        var row = det.previousElementSibling;
        var pill = row.querySelector(".pill");
        pill.className = "pill st-answered";
        pill.textContent = "answered";
        row.dataset.st = "answered";
      } else {
        msg.textContent = "Failed: " + (s.error || "unknown error");
        msg.classList.add("bad");
        btn.disabled = false;
      }
    })
    .catch(function () {
      msg.textContent = "Could not reach the panel server.";
      msg.classList.add("bad");
      btn.disabled = false;
      btn.classList.remove("spin");
    });
}
$$("[data-act]").forEach(function (el) {
  el.addEventListener("click", function (e) {
    e.stopPropagation();
    var row = el.closest("tr.qrow");
    var det = row ? row.nextElementSibling : null;
    if (!det) return;
    if (!det.classList.contains("open")) toggleDet(row);
    if (el.dataset.act === "suggest") runAi(det, "search", false);
    else det.querySelector(".qbox").focus();
  });
});

/* ---- AI: the Claude CLI reads the vault; results persist in the vault ----
   Two modes share this code path. search = fast retrieval that quotes an
   existing passage verbatim. draft = a full reply composed from everything.
   Every finished result is cached server side, embedded in the page on the
   next build, and replayed here on load, so the reload that follows every
   vault change never throws away a generation. */
function aiOut(det, mode) { return det.querySelector('.aiout[data-mode="' + mode + '"]'); }
function aiBtn(det, mode) { return det.querySelector('[data-ai="' + mode + '"]'); }
function ageText(ts) {
  var s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 3600) return Math.round(s / 60) + "m ago";
  if (s < 86400) return Math.round(s / 3600) + "h ago";
  return Math.round(s / 86400) + "d ago";
}
function aiRender(det, mode, s, btn) {
  var out = aiOut(det, mode);
  out.style.display = "block";
  if (btn) { btn.disabled = false; btn.classList.remove("spin"); }
  out.innerHTML = "";
  var label = mode === "search" ? "retrieval" : "draft";

  if (s.state === "error") {
    out.innerHTML = '<div class="src">The ' + label + " could not run</div>"
      + "<pre>" + esc(s.error || "unknown error") + "</pre>";
    return;
  }

  var conf = typeof s.confidence === "number" ? s.confidence : 0;
  var cls = conf >= 60 ? "ok" : conf >= 30 ? "warn" : "crit";
  var bits = [(mode === "search" ? "found by " : "drafted by ") + (s.model || "claude")];
  if (s.effort) bits.push("effort " + s.effort);
  if (s.elapsed) bits.push(s.elapsed + "s");
  if (typeof s.cost === "number") bits.push("$" + s.cost.toFixed(2));
  if (s.at) bits.push(ageText(s.at));

  var src = document.createElement("div");
  src.className = "src";
  src.innerHTML = esc(bits.join(" \\u00b7 "));
  if (s.answer) {
    src.innerHTML += ' <span class="conf conf-' + cls + '">'
      + '<span class="confbar"><i style="width:' + conf + '%"></i></span>'
      + conf + "% confidence</span>";
  }
  var again = document.createElement("span");
  again.className = "regen";
  again.textContent = "regenerate";
  again.title = "Run it again and replace this cached result";
  again.addEventListener("click", function () { runAi(det, mode, true); });
  src.appendChild(again);
  out.appendChild(src);

  if (s.answer) {
    var pre = document.createElement("pre");
    pre.textContent = s.answer;
    out.appendChild(pre);
  } else {
    var none = document.createElement("div");
    none.className = "aimiss";
    none.textContent = mode === "search"
      ? "Nothing in the vault answers this yet."
      : "The model returned an empty answer.";
    out.appendChild(none);
  }
  if (s.missing) {
    var miss = document.createElement("div");
    var explains = mode === "search" && s.answer;
    miss.className = explains ? "ainote" : "aimiss";
    miss.textContent = explains ? "Why this matches: " + s.missing
      : (s.answer ? "Not in the vault: " : "") + s.missing;
    out.appendChild(miss);
  }
  if (s.sources && s.sources.length) {
    var srcs = document.createElement("div");
    srcs.className = "aisrc";
    srcs.textContent = "read: " + s.sources.join(" \\u00b7 ");
    out.appendChild(srcs);
  }
  if (s.answer) {
    var use = document.createElement("button");
    use.className = "btn tiny";
    use.textContent = "Use as draft";
    use.addEventListener("click", function () {
      var box = det.querySelector(".qbox");
      box.value = s.answer;
      ss("lp-draft:" + det.dataset.id, box.value);
      box.focus();
    });
    out.appendChild(use);
  }
}
function runAi(det, mode, force) {
  var out = aiOut(det, mode), btn = aiBtn(det, mode);
  out.style.display = "block";
  if (!LIVE) {
    out.textContent = "Static file: this needs the live server (panel.py --watch).";
    return;
  }
  btn.disabled = true;
  btn.classList.add("spin");
  var t0 = Date.now();
  var waiting = mode === "search" ? "Searching the vault" : "Claude is reading your vault";
  out.innerHTML = '<div class="src">' + waiting + "...</div>";
  var tick = out.querySelector(".src");
  var timer = setInterval(function () {
    tick.textContent = waiting + "... " + Math.round((Date.now() - t0) / 1000) + "s";
  }, 1000);
  function stop() { clearInterval(timer); }
  fetch("/suggest_ai", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: det.dataset.id, mode: mode, force: !!force }) })
    .then(function (r) { return r.json(); })
    .then(function (j) {
      if (!j.ok) throw new Error(j.error || "could not start");
      if (j.cached) { stop(); aiRender(det, mode, j, btn); return; }
      (function poll() {
        fetch("/suggest_ai_status", { method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job: j.job }) })
          .then(function (r) { return r.json(); })
          .then(function (s) {
            if (s.state === "running") { setTimeout(poll, 2000); return; }
            stop();
            aiRender(det, mode, s, btn);
          })
          .catch(function () {
            stop();
            aiRender(det, mode, { state: "error", error: "lost contact with the panel server" }, btn);
          });
      })();
    })
    .catch(function (e) {
      stop();
      aiRender(det, mode, { state: "error", error: String(e.message || e) }, btn);
    });
}
$$("[data-ai]").forEach(function (b) {
  b.addEventListener("click", function () {
    runAi(b.closest("tr.qdet"), b.dataset.ai, false);
  });
});

/* replay everything already generated, so a reload costs nothing */
Object.keys(AI_CACHE).forEach(function (key) {
  var sep = key.indexOf(":");
  var mode = key.slice(0, sep), qid = key.slice(sep + 1);
  var det;
  try { det = $('tr.qdet[data-id="' + CSS.escape(qid) + '"]'); } catch (e) { return; }
  if (det) aiRender(det, mode, AI_CACHE[key], aiBtn(det, mode));
});
$$("[data-reply]").forEach(function (b) {
  b.addEventListener("click", function () { runReply(b.closest("tr.qdet")); });
});
$("#qtbody").addEventListener("input", function (e) {
  if (e.target.classList.contains("qbox")) {
    var det = e.target.closest("tr.qdet");
    ss("lp-draft:" + det.dataset.id, e.target.value || null);
  }
});

/* ---- gaps and coverage drill into the question table ---- */
function drillTo(sys) {
  var sel = $("#sysSel");
  var has = Array.prototype.some.call(sel.options, function (o) { return o.value === sys; });
  state.sys = has ? sys : "all";
  sel.value = state.sys;
  setGroup("st", "no-source");
  shown = PAGE;
  apply();
  syncUrl();
  location.hash = "#questions";
}
$$(".grow").forEach(function (g) {
  g.tabIndex = 0;
  g.setAttribute("role", "button");
  g.addEventListener("click", function () { drillTo(g.dataset.sys); });
});
$$(".sysdrill").forEach(function (el) {
  el.tabIndex = 0;
  el.setAttribute("role", "button");
  el.addEventListener("click", function () { drillTo(el.dataset.sys); });
});

/* ---- view-all toggles ---- */
$$("[data-viewall]").forEach(function (b) {
  b.addEventListener("click", function () {
    var card = b.closest(".card");
    $$(".xtra", card).forEach(function (x) { x.classList.remove("hide"); });
    b.classList.add("hide");
  });
});

/* ---- clipboard ---- */
function copyText(text, el) {
  function done() {
    toast("Copied to clipboard.", "good");
    if (!el) return;
    if (el.dataset.busy) return;
    el.dataset.busy = "1";
    var old = el.innerHTML;
    el.textContent = "copied";
    setTimeout(function () { el.innerHTML = old; delete el.dataset.busy; }, 1400);
  }
  if (navigator.clipboard && navigator.clipboard.writeText)
    navigator.clipboard.writeText(text).then(done, done);
  else done();
}
document.addEventListener("click", function (e) {
  var el = e.target.closest("[data-copy]");
  if (el) { e.stopPropagation(); copyText(el.dataset.copy, el); }
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

/* ---- keyboard: search focus, j/k navigation, n next-open ---- */
var kIdx = -1;
function kFocus(i) {
  if (!visRows.length) return;
  kIdx = Math.max(0, Math.min(visRows.length - 1, i));
  $$("tr.kfocus").forEach(function (r) { r.classList.remove("kfocus"); });
  var r = visRows[kIdx];
  r.classList.add("kfocus");
  r.focus({ preventScroll: true });
  r.scrollIntoView({ block: "nearest" });
}
document.addEventListener("keydown", function (e) {
  var tag = (document.activeElement || {}).tagName;
  var typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault(); $("#q").focus(); $("#q").select(); return;
  }
  if (typing) {
    if (e.key === "Escape" && document.activeElement === $("#q")) {
      $("#q").value = ""; state.q = ""; apply(); syncUrl();
    }
    return;
  }
  if (e.key === "/") { e.preventDefault(); $("#q").focus(); }
  else if (e.key === "j") kFocus(kIdx + 1);
  else if (e.key === "k") kFocus(kIdx - 1);
  else if (e.key === "Enter" && kIdx >= 0 && visRows[kIdx]) toggleDet(visRows[kIdx]);
  else if (e.key === "Escape") {
    $$("tr.qdet.open").forEach(function (det) { toggleDet(det.previousElementSibling); });
  } else if (e.key === "n") {
    var start = kIdx + 1;
    for (var i = 0; i < visRows.length; i++) {
      var r = visRows[(start + i) % visRows.length];
      if (r.dataset.st === "no-source" || r.dataset.st === "escalated") {
        kFocus(visRows.indexOf(r));
        if (!r.nextElementSibling.classList.contains("open")) toggleDet(r);
        break;
      }
    }
  } else if (e.key === "Enter" || e.key === " ") {
    var t = e.target;
    if (t.matches && t.matches(".fchip[data-k],.grow,.sysdrill,th[data-sort]")) {
      e.preventDefault(); t.click();
    }
  }
});

/* ---- question age markers ---- */
(function () {
  var now = Date.now();
  $$("#qtbody tr.qrow").forEach(function (r) {
    var t = Date.parse(r.dataset.date);
    if (isNaN(t)) return;
    var days = (now - t) / 86400000;
    var cell = r.querySelector("td.num");
    if (days > 30) cell.classList.add("agec");
    else if (days > 7) cell.classList.add("agew");
  });
})();

/* ---- tile count-up ---- */
(function () {
  if (reduceMotion) return;
  $$(".cu").forEach(function (el) {
    var target = parseInt(el.dataset.n, 10);
    if (isNaN(target) || target === 0) return;
    var t0 = performance.now();
    function step(t) {
      var p = Math.min(1, (t - t0) / 420);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(Math.round(target * (0.15 + 0.85 * eased)));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });
})();

/* ---- change toast across reloads ---- */
(function () {
  var cur = { open: parseInt($("#bellbtn .badge").textContent.replace(/,/g, ""), 10) || 0 };
  var prevRaw = lsGet("lp-counts");
  lsSet("lp-counts", JSON.stringify(cur));
  if (!prevRaw) return;
  try {
    var prev = JSON.parse(prevRaw);
    var d = cur.open - prev.open;
    if (d > 0) toast("+" + d + " new open question" + (d > 1 ? "s" : "") + " since your last view", "info");
  } catch (e) {}
})();

/* ---- link telemetry (locodev.dev admin API via the local server) ---- */
var ltFails = 0;
function rel(iso) {
  var t = Date.parse(iso);
  if (isNaN(t)) return esc(iso);
  var s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return Math.floor(s / 86400) + "d ago";
}
function ltChart(hc) {
  if (!hc.length) return '<div class="empty">no hourly data</div>';
  var max = 1;
  hc.forEach(function (p) { if (p.cnt > max) max = p.cnt; });
  var w = 240, bw = w / hc.length;
  var out = '<svg class="lchart" viewBox="0 0 ' + w + ' 64" preserveAspectRatio="none">';
  hc.forEach(function (p, i) {
    var bh = Math.max(1.5, p.cnt * 56 / max);
    out += '<rect x="' + (i * bw + 1).toFixed(1) + '" y="' + (60 - bh).toFixed(1)
      + '" width="' + (bw - 2).toFixed(1) + '" height="' + bh.toFixed(1) + '" rx="1.5">'
      + "<title>" + esc(p.hour) + ":00 \\u00b7 " + fmt(p.cnt) + " clicks</title></rect>";
  });
  return out + "</svg>";
}
function shortUrl(prefix, slug) {
  if (prefix === "root") return "https://locodev.dev/" + (slug === "_root" ? "" : slug);
  return "https://locodev.dev/" + prefix + "/" + slug;
}
function renderLinks(d) {
  var st = $("#lt-state"), body = $("#lt-body");
  if (!d.ok) {
    var m = {
      "not-configured": "not configured: set LOCODEV_ADMIN_SECRET in clickup-mcp/.env and restart the watcher",
      "auth": "login refused: check LOCODEV_ADMIN_SECRET",
      "network": "locodev.dev unreachable from this machine"
    };
    var txt = m[d.error] || ("error: " + d.error);
    st.innerHTML = esc(txt) + ' \\u00b7 <span class="retry" id="ltretry" role="button" tabindex="0">retry now</span>';
    body.innerHTML = '<div class="emptybox"><span class="eic">'
      + '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
      + 'stroke-width="1.9" stroke-linecap="round"><circle cx="12" cy="12" r="10"/>'
      + '<path d="M12 8v4"/><path d="M12 16h.01"/></svg></span>'
      + "<b>Link telemetry unavailable</b><p>" + esc(txt) + "</p></div>";
    var rt = $("#ltretry");
    if (rt) rt.addEventListener("click", function () { ltFails = 0; loadLinks(); });
    return;
  }
  var s = d.stats;
  st.textContent = fmt(s.clicks_24h) + " clicks in 24h \\u00b7 live from locodev.dev";
  var h = '<div class="ltk">';
  [[s.clicks_1h, "clicks 1h"], [s.clicks_24h, "clicks 24h"],
   [s.clicks_7d, "clicks 7d"], [s.total_links, "links"]].forEach(function (kv) {
    h += '<div class="mk"><div class="v">' + fmt(kv[0]) + '</div><div class="l">' + kv[1] + "</div></div>";
  });
  if (s.top_country)
    h += '<div class="mk"><div class="v">' + esc(s.top_country.country)
      + '</div><div class="l">top country \\u00b7 ' + fmt(s.top_country.cnt) + " clicks</div></div>";
  h += '</div><div class="ltgrid"><div>';
  h += '<p class="lsub">Clicks per hour, last 24h</p>' + ltChart(s.hourly_chart || []);
  h += '<p class="lsub">Top links</p><div class="scroll"><table><thead><tr>'
    + "<th>Link</th><th>1h</th><th>7d</th><th>Total</th><th></th></tr></thead><tbody>";
  var links = d.links || [];
  links.slice(0, 10).forEach(function (l) {
    var host = "";
    try { host = new URL(l.url).host; } catch (e) {}
    h += '<tr><td><span class="slug">/' + esc(l.prefix) + "/" + esc(l.slug)
      + '</span><br><span class="host">' + esc(host) + '</span></td><td class="num">'
      + fmt(l.clicks_1h) + '</td><td class="num">' + fmt(l.clicks_7d) + '</td><td class="num">'
      + fmt(l.total_clicks) + '</td><td class="num"><button class="btn tiny" data-copy="'
      + esc(shortUrl(l.prefix, l.slug)) + '">copy</button></td></tr>';
  });
  h += "</tbody>";
  var t1 = 0, t7 = 0, tt = 0;
  links.forEach(function (l) { t1 += l.clicks_1h || 0; t7 += l.clicks_7d || 0; tt += l.total_clicks || 0; });
  h += "<tfoot><tr><td>all " + fmt(links.length) + " links</td><td>" + fmt(t1)
    + "</td><td>" + fmt(t7) + "</td><td>" + fmt(tt) + "</td><td></td></tr></tfoot></table></div>";
  if (links.length > 10)
    h += '<div class="empty">' + fmt(links.length - 10) + " more links in the admin panel</div>";
  h += "</div><div>";
  h += '<p class="lsub">Recent clicks</p>';
  var rc = (s.recent_clicks || []).slice(0, 8);
  if (!rc.length) h += '<div class="empty">none yet</div>';
  rc.forEach(function (c) {
    h += '<div class="crow"><span class="slug">/' + esc(c.prefix) + "/" + esc(c.slug)
      + '</span><span class="n">' + esc(c.country_code || "?") + " \\u00b7 "
      + esc(c.referrer || "direct") + " \\u00b7 " + rel(c.clicked_at) + "</span></div>";
  });
  var refs = {};
  (s.recent_clicks || []).forEach(function (c) {
    var k = c.referrer || "direct";
    refs[k] = (refs[k] || 0) + 1;
  });
  var refList = Object.keys(refs).map(function (k) { return [k, refs[k]]; })
    .sort(function (a, b) { return b[1] - a[1]; }).slice(0, 5);
  if (refList.length) {
    h += '<p class="lsub" style="margin-top:20px">Referrers, last 30 clicks</p>';
    refList.forEach(function (r) {
      h += '<div class="crow"><span>' + esc(r[0]) + '</span><span class="n">' + r[1] + "</span></div>";
    });
  }
  h += '<p class="lsub" style="margin-top:20px">Countries, 7 days</p>';
  var cc = (d.countries || []).slice(0, 6);
  if (!cc.length) h += '<div class="empty">none yet \\u00b7 geo backfill returns after the Railway redeploy</div>';
  cc.forEach(function (c) {
    h += '<div class="crow"><span>' + esc(c.country) + '</span><span class="n">'
      + fmt(c.clicks) + "</span></div>";
  });
  h += "</div></div>";
  body.innerHTML = h;
}
function scheduleLt() {
  setTimeout(loadLinks, ltFails >= 3 ? 300000 : 60000);
}
function loadLinks() {
  if (!LIVE) { $("#lt-state").textContent = "needs the live watcher (panel.py --watch)"; return; }
  fetch("/links.json", { cache: "no-store" })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      ltFails = d.ok ? 0 : ltFails + 1;
      renderLinks(d);
      scheduleLt();
    })
    .catch(function () {
      ltFails++;
      $("#lt-state").textContent = "local server unreachable";
      scheduleLt();
    });
}
loadLinks();

/* ---- section highlighting in both navs ---- */
var navLinks = {};
$$(".nav a, .mnav a").forEach(function (a) {
  var id = a.getAttribute("href").slice(1);
  (navLinks[id] = navLinks[id] || []).push(a);
});
var io = new IntersectionObserver(function (es) {
  es.forEach(function (en) {
    if (!en.isIntersecting) return;
    $$(".nav a, .mnav a").forEach(function (a) { a.classList.remove("active"); });
    (navLinks[en.target.id] || []).forEach(function (a) { a.classList.add("active"); });
  });
}, { rootMargin: "-20% 0px -70% 0px" });
$$("section[id]").forEach(function (s) { io.observe(s); });

/* ---- boot: restore filters, sort, open rows, drafts, scroll ---- */
setGroup("ch", state.ch);
setGroup("st", state.st);
setGroup("df", state.df);
if (state.sys !== "all") {
  var sel = $("#sysSel");
  var hasOpt = Array.prototype.some.call(sel.options, function (o) { return o.value === state.sys; });
  if (hasOpt) sel.value = state.sys; else state.sys = "all";
}
if (state.q) $("#q").value = state.q;
if (state.sort !== "date" || state.dir !== "desc") sortRows();
else $$("th[data-sort]").forEach(function (th) {
  th.setAttribute("aria-sort", th.dataset.sort === "date" ? "descending" : "none");
});
apply();
try {
  for (var i = 0; i < sessionStorage.length; i++) {
    var key = sessionStorage.key(i);
    if (key && key.indexOf("lp-open:") === 0) {
      var det = $('tr.qdet[data-id="' + CSS.escape(key.slice(8)) + '"]');
      if (det && !det.previousElementSibling.classList.contains("hide")
          && !det.classList.contains("open"))
        toggleDet(det.previousElementSibling);
    }
    if (key && key.indexOf("lp-draft:") === 0) {
      var det2 = $('tr.qdet[data-id="' + CSS.escape(key.slice(9)) + '"]');
      if (det2) det2.querySelector(".qbox").value = sessionStorage.getItem(key) || "";
    }
  }
} catch (e) {}
(function () {
  var sy = ssGet("lp-scroll");
  if (sy !== null) {
    ss("lp-scroll", null);
    setTimeout(function () { scrollTo(0, parseInt(sy, 10) || 0); }, 30);
  }
})();
"""


# --------------------------------------------------------------------------
# Section builders
# --------------------------------------------------------------------------

def _tiles(d: dict, n_systems: int) -> str:
    hist = d.get("history") or []

    def series(key):
        return [p.get(key, 0) for p in hist][-60:]

    def delta(key, good_when_up: bool) -> str:
        dv = _delta24(hist, key)
        if not dv:
            return ""
        cls = ("good" if good_when_up else "bad") if dv > 0 else \
              ("bad" if good_when_up else "good")
        arrow = _icon("up", 10) if dv > 0 else _icon("down", 10)
        return (f'<span class="dlt {cls}">{arrow}{_fmt(abs(dv))}</span>'
                f'<span>vs 24h ago</span>')

    pct = d["written"] * 100 // d["total_facets"] if d["total_facets"] else 0
    tiles = [
        ("hero", "chat", "c-blue", "Open questions",
         f'<span class="cu" data-n="{d["open_q"]}">{_fmt(d["open_q"])}</span>',
         "waiting on you", delta("open", good_when_up=False),
         _spark(series("open"), "a", "var(--accent)")),
        ("", "check", "c-green", "Answered",
         f'<span class="cu" data-n="{d["answer_rate"]}">{d["answer_rate"]}</span>%',
         f"of {_fmt(len(d['questions']))} logged", delta("rate", good_when_up=True),
         _spark(series("rate"), "b", "var(--ok)")),
        ("", "book", "c-violet", "Catalog coverage",
         f'<span class="cu" data-n="{pct}">{pct}</span>%',
         f"{_fmt(d['written'])} of {_fmt(d['total_facets'])} notes", "",
         _spark(series("cov"), "c", "var(--info)")),
        ("", "alert", "c-red", "Critical systems",
         f'<span class="cu" data-n="{d["critical"]}">{_fmt(d["critical"])}</span>',
         f"{_fmt(d['urgent'])} more urgent", "",
         _spark(series("crit"), "d", "var(--crit)")),
        ("", "flag", "c-amber", "Complete",
         f'<span class="cu" data-n="{d["complete"]}">{_fmt(d["complete"])}</span>'
         f' <small>/ {n_systems}</small>',
         f"{_fmt(d['empty'])} still empty", "",
         _spark(series("complete"), "e", "var(--warn)")),
    ]
    cells = []
    for extra, icon, color, label, value, sub, dlt, spark in tiles:
        cls = f"tile {extra}".strip()
        cells.append(
            f'<div class="{cls}"><div class="h"><span class="tic {color}">{_icon(icon, 15)}</span>'
            f'{label}</div><div class="row"><div class="v">{value}</div>{spark}</div>'
            f'<div class="s"><span>{sub}</span>{dlt}</div></div>'
        )
    return f'<section id="overview"><div class="tiles">{"".join(cells)}</div></section>'


def _filters(questions: list) -> str:
    ch_counts: dict[str, int] = {}
    st_counts: dict[str, int] = {}
    for q in questions:
        ch_counts[q["channel"]] = ch_counts.get(q["channel"], 0) + 1
        st_counts[q["status"]] = st_counts.get(q["status"], 0) + 1
    statuses = [s for s in ("no-source", "escalated", "answered", "out-of-scope", "unknown")
                if s in st_counts]

    sys_counts: dict[str, int] = {}
    sys_names: dict[str, str] = {}
    for q in questions:
        if q["system"] == "-":
            continue
        sys_counts[q["system"]] = sys_counts.get(q["system"], 0) + 1
        sys_names[q["system"]] = q["system_name"]

    total = len(questions)
    parts = ['<div class="filters" id="filters" role="group" aria-label="Question filters">',
             f'<span class="fchip on" data-k="ch" data-v="all" aria-pressed="true">All channels '
             f'<span class="fc-n">{_fmt(total)}</span></span>']
    for ch in sorted(ch_counts):
        brand = _brand_icon(ch, 13)
        if not brand and ch in CH_COLORS:
            brand = f'<span class="cd" style="background:{CH_COLORS[ch]}"></span>'
        parts.append(f'<span class="fchip" data-k="ch" data-v="{escape(ch, quote=True)}" '
                     f'aria-pressed="false">{brand}{escape(ch)} '
                     f'<span class="fc-n">{_fmt(ch_counts[ch])}</span></span>')
    parts.append('<span class="fsep"></span>')
    parts.append('<span class="fchip on" data-k="st" data-v="all" aria-pressed="true">All statuses</span>')
    for st in statuses:
        parts.append(f'<span class="fchip" data-k="st" data-v="{escape(st, quote=True)}" '
                     f'aria-pressed="false" title="{escape(_STATUS_TITLE.get(st, st), quote=True)}">'
                     f'{escape(_STATUS_LABEL.get(st, st))} '
                     f'<span class="fc-n">{_fmt(st_counts[st])}</span></span>')
    parts.append('<span class="fsep"></span>')
    parts.append('<span class="fchip on" data-k="df" data-v="all" aria-pressed="true">Any difficulty</span>')
    for df in ("easy", "medium", "hard"):
        cnt = sum(1 for q in questions
                  if q.get("difficulty") == df and q["status"] != "answered")
        if not cnt:
            continue
        parts.append(f'<span class="fchip" data-k="df" data-v="{df}" aria-pressed="false">'
                     f'{df} <span class="fc-n">{_fmt(cnt)}</span></span>')
    parts.append('<span class="fsep"></span>')
    parts.append('<select id="sysSel" class="fchip" aria-label="Filter by system">'
                 '<option value="all">All systems</option>'
                 '<option value="-">catalog wide</option>')
    for slug in sorted(sys_counts, key=lambda s: -sys_counts[s]):
        parts.append(f'<option value="{escape(slug, quote=True)}">'
                     f'{escape(sys_names[slug])} ({sys_counts[slug]})</option>')
    parts.append('</select>')
    parts.append('<button class="fclear" id="fclear">clear filters</button>')
    parts.append('</div>')
    return "".join(parts)


def _question_rows(questions: list) -> str:
    rows = []
    for i, q in enumerate(questions):
        hid = "" if i < PAGE else " hide"
        sys_label = q["system_name"] if q["system"] != "-" else "catalog wide"
        sub = '<span class="m">subscriber</span>' if q["subscriber"] == "yes" else ""
        txt = escape(
            " ".join((q["code"], q["who"], q["text"], sys_label,
                      q["channel"], q["status"])).lower(),
            quote=True)
        qid = escape(q["id"], quote=True)

        rows.append(
            f'<tr class="qrow{hid}" data-id="{qid}" data-ch="{escape(q["channel"], quote=True)}"'
            f' data-st="{escape(q["status"], quote=True)}"'
            f' data-sys="{escape(q["system"], quote=True)}"'
            f' data-date="{escape(q["date"], quote=True)}"'
            f' data-who="{escape(q["who"].lower(), quote=True)}" data-df="{escape(q.get("difficulty", ""), quote=True)}" data-txt="{txt}">'
            f'<td class="idcell"><span class="qid" '
            f'data-copy="{escape(q["code"], quote=True)}" '
            f'title="Question code, stable across rebuilds. Click to copy.">'
            f'{escape(q["code"])}</span></td>'
            f'<td><span class="uc">{_avatar(q["who"])}'
            f'<span><span class="n">{escape(q["who"])}</span><br>{sub}</span></span></td>'
            f'<td class="stcell">{_pill(q["status"])}{_diff_pill(q)}</td>'
            f'<td><div class="qcell">{_mini_thumb(q)}'
            f'<div class="snip">{escape(q["text"][:230])}</div></div></td>'
            f'<td><span class="cval">{escape(sys_label)}</span></td>'
            f'<td>{_chn(q["channel"])}</td>'
            f'<td class="num"><span class="cval">{q["date"]}</span></td>'
            f'<td class="acts"><span class="rowacts">'
            f'<span class="alink" data-act="suggest" title="Search your notes and past answers">'
            f'{_icon("sparkle", 12)}Suggest answer</span>'
            f'<span class="alink" data-act="reply" title="Write a reply">'
            f'{_icon("replyic", 12)}Reply</span>'
            f'</span></td></tr>'
        )

        prov = [f'<span class="qid" data-copy="{escape(q["code"], quote=True)}">'
                f'{escape(q["code"])}</span>',
                f'{_chn(q["channel"])}', f'<span class="num">{q["date"]}</span>']
        copy_target = _safe_url(q.get("video_url", ""))
        if q.get("source"):
            prov.append(f'<span class="num">{escape(q["source"])}</span>')

        # The expanded card leads with the video still: recognising the
        # tutorial is most of the work of answering a comment about it.
        big = _thumb_url(q.get("video_id", ""), "mqdefault")
        vidcard = ""
        if big and q.get("video"):
            inner = (
                f'<img loading="lazy" alt="" width="168" height="94" '
                f'referrerpolicy="no-referrer" src="{big}" '
                f'onerror="this.classList.add(\'hide\')">'
                f'<span class="vmeta"><b>{escape(q["video"])}</b>'
                f'<span>{_icon("video", 12)}watch this moment on YouTube'
                f'{_icon("external", 11)}</span></span>')
            vidcard = (
                f'<a class="vidcard" href="{escape(copy_target, quote=True)}" '
                f'target="_blank" rel="noopener">{inner}</a>'
                if copy_target else f'<div class="vidcard">{inner}</div>')
        elif q.get("video"):
            vidcard = (f'<div class="vidcard novid"><span class="vmeta">'
                       f'<b>{escape(q["video"])}</b></span></div>')
        elif q["channel"] == "youtube":
            # Hand-logged questions carry no video. Absence has to be legible
            # and actionable, not an empty space that reads as a bug.
            vidcard = (f'<div class="vidcard novid"><span class="vmeta">'
                       f'<b>No video linked</b><span>logged by hand: add '
                       f'video_id: to this block in the vault to link it'
                       f'</span></span></div>')
        copy_btn = (f'<button class="btn tiny" data-copy="{escape(copy_target, quote=True)}">'
                    f'{_icon("copy", 12)}Copy link</button>') if copy_target else ""
        your_reply = ""
        if q.get("reply"):
            your_reply = (f'<div class="yourreply"><b>{_icon("check", 12)}Your reply on '
                          f'{escape(q["channel"])}</b>{escape(q["reply"])}</div>')

        rows.append(
            f'<tr class="qdet hide" data-id="{qid}"><td colspan="8">'
            f'<div class="detwrap"><div class="detinner"><div class="det">'
            f'{vidcard}'
            f'<div class="full">{escape(q["text"])}</div>'
            f'{your_reply}'
            f'<div class="prov">{" ".join(prov)}</div>'
            f'<div class="detbtns">'
            f'<button class="btn tiny" data-ai="search" '
            f'title="Fast retrieval: quotes an existing passage, never composes">'
            f'{_icon("sparkle", 13)}Search my notes</button>'
            f'<button class="btn tiny ai" data-ai="draft" '
            f'title="Writes a full reply from everything in the vault">'
            f'{_icon("brain", 13)}Ask Claude</button>'
            f'{copy_btn}</div>'
            f'<div class="aiout" data-mode="search"></div>'
            f'<div class="aiout" data-mode="draft"></div>'
            f'<textarea class="qbox" aria-label="Reply text" placeholder="Type the reply. '
            f'Reply always updates the vault and files the answer as searchable knowledge; '
            f'posting to YouTube for real needs the one-time OAuth setup."></textarea>'
            f'<div class="detbtns"><button class="btn tiny primary replybtn" data-reply>'
            f'{_icon("replyic", 13)}Send reply</button>'
            f'<span class="msg" aria-live="polite"></span></div>'
            f'</div></div></div></td></tr>'
        )
    return "".join(rows)


def _questions_card(d: dict) -> str:
    empty = (
        f'<tr><td colspan="8"><div class="emptybox">'
        f'<span class="eic">{_icon("inbox", 20)}</span>'
        f'<b>No questions logged yet</b>'
        f'<p>They arrive automatically from collect_youtube.py, or by hand in '
        f'Inbox/00 - Questions.md.</p></div></td></tr>')
    body = _question_rows(d["questions"]) if d["questions"] else empty
    arrow = f'<span class="sarrow">{_icon("up", 10)}</span>'
    return (
        f'<section class="card" id="questions">'
        f'<h2><span class="he">💬</span>Incoming questions'
        f'<span class="cnt">showing <span id="qcount"></span> &middot; '
        f'j/k navigate &middot; n next open</span></h2>'
        f'{_filters(d["questions"])}'
        f'<div class="scroll"><table aria-label="Incoming questions"><thead><tr>'
        f'<th scope="col">ID</th>'
        f'<th scope="col" data-sort="who" aria-sort="none">User{arrow}</th>'
        f'<th scope="col" data-sort="status" aria-sort="none">Status{arrow}</th>'
        f'<th scope="col">Question</th>'
        f'<th scope="col" data-sort="system" aria-sort="none">System{arrow}</th>'
        f'<th scope="col">Channel</th>'
        f'<th scope="col" data-sort="date" aria-sort="descending">Date{arrow}</th>'
        f'<th scope="col"></th>'
        f'</tr></thead><tbody id="qtbody">{body}</tbody></table></div>'
        f'<div class="emptybox hide" id="qempty">'
        f'<span class="eic">{_icon("filter", 20)}</span>'
        f'<b>Nothing matches these filters</b>'
        f'<p>Try widening the channel, status or system filter.</p>'
        f'<button class="btn tiny" id="qemptyclear">Clear filters</button></div>'
        f'<button class="linkbtn" id="morebtn">View all questions &rarr;</button>'
        f'</section>'
    )


def _answers_card(d: dict) -> str:
    answers = d.get("answers") or []
    week = 0
    if answers:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        week = sum(1 for a in answers if a["when"][:10] >= cutoff)
    rows = []
    for i, a in enumerate(answers):
        hid = "" if i < 5 else " xtra hide"
        posted = ('<span class="pill st-ok">posted to youtube</span>' if a["posted"]
                  else '<span class="pill st-unknown">vault only</span>')
        rows.append(
            f'<div class="arow{hid}"><div class="hd">{_avatar(a["who"], "sm")}'
            f'<b>{escape(a["who"])}</b>{_chn(a["channel"])}{posted}'
            f'<span class="w">{escape(a["when"])}</span></div>'
            f'<div class="q">{escape(a["q"])}</div>'
            f'<div class="a">{escape(a["a"])}</div></div>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(answers)} replies</button>'
            if len(answers) > 5 else "")
    body = "".join(rows) if rows else (
        f'<div class="emptybox"><span class="eic">{_icon("replyic", 20)}</span>'
        f'<b>No replies sent from the panel yet</b>'
        f'<p>Expand a question, type an answer and hit Send reply: it lands here, in '
        f'Inbox/02 - Answered.md, and in the searchable knowledge base.</p></div>')
    return (
        f'<section class="card" id="answers">'
        f'<h2><span class="he">✅</span>Answers sent'
        f'<span class="cnt">{_fmt(len(answers))} logged &middot; {week} this week</span></h2>'
        f'{body}{more}</section>'
    )


def _gaps_card(d: dict) -> str:
    rows = []
    for i, g in enumerate(d["gaps"]):
        hid = "" if i < 8 else " xtra hide"
        sys_val = "-" if g["key"] == "general" else g["key"]
        last = max((q["date"] for q in g["questions"]), default="")
        last_html = f'<small>last asked {last}</small>' if last else ""
        rows.append(
            f'<div class="grow{hid}" data-sys="{escape(sys_val, quote=True)}" '
            f'title="Filter the question list to this gap">'
            f'<span>{escape(g["label"])}{last_html}</span>'
            f'<span class="gcnt">{g["count"]}</span></div>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(d["gaps"])} gaps</button>'
            if len(d["gaps"]) > 8 else "")
    body = "".join(rows) if rows else (
        f'<div class="emptybox"><span class="eic">{_icon("check", 20)}</span>'
        f'<b>No open gaps</b><p>Nothing is marked no-source right now.</p></div>')
    return (f'<section class="card" id="gaps"><h2><span class="he">🎯</span>Gaps to close'
            f'<span class="cnt">click to filter</span></h2>{body}{more}</section>')


def _priority_card(d: dict, n_facets: int) -> str:
    queue = [s for s in d["systems"] if s["demand"] > 0 and s["done"] < n_facets]
    rows = []
    for i, s in enumerate(queue):
        hid = "" if i < 8 else " xtra hide"
        rows.append(
            f'<div class="prow{hid}"><span class="i">{i + 1}</span>'
            f'<span class="n" title="{escape(s["name"], quote=True)}">{escape(s["name"])}</span>'
            f'<span class="pbar"><i style="width:{s["pct"]}%"></i></span>'
            f'<span class="pct">{s["pct"]}%</span></div>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(queue)}</button>'
            if len(queue) > 8 else "")
    body = "".join(rows) if rows else '<div class="empty">No gaps with recorded demand.</div>'
    return (f'<section class="card" id="priority"><h2><span class="he">🔥</span>Priority queue'
            f'<span class="cnt">demand 60% &middot; gap 40%</span></h2>{body}{more}</section>')


def _coverage_card(d: dict, facets: list) -> str:
    n_facets = len(facets)
    labels = [lbl for (_k, lbl, _p, _w) in facets]
    rows = []
    for i, s in enumerate(d["systems"]):
        hid = "" if i < 8 else " xtra hide"
        cov = s["done"] * 100 // n_facets
        cls = "g" if cov >= 80 else ("a" if cov >= 40 else "r")
        missing = [lbl for lbl, ok in zip(labels, s["facets"]) if not ok]
        tip = ("complete" if not missing else "missing: " + ", ".join(missing))
        upill = (f' <span class="pill u-{s["urgency"]}">{s["urgency"]}</span>'
                 if s["urgency"] in ("critical", "urgent") else "")
        rows.append(
            f'<tr class="{hid.strip()}"><td><span class="sysdrill" '
            f'data-sys="{escape(s["slug"], quote=True)}" '
            f'title="Filter questions to this system">{escape(s["name"])}</span>{upill}</td>'
            f'<td class="num">{s["done"]}/{n_facets}</td>'
            f'<td class="num">{_fmt(s["demand"]) if s["demand"] else "-"}</td>'
            f'<td><span class="cbar" title="{escape(tip, quote=True)}"><span class="pbar">'
            f'<i class="{cls}" style="width:{cov}%"></i></span><b>{cov}%</b></span></td></tr>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(d["systems"])} systems</button>'
            if len(d["systems"]) > 8 else "")
    return (
        f'<section class="card" id="systems"><h2><span class="he">📚</span>Documentation coverage</h2>'
        f'<div class="scroll"><table aria-label="Documentation coverage"><thead><tr>'
        f'<th scope="col">System</th><th scope="col">Done</th>'
        f'<th scope="col">Asked</th><th scope="col">Coverage</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>{more}</section>'
    )


def _people_card(d: dict) -> str:
    rows = []
    for i, p in enumerate(d["people"]):
        hid = "" if i < 8 else " xtra hide"
        tags = ""
        if p.get("esc"):
            tags += ' <span class="tag esc">escalated</span>'
        if p.get("lead"):
            tags += ' <span class="tag lead">lead</span>'
        if p["subscriber"] == "yes":
            tags += ' <span class="tag sub">sub</span>'
        rows.append(
            f'<tr class="{hid.strip()}"><td><span class="uc">{_avatar(p["who"], "sm")}'
            f'<span class="n">{escape(p["who"])}{tags}</span></span></td>'
            f'<td class="num">{p["asked"]}</td><td class="num">{p["open"]}</td>'
            f'<td class="num">{p["last"]}</td></tr>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(d["people"])} users</button>'
            if len(d["people"]) > 8 else "")
    body = "".join(rows) if rows else (
        '<tr><td colspan="4"><div class="empty">Nobody logged yet.</div></td></tr>')
    return (
        f'<section class="card" id="people"><h2><span class="he">👥</span>Who is asking'
        f'<span class="cnt">{_fmt(len(d["people"]))} people</span></h2>'
        f'<div class="scroll"><table aria-label="People asking questions"><thead><tr>'
        f'<th scope="col">User</th><th scope="col">Asked</th>'
        f'<th scope="col">Open</th><th scope="col">Last</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div>{more}</section>'
    )


def _videos_card(d: dict) -> str:
    videos = d["videos"]
    transcripts = sum(1 for v in videos if v["transcript"])
    untagged = sum(1 for v in videos if not v.get("system") or v.get("system") == "-")
    rows = []
    for i, v in enumerate(videos):
        hid = "" if i < 6 else " xtra hide"
        title = escape(v["name"][11:] if len(v["name"]) > 11 else v["name"])
        vurl = _safe_url(v.get("url", ""))
        if vurl:
            title = (f'<a href="{escape(vurl, quote=True)}" target="_blank" '
                     f'rel="noopener">{title}</a>')
        if v.get("video_id"):
            thumb = (f'<span class="vthumb"><img loading="lazy" alt="" width="68" height="38" '
                     f'referrerpolicy="no-referrer" '
                     f'src="https://i.ytimg.com/vi/{escape(v["video_id"], quote=True)}/mqdefault.jpg" '
                     f'onerror="this.classList.add(\'hide\')">'
                     f'<span class="ph">{_icon("video", 14)}</span></span>')
        else:
            thumb = f'<span class="vthumb"><span class="ph">{_icon("video", 14)}</span></span>'
        tag = ""
        if v.get("system") and v["system"] != "-":
            tag = f'<span class="vtag">{escape(v["system"])}</span>'
        rows.append(
            f'<div class="vrow{hid}">{thumb}<span class="t">{title}</span>{tag}'
            f'<span class="d">{escape(v["published"])}</span></div>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(videos)} videos</button>'
            if len(videos) > 6 else "")
    body = "".join(rows) if rows else '<div class="empty">No videos collected yet.</div>'
    return (
        f'<section class="card" id="videos"><h2><span class="he">🎬</span>Videos'
        f'<span class="cnt">{_fmt(len(videos))} &middot; {transcripts} transcripts '
        f'&middot; {untagged} untagged</span></h2>{body}{more}</section>'
    )


def _links_card() -> str:
    """Skeleton only: the data comes client-side from the local /links.json,
    which the panel server fills by calling the locodev.dev admin API
    server-to-server. The page never sees the secret or the token."""
    skel = ('<div class="ltk">'
            + '<div class="mk skel skel-tile"></div>' * 4
            + '</div><div class="skel skel-row" style="width:70%"></div>'
              '<div class="skel skel-row" style="width:52%"></div>'
              '<div class="skel skel-row" style="width:61%"></div>')
    return (
        f'<section class="card" id="links"><h2><span class="he">🔗</span>Link telemetry'
        f'<span class="cnt" id="lt-state" role="status" aria-live="polite">loading...</span>'
        f'<a class="admlink" href="https://locodev.dev/adminlocoILco" target="_blank" '
        f'rel="noopener">open admin {_icon("external", 12)}</a></h2>'
        f'<div id="lt-body">{skel}</div>'
        f'</section>'
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
        f'<section class="card" id="sources"><h2><span class="he">👀</span>Measured, and blind</h2>'
        f'{"".join(rows)}</section>'
    )


_NAV = [
    ("overview", "home", "Overview", ""),
    ("questions", "chat", "Questions", "open_q"),
    ("answers", "check", "Answers", "answers"),
    ("systems", "grid", "Systems", ""),
    ("people", "users", "People", ""),
    ("videos", "video", "Videos", ""),
    ("links", "link", "Links", ""),
    ("sources", "database", "Sources", ""),
]


def _nav_counts(d: dict) -> dict:
    return {"open_q": d["open_q"], "answers": len(d.get("answers") or [])}


def _sidebar(d: dict) -> str:
    counts = _nav_counts(d)
    parts = []
    for sid, icon, label, ckey in _NAV:
        cls = ' class="active"' if sid == "overview" else ""
        badge = ""
        if ckey and counts.get(ckey):
            badge = f'<span class="navcount">{_fmt(counts[ckey])}</span>'
        parts.append(f'<a href="#{sid}"{cls}>{_icon(icon)}{label}{badge}</a>')
    return (
        '<aside class="side">'
        '<div class="brand"><span class="mark">L</span>'
        '<div><b>LocoDev</b><small>Operations</small></div></div>'
        '<div class="navlabel">Workspace</div>'
        f'<nav class="nav" aria-label="Sections">{"".join(parts)}</nav>'
        '<div class="spacer"></div>'
        '<div class="me"><span class="av sm" style="--h:214">L</span>'
        f'<div><b>Local vault</b><small>F:\\LocoDev Vault</small></div></div>'
        '</aside>'
    )


def _mobile_nav() -> str:
    parts = []
    for sid, icon, label, _c in _NAV:
        cls = ' class="active"' if sid == "overview" else ""
        parts.append(f'<a href="#{sid}"{cls}>{_icon(icon, 14)}{label}</a>')
    return f'<nav class="mnav" aria-label="Sections">{"".join(parts)}</nav>'


def _header(d: dict, live: bool) -> str:
    if live:
        chip = ('<span class="chip" id="chip" data-state="live" role="status" '
                'aria-live="polite"><span class="dot"></span>'
                '<span id="chiptxt">live</span></span>')
    else:
        chip = (f'<span class="chip" id="chip" data-state="off" role="status" '
                f'aria-live="polite"><span class="dot"></span>'
                f'<span id="chiptxt">static build {escape(d["generated_at"])}</span></span>')
    theme_icons = "".join(
        f'<span class="ticon{" hide" if name != "auto" else ""}" data-icon="{name}">'
        f'{_icon(name, 14)}</span>'
        for name in ("auto", "moon", "sun")
    )
    return (
        f'<div class="top"><h1>Operations</h1>{chip}'
        f'<div class="search">{_icon("search", 15)}'
        f'<input id="q" type="search" placeholder="Search questions, users, systems..." '
        f'autocomplete="off" aria-label="Search questions"><kbd>Ctrl K</kbd></div>'
        f'<button class="btn primary" id="updbtn" aria-label="Rebuild the panel now">'
        f'{_icon("refresh", 14)}Update</button>'
        f'<button class="btn icon" id="filtbtn" aria-label="Jump to filters" title="Filters">'
        f'{_icon("filter", 15)}</button>'
        f'<button class="btn" id="themebtn" aria-label="Switch color theme">'
        f'{theme_icons}<span class="tlabel">Auto</span></button>'
        f'<button class="btn icon bell" id="bellbtn" aria-label="Open questions" '
        f'title="Open questions">{_icon("bell", 15)}'
        f'<span class="badge">{_fmt(d["open_q"])}</span></button></div>'
    )


def render_html(d: dict, live: bool, facets: list, instrumentation: list) -> str:
    n_systems = len(d["systems"])

    import json as _json
    # </script> inside embedded JSON would close the script tag early; the
    # cache holds model prose, so escaping it is not optional.
    ai_cache = (_json.dumps(d.get("ai_cache") or {})
                .replace("</", "<\\/").replace(" ", "\\u2028")
                .replace(" ", "\\u2029"))
    js = (JS.replace("__EPOCH__", str(d["epoch"]))
            .replace("__LIVE__", "true" if live else "false")
            .replace("__PAGE__", str(PAGE))
            .replace("__AI_CACHE__", ai_cache))

    diag = (f'generated {escape(d["generated_at"])} &middot; scan {d.get("scan_ms", "?")} ms '
            f'&middot; {_fmt(d.get("md_files", 0))} notes &middot; '
            f'{len(d.get("history") or [])} history points &middot; '
            f'the vault is the source of truth, the page keeps no data of its own')

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="theme-color" content="#3d63f5" />
<meta name="color-scheme" content="light dark" />
<title>LocoDev Operations</title>
<link rel="icon" href="{FAVICON}" />
<script>{HEAD_JS}</script>
<style>{CSS}</style>
</head>
<body>
<div class="app">
{_sidebar(d)}
<main class="main">
{_header(d, live)}
{_mobile_nav()}
{_tiles(d, n_systems)}
<div class="cols">
<div class="colmain">
{_questions_card(d)}
{_answers_card(d)}
</div>
<div class="rail">
{_gaps_card(d)}
{_priority_card(d, len(facets))}
{_coverage_card(d, facets)}
</div>
</div>
{_links_card()}
<div class="grid3">
{_people_card(d)}
{_videos_card(d)}
{_sources_card(instrumentation)}
</div>
<footer>{diag}</footer>
</main>
</div>
<div id="toast" role="status" aria-live="polite" data-kind="info">
<span class="ti">{_icon("sparkle", 14)}</span><span id="toasttxt"></span></div>
<script>{js}</script>
</body>
</html>
"""
