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

PAGE = 25  # rows per page; the pager offers 25 / 50 / 100

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
    # Discord's own mark. The stand-in drawn here before was an ellipse with
    # two dots, which reads as a face rather than as Discord, and the whole
    # point of the mark is to be recognised without being read.
    "discord": (
        '<path fill="#5865f2" d="M20.317 4.3698a19.7913 19.7913 0 0 0-4.8851-1.5152'
        '.0741.0741 0 0 0-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762'
        '-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 0 0'
        '-.0785-.037 19.7363 19.7363 0 0 0-4.8852 1.515.0699.0699 0 0 0-.0321.0277'
        'C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 0 0 .0312.0561c2.0528'
        ' 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 0 0 .0842-.0276c.4616-.6304'
        '.8731-1.2952 1.226-1.9942a.076.076 0 0 0-.0416-.1057c-.6528-.2476-1.2743'
        '-.5495-1.8722-.8923a.077.077 0 0 1-.0076-.1277c.1258-.0943.2517-.1923.3718'
        '-.2914a.0743.0743 0 0 1 .0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a'
        '.0739.0739 0 0 1 .0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 0 1'
        '-.0066.1276 12.2986 12.2986 0 0 1-1.873.8914.0766.0766 0 0 0-.0407.1067c'
        '.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 0 0 .0842.0286c1.961-.6067'
        ' 3.9495-1.5219 6.0023-3.0294a.077.077 0 0 0 .0313-.0552c.5004-5.177-.8382'
        '-9.6739-3.5485-13.6604a.061.061 0 0 0-.0312-.0286ZM8.02 15.3312c-1.1825 0'
        '-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0'
        ' 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189Zm7.9748 0'
        'c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189'
        ' 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z"/>'
    ),
}


def _icon(name: str, size: int = 16) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.9" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{_ICONS[name]}</svg>'
    )


def _brand_sprite() -> str:
    """Every brand mark, drawn once, at the top of the document.

    Discord's own path is 1.4 KB. Inlined per row across a few thousand
    rows that was 3.3 MB of the same drawing, which is most of what this
    page weighed. Defined once and referenced, a mark costs about forty
    bytes wherever it appears.
    """
    symbols = "".join(
        f'<symbol id="bi-{name}" viewBox="0 0 24 24">{body}</symbol>'
        for name, body in _BRAND.items()
    )
    return f'<svg width="0" height="0" aria-hidden="true" style="position:absolute">{symbols}</svg>'


def _brand_icon(name: str, size: int = 14) -> str:
    if name not in _BRAND:
        return ""
    return (f'<svg width="{size}" height="{size}" aria-hidden="true" '
            f'class="bi"><use href="#bi-{name}"></use></svg>')


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


def _avatar(who: str, size: str = "", url: str = "") -> str:
    import hashlib
    idx = int(hashlib.sha1(who.encode()).hexdigest()[:6], 16) % len(_AV_HUES)
    hue = _AV_HUES[idx]
    initial = escape((who.lstrip("@")[:1] or "?").upper())
    cls = f"av {size}".strip()
    # The coloured initial stays underneath: a CDN image that fails to load
    # leaves an identity behind rather than a hole.
    img = ""
    if _safe_url(url):
        img = (f'<img loading="lazy" alt="" referrerpolicy="no-referrer" '
               f'src="{escape(url, quote=True)}">')
    return (f'<span class="{cls}" style="--h:{hue}" aria-hidden="true">'
            f'{initial}{img}</span>')


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


_ROLE_CLASS = {
    "LocoPremium": "r-premium", "LocoStandard": "r-standard",
    "LocoBasic": "r-basic", "LocoHelper": "r-helper",
    "LocoDev Team": "r-team", "LocoTester": "r-team", "Patreon": "r-patreon",
}


def _roles(q: dict, limit: int = 3) -> str:
    """What the asker is in the server today, tiers first."""
    roles = q.get("roles") or []
    if not roles:
        return ""
    out = []
    for r in roles[:limit]:
        out.append(f'<span class="role {_ROLE_CLASS.get(r, "r-other")}">'
                   f'{escape(r)}</span>')
    if len(roles) > limit:
        rest = escape(", ".join(roles[limit:]), quote=True)
        out.append(f'<span class="role r-other" title="{rest}">'
                   f'+{len(roles) - limit}</span>')
    return "".join(out)


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
    "escalated": "🚨",      # siren
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


_DIFF_TIP = {
    "easy": "easy: the vault already has a close match, Search my notes should find it",
    "medium": "medium: related material exists but nothing that answers it directly",
    "hard": "hard: nothing in the vault covers this yet, it is a documentation gap",
}


def _row_lookups() -> dict:
    """The small tables the row markup needs, handed to the browser.

    The rows are built there now, and these are the only thing a second
    renderer would otherwise have to keep a copy of. Passing the data means
    there is still one source for what a status is called and which colour
    a role gets.
    """
    return {"st_label": _STATUS_LABEL, "st_title": _STATUS_TITLE,
            "st_emoji": _STATUS_EMOJI, "diff_emoji": _DIFF_EMOJI,
            "diff_tip": _DIFF_TIP, "hues": list(_AV_HUES),
            "role_class": _ROLE_CLASS}


def _diff_pill(q: dict) -> str:
    """How much material the vault already has for this question."""
    d = q.get("difficulty")
    if not d or q.get("status") == "answered":
        return ""
    tips = _DIFF_TIP
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
    /* chart series, validated for the dark surface (OKLCH band 0.48-0.67) */
    --ch-main:#6684fa; --ch-warn:#bd8324; --ch-mute:#707b90;
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
  /* chart series, validated for white (CVD dE >= 16 on every pair) */
  --ch-main:#365df5; --ch-warn:#9a600a; --ch-mute:#838da1;
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
.chip[data-state="stale"] { border-color:var(--accent); color:var(--accent); }
.chip[data-state="stale"] .dot { background:var(--accent); box-shadow:0 0 0 3px var(--accent-bg); }
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
/* One screen at a time. The author rules below set display on these
   elements, which would beat the browser's own [hidden] styling, so the
   hiding has to say so out loud. */
[hidden] { display:none !important; }

/* ---- one customer, opened in place ---- */
tr.crow, tr.prodrow { cursor:pointer; }
tr.crow:hover td:first-child, tr.prodrow:hover td:first-child {
  box-shadow:inset 2px 0 0 var(--accent); }
tr.copen td { background:var(--surface2); }
tr.cdet > td, tr.pdet > td { padding:0; background:var(--surface2); }
.cprofile { padding:var(--s4) var(--s4) var(--s5); display:grid; gap:var(--s3); }
.chead { display:flex; gap:var(--s3); align-items:flex-start; }
.chead b { font-size:var(--t-lg); }
.cav { width:40px; height:40px; border-radius:var(--r-full); flex:none;
  object-fit:cover; }
.cabout { display:flex; gap:var(--s2); align-items:center; flex-wrap:wrap; }
.clabel { font-family:var(--mono); font-size:var(--t-2xs); color:var(--ink3);
  text-transform:uppercase; letter-spacing:.08em; margin-right:var(--s2); }
.ctl { display:grid; gap:var(--s2); max-height:420px; overflow-y:auto;
  padding-right:var(--s2); }
.cev { border-left:2px solid var(--line); padding:var(--s2) 0 var(--s2) var(--s3); }
.cev.open { border-left-color:var(--warn); }
.cev[data-qid] { cursor:pointer; display:flex; flex-wrap:wrap;
  gap:var(--s2) var(--s3); align-items:flex-start; }
.cev[data-qid]:hover, .cev.composing { border-left-color:var(--accent); }
.cev .cthumb { width:96px; height:54px; object-fit:cover; flex:none;
  border-radius:var(--r-xs); }
.cev .cbody { flex:1; min-width:220px; }
.cev > .detwrap { flex-basis:100%; cursor:auto; }
.cev .detwrap { cursor:auto; }
/* the panel list is capped at 420px; a composer needs the room */
.ctl.composing { max-height:none; }
.vdesc { border:1px solid var(--line); border-radius:var(--r-sm);
  padding:var(--s3); display:grid; gap:var(--s2); }
.vdesc .descbox { min-height:200px; font-family:var(--mono);
  font-size:var(--t-xs); }
.descdraft pre { white-space:pre-wrap; max-height:320px; overflow-y:auto;
  border-left:2px solid var(--info-line); padding-left:var(--s3);
  color:var(--ink2); }
.cdate { font-family:var(--mono); font-size:var(--t-2xs); color:var(--ink3); }
.cq { font-weight:560; margin-top:2px; }
.ca { color:var(--ink2); margin-top:3px; padding-left:var(--s3);
  border-left:2px solid var(--ok-line); }
.cwait { color:var(--warn); font-size:var(--t-xs); margin-top:3px; }
.clink { font-size:var(--t-xs); }
.cedit { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
  gap:var(--s3); padding-top:var(--s3); border-top:1px solid var(--line); }
.cfield { display:grid; gap:4px; align-content:start; }
.cfield.wide { grid-column:1 / -1; }
.cedit select, .cedit input, .cedit textarea {
  font:inherit; font-size:var(--t-sm); color:var(--ink); background:var(--surface);
  border:1px solid var(--line); border-radius:var(--r-sm); padding:7px 9px;
  width:100%; }
.cedit textarea { resize:vertical; min-height:64px; font-family:inherit; }
.cedit select:focus, .cedit input:focus, .cedit textarea:focus {
  outline:2px solid var(--accent); outline-offset:1px; }
.cfield.wide:last-child { display:flex; align-items:center; gap:var(--s3); }
.cmsg { min-height:1em; }

.stagenote { margin:-6px 0 var(--s3); color:var(--ink3);
  font-size:var(--t-xs); padding-left:2px; }

/* ---- search results, over everything ---- */
.search { position:relative; }
.qres { position:absolute; top:calc(100% + 6px); left:0; right:0; z-index:40;
  background:var(--surface); border:1px solid var(--line);
  border-radius:var(--r-md); box-shadow:var(--el-2); padding:var(--s2);
  max-height:60vh; overflow-y:auto; }
.qrgroup { padding:var(--s2) 0; border-bottom:1px solid var(--line2); }
.qrgroup:last-child { border-bottom:0; }
.qrgroup .clabel { display:block; padding:0 var(--s2) 4px; }
.qritem { display:block; width:100%; text-align:left; background:none;
  border:0; color:var(--ink); font:inherit; font-size:var(--t-sm);
  padding:6px var(--s2); border-radius:var(--r-sm); cursor:pointer; }
.qritem:hover, .qritem:focus-visible { background:var(--accent-bg); color:var(--accent); }
.qritem .note { color:var(--ink3); font-size:var(--t-xs); }


/* ---- charts. Recessive grid, thin marks, text in ink tokens ---- */
.chart { width:100%; height:auto; display:block; margin-top:var(--s2); }
.chtitle { font-family:var(--mono); font-size:var(--t-2xs); color:var(--ink3);
  text-transform:uppercase; letter-spacing:.08em; margin:var(--s4) 0 2px; }
.chlegend { display:flex; gap:var(--s4); font-size:var(--t-xs);
  color:var(--ink2); margin:2px 0; }
.chlegend i { display:inline-block; width:10px; height:10px; border-radius:3px;
  margin-right:5px; vertical-align:-1px; }
.chx { font-family:var(--mono); font-size:9px; fill:var(--ink3); }
.chend { font-family:var(--mono); font-size:10px; font-weight:600; fill:var(--ink); }
.chgrid { stroke:var(--line2); stroke-width:1; }
.chaxis { stroke:var(--line); stroke-width:1; }
.chbar rect { transition:opacity var(--dur) var(--ease); }
.chbar:hover rect { opacity:.82; }
.chline { fill:none; stroke:var(--ch-main); stroke-width:2;
  stroke-linejoin:round; stroke-linecap:round; }
.charea { fill:var(--ch-main); opacity:.13; }
.chhit { fill:transparent; }
.chhit:hover { fill:var(--ch-main); opacity:.25; }

/* ---- a source on Admin opens into its details ---- */
.srow[data-src] { cursor:pointer; }
.srow[data-src]:hover .nm { color:var(--accent); }
.srcdet { background:var(--surface2); border-radius:var(--r-md);
  padding:var(--s3) var(--s4); margin:0 0 var(--s2); display:grid; gap:var(--s2);
  font-size:var(--t-sm); }
.srcdet .clabel { margin-right:var(--s2); }
.srcdet ul { margin:0; padding:0; list-style:none; }
.srcdet li { padding:2px 0; color:var(--ink2); }
.srcdet li b { color:var(--ink); font-family:var(--mono);
  font-variant-numeric:tabular-nums; }

/* ---- the export form ---- */
.expbox { display:flex; gap:var(--s3); align-items:center; flex-wrap:wrap;
  width:100%; padding:var(--s2) 0; }
.expbox label { display:inline-flex; gap:6px; align-items:center;
  font-size:var(--t-xs); color:var(--ink3); }
.expbox select { font:inherit; font-size:var(--t-sm); color:var(--ink);
  background:var(--surface); border:1px solid var(--line);
  border-radius:var(--r-sm); padding:4px 8px; }

/* ---- what is owed, at the top of Home ---- */
#attention { margin-bottom:var(--s4); }
.att { display:grid; gap:2px; padding:var(--s3) 0 var(--s3) var(--s4);
  border-bottom:1px solid var(--line2); position:relative; }
.att:last-of-type { border-bottom:0; }
.att::before { content:""; position:absolute; left:0; top:var(--s3); bottom:var(--s3);
  width:3px; border-radius:2px; background:var(--ink3); }
.att-crit::before { background:var(--crit); }
.att-warn::before { background:var(--warn); }
.att-info::before { background:var(--accent); }
.att b { font-size:var(--t-base); font-weight:640; }
.att .note { color:var(--ink3); font-size:var(--t-xs); }

/* ---- the overview dashboard ---- */
.grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(380px,100%),1fr));
  gap:var(--s4); margin-top:var(--s4); }
.grid2 .card { margin-bottom:0; }
.orow { display:grid; grid-template-columns:minmax(9ch,auto) minmax(60px,1fr) auto;
  gap:var(--s3); align-items:center; padding:var(--s3) 0;
  border-bottom:1px solid var(--line2); }
.orow:last-of-type { border-bottom:0; }
.olabel { display:inline-flex; align-items:center; gap:6px; font-weight:600;
  font-size:var(--t-sm); }
.ovals { text-align:right; font-size:var(--t-xs); color:var(--ink2);
  white-space:nowrap; }
.ovals b { font-family:var(--mono); font-size:var(--t-base); color:var(--ink);
  font-variant-numeric:tabular-nums; }
.obig { padding:var(--s2) 0 var(--s3); }
.obig b { display:block; font-family:var(--mono); font-size:var(--t-3xl);
  line-height:1.05; font-variant-numeric:tabular-nums; }
.orow2 { padding:var(--s3) 0; border-bottom:1px solid var(--line2);
  font-size:var(--t-sm); }
.orow2:last-of-type { border-bottom:0; }
.orow2 .nm { font-weight:600; }
.orow2 svg { vertical-align:-2px; }
.oq { color:var(--ink2); margin-top:3px; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap; }
.cols2.solo, .grid3.solo { grid-template-columns:minmax(0,1fr); }
.cols2 { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr);
  gap:var(--s4); align-items:start; }
.cols2 .card { margin-bottom:var(--s4); }
@media (max-width:1050px) { .cols2 { grid-template-columns:minmax(0,1fr); } }
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
.pager { display:flex; align-items:center; gap:var(--s3); justify-content:center;
  padding:var(--s3) 0 var(--s1); flex-wrap:wrap; }
.pgpos { font-size:var(--t-sm); color:var(--ink2); font-variant-numeric:tabular-nums; }
.pgpos b { color:var(--ink); font-family:var(--mono); }
.pgsize { display:inline-flex; align-items:center; gap:var(--s2);
  font-size:var(--t-xs); color:var(--ink3); }
.pgsize select { padding:4px 26px 4px 9px; font-size:var(--t-xs); }

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
.av { position:relative; overflow:hidden; }
.av img { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
.roles { display:flex; gap:3px; flex-wrap:wrap; margin-top:2px; }
.role { font-size:var(--t-2xs); font-weight:650; padding:1px 6px;
  border-radius:var(--r-xs); background:var(--mute-bg); color:var(--ink2);
  white-space:nowrap; }
.r-premium { background:var(--info-bg); color:var(--info); }
.r-standard { background:var(--accent-bg); color:var(--accent); }
.r-basic { background:var(--ok-bg); color:var(--ok); }
.r-helper, .r-team { background:var(--warn-bg); color:var(--warn); }
.r-patreon { background:var(--crit-bg); color:var(--crit); }
.asker { display:flex; align-items:center; gap:var(--s2); flex-wrap:wrap;
  padding-bottom:var(--s2); border-bottom:1px solid var(--line2); }
.asker b { font-size:var(--t-md); }
.asker .w { color:var(--ink3); font-size:var(--t-xs); font-family:var(--mono); }
.askerpic { width:28px; height:28px; border-radius:var(--r-full); object-fit:cover; }
.uc .n { font-weight:600; font-size:var(--t-sm); line-height:1.3; letter-spacing:-.005em; }
.uc .m { color:var(--ink3); font-size:var(--t-2xs); }
.pill { display:inline-flex; align-items:center; gap:4px; padding:3px 9px;
  border-radius:var(--r-full); font-size:var(--t-2xs); font-weight:680;
  letter-spacing:.01em; white-space:nowrap; border:1px solid transparent; }
.pill { gap:5px; }
/* 433 rows of ordinary backlog in critical red said the everyday case was
   more urgent than the one question actually escalated. Unanswered is the
   normal state and reads neutral; red is reserved for escalation. */
.st-answered { background:var(--ok-bg); color:var(--ok); border-color:var(--ok-line); }
.st-no-source { background:var(--mute-bg); color:var(--ink2); border-color:var(--line); }
.st-escalated { background:var(--crit-bg); color:var(--crit); border-color:var(--crit-line); }
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
/* Amber marks the documentation gap, which is the thing worth acting on. */
.d-easy { background:var(--ok-bg); color:var(--ok); border-color:var(--ok-line); }
.d-medium { background:var(--mute-bg); color:var(--ink2); border-color:var(--line); }
.d-hard { background:var(--warn-bg); color:var(--warn); border-color:var(--warn-line); }
/* Question first and widest: it is what the operator reads to decide. */
.qcol { width:46%; }
.qtext { min-width:0; }
.qmeta { display:flex; gap:var(--s2); align-items:center; flex-wrap:wrap;
  margin-top:3px; font-size:var(--t-2xs); color:var(--ink3); }
.qmeta .mch { display:inline-flex; align-items:center; }
.qmeta .mvid { max-width:230px; overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; font-family:var(--mono); }
.hasai { color:var(--info); font-weight:700; }
.syscell { color:var(--ink2); font-size:var(--t-sm); }
.zero { color:var(--ink3); }
.nextfacet { color:var(--ink2); font-size:var(--t-sm); }
.deliver { color:var(--ink3); font-size:var(--t-xs); }
.answerbtn { font-weight:650; }
.snip { color:var(--ink2); max-width:none; display:-webkit-box; -webkit-line-clamp:2;
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
.ctxout { border:1px solid var(--line); border-radius:var(--r-md);
  padding:var(--s3) var(--s4); background:var(--surface); display:none;
  max-height:340px; overflow:auto; }
.ctxout .src { color:var(--ink3); font-size:var(--t-xs); margin-bottom:var(--s2);
  font-family:var(--mono); }
.ctxline { font-size:var(--t-sm); line-height:1.5; padding:2px 0;
  border-left:2px solid transparent; padding-left:var(--s2); }
.ctxline b { color:var(--ink); font-weight:640; }
.ctxline .w { color:var(--ink3); font-family:var(--mono); font-size:var(--t-2xs); }
.ctxline.self { border-left-color:var(--accent); background:var(--accent-bg);
  border-radius:var(--r-xs); }
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
.aiprompt { white-space:pre-wrap; max-height:320px; overflow-y:auto;
  font-size:var(--t-2xs); color:var(--ink3); border-top:1px dashed var(--line);
  padding-top:var(--s2); margin-top:var(--s2); }
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
.msg.warn { color:var(--warn); font-weight:600; }

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
/* The queue columns: what is waiting, and how finished the video is. */
.vrow .vcount { flex:none; width:12ch; text-align:right; font-size:var(--t-xs);
  display:grid; gap:1px; }
.vwait { font-family:var(--mono); font-weight:600; color:var(--warn);
  font-variant-numeric:tabular-nums; }
.vrow .vbar { flex:none; width:74px; }
.vtag.miss { background:var(--crit-bg); color:var(--crit); }
.tag.miss { background:var(--crit-bg); color:var(--crit); }
.vtag.has { background:var(--ok-bg); color:var(--ok); }
.vrow[data-video] { cursor:pointer; }
.vrow[data-video]:hover { background:var(--surface2); }
.vseen { display:block; margin-top:2px; color:var(--ink3); font-size:var(--t-2xs);
  font-family:var(--mono); }
.vdet { background:var(--surface2); border-radius:var(--r-md);
  margin:0 0 var(--s3); }
@media (max-width:720px) {
  .vrow { flex-wrap:wrap; }
  .vrow .vcount { width:auto; text-align:left; }
}
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
/* One block per assistant: the name, how it gets its copy, and what it has.
   The route line is the answer to "where is this going", which the first
   version of this card left the reader to infer. */
/* Where a person asks from, next to their name. Small and quiet: it is a
   glance, not a column. */
.chmark { display:inline-flex; align-items:center; margin-left:5px;
  vertical-align:-2px; opacity:.9; }
.chmark:first-of-type { margin-left:var(--s2); }
/* What is in flight. First thing in the card because it is the only part
   that changes minute to minute. */
.queue { background:var(--surface2); border:1px solid var(--line);
  border-radius:var(--r-md); padding:var(--s3) var(--s4); margin-bottom:var(--s4); }
.queue .qh { display:flex; gap:var(--s3); align-items:baseline; flex-wrap:wrap; }
.queue .qh .note { flex:1; min-width:16ch; color:var(--ink3);
  font-size:var(--t-xs); line-height:1.5; }
.qlist { list-style:none; margin:var(--s3) 0 0; padding:0; display:grid;
  gap:2px; }
.qlist li { font-size:var(--t-sm); padding:2px 0; }
.qlist .nm { font-weight:600; }
.qlist .note { color:var(--ink3); font-size:var(--t-xs); }
.who { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:var(--s4);
  align-items:start; padding:var(--s3) 0; border-bottom:1px solid var(--line2); }
.who .nm { font-weight:640; font-size:var(--t-base); margin-right:var(--s2); }
.who .route { font-family:var(--mono); font-size:var(--t-2xs); color:var(--accent); }
.who .note { color:var(--ink3); font-size:var(--t-xs); display:block;
  max-width:62ch; line-height:1.5; }
.who .cnt { text-align:right; }
.who .cnt b { font-family:var(--mono); font-size:var(--t-lg);
  font-variant-numeric:tabular-nums; }
.who .cnt .note { max-width:30ch; margin-left:auto; }
@media (max-width:720px) { .who { grid-template-columns:1fr; }
  .who .cnt { text-align:left; } .who .cnt .note { margin-left:0; } }
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
.aacts { display:flex; gap:var(--s2); align-items:center; margin-top:var(--s3); }
.amsg { font-size:var(--t-xs); color:var(--ink2); }
.arow .a { margin-top:2px; line-height:1.5; }
.arow .abody { display:flex; gap:var(--s3); align-items:flex-start; }
.arow .abody > div { min-width:0; }
.athumb { flex:none; display:block; border-radius:var(--r-xs); overflow:hidden;
  border:1px solid transparent; transition:border-color var(--dur) var(--ease); }
.athumb:hover { border-color:var(--accent); }
.tag { display:inline-block; background:var(--mute-bg); color:var(--ink2);
  border-radius:var(--r-xs); padding:1px 7px; font-size:var(--t-2xs); font-weight:680; }
.tag.lead { background:var(--warn-bg); color:var(--warn); }
.tag.req { background:var(--info-bg); color:var(--info); }
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
@media (min-width:1100px) {
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
/* ================= motion =================
   Transform and shadow only. An opacity reveal leaves the content blank if
   the tab stops compositing, which this page has done before, so nothing
   here can hide anything: at worst a card sits a few pixels lower than it
   should. Everything is switched off by the reduced-motion block below. */

/* 1. Cards arrive from just below, each a beat after the last. */
@keyframes cardIn { from { transform:translateY(9px); } to { transform:none; } }
.card { animation:cardIn .36s var(--ease) both; }
.card:nth-of-type(2) { animation-delay:.04s; }
.card:nth-of-type(3) { animation-delay:.08s; }
.card:nth-of-type(4) { animation-delay:.12s; }
.card:nth-of-type(n+5) { animation-delay:.16s; }

/* 2. The icon leans toward the label the pointer is on. */
.nav a svg, .mnav a svg { transition:transform var(--dur) var(--ease); }
.nav a:hover svg { transform:translateX(2px); }

/* 3. The marker beside the open section grows from its centre. */
@keyframes barIn { from { transform:scaleY(.2); } to { transform:scaleY(1); } }
.nav a.active::before { animation:barIn .22s var(--ease) both; }

/* 4. Buttons take a step down when pressed, and come back slower. */
.btn { transition:background var(--dur) var(--ease), border-color var(--dur)
  var(--ease), transform .18s var(--ease); }
.btn:active { transform:translateY(1px) scale(.985); }

/* 5. A hovered row grows an accent edge instead of only changing colour. */
tbody tr td:first-child { transition:box-shadow .18s var(--ease); }
tbody tr:hover td:first-child { box-shadow:inset 2px 0 0 var(--accent); }

/* 6. Status pills lift a hair, enough to read as touchable. */
.pill { transition:transform var(--dur) var(--ease); }
.pill:hover { transform:translateY(-1px); }

/* 7. The queue badge breathes while something is waiting to be sent. It is
      the one thing on the page that means "right now". */
@keyframes breathe { 0%,100% { transform:scale(1); } 50% { transform:scale(1.035); } }
.queue .st-partial { animation:breathe 3.2s var(--ease) infinite;
  transform-origin:left center; }

/* 8. Faces grow slightly under the pointer. */
.av { transition:transform .2s var(--ease); }
.uc:hover .av { transform:scale(1.08); }

/* 9. The card's emoji tips over when you are reading that card. */
.card h2 .he { display:inline-block; transition:transform .28s var(--ease); }
.card:hover h2 .he { transform:rotate(-8deg) scale(1.1); }

/* 10. Queued notes slide in one after another, so the list reads as a
       queue rather than a block that appeared. */
@keyframes qIn { from { transform:translateX(-6px); } to { transform:none; } }
.qlist li { animation:qIn .3s var(--ease) both; }
.qlist li:nth-child(2) { animation-delay:.03s; }
.qlist li:nth-child(3) { animation-delay:.06s; }
.qlist li:nth-child(4) { animation-delay:.09s; }
.qlist li:nth-child(n+5) { animation-delay:.12s; }

/* 11. Jumping to a section rings it once, so the eye lands in the right
       place after a click in the sidebar. */
@keyframes arrive { 0% { box-shadow:0 0 0 2px var(--accent); }
  100% { box-shadow:var(--el-1); } }
.card:target { animation:arrive 1.1s var(--ease) both; }

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
var PANEL_TOKEN = "__TOKEN__";
/* Every mutating call carries the launch token. A cross-site page can send
   a request but cannot read this file, so it cannot forge one. */
var _fetch = window.fetch.bind(window);
window.fetch = function (url, opts) {
  opts = opts || {};
  if (typeof url === "string" && url.charAt(0) === "/") {
    opts.headers = Object.assign({}, opts.headers, { "X-Panel-Token": PANEL_TOKEN });
  }
  return _fetch(url, opts);
};
var AI_CACHE = __AI_CACHE__;
var QDATA = __QDATA__;
/* Only the people who linked Patreon to Discord, which is a hundred-odd
   rows rather than the thousand in the table. */
var PATRONS = __PATRONS__;
var LOOKUPS = __LOOKUPS__;
/* what each Admin source shows when opened */
var SRCDET = __SRCDET__;
var BRANDS = __BRANDS__;
/* What you have written about people, and the statuses you can set. The
   ones the facts already state are not offered: they would go stale the
   day after being set. */
var CRM = __CRM__;
var MANUAL_STATUS = __MANUAL_STATUS__;
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

/* ---- one screen per tab ----
   Every card carries data-view. The sidebar links are plain anchors, so the
   browser sets the hash and this reacts to it: no click handlers to keep in
   step with the markup, and a link to #wingman still opens on that screen. */
function setView(name) {
  if (!name || !document.getElementById(name)) name = "overview";
  var any = false;
  [].forEach.call(document.querySelectorAll("[data-view]"), function (el) {
    var mine = el.dataset.view === name;
    el.hidden = !mine;
    if (mine) any = true;
  });
  if (!any) { ss("lp-view", "overview"); return setView("overview"); }
  /* A two-column wrapper holding one visible card would render it at half
     width, and an empty one would still take its gap. */
  [].forEach.call(document.querySelectorAll(".cols2, .grid3"), function (w) {
    var shown = [].filter.call(w.children, function (c) { return !c.hidden; });
    w.hidden = shown.length === 0;
    w.classList.toggle("solo", shown.length === 1);
  });
  [].forEach.call(document.querySelectorAll(".nav a, .mnav a"), function (a) {
    a.classList.toggle("active", a.getAttribute("href") === "#" + name);
  });
  ss("lp-view", name);
}
/* Anything that acts on another screen has to open it first. Edit lives on
   Answers and drives the Questions table; before this it filtered, opened
   the row and scrolled to a section that was hidden, so the click looked
   like it did nothing at all. replaceState rather than assigning the hash,
   so the switch happens now instead of on the next event loop turn. */
function goView(name) {
  setView(name);
  try { history.replaceState(null, "", "#" + name); }
  catch (e) { location.hash = "#" + name; }
}
addEventListener("hashchange", function () {
  setView(location.hash.replace("#", ""));
  scrollTo(0, 0);
});
setView(location.hash.replace("#", "") || ssGet("lp-view"));

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

/* The LIVE flag records how the page was built, which is not the same as
   how it is being served: a one-off rebuild while the watcher runs used to
   leave a live page insisting it was a static file. One probe settles it. */
if (!LIVE) {
  fetch("/status.json", { cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (s) {
      if (!s || !s.epoch) return;
      LIVE = true;
      EPOCH = s.epoch;
      setChip("live", null);
      loadLinks();
    })
    .catch(function () {});
}

var holdUntil = 0;
var lastTouch = Date.now();
var pending = false;     /* a newer build exists but now is a bad moment */
["pointerdown", "keydown", "input"].forEach(function (ev) {
  addEventListener(ev, function () { lastTouch = Date.now(); }, true);
});
/* Reloading while someone is reading a question or typing an answer throws
   their work off the screen. The page waits for a quiet moment, and says
   plainly that it is holding a newer version rather than doing it silently. */
function busy() {
  if (openCount()) return true;
  /* a composer open inside a video or product panel is edit state too,
     and it has no entry in openIds to speak for it; same for an open
     description editor */
  if (document.querySelector(".cev .detwrap, .vdesc")) return true;
  var el = document.activeElement;
  if (el && (el.tagName === "TEXTAREA" || el.tagName === "INPUT")) return true;
  return Date.now() - lastTouch < 20000;
}
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
        if (!busy()) { reloadKeepingPlace(); return; }
        if (!pending) {
          pending = true;
          setChip("stale", "new data · click to refresh");
          $("#chip").style.cursor = "pointer";
          $("#chip").addEventListener("click", reloadKeepingPlace, { once: true });
        }
        return;
      }
      if (!pending) setChip("live", null);
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
/* The panel opens on work, not on history: "open" is a virtual status
   covering unanswered and escalated. Seeing the 433 already-answered rows
   by default made half the queue irrelevant to the job at hand. */
var state = {
  /* Set when a video hands its block to the queue. Not part of the
     text search: the question text never mentions the video it came
     from, so searching the title found nothing at all. */
  vid: "",
  ch: params.get("ch") || "all",
  st: params.get("st") || "open",
  sys: params.get("sys") || "all",
  df: params.get("df") || "all",
  q: params.get("q") || "",
  sort: params.get("sort") || "triage",
  dir: params.get("dir") || "desc"
};
var size = parseInt(ssGet("lp-size") || PAGE, 10) || PAGE;
var page = 0;
function syncUrl() {
  var p = new URLSearchParams();
  if (state.ch !== "all") p.set("ch", state.ch);
  if (state.st !== "open") p.set("st", state.st);
  if (state.sys !== "all") p.set("sys", state.sys);
  if (state.df !== "all") p.set("df", state.df);
  if (state.q) p.set("q", state.q);
  if (state.sort !== "triage" || state.dir !== "desc") { p.set("sort", state.sort); p.set("dir", state.dir); }
  var qs = p.toString();
  try { history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash); } catch (e) {}
}

var PAIRS = $$("#qtbody tr.qrow").map(function (r) { return { r: r }; });
/* Triage order, the default: whatever was escalated first, then the ones
   the vault can already answer, then oldest first. Sorting by date alone
   put freshly answered questions above four-year-old open ones. */
function triageRank(r) {
  return r.dataset.st === "escalated" ? 0 : r.dataset.st === "answered" ? 2 : 1;
}
function sortRows() {
  var key = state.sort, dir = state.dir === "asc" ? 1 : -1;
  var sorted = PAIRS.slice().sort(function (a, b) {
    if (key === "triage") {
      var ra = triageRank(a.r), rb = triageRank(b.r);
      if (ra !== rb) return ra - rb;
      var ca = +a.r.dataset.cov || 0, cb = +b.r.dataset.cov || 0;
      if (ca !== cb) return cb - ca;            /* answerable first */
      return a.r.dataset.date < b.r.dataset.date ? -1 : 1;  /* oldest first */
    }
    var av, bv;
    if (key === "who") { av = a.r.dataset.who; bv = b.r.dataset.who; }
    else if (key === "status") { av = a.r.dataset.st; bv = b.r.dataset.st; }
    else if (key === "system") { av = a.r.dataset.sys; bv = b.r.dataset.sys; }
    else if (key === "cov") { av = +a.r.dataset.cov || 0; bv = +b.r.dataset.cov || 0; }
    else { av = a.r.dataset.date; bv = b.r.dataset.date; }
    if (av < bv) return -dir;
    if (av > bv) return dir;
    return 0;
  });
  var tbody = $("#qtbody");
  closeDet();   /* reordering would strand the inspector away from its row */
  sorted.forEach(function (p) { tbody.appendChild(p.r); });
  $$("th[data-sort]").forEach(function (th) {
    th.setAttribute("aria-sort", th.dataset.sort === key
      ? (dir === 1 ? "ascending" : "descending") : "none");
  });
}
$$("th[data-sort]").forEach(function (th) {
  th.tabIndex = 0;
  th.addEventListener("click", function () {
    if (state.sort === th.dataset.sort) state.dir = state.dir === "asc" ? "desc" : "asc";
    else {
      state.sort = th.dataset.sort;
      /* first click sorts the way the column is actually useful: newest
         dates, and the most answerable questions, not the least */
      state.dir = (th.dataset.sort === "date" || th.dataset.sort === "cov")
        ? "desc" : "asc";
    }
    sortRows();
    syncSortChips();
    apply();
    syncUrl();
  });
});

/* Sort order has two entry points, the chips and the column headers, and
   they have to stay in agreement: the chip reflects whatever is actually
   sorting the table, and goes blank when a column sort has no chip. */
function setSort(v) {
  if (v === "new") { state.sort = "date"; state.dir = "desc"; }
  else if (v === "old") { state.sort = "date"; state.dir = "asc"; }
  else { state.sort = "triage"; state.dir = "desc"; }
  sortRows();
  syncSortChips();
}
function syncSortChips() {
  var active = state.sort === "triage" ? "triage"
    : state.sort === "date" ? (state.dir === "asc" ? "old" : "new")
    : "";
  $$('.fchip[data-k="sort"]').forEach(function (c) {
    var on = c.dataset.v === active;
    c.classList.toggle("on", on);
    c.setAttribute("aria-pressed", on ? "true" : "false");
  });
}

var visRows = [];      /* the rows on the current page */
var matchRows = [];    /* everything matching the filters, across pages */
function isOpen(r) { return r.dataset.st === "no-source" || r.dataset.st === "escalated"; }
function match(r) {
  if (state.ch !== "all" && r.dataset.ch !== state.ch) return false;
  if (state.st === "open") { if (!isOpen(r)) return false; }
  else if (state.st !== "all" && r.dataset.st !== state.st) return false;
  if (state.sys !== "all" && r.dataset.sys !== state.sys) return false;
  /* Answerability describes work still to do. Without this, "easy 90"
     also matched the answered rows that carry the same data-df and
     returned far more rows than the chip promised. */
  if (state.df !== "all" && (r.dataset.df !== state.df || r.dataset.st === "answered"))
    return false;
  if (state.q && r.dataset.txt.indexOf(state.q) === -1) return false;
  if (state.vid) {
    var q = QDATA[r.dataset.id];
    if (!q || q.video !== state.vid) return false;
  }
  return true;
}
/* ---- rows built when they are about to be seen ----
   The queue holds a few thousand questions and shows twenty-five. Rendering
   every cell of every one of them was most of what this page weighed, for
   markup that was hidden the moment it arrived. The row keeps the
   attributes the filters and the sort read; its cells are built the first
   time it appears on a page and then left alone. */
function avatarHtml(who, url) {
  var h = 0;
  for (var i = 0; i < who.length; i++) h = (h * 31 + who.charCodeAt(i)) >>> 0;
  var hue = LOOKUPS.hues[h % LOOKUPS.hues.length];
  var initial = esc((who.replace(/^@/, "")[0] || "?").toUpperCase());
  /* The coloured initial stays underneath, so an image that fails to load
     leaves an identity rather than a hole. */
  var img = url ? '<img loading="lazy" alt="" referrerpolicy="no-referrer" src="'
    + esc(url) + '">' : "";
  return '<span class="av sm" style="--h:' + hue + '" aria-hidden="true">'
    + initial + img + "</span>";
}
function rolesHtml(roles) {
  if (!roles || !roles.length) return "";
  var out = roles.slice(0, 3).map(function (r) {
    return '<span class="role ' + (LOOKUPS.role_class[r] || "r-other") + '">'
      + esc(r) + "</span>";
  }).join("");
  if (roles.length > 3) {
    out += '<span class="role r-other" title="' + esc(roles.slice(3).join(", "))
      + '">+' + (roles.length - 3) + "</span>";
  }
  return out;
}
function fillRow(tr) {
  if (tr.firstChild) return;                 /* already built */
  var q = QDATA[tr.dataset.id];
  if (!q) { tr.innerHTML = '<td colspan="7"></td>'; return; }

  var meta = '<span class="qid" data-copy="' + esc(q.code) + '">' + esc(q.code) + "</span>";
  var brand = BRANDS.indexOf(q.channel) !== -1;
  meta += brand
    ? '<span class="mch" title="' + esc(q.channel) + '"><svg width="12" height="12" '
      + 'aria-hidden="true" class="bi"><use href="#bi-' + esc(q.channel) + '"></use></svg></span>'
    : '<span class="mch">' + esc(q.channel) + "</span>";
  if (q.video) {
    meta += '<span class="mvid" title="' + esc(q.video) + '">'
      + esc(q.video.slice(11) || q.video) + "</span>";
  }
  if (q.sub) meta += '<span class="tag sub">subscriber</span>';
  meta += genMarks(tr.dataset.id);

  var thumb = q.small
    ? '<span class="mthumb" title="' + esc(q.video || "") + '"><img loading="lazy" '
      + 'alt="" referrerpolicy="no-referrer" src="' + esc(q.small) + '"></span>'
    : "";

  var st = q.status;
  var pill = '<span class="pill st-' + st.replace(/[^a-z0-9]+/g, "-")
    + '" title="' + esc(LOOKUPS.st_title[st] || st) + '"><i class="pe">'
    + (LOOKUPS.st_emoji[st] || "") + "</i>" + esc(LOOKUPS.st_label[st] || st) + "</span>";

  var dp = "";
  if (q.df && st !== "answered") {
    dp = '<span class="dpill d-' + q.df + '" title="' + esc(LOOKUPS.diff_tip[q.df] || "")
      + '"><i class="pe">' + (LOOKUPS.diff_emoji[q.df] || "") + "</i>" + q.df
      + " <b>" + (q.cov || 0) + "%</b></span>";
  }

  tr.innerHTML =
    '<td class="qcol"><div class="qcell">' + thumb
    + '<div class="qtext"><div class="snip">' + esc(q.text.slice(0, 230)) + "</div>"
    + '<div class="qmeta">' + meta + "</div></div></div></td>"
    + '<td class="stcell">' + pill + "</td>"
    + "<td>" + dp + "</td>"
    + '<td><span class="uc">' + avatarHtml(q.who, q.avatar)
    + '<span><span class="n">' + esc(q.who) + "</span>"
    + '<span class="roles">' + rolesHtml(q.roles) + "</span></span></span></td>"
    + '<td class="syscell">' + esc(q.system) + "</td>"
    + '<td class="num agecell" data-date="' + esc(q.date) + '">' + esc(q.date) + "</td>"
    + '<td class="acts"><button class="btn tiny answerbtn" data-act="answer">'
    + (st === "answered" ? "View" : "Answer") + "</button></td>";
}

function apply() {
  var rows = $$("#qtbody tr.qrow");
  matchRows = rows.filter(match);
  var pages = Math.max(1, Math.ceil(matchRows.length / size));
  page = Math.min(Math.max(0, page), pages - 1);
  var from = page * size, to = from + size;
  visRows = matchRows.slice(from, to);
  var onPage = new Set(visRows);

  rows.forEach(function (r) { r.classList.toggle("hide", !onPage.has(r)); });
  visRows.forEach(fillRow);
  Object.keys(openIds).forEach(function (oid) {
    var openRow = rowById(oid);
    if (!openRow || openRow.classList.contains("hide")) closeDet(oid);
  });

  var total = matchRows.length;
  $("#qcount").textContent = total
    ? (from + 1) + "-" + Math.min(to, total) + " of " + fmt(total)
    : "0";
  $("#pgnow").textContent = page + 1;
  $("#pgtot").textContent = pages;
  $("#pgprev").disabled = page === 0;
  $("#pgnext").disabled = page >= pages - 1;
  $("#pager").classList.toggle("hide", total === 0);
  /* only when filters hid existing rows; an empty vault has its own message */
  $("#qempty").classList.toggle("hide", total !== 0 || PAIRS.length === 0);
  ss("lp-size", String(size));
}
function goPage(n) {
  page = n;
  apply();
  var card = $("#questions");
  if (card) card.scrollIntoView({ block: "start" });
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
    if (c.dataset.k === "sort") setSort(c.dataset.v);
    else setGroup(c.dataset.k, c.dataset.v);
    page = 0;
    apply();
    syncUrl();
  });
});
$("#sysSel").addEventListener("change", function () {
  state.sys = this.value;
  page = 0;
  apply();
  syncUrl();
});
var searchApply = debounce(function (v) {
  state.q = v.trim().toLowerCase();
  page = 0;
  apply();
  syncUrl();
}, 150);
$("#q").addEventListener("input", function () {
  searchApply(this.value); universalSearch(this.value);
});

/* ---- search that reaches past the question table ----
   Typing already filters the inbox. The same words are also somebody's
   name and somebody's product, and those were unreachable from here: you
   had to know which screen to open first. */
function universalSearch(term) {
  var box = $("#qres");
  term = (term || "").trim().toLowerCase();
  if (term.length < 2) { box.classList.add("hide"); return; }

  var people = {}, prods = {}, hits = 0;
  for (var id in QDATA) {
    var q = QDATA[id];
    var who = (q.who || "").toLowerCase();
    var sys = (q.system || "");
    if (who.indexOf(term) !== -1) people[q.who] = (people[q.who] || 0) + 1;
    if (sys.toLowerCase().indexOf(term) !== -1) prods[sys] = (prods[sys] || 0) + 1;
    if ((q.text || "").toLowerCase().indexOf(term) !== -1) hits++;
  }
  /* A patron may be findable by the name on their card rather than the
     handle they type under. */
  for (var h in PATRONS) {
    var p = PATRONS[h];
    if (p.name && p.name.toLowerCase().indexOf(term) !== -1) {
      for (var id2 in QDATA) {
        var w = (QDATA[id2].who || "");
        if (w.replace(/^@/, "").split(" ")[0].toLowerCase() === h) {
          people[w] = people[w] || 0;
        }
      }
    }
  }

  var top = function (o) {
    return Object.keys(o).sort(function (a, b) { return o[b] - o[a]; });
  };
  var out = "";
  var pk = top(people).slice(0, 5);
  if (pk.length) {
    out += '<div class="qrgroup"><span class="clabel">People</span>';
    pk.forEach(function (w) {
      var p = PATRONS[w.replace(/^@/, "").split(" ")[0].toLowerCase()];
      out += '<button class="qritem" data-go="person" data-key="' + esc(w) + '">'
        + esc(w) + (p && p.name ? ' <span class="note">' + esc(p.name) + "</span>" : "")
        + (p && p.paying ? ' <span class="tag sub">pays</span>' : "")
        + ' <span class="note">' + people[w] + " question"
        + (people[w] === 1 ? "" : "s") + "</span></button>";
    });
    out += "</div>";
  }
  var sk = top(prods).slice(0, 5);
  if (sk.length) {
    out += '<div class="qrgroup"><span class="clabel">Products</span>';
    sk.forEach(function (s) {
      out += '<button class="qritem" data-go="product" data-key="' + esc(s) + '">'
        + esc(s) + ' <span class="note">' + prods[s] + " questions</span></button>";
    });
    out += "</div>";
  }
  out += '<div class="qrgroup"><span class="clabel">Questions</span>'
    + '<button class="qritem" data-go="inbox" data-key="' + esc(term) + '">'
    + _fmt2(hits) + " mention " + esc(term) + ' <span class="note">open the inbox</span></button></div>';
  box.innerHTML = out;
  box.classList.remove("hide");
}
function _fmt2(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }

/* Reveal a row that "View all" is still hiding, or the jump lands on
   nothing and looks broken. */
function revealRow(tr) {
  if (!tr) return;
  var card = tr.closest(".card");
  if (tr.classList.contains("hide") || tr.classList.contains("xtra")) {
    $$(".xtra", card).forEach(function (x) { x.classList.remove("hide"); });
    var btn = card.querySelector("[data-viewall]");
    if (btn) btn.classList.add("hide");
  }
  tr.scrollIntoView({ block: "center" });
}

document.addEventListener("click", function (ev) {
  var b = ev.target.closest ? ev.target.closest(".qritem") : null;
  if (!b) {
    if (!ev.target.closest || !ev.target.closest(".search")) $("#qres").classList.add("hide");
    return;
  }
  var key = b.dataset.key;
  $("#qres").classList.add("hide");
  if (b.dataset.go === "person") {
    goView("people");
    setTimeout(function () {
      var tr = document.querySelector('#people tr.crow[data-who="' + key.replace(/"/g, '\\"') + '"]');
      revealRow(tr);
      if (tr && !tr.classList.contains("copen")) toggleCustomer(tr);
    }, 30);
  } else if (b.dataset.go === "product") {
    goView("systems");
    setTimeout(function () {
      var tr = document.querySelector('#systems tr.prodrow[data-name="' + key.replace(/"/g, '\\"') + '"]');
      revealRow(tr);
      if (tr && !tr.classList.contains("copen")) toggleProduct(tr);
    }, 30);
  } else {
    goView("questions");
  }
});
function clearFilters() {
  setGroup("ch", "all");
  setGroup("st", "open");   /* back to the working queue, not the archive */
  setSort("triage");
  setGroup("df", "all");
  state.sys = "all";
  $("#sysSel").value = "all";
  state.q = "";
  state.vid = "";
  $("#q").value = "";
  page = 0;
  apply();
  syncUrl();
}
$("#fclear").addEventListener("click", clearFilters);
$("#qemptyclear").addEventListener("click", clearFilters);
$("#pgprev").addEventListener("click", function () { goPage(page - 1); });
$("#pgnext").addEventListener("click", function () { goPage(page + 1); });
$("#pgsize").addEventListener("change", function () {
  size = parseInt(this.value, 10) || PAGE;
  goPage(0);
  syncUrl();
});

/* ---- expandable rows + suggest/reply, with continuity across reloads ---- */
/* ---- one inspector, built on demand ----
   The composer used to be rendered for every question, open or not, which
   was most of a 5.85 MB page. Now a detail row is created from QDATA when a
   question is opened and removed when it closes, so the DOM holds the
   composers you opened instead of 866, and any number can be open at once.
   Draft text, open state and AI results are keyed by question id exactly as
   before, so nothing is lost across a rebuild. */
var openIds = {};            /* qid -> true for every open queue detail */
function openCount() {
  var n = 0;
  for (var k in openIds) n += 1;
  return n;
}
function ssOpen() {
  var ids = Object.keys(openIds);
  ss("lp-open", ids.length ? JSON.stringify(ids) : null);
}

function composerFor(qid) {
  var q = QDATA[qid];
  if (!q) return null;
  var wrap = document.createElement("div");
  wrap.className = "detwrap";
  wrap.dataset.id = qid;
  var det = document.createElement("div");
  det.className = "det";

  var parts = [];
  if (q.thumb && q.video) {
    /* No inline onerror here: this string lives inside a Python literal,
       which collapses the escaped quotes and produced a page-wide JS syntax
       error. The handler is attached after the markup is built instead. */
    var inner = '<img loading="lazy" alt="" width="168" height="94" '
      + 'referrerpolicy="no-referrer" src="' + esc(q.thumb) + '">'
      + '<span class="vmeta"><b>' + esc(q.video) + "</b><span>"
      + "watch this moment on YouTube</span></span>";
    parts.push(q.video_url
      ? '<a class="vidcard" href="' + esc(q.video_url) + '" target="_blank" rel="noopener">'
        + inner + "</a>"
      : '<div class="vidcard">' + inner + "</div>");
  } else if (q.link) {
    parts.push('<a class="vidcard novid" href="' + esc(q.link) + '" target="_blank" '
      + 'rel="noopener"><span class="vmeta"><b>'
      + esc(q.thread || ("#" + q.channel)) + "</b><span>open the original message"
      + "</span></span></a>");
  } else if (q.channel === "youtube") {
    parts.push('<div class="vidcard novid"><span class="vmeta"><b>No video linked</b>'
      + "<span>logged by hand: add video_id: to this block in the vault</span></span></div>");
  }
  var whoLine = '<div class="asker">';
  if (q.avatar) whoLine += '<img class="askerpic" src="' + esc(q.avatar)
    + '" alt="" referrerpolicy="no-referrer">';
  whoLine += "<b>" + esc(q.asker || "") + "</b>";
  (q.roles || []).forEach(function (r) {
    whoLine += '<span class="role ' + (ROLE_CLASS[r] || "r-other") + '">' + esc(r) + "</span>";
  });
  if (q.joined) whoLine += '<span class="w">in the server since ' + esc(q.joined) + "</span>";
  parts.push(whoLine + "</div>");
  parts.push('<div class="full">' + esc(q.text) + "</div>");
  if (q.reply) {
    parts.push('<div class="yourreply"><b>Your reply on ' + esc(q.channel) + "</b>"
      + esc(q.reply) + "</div>");
  }
  parts.push('<div class="prov"><span class="qid" data-copy="' + esc(q.code) + '">'
    + esc(q.code) + "</span><span>" + esc(q.channel) + '</span><span class="num">'
    + esc(q.date) + "</span>" + (q.source ? '<span class="num">' + esc(q.source) + "</span>" : "")
    + "</div>");
  parts.push('<div class="detbtns">'
    + '<button class="btn tiny" data-ai="search">Find existing answer</button>'
    + '<button class="btn tiny ai" data-ai="draft">Draft with Claude</button>'
    + '<button class="btn tiny" data-ctx>What is this about?</button>'
    + '<button class="btn tiny" data-mark="'
    + (q.status === "answered" ? "no-source" : "answered") + '">'
    + (q.status === "answered" ? "Reopen" : "Mark as answered") + "</button>"
    + (q.video_url ? '<button class="btn tiny" data-copy="' + esc(q.video_url)
        + '">Copy link</button>' : "")
    + "</div>");
  parts.push('<div class="ctxout"></div>');
  parts.push('<div class="aiout" data-mode="search"></div>');
  parts.push('<div class="aiout" data-mode="draft"></div>');
  parts.push('<textarea class="qbox" aria-label="Reply text" '
    + 'placeholder="Write a reply..."></textarea>');
  parts.push('<div class="detbtns"><button class="btn tiny primary replybtn" data-reply>'
    + (q.postable ? "Post to " + esc(q.dest) : "Save answer to vault")
    + '</button><span class="msg" aria-live="polite"></span>'
    + '<span class="deliver">' + (q.postable
        ? "replies to the original message and files it in the vault"
        : "files it in the vault; this channel cannot be posted to from here")
    + "</span></div>");

  det.innerHTML = parts.join("");
  wrap.appendChild(det);

  var vimg = det.querySelector(".vidcard img");
  if (vimg) vimg.addEventListener("error", function () { vimg.classList.add("hide"); });

  var box = det.querySelector(".qbox");
  box.value = ssGet("lp-draft:" + qid) || "";
  box.addEventListener("input", function () {
    ss("lp-draft:" + qid, box.value || null);
  });
  box.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); runReply(wrap); }
  });
  $$("[data-ai]", det).forEach(function (b) {
    b.addEventListener("click", function () { runAi(wrap, b.dataset.ai, false); });
  });
  det.querySelector("[data-reply]").addEventListener("click", function () { runReply(wrap); });
  det.querySelector("[data-ctx]").addEventListener("click", function () {
    runContext(wrap, det.querySelector("[data-ctx]"));
  });
  /* Not every question is closed by replying from here: some were handled
     in the thread, some are not really questions. Closing one should not
     require posting something. */
  det.querySelector("[data-mark]").addEventListener("click", function () {
    var b = det.querySelector("[data-mark]");
    var msg = det.querySelector(".msg");
    b.disabled = true;
    msg.className = "msg";
    msg.textContent = "updating the vault...";
    fetch("/mark", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: qid, status: b.dataset.mark }) })
      .then(function (r) { return r.json(); })
      .then(function (s) {
        if (!s.ok) { msg.textContent = s.error || "failed"; b.disabled = false; return; }
        holdUntil = Date.now() + 4000;
        QDATA[qid].status = s.status;
        var row = rowById(qid);
        var done = s.status === "answered";
        /* Marking from a video or product panel reaches a queue row whose
           cells were never built. fillRow first (QDATA already knows the
           new status), then touch the pill only if it exists, or the
           querySelector comes back null and the catch below blames the
           network for a TypeError. */
        if (row) {
          fillRow(row);
          row.dataset.st = s.status;
          var pill = row.querySelector(".pill");
          if (pill) {
            pill.className = "pill " + (done ? "st-answered" : "st-no-source");
            pill.innerHTML = '<i class="pe">' + (done ? "✅" : "📥") + "</i>"
              + (done ? "answered" : "unanswered");
          }
        }
        panelRefresh(wrap);
        toast(done ? "Marked answered in the vault." : "Reopened in the vault.", "good");
        /* closes this question's own queue detail if open; every other
           open row is somebody else's work and stays */
        closeDet(qid);
        apply();
      })
      .catch(function () {
        msg.textContent = "could not reach the panel server";
        b.disabled = false;
      });
  });
  return wrap;
}

/* The same composer, wrapped for the table. Anywhere else it is inserted
   as it is, which is how a product or a video can carry the real controls
   rather than a copy of them that drifts. */
function detailFor(qid) {
  var wrap = composerFor(qid);
  if (!wrap) return null;
  var tr = document.createElement("tr");
  tr.className = "qdet open";
  tr.dataset.id = qid;
  var td = document.createElement("td");
  td.colSpan = 7;
  td.appendChild(wrap);
  tr.appendChild(td);
  return tr;
}

function closeDet(qid) {
  /* no argument = close every open detail: Escape, and the re-sorts that
     would strand a detail row away from where its question moved to */
  if (!qid) { Object.keys(openIds).forEach(closeDet); return; }
  if (!openIds[qid]) return;
  var det = $('tr.qdet[data-id="' + CSS.escape(qid) + '"]');
  var row = rowById(qid);
  if (det) det.remove();
  if (row) row.setAttribute("aria-expanded", "false");
  delete openIds[qid];
  ssOpen();
}

function rowById(qid) {
  var hit = null;
  $$("#qtbody tr.qrow").forEach(function (r) { if (r.dataset.id === qid) hit = r; });
  return hit;
}

function toggleDet(row, focus) {
  if (!row) return;
  var qid = row.dataset.id;
  if (openIds[qid]) { closeDet(qid); return; }
  /* the ones already open stay open: closing somebody's half-written
     reply because a second question was opened threw work away */
  var det = detailFor(qid);
  if (!det) return;
  row.parentNode.insertBefore(det, row.nextSibling);
  row.setAttribute("aria-expanded", "true");
  openIds[qid] = true;
  ssOpen();
  /* replay whatever the model already produced for this question */
  ["search", "draft"].forEach(function (mode) {
    var hit = AI_CACHE[mode + ":" + qid];
    if (hit) aiRender(det, mode, hit, aiBtn(det, mode));
  });
  if (focus === "box") det.querySelector(".qbox").focus();
}

$$("#qtbody tr.qrow").forEach(function (r) {
  r.tabIndex = 0;
  r.setAttribute("aria-expanded", "false");
  r.addEventListener("click", function (e) {
    if (e.target.closest("a, button, textarea")) return;
    toggleDet(r);
  });
});

function runReply(det) {
  var box = det.querySelector(".qbox");
  var msg = det.querySelector(".msg");
  var btn = det.querySelector(".replybtn");
  var text = box.value.trim();
  /* decided while the composer is still where the user put it: the queue
     epilogue below must know where this reply came from */
  var fromQueue = !!det.closest("tr.qdet");
  msg.className = "msg";
  if (!text) { msg.textContent = "Type the reply first."; msg.classList.add("bad"); return; }
  if (!LIVE) { msg.textContent = "Static file: replying needs the live server (panel.py --watch)."; return; }
  btn.disabled = true;
  btn.classList.add("spin");
  msg.textContent = "Updating the vault...";
  var offer = {};
  try { offer = JSON.parse(det.dataset.offer || "{}"); } catch (e) { offer = {}; }
  fetch("/reply", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: det.dataset.id, text: text,
      /* How this answer came to be. The server works out how much of the
         offer survived; the page only reports what it was handed. */
      offer_mode: offer.mode || "", offer_text: offer.text || "",
      offer_confidence: offer.confidence || 0, offer_source: offer.source || "",
    }) })
    .then(function (r) { return r.json(); })
    .then(function (s) {
      btn.classList.remove("spin");
      if (s.ok) {
        holdUntil = Date.now() + 6000;
        ss("lp-draft:" + det.dataset.id, null);
        /* the video/product panels render from QDATA; it learns first */
        QDATA[det.dataset.id].status = "answered";
        QDATA[det.dataset.id].reply = text;
        /* Saving to the vault is not the same as the customer receiving it.
           Only a real platform post earns the green. */
        msg.textContent = s.posted_to_platform
          ? "Sent, and filed in the vault."
          : "Saved to the vault only, NOT sent to the customer. "
            + (s.platform_message || "");
        msg.classList.add(s.posted_to_platform ? "good" : "warn");
        toast(s.posted_to_platform
          ? "Reply posted and filed as knowledge."
          : "Filed in the vault. Nothing was posted to the platform.",
          s.posted_to_platform ? "good" : "bad");
        var row = rowById(det.dataset.id);
        /* Answering from a product or a video reaches a row whose cells
           have never been built, and querying inside it would find
           nothing. */
        if (row) fillRow(row);
        var pill = row && row.querySelector(".pill");
        if (pill) {
          pill.className = "pill st-answered";
          pill.innerHTML = '<i class="pe">✅</i>answered';
        }
        if (row) row.dataset.st = "answered";
        panelRefresh(det);
        var answerBtn = row && row.querySelector(".answerbtn");
        if (answerBtn) answerBtn.textContent = "View";
        var badge = $("#bellbtn .badge"), nav = $(".navcount");
        var left = Math.max(0, (parseInt((badge.textContent || "0").replace(/,/g, ""), 10) || 0) - 1);
        badge.textContent = fmt(left);
        if (nav) nav.textContent = fmt(left);
        if (fromQueue) {
          /* Clearing a backlog means the answered item leaves the queue
             and the next one is ready. Leaving it open with stale counts
             made every reply end in manual cleanup. Only this question's
             detail closes; other open composers keep their work. */
          var wasAt = matchRows.indexOf(row);
          closeDet(det.dataset.id);
          apply();
          var next = matchRows[Math.min(Math.max(0, wasAt), matchRows.length - 1)];
          if (next && visRows.indexOf(next) === -1) {
            page = Math.floor(matchRows.indexOf(next) / size);
            apply();
          }
          if (next) kFocus(visRows.indexOf(next));
        } else {
          /* A panel reply leaves the queue's page, focus and open rows
             alone. Only this very question's detail closes, if open;
             anything else open there is the user's own business. */
          closeDet(det.dataset.id);
          apply();
        }
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
/* Delegated: the Answer button is built when its row first appears, long
   after a per-element binding would have run, so binding each one found at
   load reached exactly zero buttons. */
document.addEventListener("click", function (e) {
  var el = e.target.closest ? e.target.closest("[data-act]") : null;
  if (!el) return;
  e.stopPropagation();
  var row = el.closest("tr.qrow");
  if (!row) return;
  if (!openIds[row.dataset.id]) toggleDet(row, "box");
  else {
    var b = $('tr.qdet[data-id="' + CSS.escape(row.dataset.id) + '"] .qbox');
    if (b) b.focus();
  }
});

/* ---- AI: the Claude CLI reads the vault; results persist in the vault ----
   Two modes share this code path. search = fast retrieval that quotes an
   existing passage verbatim. draft = a full reply composed from everything.
   Every finished result is cached server side, embedded in the page on the
   next build, and replayed here on load, so the reload that follows every
   vault change never throws away a generation. */
var ROLE_CLASS = {
  "LocoPremium": "r-premium", "LocoStandard": "r-standard",
  "LocoBasic": "r-basic", "LocoHelper": "r-helper",
  "LocoDev Team": "r-team", "LocoTester": "r-team", "Patreon": "r-patreon"
};
function aiOut(det, mode) { return det.querySelector('.aiout[data-mode="' + mode + '"]'); }
function aiBtn(det, mode) { return det.querySelector('[data-ai="' + mode + '"]'); }

/* The exact text the model receives, fetched on demand. What a paid button
   sends should never be a mystery to the person paying for it. */
function promptPeek(det, mode, out) {
  var peek = document.createElement("span");
  peek.className = "regen";
  peek.textContent = "view prompt";
  peek.title = "Show the exact prompt this button sends to the model";
  peek.addEventListener("click", function () {
    var pre = out.querySelector(".aiprompt");
    if (pre) { pre.remove(); return; }
    pre = document.createElement("pre");
    pre.className = "aiprompt";
    pre.textContent = "fetching the prompt...";
    out.appendChild(pre);
    fetch("/ai_prompt", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: det.dataset.id, mode: mode }) })
      .then(function (r) { return r.json(); })
      .then(function (s) { pre.textContent = s.ok ? s.prompt : (s.error || "failed"); })
      .catch(function () { pre.textContent = "could not reach the panel server"; });
  });
  return peek;
}
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

  /* a finished result is knowledge the whole page can use: the client
     cache feeds the replay on reopen and the ready marks on rows and
     panel items, without waiting for the next server build */
  AI_CACHE[mode + ":" + det.dataset.id] = s;
  stampGen(det.dataset.id, det);

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
  src.appendChild(promptPeek(det, mode, out));
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
      /* What was offered, kept beside the row until the reply is sent.
         Without it nothing downstream can tell an answer the assistant
         wrote from one that was typed, and every count of how much it
         helped is a guess. */
      det.dataset.offer = JSON.stringify({
        mode: mode, text: s.answer,
        confidence: s.confidence || 0,
        source: (s.sources || []).join(" · "),
      });
      box.focus();
    });
    out.appendChild(use);
  }
}
/* The conversation a question sits in. Half of what people ask in a chat
   is a reply to something, and the question alone reads as nonsense. */
function runContext(det, btn) {
  var out = det.querySelector(".ctxout");
  out.style.display = "block";
  if (!LIVE) { out.textContent = "needs the live server"; return; }
  btn.disabled = true;
  out.innerHTML = '<div class="src">reading the conversation...</div>';
  fetch("/context", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: det.dataset.id }) })
    .then(function (r) { return r.json(); })
    .then(function (s) {
      btn.disabled = false;
      if (!s.ok) { out.innerHTML = '<div class="src">' + esc(s.error || "no context") + "</div>"; return; }
      var h = '<div class="src">around this message in ' + esc(s.where) + "</div>";
      s.lines.forEach(function (l) {
        h += '<div class="ctxline' + (l.self ? " self" : "") + '">'
          + (l.who ? "<b>" + esc(l.who) + "</b> " : "")
          + (l.when ? '<span class="w">' + esc(l.when) + "</span> " : "")
          + (l.reply_to ? '<span class="w">↪</span> ' : "")
          + esc(l.text) + "</div>";
      });
      out.innerHTML = h;
    })
    .catch(function () {
      btn.disabled = false;
      out.innerHTML = '<div class="src">could not reach the panel server</div>';
    });
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
  /* its own row: the ticking timer rewrites tick's text every second and
     would wipe anything appended inside it */
  var peekrow = document.createElement("div");
  peekrow.className = "src";
  peekrow.appendChild(promptPeek(det, mode, out));
  out.appendChild(peekrow);
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
/* A question whose answer was already generated says so right on the
   message, wherever the message shows: the queue row (stamped by fillRow,
   which reaches lazy rows the old load-time pass never saw), the video and
   product panel items, and live the moment a generation finishes. Only a
   result that carries an answer earns a mark; an errored run or a search
   that came back empty would make it say ready when nothing usable
   exists. */
function genLabel(mode, s) {
  if (!s || s.state === "error" || !s.answer) return "";
  return mode === "draft" ? "draft ready" : "answer found";
}
function genMarks(qid) {
  var out = "";
  ["search", "draft"].forEach(function (mode) {
    var lab = genLabel(mode, AI_CACHE[mode + ":" + qid]);
    if (lab) out += ' <span class="hasai gen-' + mode + '">✦ ' + lab + "</span>";
  });
  return out;
}
function stampGen(qid, det) {
  var spots = [];
  var row = rowById(qid);
  var meta = row && row.querySelector(".qmeta");
  if (meta) spots.push(meta);
  var item = det && det.closest(".cev[data-qid]");
  var cd = item && item.querySelector(".cdate");
  if (cd) spots.push(cd);
  spots.forEach(function (spot) {
    ["search", "draft"].forEach(function (mode) {
      var old = spot.querySelector(".gen-" + mode);
      if (old) old.remove();
      var lab = genLabel(mode, AI_CACHE[mode + ":" + qid]);
      if (!lab) return;
      var mk = document.createElement("span");
      mk.className = "hasai gen-" + mode;
      mk.textContent = "✦ " + lab;
      spot.appendChild(mk);
    });
  });
}

/* ---- a logged answer can be resent or edited ---- */
function answerRow(el) { return el.closest(".arow"); }

$$("[data-resend]").forEach(function (b) {
  b.addEventListener("click", function () {
    var row = answerRow(b), msg = row.querySelector(".amsg");
    if (!LIVE) { msg.textContent = "needs the live server"; return; }
    b.disabled = true;
    b.classList.add("spin");
    msg.textContent = "posting...";
    fetch("/resend", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: b.dataset.code, when: b.dataset.when }) })
      .then(function (r) { return r.json(); })
      .then(function (s) {
        b.classList.remove("spin");
        if (s.ok) {
          msg.textContent = "posted";
          toast("Answer posted to YouTube.", "good");
        } else {
          msg.textContent = s.error || "failed";
          b.disabled = false;
        }
      })
      .catch(function () {
        b.classList.remove("spin");
        msg.textContent = "could not reach the panel server";
        b.disabled = false;
      });
  });
});

/* Edit reopens the question itself with this answer loaded, so a correction
   goes through the same composer and the same delivery rules as any reply. */
$$("[data-editans]").forEach(function (b) {
  b.addEventListener("click", function () {
    var code = b.dataset.code.toLowerCase();
    var text = answerRow(b).dataset.answer || "";
    var target = null;
    $$("#qtbody tr.qrow").forEach(function (r) {
      if (r.dataset.txt.indexOf(code) !== -1) target = r;
    });
    if (!target) {
      answerRow(b).querySelector(".amsg").textContent = "question not in the inbox";
      return;
    }
    goView("questions");          /* the row it opens lives on that screen */
    setGroup("st", "all");        /* it is answered: the open queue hides it */
    state.q = code;
    $("#q").value = b.dataset.code;
    page = 0;
    apply();
    syncUrl();
    ss("lp-draft:" + target.dataset.id, text);
    toggleDet(target, "box");
    var box = $("tr.qdet .qbox");
    if (box) { box.value = text; box.focus(); }
    $("#questions").scrollIntoView({ block: "start" });
  });
});

/* ---- one customer, everything about them ----
   Built from the question payload the page already carries rather than a
   second copy of the same conversations: a profile is a filter over what is
   here, and duplicating it would grow the file for nothing. */
function customerProfile(who) {
  var mine = [], pat = PATRONS[who.replace(/^@/, "").split(" ")[0].toLowerCase()] || null;
  for (var id in QDATA) if (QDATA[id].who === who) mine.push(QDATA[id]);
  mine.sort(function (a, b) { return a.date < b.date ? 1 : -1; });

  var open = mine.filter(function (q) { return q.status !== "answered"; }).length;
  var sys = {}, chans = {};
  mine.forEach(function (q) {
    if (q.system) sys[q.system] = (sys[q.system] || 0) + 1;
    if (q.channel) chans[q.channel] = (chans[q.channel] || 0) + 1;
  });
  var byCount = function (o) {
    return Object.keys(o).sort(function (a, b) { return o[b] - o[a]; });
  };

  var head = '<div class="cprofile">';
  head += '<div class="chead">';
  if (mine[0] && mine[0].avatar) head += '<img class="cav" src="' + mine[0].avatar + '" alt="">';
  head += '<div><b>' + esc(pat && pat.name ? pat.name : who) + '</b>';
  if (pat && pat.name) head += ' <span class="note">' + esc(who) + "</span>";
  head += '<br><span class="note">';
  var facts = [];
  if (pat && pat.paying) {
    facts.push("paying US$ " + (pat.monthly / 100).toFixed(0) + "/mo"
      + (pat.tiers.length ? " on " + esc(pat.tiers.join(", ")) : ""));
  } else if (pat) { facts.push("used to pay"); }
  if (pat && pat.lifetime) facts.push("US$ " + (pat.lifetime / 100).toFixed(0) + " in total");
  if (pat && pat.since) facts.push("customer since " + esc(pat.since.slice(0, 7)));
  if (mine[0] && mine[0].joined) facts.push("in the server since " + esc(mine[0].joined));
  facts.push(mine.length + " question" + (mine.length === 1 ? "" : "s")
    + (open ? ", " + open + " still waiting" : ", all answered"));
  head += facts.join(" &middot; ") + "</span></div></div>";

  var about = byCount(sys).slice(0, 6).map(function (s) {
    return '<span class="tag">' + esc(s) + " &middot; " + sys[s] + "</span>";
  }).join(" ");
  if (about) head += '<div class="cabout"><span class="clabel">Asks about</span>' + about + "</div>";
  var where = byCount(chans).map(function (c) { return esc(c) + " (" + chans[c] + ")"; }).join(", ");
  if (where) head += '<div class="cabout"><span class="clabel">Talks on</span>'
    + '<span class="note">' + where + "</span></div>";

  /* The conversation, newest first: what they asked and what you replied. */
  head += '<div class="ctl">';
  mine.slice(0, 40).forEach(function (q) {
    head += '<div class="cev' + (q.status === "answered" ? "" : " open") + '">'
      + '<span class="cdate">' + esc(q.date) + "</span>"
      + '<div class="cq">' + esc(q.text.slice(0, 260)) + "</div>"
      + (q.reply ? '<div class="ca">' + esc(q.reply.slice(0, 260)) + "</div>"
                 : '<div class="cwait">no reply yet</div>')
      + (q.link ? ' <a class="clink" href="' + q.link + '" target="_blank" rel="noopener">open where it was asked</a>' : "")
      + "</div>";
  });
  if (mine.length > 40) head += '<div class="note">and ' + (mine.length - 40) + " older</div>";
  head += "</div>";

  /* Yours to set: what the facts cannot tell anyone. */
  var st = CRM[who] || {};
  head += '<div class="cedit" data-who="' + esc(who) + '">';
  head += '<div class="cfield"><span class="clabel">Where they stand</span><select class="cstatus">';
  head += '<option value="">from the facts: ' + esc(st.derived || "") + "</option>";
  MANUAL_STATUS.forEach(function (s) {
    head += '<option value="' + esc(s) + '"' + (st.status === s ? " selected" : "")
      + ">" + esc(s) + "</option>";
  });
  head += "</select></div>";
  head += '<div class="cfield"><span class="clabel">Next action</span>'
    + '<input class="cnext" type="text" placeholder="Follow up about the Ledge System on Monday" value="'
    + esc(st.next || "") + '"></div>';
  head += '<div class="cfield"><span class="clabel">Tags</span>'
    + '<input class="ctags" type="text" placeholder="Ledge System, Rope, Wingman" value="'
    + esc((st.tags || []).join(", ")) + '"></div>';
  head += '<div class="cfield wide"><span class="clabel">Private notes</span>'
    + '<textarea class="cnotes" rows="3" placeholder="Only you see this. It never reaches the customer.">'
    + esc(st.notes || "") + "</textarea></div>";
  head += '<div class="cfield wide"><button class="btn primary csave">Save</button>'
    + '<span class="cmsg note"></span></div>';
  return head + "</div></div>";
}

function saveCustomer(box) {
  var msg = box.querySelector(".cmsg");
  var body = {
    who: box.dataset.who,
    status: box.querySelector(".cstatus").value,
    next: box.querySelector(".cnext").value,
    tags: box.querySelector(".ctags").value.split(",").map(function (t) {
      return t.trim(); }).filter(Boolean),
    notes: box.querySelector(".cnotes").value,
  };
  msg.textContent = "Saving...";
  fetch("/customer", { method: "POST",
    headers: { "Content-Type": "application/json", "X-Panel-Token": PANEL_TOKEN },
    body: JSON.stringify(body) })
    .then(function (r) { return r.json(); })
    .then(function (s) {
      if (!s.ok) { msg.textContent = s.error || "could not save"; return; }
      CRM[body.who] = { status: body.status, next: body.next, tags: body.tags,
                        notes: body.notes, derived: (CRM[body.who] || {}).derived };
      msg.textContent = "Saved to the vault.";
      /* The page rebuilds on any vault change; hold it off long enough to
         read the confirmation instead of watching the row vanish. */
      holdUntil = Date.now() + 6000;
    })
    .catch(function (e) { msg.textContent = "could not save: " + e.message; });
}
document.addEventListener("click", function (ev) {
  var b = ev.target.closest ? ev.target.closest(".csave") : null;
  if (b) saveCustomer(b.closest(".cedit"));
});

/* Delegated, because "View all" adds rows after this runs and a listener
   bound per row would miss every one of them. */
document.addEventListener("click", function (ev) {
  if (!ev.target.closest) return;
  /* The open profile sits in a row of its own directly under the clickable
     one. Typing in it must not fold it shut, and an earlier attempt to
     guard that by stopping the event during capture silently killed the
     Save button along with it. */
  if (ev.target.closest(".cdet") || ev.target.closest("a")) return;
  var tr = ev.target.closest("tr.crow");
  if (tr) toggleCustomer(tr);
});
document.addEventListener("keydown", function (ev) {
  if (ev.key !== "Enter" && ev.key !== " ") return;
  var tr = ev.target.closest ? ev.target.closest("tr.crow") : null;
  if (tr) { ev.preventDefault(); toggleCustomer(tr); }
});

function toggleCustomer(tr) {
  var next = tr.nextElementSibling;
  if (next && next.classList.contains("cdet")) { next.remove(); tr.classList.remove("copen"); return; }
  var open = tr.closest("tbody").querySelector("tr.cdet");
  if (open) { open.previousElementSibling.classList.remove("copen"); open.remove(); }
  var row = document.createElement("tr");
  row.className = "cdet";
  row.innerHTML = '<td colspan="5">' + customerProfile(tr.dataset.who) + "</td>";
  tr.after(row);
  tr.classList.add("copen");
}

/* ---- one product, and everyone waiting on it ----
   Same idea as a customer profile: a filter over the questions the page
   already carries, so no second copy of anything. */
var STOP = {the:1,a:1,an:1,is:1,it:1,in:1,of:1,to:1,my:1,me:1,do:1,can:1,be:1,
  for:1,how:1,what:1,where:1,when:1,why:1,who:1,will:1,are:1,have:1,has:1,
  was:1,not:1,that:1,this:1,on:1,at:1,by:1,or:1,and:1,but:1,if:1,as:1,with:1,
  from:1,any:1,you:1,your:1,we:1,they:1,their:1,there:1,just:1,im:1,its:1,
  get:1,got:1,so:1,up:1,out:1,about:1,also:1,some:1,all:1,no:1,need:1,want:1,
  like:1,more:1,would:1,could:1,should:1,does:1,did:1,use:1,using:1,work:1,
  works:1,make:1,made:1,know:1,think:1,see:1,thanks:1,thank:1,hey:1,hello:1};

function productProfile(name) {
  var mine = [];
  /* the id lives only in the QDATA key; the composer needs it on the item */
  for (var id in QDATA) if (QDATA[id].system === name) {
    QDATA[id].id = id;
    mine.push(QDATA[id]);
  }
  if (!mine.length) return '<div class="cprofile"><p class="empty">Nobody has '
    + "asked about this one yet.</p></div>";
  mine.sort(function (a, b) { return a.date < b.date ? 1 : -1; });
  var open = mine.filter(function (q) { return q.status !== "answered"; });

  /* Who is asking, and which of them pay. Tiers are not per product, so
     this says "these customers care about it", never "these bought it". */
  var byWho = {}, chans = {}, vids = {};
  mine.forEach(function (q) {
    (byWho[q.who] = byWho[q.who] || []).push(q);
    if (q.channel) chans[q.channel] = (chans[q.channel] || 0) + 1;
    if (q.video) vids[q.video] = (vids[q.video] || 0) + 1;
  });
  var askers = Object.keys(byWho).sort(function (a, b) {
    return byWho[b].length - byWho[a].length; });
  var paying = askers.filter(function (w) {
    var p = PATRONS[w.replace(/^@/, "").split(" ")[0].toLowerCase()];
    return p && p.paying; });
  var money = paying.reduce(function (s, w) {
    return s + PATRONS[w.replace(/^@/, "").split(" ")[0].toLowerCase()].monthly; }, 0);

  var out = '<div class="cprofile"><div class="chead"><div><b>' + esc(name) + "</b><br>"
    + '<span class="note">' + mine.length + " question" + (mine.length === 1 ? "" : "s")
    + " from " + askers.length + " people &middot; " + open.length + " still open"
    + (paying.length ? " &middot; " + paying.length + " of them pay, US$ "
        + (money / 100).toFixed(0) + "/mo between them" : "")
    + "</span></div></div>";

  var where = Object.keys(chans).sort(function (a, b) { return chans[b] - chans[a]; })
    .map(function (c) { return esc(c) + " (" + chans[c] + ")"; }).join(", ");
  out += '<div class="cabout"><span class="clabel">Asked on</span>'
    + '<span class="note">' + where + "</span></div>";

  var vlist = Object.keys(vids).sort(function (a, b) { return vids[b] - vids[a]; });
  if (vlist.length) {
    out += '<div class="cabout"><span class="clabel">From videos</span>'
      + vlist.slice(0, 4).map(function (v) {
          return '<span class="tag">' + esc(v.slice(0, 46)) + " &middot; " + vids[v] + "</span>";
        }).join(" ") + "</div>";
  }

  /* Words that keep coming back. Counting is enough to find them; a model
     would be a heavier way to learn the same thing. */
  var freq = {};
  mine.forEach(function (q) {
    var seen = {};
    (q.text.toLowerCase().match(/[a-z]{4,}/g) || []).forEach(function (w) {
      if (STOP[w] || seen[w]) return;
      seen[w] = 1; freq[w] = (freq[w] || 0) + 1;
    });
  });
  var common = Object.keys(freq).filter(function (w) { return freq[w] > 2; })
    .sort(function (a, b) { return freq[b] - freq[a]; }).slice(0, 10);
  if (common.length) {
    out += '<div class="cabout"><span class="clabel">Keeps coming up</span>'
      + common.map(function (w) {
          return '<span class="tag">' + esc(w) + " &middot; " + freq[w] + "</span>";
        }).join(" ") + "</div>";
  }

  out += '<div class="cabout"><span class="clabel">Waiting</span>'
    + '<span class="note">oldest first, so the person who has waited longest is at the top</span></div>';
  out += '<div class="ctl">';
  open.slice().reverse().slice(0, 25).forEach(function (q) {
    var p = PATRONS[q.who.replace(/^@/, "").split(" ")[0].toLowerCase()];
    /* each question here came from a different video; the thumbnail is how
       the eye tells them apart before reading a word */
    out += '<div class="cev open" data-qid="' + esc(q.id) + '">'
      + (q.small ? '<img class="cthumb" loading="lazy" alt="" title="' + esc(q.video || "")
          + '" referrerpolicy="no-referrer" src="' + esc(q.small) + '">' : "")
      + '<div class="cbody"><span class="cdate">'
      + esc(q.date) + " &middot; "
      + esc(q.who) + (p && p.paying ? ' <span class="tag sub">pays</span>' : "")
      + genMarks(q.id)
      + "</span>"
      + '<div class="cq">' + esc(q.text.slice(0, 200)) + "</div>"
      + (q.link ? '<a class="clink" href="' + q.link + '" target="_blank" rel="noopener">open it</a> ' : "")
      + '<button class="btn tiny">Answer</button>'
      + "</div></div>";
  });
  if (!open.length) out += '<div class="note">Nothing open. Everyone who asked got an answer.</div>';
  if (open.length > 25) out += '<div class="note">and ' + (open.length - 25) + " more</div>";
  return out + "</div></div>";
}

function toggleProduct(tr) {
  var next = tr.nextElementSibling;
  if (next && next.classList.contains("pdet")) { next.remove(); tr.classList.remove("copen"); return; }
  var open = tr.closest("tbody").querySelector("tr.pdet");
  if (open) { open.previousElementSibling.classList.remove("copen"); open.remove(); }
  var row = document.createElement("tr");
  row.className = "pdet";
  row.dataset.name = tr.dataset.name;
  row.innerHTML = '<td colspan="5">' + productProfile(tr.dataset.name) + "</td>";
  tr.after(row);
  tr.classList.add("copen");
}
document.addEventListener("click", function (ev) {
  if (!ev.target.closest) return;
  /* The product name still filters the queue; the rest of the row opens
     the product. Two useful actions, and neither steals the other. */
  if (ev.target.closest(".pdet") || ev.target.closest("a")
      || ev.target.closest(".sysdrill")) return;
  var tr = ev.target.closest("tr.prodrow");
  if (tr) toggleProduct(tr);
});

/* A comment is a request when it asks the creator to act rather than asks
   how something works: make a video, add a feature, fix the system. The
   only signal is wording, so the section that uses this says it guessed.
   Word boundaries come from padding with spaces, not from regex escapes:
   this file is a Python string and a backslash would not survive it. */
function reqKind(text) {
  var t = " " + text.toLowerCase().replace(/[^a-z0-9']+/g, " ") + " ";
  var asks = false;
  [" can you ", " could you ", " will you ", " would you ", " can u ", " could u "]
    .forEach(function (s) {
      var i = -1;
      while ((i = t.indexOf(s, i + 1)) !== -1) {
        /* "how can you make X work" asks how, not for */
        if (t.slice(Math.max(0, i - 4), i + 1) === " how ") continue;
        [" make ", " create ", " add ", " build ", " do ", " show ", " cover ",
         " release ", " fix ", " update ", " upgrade ", " support ", " bring "]
          .forEach(function (v) { if (t.indexOf(v, i) !== -1) asks = true; });
      }
    });
  [" please make ", " please add ", " please create ", " please fix ",
   " please update ", " any plans ", " any chance ", " make a video ",
   " make a tutorial ", " do a tutorial ", " tutorial on ", " tutorial about ",
   " tutorial request ", " would love to see ", " would like to see ",
   " is there a tutorial "].forEach(function (m) {
    if (t.indexOf(m) !== -1) asks = true;
  });
  if (!asks) return "";
  var fix = false;
  [" fix ", " fixed ", " update ", " updated ", " upgrade ", " patch ",
   " broken ", " bug "].forEach(function (m) {
    if (t.indexOf(m) !== -1) fix = true;
  });
  return fix ? "fix" : "new";
}

/* ---- one video, and the people still waiting under it ----
   A count tells you where the work is; it does not let you do it. Opening
   a video shows the questions themselves, and hands the whole block to the
   inbox in one move. */
function videoPanel(name) {
  var mine = [];
  for (var id in QDATA) if (QDATA[id].video === name) {
    QDATA[id].id = id;
    mine.push(QDATA[id]);
  }
  var open = mine.filter(function (q) { return q.status !== "answered"; });
  open.sort(function (a, b) { return a.date < b.date ? -1 : 1; });   /* oldest first */
  if (!mine.length) return '<div class="cprofile"><p class="empty">No questions '
    + "came from this video.</p></div>";

  var freq = {};
  mine.forEach(function (q) {
    var seen = {};
    (q.text.toLowerCase().match(/[a-z]{4,}/g) || []).forEach(function (w) {
      if (STOP[w] || seen[w]) return;
      seen[w] = 1; freq[w] = (freq[w] || 0) + 1;
    });
  });
  var common = Object.keys(freq).filter(function (w) { return freq[w] > 2; })
    .sort(function (a, b) { return freq[b] - freq[a]; }).slice(0, 8);

  function cev(q, extra) {
    return '<div class="cev open" data-qid="' + esc(q.id) + '"><div class="cbody"><span class="cdate">'
      + esc(q.date) + " &middot; "
      + esc(q.who) + (extra || "") + genMarks(q.id) + "</span>"
      + '<div class="cq">' + esc(q.text.slice(0, 200)) + "</div>"
      + (q.link ? '<a class="clink" href="' + q.link + '" target="_blank" rel="noopener">open the comment</a> ' : "")
      + '<button class="btn tiny">Answer</button>'
      + "</div></div>";
  }

  /* Requests are decisions for you, questions are answers for them; mixed
     together the requests sank among the how-questions and were never
     weighed as a group. */
  var reqs = [], rest = [];
  open.forEach(function (q) {
    var k = reqKind(q.text);
    if (k) reqs.push({ q: q, kind: k }); else rest.push(q);
  });

  var out = '<div class="cprofile"><div class="cabout">'
    + '<span class="clabel">' + open.length + " waiting</span>"
    + '<button class="btn tiny" data-vall="' + esc(name) + '">Show them all in the inbox</button>'
    + '<button class="btn tiny" data-vdesc="' + esc(name) + '">Description</button>'
    + "</div>";
  if (common.length) {
    out += '<div class="cabout"><span class="clabel">Keeps coming up</span>'
      + common.map(function (w) {
          return '<span class="tag">' + esc(w) + " &middot; " + freq[w] + "</span>";
        }).join(" ") + "</div>";
  }
  if (reqs.length) {
    out += '<div class="cabout"><span class="clabel">Requests &middot; ' + reqs.length + "</span>"
      + '<span class="note">asking you to build, cover or fix something; guessed from the wording</span></div>';
    out += '<div class="ctl">';
    reqs.slice(0, 25).forEach(function (r) {
      out += cev(r.q, ' <span class="tag req">' + (r.kind === "fix" ? "fix ask" : "new ask") + "</span>");
    });
    if (reqs.length > 25) out += '<div class="note">and ' + (reqs.length - 25) + " more</div>";
    out += "</div>";
    if (rest.length) out += '<div class="cabout"><span class="clabel">Questions &middot; '
      + rest.length + "</span></div>";
  }
  out += '<div class="ctl">';
  rest.slice(0, 25).forEach(function (q) { out += cev(q); });
  if (rest.length > 25) out += '<div class="note">and ' + (rest.length - 25) + " more</div>";
  if (!open.length) out += '<div class="note">Everyone who asked here got an answer.</div>';
  return out + "</div></div>";
}

document.addEventListener("click", function (ev) {
  if (!ev.target.closest) return;
  var all = ev.target.closest("[data-vall]");
  if (all) {
    /* The whole block, in the queue, ready to work through. */
    ev.stopPropagation();
    goView("questions");
    setGroup("st", "open");
    state.vid = all.dataset.vall;
    state.q = "";
    $("#q").value = "";
    page = 0; apply(); syncUrl();
    return;
  }
  var descBtn = ev.target.closest("[data-vdesc]");
  if (descBtn) { ev.stopPropagation(); toggleVdesc(descBtn); return; }
  if (ev.target.closest("a") || ev.target.closest(".vdet")) return;
  var row = ev.target.closest(".vrow[data-video]");
  if (!row) return;
  var next = row.nextElementSibling;
  if (next && next.classList.contains("vdet")) { next.remove(); return; }
  var openOne = row.parentNode.querySelector(".vdet");
  if (openOne) openOne.remove();
  var box = document.createElement("div");
  box.className = "vdet";
  box.dataset.video = row.dataset.video;
  box.innerHTML = videoPanel(row.dataset.video);
  row.after(box);
});

/* ---- the real composer, inside a video or a product ----
   The waiting lists used to be read-only: every answer meant leaving the
   panel for the inbox. Clicking a question now puts composerFor(qid) right
   under it, with the same buttons, drafts and cached generations as the
   queue. openIds/closeDet stay out of this on purpose: they belong to the
   queue, and opening here must not close what is open there. */
document.addEventListener("click", function (ev) {
  if (!ev.target.closest) return;
  var item = ev.target.closest(".cev[data-qid]");
  if (!item) return;
  /* links still leave; clicks inside the composer are the composer's */
  if (ev.target.closest("a") || ev.target.closest(".detwrap")) return;
  /* a drag to copy part of the question is not a request to toggle */
  var sel = window.getSelection ? window.getSelection() : null;
  if (sel && !sel.isCollapsed) return;
  /* Any number of composers can be open at once, here and in the queue:
     closing somebody's half-written reply because a second question was
     opened threw work away. The list stays expanded while any composer
     inside it is open. */
  var ctl = item.closest(".ctl");
  var mine = item.querySelector(".detwrap");
  if (mine) {
    mine.remove();
    item.classList.remove("composing");
    if (ctl && !ctl.querySelector(".detwrap")) ctl.classList.remove("composing");
    return;
  }
  var wrap = composerFor(item.dataset.qid);
  if (!wrap) return;
  item.appendChild(wrap);
  item.classList.add("composing");
  if (ctl) ctl.classList.add("composing");
  ["search", "draft"].forEach(function (mode) {
    var hit = AI_CACHE[mode + ":" + item.dataset.qid];
    if (hit) aiRender(wrap, mode, hit, aiBtn(wrap, mode));
  });
  wrap.querySelector(".qbox").focus();
});

/* ---- edit the real video's description without leaving the panel ----
   Reads the live one from YouTube, lets Claude draft a new one from the
   video's own notes, and Save writes it back to the real video with the
   previous version filed in the vault first, so it is never a one-way
   door. The draft lands in a preview, never straight into the textarea:
   overwriting hand edits with a generation threw work away. */
function toggleVdesc(btn) {
  var cab = btn.closest(".cabout");
  var open = cab.nextElementSibling;
  if (open && open.classList.contains("vdesc")) { open.remove(); return; }
  var name = btn.dataset.vdesc;
  var box = document.createElement("div");
  box.className = "vdesc";
  box.innerHTML = '<div class="src">reading the live description from YouTube...</div>'
    + '<textarea class="qbox descbox" aria-label="Video description"></textarea>'
    + '<div class="detbtns">'
    + '<button class="btn tiny ai" data-descai>Draft with Claude</button>'
    + '<button class="btn tiny primary" data-descsave>Save to YouTube</button>'
    + '<span class="msg" aria-live="polite"></span>'
    + '<span class="deliver">saves to the real video; the previous description is filed in the vault first</span>'
    + "</div>";
  cab.after(box);
  var head = box.querySelector(".src");
  var ta = box.querySelector(".descbox");
  var msg = box.querySelector(".msg");
  function count() {
    head.textContent = (head.dataset.title ? head.dataset.title + " · " : "")
      + ta.value.length + " / 5000 characters";
  }
  ta.addEventListener("input", count);
  if (!LIVE) { head.textContent = "Static file: this needs the live server."; return; }
  fetch("/video_desc", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video: name }) })
    .then(function (r) { return r.json(); })
    .then(function (s) {
      if (!s.ok) { head.textContent = s.error || "could not read the description"; return; }
      head.dataset.title = s.title;
      ta.value = s.description || "";
      count();
    })
    .catch(function () { head.textContent = "could not reach the panel server"; });
  box.querySelector("[data-descai]").addEventListener("click", function () {
    var b = box.querySelector("[data-descai]");
    b.disabled = true;
    b.classList.add("spin");
    msg.className = "msg";
    var t0 = Date.now();
    msg.textContent = "Claude is reading this video's notes...";
    var timer = setInterval(function () {
      msg.textContent = "Claude is reading this video's notes... "
        + Math.round((Date.now() - t0) / 1000) + "s";
    }, 1000);
    fetch("/video_desc_ai", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video: name }) })
      .then(function (r) { return r.json(); })
      .then(function (s) {
        clearInterval(timer);
        b.disabled = false;
        b.classList.remove("spin");
        var old = box.querySelector(".descdraft");
        if (old) old.remove();
        if (!s.ok) { msg.textContent = s.error || "failed"; msg.classList.add("bad"); return; }
        msg.textContent = "drafted" + (typeof s.cost === "number"
          ? " for $" + s.cost.toFixed(2) : "") + "; review it below";
        var wrap = document.createElement("div");
        wrap.className = "descdraft";
        var pre = document.createElement("pre");
        pre.textContent = s.description;
        var use = document.createElement("button");
        use.className = "btn tiny";
        use.textContent = "Use this draft";
        use.addEventListener("click", function () {
          ta.value = s.description;
          count();
          wrap.remove();
        });
        wrap.appendChild(pre);
        wrap.appendChild(use);
        box.appendChild(wrap);
      })
      .catch(function () {
        clearInterval(timer);
        b.disabled = false;
        b.classList.remove("spin");
        msg.textContent = "could not reach the panel server";
        msg.classList.add("bad");
      });
  });
  box.querySelector("[data-descsave]").addEventListener("click", function () {
    var b = box.querySelector("[data-descsave]");
    b.disabled = true;
    msg.className = "msg";
    msg.textContent = "updating the real video...";
    fetch("/video_desc_save", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video: name, description: ta.value }) })
      .then(function (r) { return r.json(); })
      .then(function (s) {
        b.disabled = false;
        if (!s.ok) { msg.textContent = s.error || "failed"; msg.classList.add("bad"); return; }
        holdUntil = Date.now() + 6000;
        msg.textContent = s.message || "updated";
        msg.classList.add("good");
        toast("Description updated on the real video.", "good");
      })
      .catch(function () {
        b.disabled = false;
        msg.textContent = "could not reach the panel server";
        msg.classList.add("bad");
      });
  });
}

/* After a reply or a status change lands, the panel holding the composer
   still says the question is waiting. These panels render from QDATA, so
   the caller updates QDATA first and this redraw brings the list and the
   counts back into agreement. A composer in the queue matches neither
   selector and nothing happens, which is the point. */
function panelRefresh(wrap) {
  var vd = wrap.closest(".vdet");
  if (vd && vd.dataset.video) { vd.innerHTML = videoPanel(vd.dataset.video); return; }
  var pd = wrap.closest("tr.pdet");
  if (pd && pd.dataset.name)
    pd.firstElementChild.innerHTML = productProfile(pd.dataset.name);
}


/* ---- a source row on Admin opens into what it actually holds ---- */
document.addEventListener("click", function (ev) {
  if (!ev.target.closest) return;
  var row = ev.target.closest(".srow[data-src]");
  if (!row || ev.target.closest(".srcdet")) return;
  var next = row.nextElementSibling;
  if (next && next.classList.contains("srcdet")) { next.remove(); return; }
  var open = row.parentNode.querySelector(".srcdet");
  if (open) open.remove();
  var det = SRCDET[row.dataset.src];
  if (!det) return;
  var out = '<div><span class="clabel">How it runs</span>'
    + '<span class="note">' + esc(det.script || "") + "</span></div>";
  if (det.files && det.files.length) {
    out += '<div><span class="clabel">What it left on disk</span><ul>'
      + det.files.map(function (f) {
          return "<li><b>" + esc(f.name) + "</b> · " + fmt(f.kb)
            + " KB · written " + f.age_h + "h ago</li>";
        }).join("") + "</ul></div>";
  }
  if (det.counts && det.counts.length) {
    out += '<div><span class="clabel">What is inside</span><ul>'
      + det.counts.map(function (c) {
          return "<li><b>" + fmt(c[1]) + "</b> " + esc(c[0]) + "</li>";
        }).join("") + "</ul></div>";
  }
  if (det.if_broken) {
    out += '<div><span class="clabel">If it stops</span>'
      + '<span class="note">' + esc(det.if_broken) + "</span></div>";
  }
  var box = document.createElement("div");
  box.className = "srcdet";
  box.innerHTML = out;
  row.after(box);
});

/* ---- export what the filters describe ----
   The product list is cloned from the filter select, so the two can never
   disagree about which systems exist. The download goes through fetch with
   the session token in the header, because a plain link cannot carry a
   header and putting the token in a URL leaves it in history. */
(function () {
  var btn = $("#expbtn");
  if (!btn) return;
  btn.addEventListener("click", function () {
    var box = $("#expbox");
    var open = box.classList.toggle("hide");
    btn.setAttribute("aria-expanded", String(!open));
    if (!open) {
      var sel = $("#expsys");
      sel.innerHTML = $("#sysSel").innerHTML.replace("All systems", "all of them");
      sel.value = state.sys;
      $("#expch").value = state.ch;
      $("#expst").value = state.st === "open" ? "open" : state.st === "answered" ? "answered" : "all";
    }
  });
  $("#exprun").addEventListener("click", function () {
    var msg = $("#expmsg");
    msg.textContent = "Building...";
    var params = { channel: $("#expch").value, status: $("#expst").value,
                   system: $("#expsys").value, format: $("#expfmt").value };
    fetch("/export", { method: "POST",
      headers: { "Content-Type": "application/json", "X-Panel-Token": PANEL_TOKEN },
      body: JSON.stringify(params) })
      .then(function (r) {
        if (!r.ok) throw new Error("the server said " + r.status);
        var n = r.headers.get("X-Row-Count") || "?";
        return r.blob().then(function (b) { return { blob: b, n: n }; });
      })
      .then(function (got) {
        var ext = params.format === "md" ? "md" : params.format;
        var stamp = new Date().toISOString().slice(0, 10);
        var name = ["locodev-questions", params.channel, params.status, stamp]
          .join("-") + "." + ext;
        var url = URL.createObjectURL(got.blob);
        var a = document.createElement("a");
        a.href = url; a.download = name;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
        msg.textContent = got.n + " questions in " + name;
      })
      .catch(function (e) { msg.textContent = "could not export: " + e.message; });
  });
})();


/* ---- charts, drawn here rather than baked into the page ----
   Every control below changes geometry: a range slices the series, a
   projection extends the x axis, and expanding a card changes the width.
   A server-drawn SVG could do none of those without a round trip, so the
   whole monthly history ships in CHARTS and the marks are built here.

   The projection is the same series continued: same hue, told apart by a
   dashed stroke, a shaded range and its own legend chip, never by a colour
   of its own. That keeps the palette at the three validated series colours. */

/* ---- gaps and coverage drill into the question table ---- */
function drillTo(sys) {
  var sel = $("#sysSel");
  var has = Array.prototype.some.call(sel.options, function (o) { return o.value === sys; });
  state.sys = has ? sys : "all";
  sel.value = state.sys;
  setGroup("st", "no-source");
  page = 0;
  apply();
  syncUrl();
  goView("questions");
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
  goView("questions");
  var f = $("#filters");
  f.classList.remove("flash");
  void f.offsetWidth;
  f.classList.add("flash");
});
$("#bellbtn").addEventListener("click", function () { goView("questions"); });

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
    closeDet();
  } else if (e.key === "n") {
    var start = kIdx + 1;
    for (var i = 0; i < visRows.length; i++) {
      var r = visRows[(start + i) % visRows.length];
      if (r.dataset.st === "no-source" || r.dataset.st === "escalated") {
        kFocus(visRows.indexOf(r));
        if (!openIds[r.dataset.id]) toggleDet(r);
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
  $$("#qtbody .agecell").forEach(function (cell) {
    var t = Date.parse(cell.dataset.date);
    if (isNaN(t)) return;
    var days = Math.floor((now - t) / 86400000);
    cell.title = cell.dataset.date;
    /* "4y" says backlog; "2022-10-29" makes you do the arithmetic */
    var years = days / 365;
    cell.textContent = days < 1 ? "today"
      : days < 30 ? days + "d"
      : days < 365 ? Math.round(days / 30) + "mo"
      /* one decimal, but never a bare ".0": 2y and 2.0y side by side read
         as two different precisions of the same thing */
      : (Math.round(years * 10) / 10) + "y";
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
      + "<b>Click data is not reachable right now</b><p>" + esc(txt) + "</p></div>";
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
sortRows();
syncSortChips();
apply();
try {
  for (var i = 0; i < sessionStorage.length; i++) {
    var key = sessionStorage.key(i);
    if (key === "lp-open") {
      /* a JSON array now; a plain id is a leftover from before multi-open
         and still restores as a single row */
      var wasOpen = sessionStorage.getItem(key) || "";
      var ids;
      try { ids = JSON.parse(wasOpen); } catch (e2) { ids = [wasOpen]; }
      if (!Array.isArray(ids)) ids = [String(ids)];
      ids.forEach(function (oid) {
        var r = oid && rowById(oid);
        if (r && !r.classList.contains("hide")) toggleDet(r);
      });
    }
  }
} catch (e) {}
(function () {
  /* The browser's own restore fights this one, and `scroll-behavior:smooth`
     turned the restore into a visible slide from the top of the page. Both
     are switched off for the jump, then put back. */
  try { history.scrollRestoration = "manual"; } catch (e) {}
  var sy = ssGet("lp-scroll");
  if (sy === null) return;
  ss("lp-scroll", null);
  var y = parseInt(sy, 10) || 0;
  if (!y) return;
  var html = document.documentElement;
  var prev = html.style.scrollBehavior;
  html.style.scrollBehavior = "auto";
  scrollTo(0, y);
  requestAnimationFrame(function () {
    scrollTo(0, y);          /* again once layout settled, images shift it */
    html.style.scrollBehavior = prev;
  });
})();
"""


# --------------------------------------------------------------------------
# Section builders
# --------------------------------------------------------------------------

def _tiles(d: dict, n_systems: int, below: str = "") -> str:
    """A queue summary, not a KPI gallery.

    Three of the old five tiles measured documentation health, which is not
    what the operator decides on when opening the panel. Those numbers moved
    into the System pressure card, where they sit next to the systems they
    describe. What is left answers: how much is waiting, how much of it is
    ready to answer, and how old the oldest one is.
    """
    hist = d.get("history") or []
    qs = d["questions"]
    open_qs = [q for q in qs if q["status"] in ("no-source", "escalated")]
    escalated = sum(1 for q in open_qs if q["status"] == "escalated")
    ready = sum(1 for q in open_qs if q.get("difficulty") == "easy")
    oldest = min((q["date"] for q in open_qs), default="")

    def series(key):
        return [p.get(key, 0) for p in hist][-60:]

    def delta(key, good_when_up: bool, unit: str = "") -> str:
        dv = _delta24(hist, key)
        if not dv:
            return ""
        cls = ("good" if good_when_up else "bad") if dv > 0 else               ("bad" if good_when_up else "good")
        sign = "+" if dv > 0 else "−"
        arrow = _icon("up", 10) if dv > 0 else _icon("down", 10)
        return (f'<span class="dlt {cls}">{arrow}{sign}{_fmt(abs(dv))}{unit}</span>'
                f'<span>vs 24h ago</span>')

    # Written as what is true of people, not as metric names. "Open
    # questions 1,462" is a number about the database; "1,462 people are
    # waiting for an answer" is the same number about the day ahead, and
    # only the second one tells anyone what to do.
    tiles = [
        ("hero", "chat", "c-blue", "People waiting for an answer",
         _fmt(len(open_qs)), "nobody has replied to them yet",
         delta("open", False), _spark(series("open"), "a", "var(--accent)")),
        ("", "alert", "c-red", "Asked for you by name", _fmt(escalated),
         "they used your name, so a reply is expected", "", ""),
        ("", "sparkle", "c-green", "You can answer these today", _fmt(ready),
         "the answer is already written somewhere in your vault", "", ""),
        ("", "flame", "c-amber", "Waiting the longest", escape(oldest or "-"),
         "that person has had no reply since this day", "", ""),
        ("", "check", "c-violet", "You have answered", f"{d['answer_rate']}%",
         f"{_fmt(sum(1 for q in qs if q['status'] == 'answered'))} of "
         f"{_fmt(len(qs))} people who asked", delta("rate", True, " pp"),
         _spark(series("rate"), "b", "var(--info)")),
    ]
    cells = []
    for extra, icon, color, label, value, sub, dlt, spark in tiles:
        cls = f"tile {extra}".strip()
        cells.append(
            f'<div class="{cls}"><div class="h"><span class="tic {color}">'
            f'{_icon(icon, 14)}</span>{label}</div>'
            f'<div class="row"><div class="v">{value}</div>{spark}</div>'
            f'<div class="s"><span>{sub}</span>{dlt}</div></div>'
        )
    # Not named "extra": the loop above binds that name for the tile class,
    # so a parameter called extra is overwritten before it is ever used and
    # the whole dashboard below silently disappears.
    return (f'<section id="overview"><div class="tiles">{"".join(cells)}</div>'
            f'{below}</section>')


def _bar(pct: int, tone: str = "g") -> str:
    pct = max(0, min(100, int(pct)))
    return (f'<span class="pbar"><i class="{tone}" style="width:{pct}%"></i></span>')


def _needs_attention(d: dict) -> str:
    """What is owed, in the order it is owed.

    Everything here is somebody waiting. Sorted by who is owed most, which
    puts a paying customer above a queue count and a promise you made
    above a stranger's first question.
    """
    people = d["people"]
    items = []

    owed = [p for p in people if p.get("patron", {}).get("paying") and p["open"]]
    if owed:
        money = sum(p["patron"]["monthly_cents"] for p in owed) / 100
        names = ", ".join(escape(p["who"]) for p in owed[:4])
        items.append(("crit", f"{len(owed)} paying customers waiting for a reply",
                      f"US$ {money:,.0f} a month between them &middot; {names}"
                      + (" and more" if len(owed) > 4 else "")))

    promised = [p for p in people if (p.get("note") or {}).get("next")]
    if promised:
        first = promised[0]
        items.append(("warn", f"{len(promised)} next actions you wrote down",
                      f"{escape(first['who'])}: "
                      f"{escape(first['note']['next'][:80])}"))

    esc_n = sum(1 for p in people if p.get("esc"))
    if esc_n:
        items.append(("warn", f"{esc_n} people asked for you by name",
                      "they used your name, so they are waiting on you and "
                      "not on the community"))

    waiting = sum(1 for p in people if p["open"])
    oldest = min((q["date"] for q in d["questions"]
                  if q["status"] != "answered" and q["date"]), default="")
    if waiting:
        items.append(("info", f"{_fmt(waiting)} people have an unanswered question",
                      f"the longest has been waiting since {escape(oldest)}"
                      if oldest else ""))

    lost = [p for p in people
            if p.get("patron") and not p["patron"].get("paying")
            and p["patron"].get("lifetime_cents")]
    if lost:
        items.append(("info", f"{len(lost)} customers stopped paying",
                      "they paid before and no longer do, which is a "
                      "different conversation to have"))

    rows = "".join(
        f'<div class="att att-{tone}"><b>{label}</b>'
        f'<span class="note">{sub}</span></div>'
        for tone, label, sub in items
    ) or '<p class="empty">Nobody is waiting on you. Genuinely.</p>'
    return (f'<section class="card" id="attention"><h2><span class="he">🔔</span>'
            f'Needs attention</h2>{rows}</section>')


def _today_card(d: dict) -> str:
    from datetime import datetime as _dt, timedelta as _td
    today = _dt.now().strftime("%Y-%m-%d")
    week = (_dt.now() - _td(days=7)).strftime("%Y-%m-%d")
    qs = d["questions"]
    asked_today = sum(1 for q in qs if q["date"] == today)
    asked_week = sum(1 for q in qs if q["date"] >= week)
    answered_today = sum(1 for a in (d.get("answers") or [])
                         if (a.get("when") or "")[:10] == today)
    new_people = sum(1 for p in d["people"] if p.get("first") == today)
    pat = d.get("patreon") or {}

    def line(n, label, sub=""):
        return (f'<div class="orow"><span class="olabel">{label}</span>'
                f'<span class="ovals"><b>{_fmt(n)}</b>'
                + (f'<br><span class="note">{sub}</span>' if sub else "")
                + "</span></div>")

    return (
        f'<section class="card"><h2><span class="he">📅</span>Today</h2>'
        + line(asked_today, "questions arrived", f"{_fmt(asked_week)} in the last 7 days")
        + line(answered_today, "you answered")
        + line(new_people, "people asked for the first time")
        + line(pat.get("new_this_month", 0), "new patrons", "this month")
        + "</section>"
    )


def _business_card(d: dict) -> str:
    pat = d.get("patreon") or {}
    people = d["people"]
    waiting = sum(1 for p in people if p["open"])

    def line(label, value, sub=""):
        return (f'<div class="orow"><span class="olabel">{label}</span>'
                f'<span class="ovals"><b>{value}</b>'
                + (f'<br><span class="note">{sub}</span>' if sub else "")
                + "</span></div>")

    rows = line("people who have asked something", _fmt(len(people)))
    if pat:
        rows += line("paying right now", _fmt(pat.get("paying", 0)),
                     f"of {_fmt(pat.get('total', 0))} on Patreon")
        rows += line("coming in monthly",
                     f"US$ {pat.get('monthly_cents', 0) / 100:,.0f}")
        rows += line("paid over the years",
                     f"US$ {pat.get('lifetime_cents', 0) / 100:,.0f}")
    rows += line("questions still open", _fmt(waiting))
    if pat.get("read_at"):
        rows += (f'<p class="note">Patreon read {escape(pat["read_at"])}. '
                 f'WhatsApp and website sales are not here: nothing in this '
                 f'panel can see them yet.</p>')
    return (f'<section class="card"><h2><span class="he">📊</span>'
            f'The business, in short</h2>{rows}</section>')


def _sales_card(d: dict) -> str:
    """Where people are, between never having paid and having left."""
    stages = d.get("pipeline") or []
    if not stages:
        return ""
    top = max((s["n"] for s in stages), default=1) or 1
    rows = []
    for s in stages:
        width = max(2, round(s["n"] * 100 / top))
        tone = "r" if s.get("urgent") else ("g" if s["value"] else "a")
        names = ""
        if s.get("names"):
            names = " &middot; " + ", ".join(escape(n) for n in s["names"])
        rows.append(
            f'<div class="orow"><span class="olabel">{escape(s["stage"])}</span>'
            f'{_bar(width, tone)}'
            f'<span class="ovals"><b>{_fmt(s["n"])}</b>'
            f'<br><span class="note">{escape(s["value"]) if s["value"] else ""}</span>'
            f'</span></div>'
            f'<p class="note stagenote">{escape(s["note"])}{names}</p>'
        )
    return (
        f'<section class="card" id="sales">'
        f'<h2><span class="he">💳</span>Where people are</h2>'
        f'<p class="note">Only what Patreon can prove. A sale made anywhere '
        f'else, on the website or by hand, is not in this and would have to '
        f'come from wherever it was recorded.</p>'
        f'{"".join(rows)}</section>'
    )


def _chart_legend(items: list) -> str:
    """Colour chips with names, above every two-series chart.

    Identity never rides on colour alone: the grey series in these charts is
    deliberately grey, so the legend and the per-bar tooltips are what name
    it, and they are not optional.
    """
    return ('<div class="chlegend">'
            + "".join(f'<span><i style="background:var(--ch-{var})"></i>'
                      f'{escape(label)}</span>' for var, label in items)
            + "</div>")


def _stack_chart(rows: list, bottom: str, top: str, b_var: str, t_var: str,
                 tip: str) -> str:
    """Twelve months as stacked bars, base series anchored to the baseline.

    Plain SVG on the page's own tokens, so it follows the theme like every
    other element. The 2px gap between segments is the surface showing
    through, which keeps the two series apart even where their colours
    cannot (that is what lets the context series be grey).
    """
    if not rows:
        return ""
    W, H, PAD = 560, 132, 16
    peak = max((r[bottom] + r[top] for r in rows), default=1) or 1
    n = len(rows)
    step = (W - PAD) / n
    bw = step - 6
    bars = []
    for i, r in enumerate(rows):
        x = PAD + i * step + 3
        hb = (H - 30) * r[bottom] / peak
        ht = (H - 30) * r[top] / peak
        yb = H - 18 - hb
        yt = yb - (2 if ht else 0) - ht
        title = tip.format(**r, both=r[bottom] + r[top])
        bars.append(
            f'<g class="chbar"><title>{escape(title)}</title>'
            + (f'<rect x="{x:.1f}" y="{yt:.1f}" width="{bw:.1f}" height="{ht:.1f}" '
               f'rx="2" fill="var(--ch-{t_var})"/>' if ht > 0.5 else "")
            + (f'<rect x="{x:.1f}" y="{yb:.1f}" width="{bw:.1f}" height="{hb:.1f}" '
               f'rx="2" fill="var(--ch-{b_var})"/>' if hb > 0.5 else "")
            + "</g>")
        if i % 2 == (n - 1) % 2:
            bars.append(f'<text x="{x + bw / 2:.1f}" y="{H - 4}" class="chx">'
                        f'{escape(r["m"][2:])}</text>')
    grid_y = H - 18 - (H - 30)
    return (
        f'<svg viewBox="0 0 {W} {H}" class="chart" role="img">'
        f'<line x1="{PAD}" y1="{grid_y}" x2="{W}" y2="{grid_y}" class="chgrid"/>'
        f'<text x="{PAD}" y="{grid_y - 4}" class="chx">{_fmt(peak)}</text>'
        f'<line x1="{PAD}" y1="{H - 18}" x2="{W}" y2="{H - 18}" class="chaxis"/>'
        + "".join(bars) + "</svg>")


def _area_chart(points: list, key: str, label_last: str) -> str:
    """One series over time, area under it, endpoint named.

    A single series carries no legend: the card's own heading names it.
    """
    if len(points) < 2:
        return ""
    W, H, PAD = 560, 110, 16
    peak = max(p[key] for p in points) or 1
    n = len(points)

    def xy(i, v):
        return (PAD + i * (W - PAD - 46) / (n - 1), H - 16 - (H - 30) * v / peak)

    coords = [xy(i, p[key]) for i, p in enumerate(points)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    lx, ly = coords[-1]
    hover = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" class="chhit">'
        f'<title>{escape(p["m"])}: {_fmt(p[key])}</title></circle>'
        for (x, y), p in zip(coords, points))
    return (
        f'<svg viewBox="0 0 {W} {H}" class="chart" role="img">'
        f'<polygon points="{PAD},{H - 16} {line} {lx:.1f},{H - 16}" class="charea"/>'
        f'<polyline points="{line}" class="chline"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="var(--ch-main)"/>'
        f'<text x="{lx + 7:.1f}" y="{ly + 4:.1f}" class="chend">{escape(label_last)}</text>'
        f'<text x="{PAD}" y="{H - 4}" class="chx">{escape(points[0]["m"])}</text>'
        f'<text x="{lx:.1f}" y="{H - 4}" class="chx" text-anchor="end">'
        f'{escape(points[-1]["m"])}</text>'
        + hover + "</svg>")


def _business_screen(d: dict) -> str:
    """One screen for the numbers, said as money and people.

    Everything here already existed somewhere: totals on Home, movement in
    Sales, reach in Community. What did not exist is the view an owner
    opens before a decision, where the same numbers sit next to each other
    and one glance answers what the business earns, from whom, and which
    way it is moving.
    """
    pat = d.get("patreon") or {}
    if not pat:
        return ""
    yt = d.get("youtube") or {}
    people = d["people"]

    # Twelve months of questions. "Answered" is their state today, which is
    # the honest reading: nothing records the day an answer was written.
    from datetime import datetime as _dt
    _now = _dt.now()
    _mo12 = []
    y, mth = _now.year, _now.month
    for _ in range(12):
        _mo12.append(f"{y:04d}-{mth:02d}")
        mth -= 1
        if mth == 0:
            y, mth = y - 1, 12
    _mo12.reverse()
    qmonths = [{"m": mo, "answered": 0, "waiting": 0} for mo in _mo12]
    _qidx = {mo: row for mo, row in zip(_mo12, qmonths)}
    for q in d["questions"]:
        row = _qidx.get((q.get("date") or "")[:7])
        if row is None:
            continue
        row["answered" if q["status"] == "answered" else "waiting"] += 1

    def line(label, value, sub=""):
        return (f'<div class="orow"><span class="olabel">{escape(label)}</span>'
                f'<span class="ovals"><b>{value}</b>'
                + (f'<br><span class="note">{sub}</span>' if sub else "")
                + "</span></div>")

    # Where the money comes from
    tiers = ""
    for r in pat.get("by_tier") or []:
        each = r["monthly_cents"] / r["count"] / 100 if r["count"] else 0
        tiers += line(r["tier"], f'US$ {r["monthly_cents"] / 100:,.0f}/mo',
                      f'{_fmt(r["count"])} people at ~US$ {each:,.0f} each')
    paying = pat.get("paying", 0)
    avg = pat.get("monthly_cents", 0) / paying / 100 if paying else 0
    money = (
        f'<section class="card"><h2><span class="he">💰</span>Where the money '
        f'comes from</h2>{tiers}'
        + line("All together", f'US$ {pat.get("monthly_cents", 0) / 100:,.0f}/mo',
               f'{_fmt(paying)} paying, ~US$ {avg:,.0f} each on average')
        + line("Since the campaign began",
               f'US$ {pat.get("lifetime_cents", 0) / 100:,.0f}')
        + "</section>")

    # Which way it is moving
    moving = (
        f'<section class="card"><h2><span class="he">📈</span>Which way it is '
        f'moving</h2>'
        + line("Joined this month", _fmt(pat.get("new_this_month", 0)),
               f'worth US$ {pat.get("new_month_cents", 0) / 100:,.0f}/mo')
        + line("Payment just failed", _fmt(pat.get("declined", 0)),
               f'they paid US$ {pat.get("declined_lifetime_cents", 0) / 100:,.0f} '
               f'before, and have not cancelled')
        + line("Stopped over the years", _fmt(pat.get("stopped", 0)),
               f'US$ {pat.get("stopped_lifetime_cents", 0) / 100:,.0f} earned '
               f'while they stayed')
        + '<p class="chtitle">Pledges started, last 12 months</p>'
        + _chart_legend([("main", "still paying today"),
                         ("mute", "since left")])
        + _stack_chart([{**r, "left": r["total"] - r["still"]}
                        for r in (pat.get("joins") or [])], "still",
                       "left", "main", "mute",
                       "{m}: {both} started, {still} still paying")
        + '<p class="chtitle">When today\'s patrons joined</p>'
        + _area_chart(pat.get("cohort") or [], "cum",
                      _fmt((pat.get("cohort") or [{}])[-1].get("cum", 0)))
        + "</section>")

    # Reach, and how much of it pays
    reach = (yt.get("subscribers", 0) or 0) + (d.get("discord_members") or 0)
    conv = (
        f'<section class="card"><h2><span class="he">🌍</span>Reach, and how '
        f'much of it pays</h2>'
        + line("YouTube", _fmt(yt.get("subscribers", 0)),
               f'{_fmt(yt.get("views", 0))} views all time')
        + line("Discord", _fmt(d.get("discord_members") or 0))
        + line("Patreon", _fmt(pat.get("total", 0)),
               f'{_fmt(paying)} of them pay')
        + line("Paying, out of everyone reached",
               f"{(paying * 100 / reach):.1f}%" if reach else "-",
               f'{_fmt(paying)} of roughly {_fmt(reach)}')
        + "</section>")

    # The work side, in the same breath
    waiting = sum(1 for p in people if p["open"])
    owed = [p for p in people if p.get("patron", {}).get("paying") and p["open"]]
    work = (
        f'<section class="card"><h2><span class="he">💬</span>The work behind '
        f'it</h2>'
        + line("People who have asked something", _fmt(len(people)))
        + line("Waiting for an answer", _fmt(waiting))
        + line("Paying customers among them", _fmt(len(owed)),
               "they come first in Customers")
        + line("You have answered", f'{d["answer_rate"]}%',
               "of everything ever asked")
        + '<p class="chtitle">Questions per month, and what is still waiting</p>'
        + _chart_legend([("mute", "answered by now"), ("warn", "still waiting")])
        + _stack_chart(qmonths, "answered", "waiting", "mute", "warn",
                       "{m}: {both} asked, {waiting} still waiting")
        + "</section>")

    return (
        f'<section id="business"><div class="grid2">'
        f'{money}{moving}{conv}{work}</div>'
        f'<p class="note">Patreon read {escape(pat.get("read_at") or "?")}. '
        f'WhatsApp and website sales are not here: nothing in this panel can '
        f'see them yet, so every money figure on this screen is Patreon only.</p>'
        f'</section>')


def _new_patrons_card(d: dict) -> str:
    """The people who just started paying, by name.

    The Today tile already counts them; a count says the month went well and
    leaves nothing to act on. These are the people a welcome still lands
    for, and whether each one linked their Discord decides whether they show
    up in Customers as themselves or as a stranger.
    """
    rows = []
    for m in (d.get("patreon") or {}).get("recent") or []:
        tier = ", ".join(m["tiers"]) or "no tier yet"
        money = (f'US$ {m["monthly_cents"] / 100:,.0f}/mo'
                 if m.get("monthly_cents") else "free")
        linked = ('' if m.get("linked") else
                  ' <span class="tag miss" title="No Discord linked: their '
                  'questions in the server cannot be matched to this pledge">'
                  'no Discord</span>')
        rows.append(
            f'<div class="orow2"><span class="nm">{escape(m["name"])}</span>'
            f'{linked}<br><span class="note">{escape(tier)} &middot; {money}'
            f' &middot; since {escape(m["since"])}</span></div>'
        )
    if not rows:
        return ""
    return (f'<section class="card"><h2><span class="he">🎉</span>'
            f'New patrons</h2>{"".join(rows)}</section>')


def _community_card(d: dict) -> str:
    """How many people each channel actually reaches.

    Sizes rather than health scores: a number someone can repeat out loud,
    with the one comparison that matters underneath it, which is how much of
    that audience ever pays.
    """
    pat = d.get("patreon") or {}
    yt = d.get("youtube") or {}
    disc = d.get("discord_members") or 0
    rows = []

    def line(label, value, sub=""):
        return (f'<div class="orow"><span class="olabel">{label}</span>'
                f'<span class="ovals"><b>{value}</b>'
                + (f'<br><span class="note">{sub}</span>' if sub else "")
                + "</span></div>")

    if yt.get("subscribers"):
        rows.append(line("YouTube", _fmt(yt["subscribers"]),
                         f'{_fmt(yt.get("views", 0))} views across '
                         f'{_fmt(yt.get("videos", 0))} videos'))
    if disc:
        rows.append(line("Discord", _fmt(disc), "people in the server"))
    if pat.get("total"):
        share = (pat.get("paying", 0) * 100 / pat["total"]) if pat["total"] else 0
        rows.append(line("Patreon", _fmt(pat["total"]),
                         f'{_fmt(pat.get("paying", 0))} of them pay, {share:.0f}%'))
    if not rows:
        return ""
    # The one number that ties the three together, and the honest gap.
    reach = (yt.get("subscribers", 0) or 0) + disc
    paying = pat.get("paying", 0)
    rows.append(line("Paying, out of all that",
                     f"{(paying * 100 / reach):.1f}%" if reach else "-",
                     f'{_fmt(paying)} people out of roughly {_fmt(reach)} reached'))
    return (f'<section class="card"><h2><span class="he">🌍</span>Community</h2>'
            f'{"".join(rows)}'
            f'<p class="note">Email subscribers and Wingman users are not here: '
            f'nothing in this panel can count them yet.</p></section>')


def _overview_cards(d: dict) -> str:
    """The screen that was five numbers and a footer.

    Four questions a person actually opens this page with: where the asking
    happens, which system is under the most pressure, whether the bot has
    what was written, and what was answered last.
    """
    qs = d["questions"]
    ch_q: dict = {}
    for q in qs:
        ch = q.get("channel") or "other"
        ch_q[ch] = ch_q.get(ch, 0) + 1
    ch_p: dict = {}
    for p in d["people"]:
        for ch in (p.get("channels") or {}):
            ch_p[ch] = ch_p.get(ch, 0) + 1
    total_q = sum(ch_q.values()) or 1

    where = []
    for ch in sorted(ch_q, key=lambda c: -ch_q[c])[:3]:
        pct = ch_q[ch] * 100 // total_q
        where.append(
            f'<div class="orow"><span class="olabel">{_brand_icon(ch, 15)}'
            f'{escape(ch)}</span>{_bar(pct, "g" if ch == "discord" else "a")}'
            f'<span class="ovals"><b>{_fmt(ch_q[ch])}</b> questions<br>'
            f'<span class="note">{_fmt(ch_p.get(ch, 0))} people</span></span></div>'
        )

    pressure = []
    for s in sorted(d["systems"], key=lambda s: -s.get("demand", 0))[:5]:
        if not s.get("demand"):
            continue
        tone = "r" if s["pct"] < 40 else ("a" if s["pct"] < 80 else "g")
        pressure.append(
            f'<div class="orow"><span class="olabel">{escape(s["name"])}</span>'
            f'{_bar(s["pct"], tone)}'
            f'<span class="ovals"><b>{_fmt(s["demand"])}</b> waiting<br>'
            f'<span class="note">{s["pct"]}% written</span></span></div>'
        )

    s = d.get("sync") or {}
    queue = len(s.get("waiting_out") or [])
    bot = next((c for c in (s.get("consumers") or []) if c.get("key") == "locoai"), {})
    with_text = s.get("delivered", 0)
    empty = s.get("silent", 0)
    cov = with_text * 100 // max(1, with_text + empty)
    know = (
        f'<div class="obig"><b>{_fmt(bot.get("knows", 0))}</b>'
        f'<span class="note">things the Discord bot can answer from</span></div>'
        f'<div class="orow"><span class="olabel">notes it has</span>{_bar(cov)}'
        f'<span class="ovals"><b>{_fmt(with_text)}</b> of {_fmt(with_text + empty)}<br>'
        f'<span class="note">{_fmt(empty)} still empty</span></span></div>'
        + (f'<p class="note">{_fmt(queue)} notes edited since the last copy '
           f'left, going out about {escape(s.get("next_copy") or "?")}.</p>'
           if queue else '<p class="note">Everything written has been sent.</p>')
    )

    latest = []
    for a in (d.get("answers") or [])[:4]:
        latest.append(
            f'<div class="orow2"><span class="nm">{escape(a["who"])}</span> '
            f'{_brand_icon(a.get("channel", ""), 13)}<br>'
            f'<span class="note">{escape(a["when"])}'
            f'{" &middot; " + escape(a["system"]) if a.get("system") not in ("", "-") else ""}'
            f'</span><div class="oq">{escape(" ".join(a["q"].split())[:110])}</div></div>'
        )

    def card(title, emoji, inner, empty_msg="Nothing yet."):
        body = inner or f'<p class="empty">{empty_msg}</p>'
        return (f'<section class="card"><h2><span class="he">{emoji}</span>'
                f'{title}</h2>{body}</section>')

    # Attention first, then what happened today, then the shape of the
    # business. Everything below that is context rather than a call to act.
    return (
        _needs_attention(d)
        + '<div class="grid2">'
        + _today_card(d)
        + _business_card(d)
        + _new_patrons_card(d)
        + _community_card(d)
        + card("Where they ask", "📣", "".join(where))
        + card("Under the most pressure", "🔥", "".join(pressure))
        + card("What the bot knows", "🤖", know)
        + card("Answered last", "✅", "".join(latest))
        + '</div>'
    )


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
    open_n = sum(1 for q in questions if q["status"] in ("no-source", "escalated"))
    parts.append(f'<span class="fchip on" data-k="st" data-v="open" aria-pressed="true" '
                 f'title="Unanswered plus escalated: everything still waiting on you">'
                 f'<i class="pe">📥</i>Open '
                 f'<span class="fc-n">{_fmt(open_n)}</span></span>')
    parts.append('<span class="fchip" data-k="st" data-v="all" aria-pressed="false">Everything</span>')
    for st in statuses:
        parts.append(f'<span class="fchip" data-k="st" data-v="{escape(st, quote=True)}" '
                     f'aria-pressed="false" title="{escape(_STATUS_TITLE.get(st, st), quote=True)}">'
                     f'{escape(_STATUS_LABEL.get(st, st))} '
                     f'<span class="fc-n">{_fmt(st_counts[st])}</span></span>')
    parts.append('<span class="fsep"></span>')
    parts.append('<span class="fchip on" data-k="sort" data-v="triage" aria-pressed="true" '
                 'title="Escalated first, then what the vault can already answer, '
                 'then oldest">Triage</span>')
    parts.append('<span class="fchip" data-k="sort" data-v="new" aria-pressed="false" '
                 'title="Newest question first">Newest</span>')
    parts.append('<span class="fchip" data-k="sort" data-v="old" aria-pressed="false" '
                 'title="Oldest question first, the longest anyone has waited">'
                 'Oldest</span>')
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
    # Export lives with the filters because it exports what they describe.
    parts.append(
        '<button class="fclear" id="expbtn" aria-expanded="false">export...</button>'
        '<div id="expbox" class="expbox hide" role="group" aria-label="Export">'
        '<label>From<select id="expch"><option value="all">everywhere</option>'
        '<option value="youtube">YouTube</option>'
        '<option value="discord">Discord</option></select></label>'
        '<label>Status<select id="expst"><option value="all">with and without answer</option>'
        '<option value="open">still waiting</option>'
        '<option value="answered">answered</option></select></label>'
        '<label>Product<select id="expsys"></select></label>'
        '<label>As<select id="expfmt"><option value="csv">CSV (Excel)</option>'
        '<option value="md">Markdown</option>'
        '<option value="json">JSON</option></select></label>'
        '<button class="btn primary tiny" id="exprun">Download</button>'
        '<span class="note" id="expmsg"></span></div>')

    parts.append('</div>')
    return "".join(parts)


def _question_rows(questions: list) -> str:
    """Summary rows only.

    The detail card used to be rendered for all 866 questions, textarea and
    buttons included, which is most of a 5.85 MB page for markup nobody had
    opened. The composer is now built once, on demand, from the payload in
    _question_payload().
    """
    rows = []
    for i, q in enumerate(questions):
        hid = "" if i < PAGE else " hide"   # apply() re-pages on load
        sys_label = q["system_name"] if q["system"] != "-" else "catalog wide"
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
            f' data-who="{escape(q["who"].lower(), quote=True)}"'
            f' data-df="{escape(q.get("difficulty", ""), quote=True)}"'
            f' data-cov="{q.get("coverage", 0)}" data-txt="{txt}"></tr>'
        )
    return "".join(rows)


def _question_payload(questions: list) -> dict:
    """Everything the on-demand composer needs, keyed by question id."""
    from urllib.parse import quote

    def where_asked(q: dict) -> str:
        """The link that opens the comment itself.

        Discord questions arrive with one. YouTube ones never did: the
        collector stores the comment id and the video id separately and
        nothing ever put them together, so every one of 859 YouTube
        questions had no way back to the person who asked it. The permalink
        is those two ids in one URL.
        """
        direct = _safe_url(q.get("url", ""))
        if direct:
            return direct
        src = q.get("source", "")
        if q.get("channel") == "youtube" and q.get("video_id") and src.startswith("yt:"):
            return (f"https://www.youtube.com/watch?v={quote(q['video_id'], safe='')}"
                    f"&lc={quote(src[3:], safe='')}")
        return ""

    out = {}
    for q in questions:
        url = _safe_url(q.get("video_url", ""))
        out[q["id"]] = {
            "code": q["code"], "who": q["who"], "channel": q["channel"],
            "date": q["date"], "status": q["status"],
            "system": q["system_name"] if q["system"] != "-" else "catalog wide",
            "text": q["text"], "reply": q.get("reply", ""),
            "video": q.get("video", ""), "video_id": q.get("video_id", ""),
            "video_url": url, "source": q.get("source", ""),
            "link": where_asked(q), "thread": q.get("thread", ""),
            "roles": q.get("roles") or [], "avatar": _safe_url(q.get("avatar_url", "")),
            "joined": q.get("joined", ""), "asker": q["who"],
            "status": q["status"],
            "thumb": _thumb_url(q.get("video_id", "")),
            # For the row itself, which the browser now builds.
            "df": q.get("difficulty", ""), "cov": q.get("coverage", 0),
            "sub": q.get("subscriber") == "yes",
            "small": _thumb_url(q.get("video_id", ""), "default"),
            # Only a YouTube comment can be answered in place; everything
            # else is filed in the vault and the button must say so.
            "postable": bool(
                (q["channel"] == "youtube" and q.get("source", "").startswith("yt:"))
                or (q["channel"] == "discord" and q.get("source", "").startswith("dc:")
                    and "discord.com/channels/" in q.get("url", ""))),
            "dest": ("YouTube" if q["channel"] == "youtube" else "Discord"),
        }
    return out


def _questions_card(d: dict) -> str:
    empty = (
        f'<tr><td colspan="7"><div class="emptybox">'
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
        f'j/k navigate &middot; n next open &middot; Enter to answer</span></h2>'
        f'{_filters(d["questions"])}'
        f'<div class="scroll"><table aria-label="Incoming questions"><thead><tr>'
        f'<th scope="col" class="qcol">Question</th>'
        f'<th scope="col" data-sort="status" aria-sort="none">Status{arrow}</th>'
        f'<th scope="col" data-sort="cov" aria-sort="none">Vault match{arrow}</th>'
        f'<th scope="col" data-sort="who" aria-sort="none">Customer{arrow}</th>'
        f'<th scope="col" data-sort="system" aria-sort="none">System{arrow}</th>'
        f'<th scope="col" data-sort="date" aria-sort="none">Age{arrow}</th>'
        f'<th scope="col"></th>'
        f'</tr></thead><tbody id="qtbody">{body}</tbody></table></div>'
        f'<div class="emptybox hide" id="qempty">'
        f'<span class="eic">{_icon("filter", 20)}</span>'
        f'<b>Nothing matches these filters</b>'
        f'<p>Try widening the channel, status or system filter.</p>'
        f'<button class="btn tiny" id="qemptyclear">Clear filters</button></div>'
        f'<div class="pager" id="pager">'
        f'<button class="btn tiny" id="pgprev">&larr; Previous</button>'
        f'<span class="pgpos">page <b id="pgnow">1</b> of <b id="pgtot">1</b></span>'
        f'<button class="btn tiny" id="pgnext">Next &rarr;</button>'
        f'<label class="pgsize">rows'
        f'<select id="pgsize" class="fchip" aria-label="Rows per page">'
        f'<option value="25">25</option><option value="50">50</option>'
        f'<option value="100">100</option></select></label></div>'
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
        # "vault only" is not a neutral state: the customer never got the
        # reply. It reads as a warning until the platform actually has it.
        posted = ('<span class="pill st-ok"><i class="pe">\U0001f4e4</i>'
                  'posted to youtube</span>' if a["posted"]
                  else '<span class="pill st-escalated"><i class="pe">⚠️</i>'
                       'not sent yet</span>')
        code = (f'<span class="qid" data-copy="{escape(a["code"], quote=True)}">'
                f'{escape(a["code"])}</span>') if a.get("code") else ""
        url = _safe_url(a.get("video_url", ""))
        thumb = ""
        if a.get("video_id"):
            img = (f'<span class="vthumb"><img loading="lazy" alt="" width="68" '
                   f'height="38" referrerpolicy="no-referrer" '
                   f'src="{_thumb_url(a["video_id"])}" '
                   f'onerror="this.parentNode.classList.add(\'hide\')"></span>')
            thumb = (f'<a class="athumb" href="{escape(url, quote=True)}" target="_blank" '
                     f'rel="noopener" title="{escape(a.get("video", ""), quote=True)}">'
                     f'{img}</a>') if url else img

        # A reply that never reached the customer needs a way out, not just
        # a warning label. Retry only appears where there is somewhere to
        # post to; Edit reopens the question with this text loaded.
        acts = []
        if a.get("code"):
            acts.append(f'<button class="btn tiny" data-editans '
                        f'data-code="{escape(a["code"], quote=True)}">Edit</button>')
            if not a["posted"] and a["channel"] in ("youtube", "discord"):
                acts.append(f'<button class="btn tiny primary" data-resend '
                            f'data-code="{escape(a["code"], quote=True)}" '
                            f'data-when="{escape(a["when"], quote=True)}">'
                            f'Retry send</button>')
        actions = (f'<div class="aacts">{"".join(acts)}'
                   f'<span class="amsg" aria-live="polite"></span></div>'
                   if acts else "")

        rows.append(
            f'<div class="arow{hid}" data-answer="{escape(a["a"], quote=True)}">'
            f'<div class="hd">{code}{_avatar(a["who"], "sm")}'
            f'<b>{escape(a["who"])}</b>{_chn(a["channel"])}{posted}'
            f'<span class="w">{escape(a["when"])}</span></div>'
            f'<div class="abody">{thumb}<div>'
            f'<div class="q">{escape(a["q"])}</div>'
            f'<div class="a">{escape(a["a"])}</div>{actions}</div></div></div>'
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


def _system_pressure_card(d: dict, facets: list) -> str:
    """One table where three cards used to disagree.

    Gaps, Priority queue and Documentation coverage each listed the same
    systems in a different grammar, so Weapon System read as 88 gaps, 100%
    priority and 0% coverage and the reader had to reconcile them. One row
    per system, sorted by the pressure it is under.
    """
    n_facets = len(facets)
    labels = [lbl for (_k, lbl, _p, _w) in facets]
    gap_by_key = {g["key"]: g for g in d["gaps"]}

    rows_data = []
    for s in d["systems"]:
        gap = gap_by_key.get(s["slug"])
        rows_data.append({
            "slug": s["slug"], "name": s["name"],
            "open": gap["count"] if gap else 0,
            "done": s["done"], "pct": s["pct"], "urgency": s["urgency"],
            "missing": [lbl for lbl, ok in zip(labels, s["facets"]) if not ok],
            "last": max((q["date"] for q in gap["questions"]), default="") if gap else "",
        })
    rows_data.sort(key=lambda r: (-r["open"], -r["pct"]))

    rows = []
    for i, r in enumerate(rows_data):
        if not r["open"] and r["done"] == n_facets:
            continue          # nothing pending and nothing missing
        hid = "" if i < 10 else " xtra hide"
        cov = r["done"] * 100 // n_facets
        cls = "g" if cov >= 80 else ("a" if cov >= 40 else "r")
        nxt = r["missing"][0] if r["missing"] else "complete"
        upill = (f' <span class="pill u-{r["urgency"]}">{r["urgency"]}</span>'
                 if r["urgency"] in ("critical", "urgent") else "")
        openc = (f'<span class="gcnt">{r["open"]}</span>' if r["open"]
                 else '<span class="zero">0</span>')
        rows.append(
            f'<tr class="prodrow {hid.strip()}" tabindex="0" '
            f'data-name="{escape(r["name"], quote=True)}" '
            f'title="Open this product"><td><span class="sysdrill" '
            f'data-sys="{escape(r["slug"], quote=True)}" '
            f'title="Filter the queue to this system">{escape(r["name"])}</span>{upill}</td>'
            f'<td class="num">{openc}</td>'
            f'<td><span class="cbar"><span class="pbar">'
            f'<i class="{cls}" style="width:{cov}%"></i></span>'
            f'<b>{r["done"]}/{n_facets}</b></span></td>'
            f'<td class="nextfacet">{escape(nxt)}</td>'
            f'<td class="num">P{i + 1}</td></tr>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(rows)} systems</button>'
            if len(rows) > 10 else "")
    pct = d["written"] * 100 // d["total_facets"] if d["total_facets"] else 0
    return (
        f'<section class="card" id="systems">'
        f'<h2><span class="he">🔥</span>Products, and who is waiting on each'
        f'<span class="cnt">{_fmt(d["total_facets"] - d["written"])} notes still '
        f'to write across every product</span></h2>'
        f'<div class="scroll"><table aria-label="Products by demand"><thead><tr>'
        f'<th scope="col">Product</th><th scope="col">People waiting</th>'
        f'<th scope="col">Written up</th><th scope="col">Write this next</th>'
        f'<th scope="col">Order</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>{more}</section>'
    )


def _people_card(d: dict) -> str:
    rows = []
    for i, p in enumerate(d["people"]):
        hid = "" if i < 8 else " xtra hide"
        tags = ""
        if p.get("esc"):
            tags += ' <span class="tag esc">asked for you</span>'
        if p.get("lead"):
            tags += ' <span class="tag lead">lead</span>'
        if p["subscriber"] == "yes":
            tags += ' <span class="tag sub">sub</span>'
        # Where they turn up, in order of how often. Someone who asks in
        # Discord is in the community; someone who only comments on a video
        # is an audience, and the two are worth telling apart at a glance.
        seen = p.get("channels") or ({p["channel"]: p["asked"]} if p.get("channel") else {})
        marks = "".join(
            f'<span class="chmark" title="{n} on {escape(ch, quote=True)}">'
            f'{_brand_icon(ch, 13) or ""}</span>'
            for ch, n in sorted(seen.items(), key=lambda kv: -kv[1])
            if ch in _BRAND
        )
        rows.append(
            f'<tr class="crow {hid.strip()}" tabindex="0" '
            f'data-who="{escape(p["who"], quote=True)}" '
            f'title="Open this customer"><td><span class="uc">{_avatar(p["who"], "sm")}'
            f'<span class="n">{escape(p["who"])}{tags}</span>{marks}</span>'
            f'{_patron_line(p)}</td>'
            f'<td>{_pays(p)}</td>'
            f'<td class="num">{p["asked"]}</td><td class="num">{p["open"]}</td>'
            f'<td class="num">{p["last"]}</td></tr>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(d["people"])} people</button>'
            if len(d["people"]) > 8 else "")
    body = "".join(rows) if rows else (
        '<tr><td colspan="5"><div class="empty">Nobody logged yet.</div></td></tr>')

    paying = [p for p in d["people"] if p.get("patron", {}).get("paying")]
    monthly = sum(p["patron"]["monthly_cents"] for p in paying)
    owed = [p for p in paying if p["open"]]
    head = f'{_fmt(len(d["people"]))} people'
    if paying:
        head += (f' &middot; {len(paying)} paying, US$ {monthly / 100:,.0f}/mo'
                 f'{f" &middot; {len(owed)} waiting on you" if owed else ""}')
    return (
        f'<section class="card" id="people"><h2><span class="he">👥</span>Customers'
        f'<span class="cnt">{head}</span></h2>'
        f'<p class="note">Paying customers with an unanswered question come '
        f'first. Money shows only where someone linked their Patreon to their '
        f'Discord; everyone else may well be paying and nothing here says so.</p>'
        f'<div class="scroll"><table aria-label="Customers"><thead><tr>'
        f'<th scope="col">Person</th><th scope="col">Paying</th>'
        f'<th scope="col">Asked</th><th scope="col">Waiting</th>'
        f'<th scope="col">Last seen</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div>{more}</section>'
    )


def _patron_line(p: dict) -> str:
    """The customer's real name and how long they have been paying."""
    pat = p.get("patron") or {}
    if not pat:
        return ""
    bits = []
    if pat.get("name"):
        bits.append(escape(pat["name"]))
    if pat.get("since"):
        bits.append(f'customer since {escape(pat["since"][:7])}')
    if pat.get("lifetime_cents"):
        bits.append(f'US$ {pat["lifetime_cents"] / 100:,.0f} in total')
    return f'<br><span class="note">{" &middot; ".join(bits)}</span>' if bits else ""


def _pays(p: dict) -> str:
    pat = p.get("patron") or {}
    if not pat:
        return '<span class="note">-</span>'
    if not pat.get("paying"):
        # Someone who used to pay is a different person to talk to than
        # someone who never did, so the difference is on the row.
        return '<span class="pill st-no-source">was paying</span>'
    tier = ", ".join(t for t in pat.get("tiers", []) if t and t != "Free")
    money = f'US$ {pat["monthly_cents"] / 100:,.0f}/mo' if pat.get("monthly_cents") else "free tier"
    return (f'<span class="pill st-ok">{escape(tier or "patron")}</span>'
            f'<br><span class="note">{money}</span>')


def _videos_card(d: dict) -> str:
    """Videos ordered by how much work each one is still holding.

    A list by date answers which videos exist. Sorted by unanswered
    comments it answers where half an hour goes furthest, which is a
    different question and the one somebody opens this page with. One
    tutorial is holding 73 people; on a date-ordered list it sat between
    two videos nobody has asked about.
    """
    videos = d["videos"]
    transcripts = sum(1 for v in videos if v["transcript"])
    assets_n = sum(1 for v in videos if v.get("assets"))
    untagged = sum(1 for v in videos if not v.get("system") or v.get("system") == "-")

    # Comments per video, from the questions the scan already read.
    open_by, total_by = {}, {}
    for q in d["questions"]:
        name = q.get("video")
        if not name:
            continue
        total_by[name] = total_by.get(name, 0) + 1
        if q["status"] != "answered":
            open_by[name] = open_by.get(name, 0) + 1

    # Waiting people first, then the ones missing a piece, then the rest.
    def rank(v):
        missing = (0 if v.get("system") and v["system"] != "-" else 1) + \
                  (0 if v["transcript"] else 1)
        return (-open_by.get(v["name"], 0), -missing, v["published"])
    videos = sorted(videos, key=rank)

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
        tagged = bool(v.get("system") and v["system"] != "-")
        tag = (f'<span class="vtag">{escape(v["system"])}</span>' if tagged
               else '<span class="vtag miss">no product</span>')
        # Absence-only marking hid the answer to "does this one have its
        # transcript?" whenever the answer was yes, which for the visible
        # rows was always. Both states say so now.
        tag += ('<span class="vtag has" title="The spoken words are in the '
                'vault: Suggest and the bot can quote this video">'
                'transcript</span>' if v["transcript"]
                else '<span class="vtag miss" title="Nothing said in this '
                'video is in the vault: Suggest and the bot cannot answer '
                'from it">no transcript</span>')
        # Positive-only while the rollout is one video old: 158 red tags
        # would say nothing except that the initiative is new.
        if v.get("assets"):
            tag += ('<span class="vtag has" title="This video has an assets '
                    'and access note: free downloads, tier access and short '
                    'links, ready to answer with">assets</span>')

        waiting = open_by.get(v["name"], 0)
        total = total_by.get(v["name"], 0)
        answered = total - waiting
        # Three things make a video finished: it is filed under a product,
        # its words are in the vault, and nobody is still waiting on it.
        done = (1 if tagged else 0) + (1 if v["transcript"] else 0) \
            + (1 if total and not waiting else 0)
        pct = done * 100 // 3
        tone = "g" if done == 3 else ("a" if done == 2 else "r")
        count = (f'<span class="vwait">{_fmt(waiting)} waiting</span>'
                 f'<span class="note">of {_fmt(total)}</span>' if waiting
                 else (f'<span class="note">all {_fmt(total)} answered</span>'
                       if total else '<span class="note">no comments</span>'))
        views = v.get("views", "")
        seen = ""
        if str(views).isdigit():
            n = int(views)
            # One question per so many viewers says more than either number
            # alone: a video nobody asks about is either clear or ignored,
            # and the ratio tells you which.
            per = f" &middot; one question per {n // total:,} viewers" if total else ""
            seen = (f'<span class="vseen">{_fmt(n)} views{per}</span>')
        if not v.get("description"):
            tag += '<span class="vtag miss">no description</span>'

        rows.append(
            f'<div class="vrow{hid}" data-video="{escape(v["name"], quote=True)}" '
            f'tabindex="0" title="Open the questions from this video">{thumb}'
            f'<span class="t">{title}<br>{tag}{seen}</span>'
            f'<span class="vcount">{count}</span>'
            f'<span class="vbar">{_bar(pct, tone)}</span>'
            f'<span class="d">{escape(v["published"])}</span></div>'
        )
    more = (f'<button class="linkbtn" data-viewall>View all {len(videos)} videos</button>'
            if len(videos) > 6 else "")
    body = "".join(rows) if rows else '<div class="empty">No videos collected yet.</div>'
    waiting_total = sum(open_by.values())
    return (
        f'<section class="card" id="videos">'
        f'<h2><span class="he">🎬</span>Videos, by how much each is holding'
        f'<span class="cnt">{_fmt(waiting_total)} people waiting across '
        f'{_fmt(len(videos))} videos</span></h2>'
        f'<p class="note">Most waiting first. {untagged} are not linked to a '
        f'product, so their questions belong to nothing, and '
        f'{len(videos) - transcripts} have no transcript in the vault, so '
        f'neither Suggest nor the bot can answer from what was said in them. '
        f'{_fmt(assets_n)} of {_fmt(len(videos))} carry an assets and access '
        f'note saying what is free, what each tier gets and the short links '
        f'to hand out.</p>'
        f'{body}{more}</section>'
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
        f'<section class="card" id="links"><h2><span class="he">🔗</span>Links people clicked'
        f'<span class="cnt" id="lt-state" role="status" aria-live="polite">loading...</span>'
        f'<a class="admlink" href="https://locodev.dev/adminlocoILco" target="_blank" '
        f'rel="noopener">open admin {_icon("external", 12)}</a></h2>'
        f'<div id="lt-body">{skel}</div>'
        f'</section>'
    )


_HEALTH_PILL = {"ok": "ok", "late": "partial", "stale": "blind",
                "missing": "blind", "unknown": "no-source"}
_HEALTH_WORD = {"ok": "arriving", "late": "running late", "stale": "not arriving",
                "missing": "never arrived", "unknown": "unknown"}


def _health_card(d: dict) -> str:
    """Whether each source is still arriving, said plainly.

    Every silent failure this panel has had looked identical from outside:
    a number that was simply old. Nothing said so, and the fix always
    started with somebody noticing by accident.
    """
    rows = []
    for h in (d.get("health") or []):
        pill = _HEALTH_PILL.get(h["state"], "no-source")
        fix = (f'<br><span class="note">{escape(h["fix"])}</span>'
               if h.get("fix") else "")
        rows.append(
            f'<div class="srow"><span><span class="nm">{escape(h["name"])}</span>'
            f'<br><span class="note">{escape(h["note"])}{fix}</span></span>'
            f'<span class="vol">{escape(h["expect"])}</span>'
            f'<span class="pill st-{pill}">{escape(_HEALTH_WORD.get(h["state"], h["state"]))}</span>'
            f'</div>'
        )
    if not rows:
        return ""
    # Stamped by hand: the screen a card belongs to is derived from its id,
    # and this one has no nav entry of its own, so it was showing on every
    # screen instead of on Admin.
    return (f'<section class="card" id="health" data-view="sources">'
            f'<h2><span class="he">🩺</span>Is everything still arriving?</h2>'
            f'<p class="note">Read from what each collector last wrote, not by '
            f'calling anything: what matters is whether the data arrived.</p>'
            f'{"".join(rows)}</section>')


def _sources_card(instrumentation: list, d: dict | None = None) -> str:
    d = d or {}
    # The technical readout lives here and only here. It was in the footer
    # of every screen, where it was noise under pages about people; someone
    # who wants the scan time comes to Admin to find it.
    tech = (
        f'<p class="note">Last read of the vault: {escape(d.get("generated_at", "?"))}, '
        f'{_fmt(d.get("scan_ms", 0))} ms across {_fmt(d.get("md_files", 0))} notes. '
        f'{_fmt(len(d.get("history") or []))} points of history kept. '
        f'The page is a rendered snapshot of the vault: closing it loses no '
        f'work, and Panel/panel.html on disk holds whatever it shows.</p>'
    )
    rows = [tech]
    for source, vol, state, note in instrumentation:
        rows.append(
            f'<div class="srow" data-src="{escape(source, quote=True)}" tabindex="0" '
            f'title="Open the details">'
            f'<span><span class="nm">{escape(source)}</span><br>'
            f'<span class="note" title="{escape(note, quote=True)}">{escape(note)}</span></span>'
            f'<span class="vol">{escape(vol)}</span>'
            f'<span class="pill st-{escape(state, quote=True)}">{escape(state)}</span></div>'
        )
    return (
        f'<section class="card" id="sources"><h2><span class="he">👀</span>What this panel can and cannot see</h2>'
        f'{"".join(rows)}</section>'
    )


# Plain words, because these are read by the person who wrote the notes and
# not by whoever built the pipeline. "Delivered" and "silent" meant nothing
# to the one reader this screen has.
_SYNC_STATE = {
    "delivered": ("ok", "Yes", "the bot can answer from this note"),
    "pending": ("partial", "Not yet", "written, but the copy has not gone out"),
    "silent": ("blind", "Nothing to send",
               "the note is empty, so there is nothing for the bot to learn"),
    "generated": ("no-source", "Sent as answers",
                  "this file is written for you from answers you already gave"),
}


def _sync_card(d: dict) -> str:
    s = d.get("sync") or {}
    rows = s.get("rows") or []
    if not rows:
        return ('<section class="card" id="sync"><h2><span class="he">🔄</span>'
                'Knowledge delivery</h2><p class="empty">No catalog notes found.</p>'
                '</section>')

    who = []
    for c in s.get("consumers") or []:
        pill = ("ok" if c["state"] == "up to date"
                else "partial" if c["state"] == "waiting for the next copy"
                else "no-source")
        who.append(
            f'<div class="who"><div><span class="nm">{escape(c["name"])}</span>'
            f'<span class="pill st-{pill}">{escape(c["state"])}</span><br>'
            f'<span class="route">{escape(c["route"])}</span><br>'
            f'<span class="note">{escape(c["how"])}</span></div>'
            f'<div class="cnt"><b>{_fmt(c["knows"])}</b><br>'
            f'<span class="note">{escape(c["detail"])}<br>'
            f'last copy: {escape(c["stamp"] or "never")}</span></div></div>'
        )

    # Empty notes first: a note the bot already has asks nothing of anyone.
    order = {"silent": 0, "pending": 1, "delivered": 2, "generated": 3}
    body = []
    for r in sorted(rows, key=lambda x: (order.get(x["state"], 9), x["rel"])):
        cls, label, why = _SYNC_STATE.get(r["state"], ("unknown", "?", ""))
        extra = f' ({_fmt(r["shipped"])} pieces)' if r["state"] == "delivered" else ""
        tier = f' <span class="tag">{escape(r["tier"])}</span>' if r["tier"] else ""
        body.append(
            f'<tr data-state="{escape(r["state"], quote=True)}">'
            f'<td><span class="nm">{escape(r["name"])}</span>{tier}<br>'
            f'<span class="note">{escape(r["rel"])}</span></td>'
            f'<td class="num">{_fmt(r["written"])}</td>'
            f'<td><span class="pill st-{cls}" title="{escape(why, quote=True)}">'
            f'{escape(label)}</span>{extra}</td>'
            f'<td><span class="pill st-ok">Yes</span></td>'
            f'<td class="note">{escape(r["modified"])}</td></tr>'
        )

    # What is in flight, at the top, because it is the only part of this
    # screen that changes minute to minute. The page rebuilds on every vault
    # change, so editing a note puts it in this list on the next save.
    queue = s.get("waiting_out") or []
    if queue:
        items = []
        for q in queue[:8]:
            ago = f", {_fmt(q['mins'])} min ago" if q["mins"] < 600 else ""
            items.append(
                f'<li><span class="nm">{escape(q["name"])}</span> '
                f'<span class="note">{escape(q["rel"])} &middot; '
                f'edited {escape(q["when"])}{escape(ago)}</span></li>'
            )
        names = "".join(items)
        rest = (f'<li class="note">and {_fmt(len(queue) - 8)} more</li>'
                if len(queue) > 8 else "")
        live = (
            f'<div class="queue"><div class="qh">'
            f'<span class="pill st-partial">{_fmt(len(queue))} waiting to go out</span>'
            f'<span class="note">Notes you changed since the last copy left. '
            f'The next copy goes out about {escape(s.get("next_copy") or "?")}, '
            f'then the bot picks it up within the hour.</span></div>'
            f'<ul class="qlist">{names}{rest}</ul></div>'
        )
    else:
        live = (
            f'<div class="queue"><div class="qh">'
            f'<span class="pill st-ok">nothing waiting</span>'
            f'<span class="note">Everything you have written has left this '
            f'computer. {escape(s.get("upload") or "")}.</span></div></div>'
        )

    empty = s.get("silent", 0)
    summary = (
        f'<p class="note">Every note you have written, and whether each '
        f'assistant can use it. <b>{_fmt(s.get("delivered", 0))}</b> notes are '
        f'in the Discord bot. <b>{_fmt(empty)}</b> are still empty, so there is '
        f'nothing in them for it to learn. Wingman reads the files here, so it '
        f'can open all of them either way.</p>'
    )

    return (
        f'<section class="card" id="sync">'
        f'<h2><span class="he">🔄</span>What each assistant knows</h2>'
        f'{live}{"".join(who)}{summary}'
        f'<div class="scroll"><table><thead><tr>'
        f'<th>Note</th><th class="num">Letters you wrote</th>'
        f'<th>Discord bot knows it?</th><th>Wingman can read it?</th>'
        f'<th>Last edited</th>'
        f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
        f'</section>'
    )


def _wingman_card(d: dict) -> str:
    s = d.get("sync") or {}
    backlog = [b for b in (s.get("backlog") or []) if b["waiting"] or b["written"]]
    if not backlog:
        return ""

    rows = []
    for b in backlog[:24]:
        # The comparison that decides the order: people waiting against how
        # much has been written for them.
        if b["waiting"] >= 40 and b["written"] < 1000:
            cls, label = "blind", "write this first"
        elif b["written"] < 1000:
            cls, label = "partial", "nothing written yet"
        else:
            cls, label = "ok", "documented"
        rows.append(
            f'<tr><td><span class="nm">{escape(b["name"])}</span><br>'
            f'<span class="note">{escape(b["slug"])}</span></td>'
            f'<td class="num">{_fmt(b["waiting"])}</td>'
            f'<td class="num">{_fmt(b["written"])}</td>'
            f'<td class="num">{_fmt(b["notes"] - b["empty"])} of {_fmt(b["notes"])}</td>'
            f'<td><span class="pill st-{cls}">{escape(label)}</span></td></tr>'
        )

    return (
        f'<section class="card" id="wingman">'
        f'<h2><span class="he">✍️</span>What to write next</h2>'
        f'<p class="note">Wingman reads your Unreal projects here on this '
        f'computer and writes the notes. This is the order that matters: how '
        f'many people are waiting for an answer about a system, against how '
        f'much has been written about it. The brief it follows is '
        f'<code>clickup-mcp/WINGMAN_BRIEF.md</code>.</p>'
        f'<div class="scroll"><table><thead><tr>'
        f'<th>System</th><th class="num">People waiting</th>'
        f'<th class="num">Letters written</th><th class="num">Notes with text</th>'
        f'<th>Where it stands</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        f'</section>'
    )


# Named for what a person comes here to do. The ids stay as they were:
# they are what the screen switch and every #questions link already use, and
# renaming them would break bookmarks to rename nothing a reader can see.
#
# No tab is created for something that does not exist yet. A Sales tab with
# no purchase anywhere behind it looks like a finished feature and answers
# every question with a blank, which is worse than not having it.
_NAV = [
    ("overview", "home", "Home", ""),
    ("questions", "chat", "Inbox", "open_q"),
    # Label matches the screen's own heading: this tab counts replies sent
    # from the panel's log, not the 900-odd vault-wide answered questions
    # the Home tile counts, and calling both "answered" read as a bug.
    ("answers", "check", "Answers sent", "answers"),
    ("people", "users", "Customers", ""),
    ("sales", "target", "Sales", ""),
    ("business", "grid", "Business", ""),
    ("systems", "flame", "Products", ""),
    ("videos", "video", "Videos", ""),
    ("links", "link", "Links", ""),
    ("sync", "refresh", "Knowledge", "silent"),
    ("wingman", "sparkle", "Writing", ""),
    ("sources", "database", "Admin", ""),
]


def _stamp_views(html: str) -> str:
    """Tag each card with the screen it belongs to, from its own id.

    Derived rather than declared in ten places: the sidebar already links to
    #people, so the card with id="people" is the People screen by
    definition, and a card added later joins a screen by being given an id
    that a nav entry points at.
    """
    known = {sid for sid, _i, _l, _c in _NAV}
    return re.sub(
        r'<section((?:\s+class="[^"]*")?)\s+id="([a-z]+)"',
        lambda m: (f'<section{m.group(1)} id="{m.group(2)}" '
                   f'data-view="{m.group(2)}"' if m.group(2) in known
                   else m.group(0)),
        html,
    )


def _nav_counts(d: dict) -> dict:
    return {"open_q": d["open_q"], "answers": len(d.get("answers") or []),
            # The badge counts the notes delivering nothing, because that is
            # the number worth acting on; a delivered note needs no attention.
            "silent": (d.get("sync") or {}).get("silent", 0)}


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
        f'autocomplete="off" aria-label="Search questions"><kbd>Ctrl K</kbd>'
        f'<div id="qres" class="qres hide" role="listbox"></div></div>'
        f'<button class="btn primary" id="updbtn" aria-label="Rebuild the panel now">'
        f'{_icon("refresh", 14)}Update</button>'
        f'<button class="btn icon" id="filtbtn" aria-label="Jump to filters" title="Filters">'
        f'{_icon("filter", 15)}</button>'
        f'<button class="btn" id="themebtn" aria-label="Switch color theme">'
        f'{theme_icons}<span class="tlabel">Auto</span></button>'
        f'<button class="btn icon bell" id="bellbtn" aria-label="People waiting for an answer" '
        f'title="People waiting for an answer">{_icon("bell", 15)}'
        f'<span class="badge">{_fmt(d["open_q"])}</span></button></div>'
    )


def render_html(d: dict, live: bool, facets: list, instrumentation: list,
                token: str = "", manual_status: tuple = ()) -> str:
    import json as _json

    def embed(obj) -> str:
        # Escaped for embedding in a <script>: "</" would close the tag early,
        # and U+2028/U+2029 are literal line breaks to a JS parser. These hold
        # model prose and customer text, so this is not theoretical.
        return (_json.dumps(obj)
                .replace("</", "<\/")
                .replace(" ", "\u2028")
                .replace(" ", "\u2029"))

    js = (JS.replace("__EPOCH__", str(d["epoch"]))
            .replace("__LIVE__", "true" if live else "false")
            .replace("__PAGE__", str(PAGE))
            .replace("__TOKEN__", token)
            .replace("__AI_CACHE__", embed(d.get("ai_cache") or {}))
            .replace("__QDATA__", embed(_question_payload(d["questions"])))
            .replace("__LOOKUPS__", embed(_row_lookups()))
            .replace("__SRCDET__", embed(d.get("source_details") or {}))
            .replace("__BRANDS__", embed(list(_BRAND)))
            .replace("__MANUAL_STATUS__", embed(list(manual_status)))
            .replace("__CRM__", embed({
                p["who"]: {"status": (p.get("note") or {}).get("status", ""),
                           "next": (p.get("note") or {}).get("next", ""),
                           "tags": (p.get("note") or {}).get("tags", []),
                           "notes": (p.get("note") or {}).get("notes", ""),
                           "derived": p.get("status", "")}
                for p in d["people"]
                if (p.get("note") or p.get("status"))}))
            .replace("__PATRONS__", embed({
                h: {"name": p["name"], "tiers": p["tiers"],
                    "monthly": p["monthly_cents"], "lifetime": p["lifetime_cents"],
                    "since": p["since"], "paying": p["paying"]}
                for h, p in (d.get("patrons") or {}).items()})))

    # The timings and file counts moved to Admin, where someone looking for
    # them is looking for them. On every other screen they were noise at the
    # bottom of a page about people.
    diag = (f'updated {escape(d["generated_at"])} &middot; '
            f'everything here is rendered from your vault; edits land there, '
            f'never only here')

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
{_brand_sprite()}
<div class="app">
{_sidebar(d)}
<main class="main">
{_header(d, live)}
{_mobile_nav()}
{_stamp_views(_tiles(d, len(d["systems"]), _overview_cards(d)) + _questions_card(d))}
<div class="cols2">
{_stamp_views(_answers_card(d) + _system_pressure_card(d, facets))}
</div>
{_stamp_views(_sales_card(d) + _business_screen(d) + _links_card() + _sync_card(d) + _wingman_card(d))}
<div class="grid3">
{_stamp_views(_people_card(d) + _videos_card(d) + _sources_card(instrumentation, d) + _health_card(d))}
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
