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
from collections import namedtuple
from datetime import date
from html import escape

PAGE = 25  # rows per page; the pager offers 25 / 50 / 100

CH_COLORS = {
    "discord": "#5865f2",
    "youtube": "#e5332a",
    "patreon": "#ff424d",
    "email": "#3fd39c",
}

# The Wingman email audiences, defined once. The same four were listed in
# three places (the send path in panel.py, the account-card buttons, and the
# email-card tiles) with labels and descriptions that had to be kept in step
# by hand. Each field is named so a site reads only what it needs:
#   key       the segment key the collector writes and the send resolves
#   label     the audience name, shown everywhere
#   desc      the one-line explanation (send report + email-card tiles)
#   tag       the account card's short purpose ("onboarding nudge")
#   hist_key  the history.json series for this audience's sparkline
#   color     the sparkline colour
WingmanSegment = namedtuple(
    "WingmanSegment", "key label desc tag hist_key color")
WINGMAN_SEGMENTS = (
    WingmanSegment("never_generated", "Never generated",
                   "created an account, never used it", "onboarding nudge",
                   "wm_never", "var(--warn)"),
    WingmanSegment("power_free", "Power users, still free",
                   "heavy use on the free plan", "upsell to premium",
                   "wm_power", "var(--ok)"),
    WingmanSegment("churning_premium", "Premium gone quiet",
                   "paying, but inactive", "win them back",
                   "wm_churn", "var(--crit)"),
    WingmanSegment("new_7d", "New this week",
                   "signed up in the last 7 days", "welcome",
                   "wm_new", "var(--info)"),
)

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
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
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
    # Browser and destination marks for the link drilldown. Each one is the
    # brand's own colour and its simplest true shape; where a mark is too
    # intricate to draw honestly at 14px it is a tinted outline instead of a
    # bad likeness. The name is always beside it, so nothing depends on the
    # drawing being recognised.
    "chrome": ('<circle cx="12" cy="12" r="10" fill="#f1c21b"/>'
               '<path d="M12 2a10 10 0 0 1 8.66 5H12a5 5 0 0 0-4.33 2.5L3.34 7A10 10 0 0 1 12 2z" fill="#ea4335"/>'
               '<path d="M3.34 7l4.33 2.5A5 5 0 0 0 12 17l-4.33 4.5A10 10 0 0 1 3.34 7z" fill="#34a853"/>'
               '<circle cx="12" cy="12" r="4.6" fill="#fff"/>'
               '<circle cx="12" cy="12" r="3.4" fill="#4285f4"/>'),
    "firefox": ('<circle cx="12" cy="12.6" r="9.2" fill="#ff7139"/>'
                '<path d="M12 3.4c2.2 2 2.6 4.2 1.9 5.6 1.2-.7 2.6-.4 3.4.6-1.1.2-1.7 1-1.7 2 0 2.4-2 4.3-4.4 4.3S6.8 14 6.8 11.6c0-2 1-3.4 2.3-4.6C10.6 5.6 11.7 4.6 12 3.4z" fill="#ffbd4f"/>'),
    "safari": ('<circle cx="12" cy="12" r="9.4" fill="#1e9bf0"/>'
               '<circle cx="12" cy="12" r="7.4" fill="#f6f7f9"/>'
               '<path d="M16.4 7.6l-2.1 5.3-5.3 2.1 2.1-5.3z" fill="#ff5b4a"/>'
               '<path d="M12 12l4.4-4.4-2.1 5.3z" fill="#c9302c"/>'),
    "edge": ('<circle cx="12" cy="12" r="9.4" fill="#0e79c0"/>'
             '<path d="M3.6 14.4C4.4 8.9 8.2 5.6 12.6 5.6c4 0 6.6 2.4 6.6 5.2 0 1.9-1.4 3-3.3 3H9.3c0 2.6 2.2 4.4 5.2 4.4 1.9 0 3.5-.5 4.6-1.2-1.5 2.4-4.2 4-7.3 4-4.6 0-8.2-2.9-8.2-6.6z" fill="#35c1f1"/>'),
    "opera": ('<circle cx="12" cy="12" r="9.4" fill="#e6142b"/>'
              '<ellipse cx="12" cy="12" rx="3.9" ry="6.6" fill="#fff"/>'),
    "patreon": ('<circle cx="14.6" cy="9.3" r="6.3" fill="#f96854"/>'
                '<rect x="2.6" y="3" width="3.7" height="18" fill="#052d49"/>'),
    "drive": ('<path d="M8.8 2.6h6.4l6.4 11.1h-6.4z" fill="#ffcf63"/>'
              '<path d="M2.4 13.7L5.6 8.2l6.4 11.1H5.6z" fill="#11a861"/>'
              '<path d="M5.6 8.2L8.8 2.6l6.4 11.1-3.2 5.6z" fill="#3777e3"/>'),
    "gdocs": ('<rect x="4.6" y="2.4" width="14.8" height="19.2" rx="2" fill="#4285f4"/>'
              '<path d="M7.6 8.4h8.8M7.6 11.6h8.8M7.6 14.8h6" stroke="#fff" '
              'stroke-width="1.5" stroke-linecap="round"/>'),
    "mega": ('<circle cx="12" cy="12" r="9.4" fill="#d9272e"/>'
             '<path d="M6.6 15.8V8.2l5.4 4.6 5.4-4.6v7.6" stroke="#fff" '
             'stroke-width="1.9" fill="none" stroke-linejoin="round"/>'),
    "gamma": ('<circle cx="12" cy="12" r="9.4" fill="#7c4dff"/>'
              '<path d="M8 8h8l-4.4 5.2V17" stroke="#fff" stroke-width="1.9" '
              'fill="none" stroke-linecap="round" stroke-linejoin="round"/>'),
    "notebooklm": ('<rect x="3.4" y="3.4" width="17.2" height="17.2" rx="4" fill="#1a73e8"/>'
                   '<path d="M8 8.6h8M8 12h8M8 15.4h5" stroke="#fff" stroke-width="1.6" '
                   'stroke-linecap="round"/>'),
    "web": ('<circle cx="12" cy="12" r="8.6" fill="none" stroke="currentColor" '
            'stroke-width="1.7"/><path d="M3.4 12h17.2M12 3.4c4.6 5 4.6 12.2 0 17.2'
            'M12 3.4c-4.6 5-4.6 12.2 0 17.2" fill="none" stroke="currentColor" '
            'stroke-width="1.7"/>'),
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
        f'<polyline points="{poly}" pathLength="100" fill="none" stroke="{color}" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round"></polyline></svg>'
    )


def _safe_url(url: str) -> str:
    """Only http(s) URLs may become hrefs or clipboard payloads. Vault
    fields are hand-editable; a pasted javascript: URL must render inert,
    not become a click-to-execute link inside the panel's origin."""
    u = (url or "").strip()
    if not u.lower().startswith(("http://", "https://")):
        return ""
    # The prefix was the only test and everything after it was free.
    # A public comment can write a vault field, so a value beginning
    # https:// and continuing with a quote and an event handler used to
    # reach an href. None of these characters survive a collector
    # unencoded inside a real URL, so their presence means it is not one.
    bad = chr(34) + chr(39) + "<>` " + chr(9) + chr(10) + chr(13)
    return "" if any(c in u for c in bad) else u


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


_ROLE_CLASS = {
    "LocoPremium": "r-premium", "LocoStandard": "r-standard",
    "LocoBasic": "r-basic", "LocoHelper": "r-helper",
    "LocoDev Team": "r-team", "LocoTester": "r-team", "Patreon": "r-patreon",
}


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
    /* Taken from blueprint.locodev.dev: pure black ground, 4% cards, 8%
       raised, 15% lines, 64% secondary ink, and white as the primary.
       The site is monochrome because a landing page only has to look like
       one thing. This is a dashboard, so the status hues below stay: they
       carry meaning that weight and position cannot, and a confidence bar
       that is grey at 24% and grey at 92% has stopped saying anything. */
    --ground:#000000; --surface:#0a0a0a; --surface2:#141414; --surface3:#1f1f1f;
    --line:#262626; --line2:#1c1c1c;
    --ink:#ffffff; --ink2:#a3a3a3; --ink3:#737373;
    --accent:#ffffff; --accent-ink:#000000;
    --accent-bg:rgba(255,255,255,.10); --accent-line:rgba(255,255,255,.22);
    --ok:#3fcf8e; --ok-bg:#0d1f17; --ok-line:#1b3d2c;
    --warn:#e5a13a; --warn-bg:#221a0d; --warn-line:#453519;
    /* the site's own destructive, hsl(0 84% 60%) */
    --crit:#ef4343; --crit-bg:#241010; --crit-line:#4a2020;
    --info:#a78bfa; --info-bg:#1a1626; --info-line:#332a4d;
    /* chart series, kept: validated against a near-black surface and pure
       black only widens the contrast */
    --ch-main:#6684fa; --ch-warn:#bd8324; --ch-mute:#707b90;
    --mute-bg:#1c1c1c;
    --av-l:36%; --av-s:38%;
    --e1:0 1px 2px rgba(0,0,0,.6);
    --e2:0 2px 10px rgba(0,0,0,.7);
    --e3:0 18px 44px rgba(0,0,0,.85);
    --skel:linear-gradient(90deg,#141414 25%,#1f1f1f 37%,#141414 63%);
    --glow-a:rgba(255,255,255,.05); --glow-b:rgba(255,255,255,.03);
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
  --r-xs:6px; --r-sm:8px; --r-md:8px; --r-lg:12px; --r-xl:16px; --r-full:999px;
  /* ---- motion ---- */
  --dur:.16s; --ease:cubic-bezier(.2,.6,.3,1);
  /* ---- type faces ---- */
  --ui:"Geist","GeistSans",-apple-system,"Segoe UI Variable Text","Segoe UI",system-ui,Roboto,Arial,sans-serif;
  --mono:"Geist Mono","GeistMono","Cascadia Mono","SF Mono",Consolas,ui-monospace,monospace;
  /* ---- light palette ---- */
  --ground:#ffffff; --surface:#ffffff; --surface2:#fafafa; --surface3:#f5f5f5;
  --line:#e5e5e5; --line2:#f0f0f0;
  --ink:#000000; --ink2:#525252; --ink3:#737373;
  --accent:#000000; --accent-ink:#ffffff;
  --accent-bg:rgba(0,0,0,.06); --accent-line:rgba(0,0,0,.18);
  --ok:#0f7a44; --ok-bg:#e8f6ee; --ok-line:#c3e6d2;
  --warn:#8a5a0c; --warn-bg:#fcf2e0; --warn-line:#f0dcb6;
  --crit:#d13434; --crit-bg:#fdeded; --crit-line:#f5d0d0;
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

/* Bell feed: a dropdown under the bell with the sync line and a scrollable
   list of what came in since the last build. */
.bellwrap { position:relative; }
.actbox { position:absolute; right:0; top:calc(100% + 8px); width:min(380px, 92vw);
  max-height:min(72vh, 560px); display:flex; flex-direction:column;
  background:var(--surface2); border:1px solid var(--line); border-radius:var(--r-lg);
  box-shadow:var(--shadow-lg, 0 12px 32px rgba(0,0,0,.45)); z-index:60; overflow:hidden; }
.actbox.hide { display:none; }
.actbox .achead { display:flex; align-items:baseline; justify-content:space-between;
  gap:8px; padding:12px 14px 8px; }
.actbox .achead b { font-size:var(--t-sm); }
.actbox .achead .acbuilt { color:var(--ink3); font-size:var(--t-2xs); font-family:var(--mono); }
.acsync { display:flex; flex-direction:column; gap:2px; padding:2px 14px 10px;
  border-bottom:1px solid var(--line); }
.acsrc { display:flex; align-items:center; gap:8px; font-size:var(--t-xs); padding:3px 0; }
.acsrc .acname { display:flex; align-items:center; gap:6px; min-width:88px; color:var(--ink); }
.acsrc .account { color:var(--ink2); }
.acsrc .acwhen { margin-left:auto; color:var(--ink3); font-family:var(--mono);
  font-size:var(--t-2xs); }
.acsrc .acdot { width:7px; height:7px; border-radius:var(--r-full); background:var(--ok); flex:none; }
.acsrc .acdot.warn { background:var(--warn); }
.acsrc .acdot.stale { background:var(--ink3); }
.aclist { overflow-y:auto; padding:4px 0; }
.acitem { display:flex; gap:10px; padding:8px 14px; border-bottom:1px solid var(--line2);
  cursor:pointer; }
.acitem:last-child { border-bottom:0; }
.acitem:hover { background:var(--surface3); }
.acitem .acav { flex:none; margin-top:2px; }
.acitem .acbody { min-width:0; flex:1; }
.acitem .acmeta { display:flex; align-items:center; gap:6px; font-size:var(--t-2xs);
  color:var(--ink3); margin-bottom:2px; }
.acitem .acmeta .acwho { color:var(--ink2); font-weight:600; }
.acitem .acq { font-size:var(--t-xs); color:var(--ink); line-height:1.35;
  display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
.acempty { padding:22px 14px; text-align:center; color:var(--ink3); font-size:var(--t-xs); }
.acfoot { padding:8px 14px; border-top:1px solid var(--line); }
.acfoot button { width:100%; }

/* Wingman accounts card. wm- prefix because the stylesheet has no
   namespace and a bare .tile / .seg would collide. */
.wm-tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:var(--s3); margin:var(--s3) 0; }
.wm-tile { background:var(--surface2); border:1px solid var(--line); border-radius:var(--r-md);
  padding:12px 14px; display:flex; flex-direction:column; gap:2px; }
.wm-tile .spark { width:100%; height:26px; margin-top:auto; padding-top:8px; }
.wm-n { font-size:var(--t-xl); font-weight:700; font-family:var(--mono); line-height:1.1; }
.wm-l { font-size:var(--t-xs); color:var(--ink2); }
.wm-gap { background:var(--warn-bg); border:1px solid var(--warn); color:var(--ink);
  border-radius:var(--r-md); padding:10px 14px; font-size:var(--t-sm); margin:var(--s3) 0; }
.wm-gap b { color:var(--warn); font-family:var(--mono); }
.wm-h { font-size:var(--t-sm); margin:var(--s4) 0 var(--s2); color:var(--ink2);
  text-transform:uppercase; letter-spacing:.04em; }
.wm-segs { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:var(--s3); }
.wm-seg { text-align:left; background:var(--surface2); border:1px solid var(--line);
  border-radius:var(--r-md); padding:12px 14px; cursor:pointer; display:flex;
  flex-direction:column; gap:2px; transition:border-color .15s, background .15s; }
.wm-seg:hover { border-color:var(--accent-line); background:var(--surface3); }
.wm-segn { font-size:var(--t-lg); font-weight:700; font-family:var(--mono); }
.wm-segl { font-size:var(--t-sm); color:var(--ink); }
.wm-segt { font-size:var(--t-2xs); color:var(--ink3); text-transform:uppercase; letter-spacing:.04em; }
.wm-cols { display:grid; grid-template-columns:1fr 1fr; gap:var(--s4); margin-top:var(--s3); }
.wm-col { min-width:0; }
.wm-src { display:flex; flex-direction:column; gap:6px; }
.wm-srow { display:flex; align-items:center; gap:10px; font-size:var(--t-xs); }
.wm-sl { min-width:130px; color:var(--ink2); }
.wm-sn { font-family:var(--mono); color:var(--ink2); min-width:36px; text-align:right; }
.wm-built { margin-top:var(--s3); color:var(--ink3); font-family:var(--mono); font-size:var(--t-2xs); }
.pill.st-mut { background:var(--surface3); color:var(--ink3); }
.em-aud { text-align:left; background:var(--surface2); border:1px solid var(--line);
  border-radius:var(--r-md); padding:12px 14px; cursor:pointer; display:flex;
  flex-direction:column; gap:2px; transition:border-color .15s, background .15s; }
.em-aud:hover { background:var(--surface3); }
.em-aud[aria-pressed="true"] { border-color:var(--accent); background:var(--accent-bg); }
.em-form { display:flex; flex-direction:column; gap:var(--s3); }
.em-subj, .em-testto { background:var(--surface2); border:1px solid var(--line);
  border-radius:var(--r-md); color:var(--ink); padding:9px 12px; font:inherit; }
.em-subj { font-weight:600; }
.em-testto { width:220px; }
.em-body { background:var(--surface2); border:1px solid var(--line);
  border-radius:var(--r-md); color:var(--ink); padding:10px 12px; font:inherit;
  line-height:1.5; resize:vertical; }
@media (max-width:720px){ .wm-cols { grid-template-columns:1fr; } }

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
@media (prefers-reduced-motion: no-preference) {
  .spark.go polyline { stroke-dasharray:100; stroke-dashoffset:100;
    animation:sparkdraw .9s ease-out forwards; }
  .spark.go polygon { transform-box:fill-box; transform-origin:bottom;
    animation:sparkfill .9s ease-out forwards; }
}
@keyframes sparkdraw { to { stroke-dashoffset:0; } }
@keyframes sparkfill { from { transform:scaleY(0); opacity:0; }
  to { transform:scaleY(1); opacity:1; } }
.em-aud .spark { width:100%; height:30px; margin-top:6px; }
.ltk .mk .spark { width:100%; height:24px; margin-top:6px; }
.c-blue { background:var(--accent-bg); color:var(--accent); }
.c-violet { background:var(--info-bg); color:var(--info); }

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
  border-radius:var(--r-md); box-shadow:var(--e2); padding:var(--s2);
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
.chx { font-family:var(--mono); font-size:11px; fill:var(--ink3); }
.chend { font-family:var(--mono); font-size:12px; font-weight:600; fill:var(--ink); }
.chgrid { stroke:var(--line2); stroke-width:1; }
.chaxis { stroke:var(--line); stroke-width:1; }
.chbar rect { transition:opacity var(--dur) var(--ease); }
.chbar:hover rect { opacity:.82; }
.chline { fill:none; stroke:var(--ch-main); stroke-width:2;
  stroke-linejoin:round; stroke-linecap:round; }
.charea { fill:var(--ch-main); opacity:.13; }
.chhit { fill:transparent; }
.chhit:hover { fill:var(--ch-main); opacity:.25; }


/* ---- chart controls, and the card that grows to hold them ---- */
.figbar { display:flex; gap:var(--s3); align-items:center; flex-wrap:wrap;
  margin:var(--s3) 0 2px; }
.seg { display:inline-flex; border:1px solid var(--line); border-radius:var(--r-sm);
  overflow:hidden; }
.seg button { border:0; background:transparent; color:var(--ink3);
  font:inherit; font-size:var(--t-2xs); font-family:var(--mono); padding:3px 7px;
  cursor:pointer; border-right:1px solid var(--line); }
.seg button:last-child { border-right:0; }
.seg button[aria-pressed="true"] { background:var(--accent); color:var(--accent-ink); }
.seg button:hover:not([aria-pressed="true"]) { background:var(--surface2);
  color:var(--ink); }
.figlab { font-family:var(--mono); font-size:var(--t-2xs); color:var(--ink3);
  text-transform:uppercase; letter-spacing:.06em; }
.figstat { display:flex; gap:var(--s4); flex-wrap:wrap; margin-top:var(--s3);
  padding-top:var(--s3); border-top:1px solid var(--line2); }
.figstat div { min-width:0; }
.figstat .k { display:block; font-size:var(--t-2xs); color:var(--ink3);
  text-transform:uppercase; letter-spacing:.06em; }
.figstat .v { font-family:var(--mono); font-size:var(--t-md); color:var(--ink);
  font-weight:600; }
.figstat .v.warn { color:var(--warn); }
.figwhy { font-size:var(--t-xs); color:var(--ink3); margin:var(--s3) 0 0;
  line-height:1.45; }
/* The projection is the same series continued, so it keeps the same hue and
   is told apart by the dash and the band, never by a colour of its own. */
.chfc { fill:none; stroke:var(--ch-main); stroke-width:2; stroke-dasharray:5 4;
  stroke-linecap:round; }
.chband { fill:var(--ch-main); opacity:.12; }
.chnow { stroke:var(--line); stroke-width:1; stroke-dasharray:2 3; }
.chlegend i.dash { background:none; border-top:2px dashed var(--ch-main);
  height:0; border-radius:0; width:14px; vertical-align:2px; }
.expand { margin-left:auto; border:1px solid var(--line); background:transparent;
  color:var(--ink3); border-radius:var(--r-sm); font:inherit;
  font-size:var(--t-2xs); padding:2px 8px; cursor:pointer; }
.expand:hover { color:var(--ink); border-color:var(--ink3); }
.card.wide { grid-column:1 / -1; }
.card h2 { display:flex; align-items:center; }

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






/* ---- one link opened: the full short link, and every click in it ---- */
.lfull { display:flex; gap:var(--s3); align-items:center; flex-wrap:wrap;
  margin-bottom:var(--s3); }
.lfull a { font-family:var(--mono); font-size:var(--t-md); color:var(--ink);
  text-decoration:none; border-bottom:1px solid var(--line); }
.lfull a:hover { color:var(--accent); border-color:var(--accent); }
.lclicks { max-height:420px; overflow-y:auto; border:1px solid var(--line);
  border-radius:var(--r-md); background:var(--surface); }
.lclick { display:grid; grid-template-columns:34px minmax(90px,auto) 1fr auto auto;
  gap:var(--s3); align-items:center; padding:6px var(--s3);
  border-bottom:1px solid var(--line2); font-size:var(--t-sm); }
.lclick:last-child { border-bottom:0; }
.lclick .lb, .lclick .lr { display:inline-flex; align-items:center; gap:6px;
  min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  color:var(--ink2); }
.lclick .n { font-family:var(--mono); font-size:var(--t-xs); color:var(--ink3);
  white-space:nowrap; }
.cc { font-family:var(--mono); font-size:var(--t-2xs); font-weight:700;
  color:var(--ink2); background:var(--surface3); border-radius:var(--r-xs);
  padding:2px 5px; text-align:center; }
.cc.none { color:var(--ink3); font-weight:400; }
/* Burst rows are tinted and tagged, never tinted alone: the tag is what
   says why, and colour on its own would just look decorative. */
.lclick.burst { background:var(--warn-bg); }
.btag { font-family:var(--mono); font-size:var(--t-2xs); color:var(--warn);
  border:1px solid var(--warn); border-radius:var(--r-xs); padding:1px 5px; }
.bi { vertical-align:-2px; flex:none; }

/* A card with no expand of its own (it is not in a grid) still gets to
   fill the page width when a reply needs the room. */
.card.fullrow { max-width:none; }
.card.fullrow .qbox { min-height:320px; }
.card.wide .qbox { min-height:200px; }


/* ---- the note asked for before a draft ---- */
.modalback { position:fixed; inset:0; background:rgba(0,0,0,.55);
  display:grid; place-items:center; z-index:60; padding:var(--s4);
  backdrop-filter:blur(2px); }
.modal { background:var(--surface); border:1px solid var(--line);
  border-radius:var(--r-lg); padding:var(--s5); width:min(620px,100%);
  box-shadow:0 18px 50px rgba(0,0,0,.4); }
.modal h3 { margin:0 0 var(--s2); font-size:var(--t-lg); }
.modal .note { margin:0 0 var(--s3); }
.mq { margin:0 0 var(--s3); padding:var(--s3); background:var(--surface2);
  border-left:3px solid var(--line); border-radius:var(--r-sm);
  font-size:var(--t-sm); color:var(--ink2); max-height:120px; overflow:auto; }
.mctx { width:100%; font:inherit; font-size:var(--t-sm); color:var(--ink);
  background:var(--surface2); border:1px solid var(--line);
  border-radius:var(--r-sm); padding:var(--s3); resize:vertical; }
.mbtns { display:flex; gap:var(--s2); margin-top:var(--s3); flex-wrap:wrap; }

/* ---- answering a whole system ---- */
.prow2 { display:grid; grid-template-columns:minmax(11ch,17ch) repeat(3,1fr);
  gap:var(--s4); align-items:start; padding:var(--s3) 0;
  border-bottom:1px solid var(--line2); }
.prow2:last-of-type { border-bottom:0; }
.pcell { display:flex; flex-direction:column; gap:2px; }
.pcell .k { font-size:var(--t-2xs); color:var(--ink3);
  text-transform:uppercase; letter-spacing:.06em; }
.pcell .v { font-family:var(--mono); font-size:var(--t-lg); color:var(--ok);
  font-weight:600; }
.pcell .v.warn { color:var(--warn); }
@media (max-width:900px) { .prow2 { grid-template-columns:1fr 1fr; } }

.bbase { position:absolute; top:-2px; bottom:-2px; width:2px;
  background:var(--ink3); opacity:.7; }
.bt { position:relative; }
.chlegend i.basetick { background:var(--ink3); width:2px; height:12px;
  border-radius:0; }

.reneeds { margin-left:auto; }

#qnarrow { color:var(--warn); }
.qclearq { border:1px solid var(--warn); background:transparent; color:var(--warn);
  border-radius:var(--r-xs); font:inherit; font-size:var(--t-2xs);
  padding:1px 6px; cursor:pointer; margin-left:4px; }
.qclearq:hover { background:var(--warn-bg); }

.bulkst.bs-polishing { color:var(--accent); }
.bulkst.bs-drafting { color:var(--accent); }

.bigmsg { color:var(--warn); font-weight:600; }
.bulkst.bs-queued { color:var(--ink3); }

/* Named bulkbar, not pbar: .pbar already exists and is used by the
   coverage meter in 205 rows of the Products table, where this rule's
   margin pushed every bar 6px off centre. */
.bulkbar { height:6px; border-radius:3px; background:var(--surface3);
  overflow:hidden; margin:var(--s3) 0 2px; }
.bulkbar i { display:block; height:100%; background:var(--accent);
  border-radius:3px; transition:width var(--dur) var(--ease); }
.bulkone { display:flex; gap:var(--s3); align-items:center; margin-top:var(--s2); }

.flashcard { animation:flash 1.3s var(--ease); }

/* Review replaces the queue: same card, one list on screen at a time. */
#questions.reviewing .filters, #questions.reviewing #bulkbar,
#questions.reviewing .scroll, #questions.reviewing #qempty,
#questions.reviewing .pager, #questions.reviewing .cnt { display:none; }
.bulkslim { align-items:center; }
.bulklist { display:flex; flex-direction:column; gap:var(--s3);
  margin-top:var(--s3); max-height:60vh; overflow-y:auto; }
.bulkitem { border:1px solid var(--line); border-radius:var(--r-md);
  padding:var(--s3); background:var(--surface); }
.bulkhead { display:flex; gap:var(--s3); align-items:center; flex-wrap:wrap; }
.bulkwho { color:var(--ink3); font-size:var(--t-xs);
  display:inline-flex; align-items:center; gap:5px; }
.bulkst { margin-left:auto; font-family:var(--mono); font-size:var(--t-2xs);
  color:var(--ink3); }
.bulkst.bs-sent { color:var(--ok); }
/* Recorded in the vault, refused by the platform. Amber because the
   answer exists and nobody has read it. */
.bulkst.bs-filed { color:var(--warn); }
.bulkst.bs-failed { color:var(--crit); }
.bulkst.bs-drafted { color:var(--accent); }
.bulkq { margin:var(--s2) 0; font-size:var(--t-sm); color:var(--ink2); }
.bulkdraft { width:100%; min-height:150px; font:inherit; font-size:var(--t-sm);
  color:var(--ink); background:var(--surface2); border:1px solid var(--line);
  border-radius:var(--r-sm); padding:var(--s3); resize:vertical; }
.bulkdraft[readonly] { opacity:.75; }

/* ---- ranked bars: which system, which kind, which country ---- */
.bars { display:flex; flex-direction:column; gap:5px; margin:var(--s3) 0; }
/* The label column sizes itself between these two, so a short one like a
   country name still leaves the bar its room while "paid once, same month"
   is not cut to "paid once, sa...". */
.bar { display:grid; grid-template-columns:minmax(9ch,22ch) 1fr auto;
  gap:var(--s3); align-items:center; font-size:var(--t-sm); }
.bl { color:var(--ink2); overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; }
.bt { background:var(--surface3); border-radius:3px; height:12px;
  overflow:hidden; }
.bt i { display:block; height:100%; background:var(--ch-main);
  border-radius:3px; }
.bv { font-family:var(--mono); font-size:var(--t-xs); color:var(--ink);
  font-variant-numeric:tabular-nums; }
.bar:hover .bt i { opacity:.82; }

.lask { display:flex; gap:var(--s2); align-items:center; flex-wrap:wrap;
  margin:var(--s4) 0 var(--s2); }
.lask .lq { flex:1; min-width:220px; font:inherit; font-size:var(--t-sm);
  color:var(--ink); background:var(--surface); border:1px solid var(--line);
  border-radius:var(--r-sm); padding:5px 9px; }
.lqcard { background:var(--surface2); border:1px solid var(--line);
  border-radius:var(--r-md); padding:var(--s3) var(--s4); margin-bottom:var(--s3); }
.lqcard b { font-family:var(--mono); font-size:var(--t-md); color:var(--ink); }
.lqbad { color:var(--warn); font-size:var(--t-xs); font-weight:600; }

/* ---- the short-link manager ---- */
tr.lkrow { cursor:pointer; }
tr.lkrow:hover .slug { color:var(--accent); }
tr.lkdet { display:none; }
tr.lkdet.open { display:table-row; }
tr.lkdet > td { background:var(--surface2); padding:var(--s3) var(--s4); }
.lnew, .ledit { display:flex; gap:var(--s2); align-items:center; flex-wrap:wrap;
  margin:var(--s3) 0; }
.ledit label { font-family:var(--mono); font-size:var(--t-2xs); color:var(--ink3);
  text-transform:uppercase; letter-spacing:.06em; }
.lnew select, .lnew input, .ledit input { font:inherit; font-size:var(--t-sm);
  color:var(--ink); background:var(--surface); border:1px solid var(--line);
  border-radius:var(--r-sm); padding:5px 9px; }
.lnew .lns { width:150px; }
.lnew .lnu, .ledit input { flex:1; min-width:230px; }
.lfind { width:100%; font:inherit; font-size:var(--t-sm); color:var(--ink);
  background:var(--surface); border:1px solid var(--line);
  border-radius:var(--r-sm); padding:6px 10px; margin-bottom:var(--s2); }

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
.ovals b { font-family:var(--mono); font-size:var(--t-xl); color:var(--ink);
  letter-spacing:-.02em;
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
.fexport { display:inline-flex; align-items:center; gap:6px;
  color:var(--accent); background:var(--accent-bg); border:1px solid var(--accent-line);
  font-family:var(--ui); font-size:var(--t-xs); font-weight:600; cursor:pointer;
  padding:var(--s1) var(--s3); border-radius:var(--r-sm); }
.fexport:hover { background:var(--accent); color:var(--accent-ink); border-color:var(--accent); }
.fexport[aria-expanded="true"] { background:var(--accent); color:var(--accent-ink); }
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
tr.qrow[aria-expanded="true"] .chn { visibility:hidden; }
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
.pe { font-style:normal; font-size:11px; line-height:1; }
.he { font-size:16px; line-height:1; }
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
/* Polish rewrites text and can be redone; Send publishes under your
   name and cannot. They were the same grey button side by side. */
.btn.tiny.bulksend1 { border-color:var(--warn-line); color:var(--warn); }
/* The subset the vault actually backed, so it carries the ok line
   rather than the accent that means "everything, now". */
.btn.tiny.bulkconfsend { border-color:var(--ok-line); color:var(--ok); }
.btn.tiny.bulkconfsend:disabled { opacity:.45; }
.conffloor { display:inline-flex; align-items:center; gap:5px;
  font-size:var(--t-xs); color:var(--ink2); }
.refsbox { display:inline-flex; align-items:center; gap:4px;
  font-size:var(--t-2xs); color:var(--ink3); }
.refsbox input { width:52px; padding:3px 5px; font:inherit;
  font-size:var(--t-xs); color:var(--ink);
  background:var(--surface2); border:1px solid var(--line);
  border-radius:var(--r-sm); }
.conffloor input { width:58px; padding:4px 6px; font:inherit;
  color:var(--ink); background:var(--surface2);
  border:1px solid var(--line); border-radius:var(--r-sm); }
.btn.tiny.bulkconfsend:hover { background:var(--ok-bg); border-color:var(--ok); }
.btn.tiny.bulksend1:hover { background:var(--warn-bg);
  border-color:var(--warn); }
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
  font-size:var(--t-base); line-height:1.55; resize:both; max-width:100%;
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
.pbar { height:6px; border-radius:var(--r-full); background:var(--surface3); overflow:hidden; }
.pbar i { display:block; height:100%; border-radius:var(--r-full); background:var(--accent);
  transition:width .5s var(--ease); }
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
.lsub { color:var(--ink3); font-family:var(--mono); font-size:var(--t-2xs);
  letter-spacing:.08em; text-transform:uppercase; margin:0 0 var(--s2); font-weight:600; }
/* Named lrow, not crow: the customer table's rows are <tr class="crow">,
   and a display:flex here took those rows out of the table's column
   algorithm, so every Customers row sized itself and none lined up with
   the header. Same collision the Products table hit as .prow. */
/* The slug is the part that may be long, so it is the part that gives
   way. Without min-width:0 a flex item refuses to shrink below its content
   and the time on the right was drawn over it. */
.lrow > span:first-child { min-width:0; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap; }
.lrow .n { flex:none; white-space:nowrap; }
.lrow { display:flex; justify-content:space-between; gap:var(--s2); padding:var(--s2) 0;
  border-bottom:1px solid var(--line2); font-size:var(--t-sm); align-items:center; }
.lrow:last-child { border-bottom:0; }
.lrow .n { font-family:var(--mono); font-size:var(--t-xs); color:var(--ink3);
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
#toast[data-kind="warn"] .ti { background:var(--warn-bg); color:var(--warn); }

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
  100% { box-shadow:var(--e1); } }
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
/* {name: [low, high]} straight from BULK_GAPS. The labels, the time
   estimate and the words in the confirmation are all derived from
   this, so a gap is added in one place. */
var BULK_GAPS = __BULK_GAPS__;
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
/* The bell feed: {events:[...newest first], sources:[...], built}. events
   are questions that appeared since the previous build, sources the
   per-collector last-sync line above them. */
var ACTIVITY = __ACTIVITY__;
/* Pre-rendered trend sparks for the Links tiles, keyed by tile label.
   Built server-side by the same _spark the other graphs use, so the page
   carries no second graph builder to drift from the first. */
var LTSPARKS = __LTSPARKS__;
/* Full monthly history for every chart. The browser slices the window,
   fits the trend and extends the projection, so the whole series has to
   be here rather than the twelve months a server-drawn chart would send. */
var CHARTS = __CHARTS__;
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
  /* A hidden figure measures zero wide, so a chart drawn while its screen
     was closed would come out empty. Draw on arrival instead. The guard is
     on the data, not the function: setView runs once before the chart
     engine's own statements have, and a declaration is hoisted while the
     specs it reads are not. */
  if (typeof CHSPEC !== "undefined") { chSyncExpand(); chDrawAll(); }
  /* The bulk card holds its list after a run settles, since the poll stops
     then. Arriving on the screen is the moment to check it is still the
     list the server has. */
  if (name === "questions" && typeof bulkTick === "function") bulkTick();
  if (name === "business" && typeof wmDetail === "function") wmDetail();
  /* The graphs on the arriving screen fill up as it opens. Hidden ones
     would have finished animating invisibly, so it runs per arrival. */
  if (typeof sparkReplay === "function") sparkReplay(document.getElementById(name));
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
/* Scrolling is reading. The wheel raises "wheel" and "scroll", neither
   of which was here, so someone working down a long queue never
   registered as busy and the page reloaded out from under them at the
   next rebuild, which during a drafting run is every few minutes. */
["pointerdown", "keydown", "input", "wheel", "scroll", "touchmove"]
  .forEach(function (ev) {
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
  toast("Fetching the latest Discord questions, then rebuilding "
    + "(up to a minute)...", "info");
  fetch("/refresh", { method: "POST" })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      /* The rebuild always ran; the message is about the Discord pull that
         ran before it. A failed pull still refreshed everything already
         collected, so it is a warning, not a dead end, and it keeps the
         reason the collector gave rather than a generic line. */
      var dc = (d && d.discord) || {};
      if (dc.ok) {
        toast(dc.added
          ? "Pulled " + dc.added + " new Discord question"
            + (dc.added === 1 ? "" : "s") + "; the page refreshes when it lands."
          : "No new Discord questions; refreshed everything else.", "good");
      } else {
        toast("Discord fetch: " + (dc.error || "did not run")
          + ". Refreshed what was already collected.", "warn");
      }
      /* Left spinning: the rebuilt page reloads under it in a moment. */
    })
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
  /* A backfill drops years of archaeology in beside this week's work.
     Both belong in the queue; only one of them is worth a morning. */
  age: params.get("age") || "all",
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
  if (state.age !== "all") p.set("age", state.age);
  if (state.q) p.set("q", state.q);
  if (state.sort !== "triage" || state.dir !== "desc") { p.set("sort", state.sort); p.set("dir", state.dir); }
  var qs = p.toString();
  try { history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash); } catch (e) {}
}

/* The haystack each row is searched against, built here from QDATA rather
   than shipped as a data-txt attribute on all 2,401 shells. That attribute
   was 467 KB, 10.4% of the page, restating fields QDATA already carries in
   full; the browser assembles the same string once, at load, for nothing.
   It hangs off the pair rather than the element so it costs no attribute
   write and no reflow. */
var PAIRS = $$("#qtbody tr.qrow").map(function (r) {
  var q = QDATA[r.dataset.id] || {};
  /* A plain property, not an attribute: setting 2,401 attributes would
     write to the DOM and cost a reflow, while this is just a field on an
     object that already exists. Read by match() and by the Edit jump. */
  r._txt = [q.code, q.who, q.text, q.system, q.channel, q.status]
    .join(" ").toLowerCase();
  return { r: r };
});
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
      /* ts, not date: a dozen messages from one afternoon share a date, so
         "oldest first" among them has to read the real instant to be true. */
      return (+a.r.dataset.ts || 0) - (+b.r.dataset.ts || 0);  /* oldest first */
    }
    var av, bv;
    if (key === "who") { av = a.r.dataset.who; bv = b.r.dataset.who; }
    else if (key === "status") { av = a.r.dataset.st; bv = b.r.dataset.st; }
    else if (key === "system") { av = a.r.dataset.sys; bv = b.r.dataset.sys; }
    else if (key === "cov") { av = +a.r.dataset.cov || 0; bv = +b.r.dataset.cov || 0; }
    /* The Age column sorts on the exact instant, not the day: Discord ids
       carry their own time, so the message posted last in a busy afternoon
       sorts newest instead of landing mid-list where it read as missing. */
    else { av = +a.r.dataset.ts || 0; bv = +b.r.dataset.ts || 0; }
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
/* How old a question is, in days, from the date it was asked. Read off
   QDATA rather than a data attribute for the same reason the search text
   is: three thousand extra attributes cost a reflow and buy nothing. */
var AGE_WINDOW = { "30d": 30, "90d": 90, "12m": 365 };
function ageOk(r) {
  if (state.age === "all") return true;
  var q = QDATA[r.dataset.id];
  if (!q || !q.date) return false;
  /* Whole days, floored, because the chip's count is calendar arithmetic
     done in Python. Left fractional, a question asked exactly 30 days ago
     reads as 30.6 here and falls outside a chip that counted it, so the
     number on the chip and the number of rows disagreed by four. */
  var days = Math.floor((Date.now() - Date.parse(q.date + "T00:00:00")) / 86400000);
  /* "older" is the other half of the cut, so nothing becomes unreachable
     by narrowing: the archaeology is a click away rather than buried. */
  if (state.age === "old") return days > 365;
  return days <= AGE_WINDOW[state.age];
}

function match(r) {
  if (state.ch !== "all" && r.dataset.ch !== state.ch) return false;
  if (!ageOk(r)) return false;
  if (state.st === "open") { if (!isOpen(r)) return false; }
  else if (state.st !== "all" && r.dataset.st !== state.st) return false;
  if (state.sys !== "all" && r.dataset.sys !== state.sys) return false;
  /* Answerability describes work still to do. Without this, "easy 90"
     also matched the answered rows that carry the same data-df and
     returned far more rows than the chip promised. */
  if (state.df !== "all" && (r.dataset.df !== state.df || r.dataset.st === "answered"))
    return false;
  if (state.q && (r._txt || "").indexOf(state.q) === -1) return false;
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
  /* Say when a search is what makes this number small. The box sits in the
     top bar, far from the table, and the filter chips keep showing their own
     totals, so "1 of 1" under a chip reading "Open 1,422" looked like the
     inbox had lost everything. */
  var qn = $("#qcount");
  qn.textContent = total
    ? (from + 1) + "-" + Math.min(to, total) + " of " + fmt(total)
    : "0";
  var nar = $("#qnarrow");
  if (nar) {
    if (state.q) {
      nar.innerHTML = ' matching "' + esc(state.q) + '" '
        + '<button class="qclearq" type="button">show all</button>';
      nar.hidden = false;
    } else {
      nar.hidden = true;
      nar.textContent = "";
    }
  }
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
    /* Customers lives on Business now, so the jump has to open that screen
       and then bring the card into view: it sits below the money and the
       funnel, off screen on arrival. */
    goView("business");
    setTimeout(function () {
      var tr = document.querySelector('#people tr.crow[data-who="' + key.replace(/"/g, '\\"') + '"]');
      if (tr && !tr.classList.contains("copen")) toggleCustomer(tr);
      /* Scroll last. Opening the row inserts a detail row and moves
         everything below it, so a scroll measured before that lands in the
         wrong place, and Customers now sits 2,300px down the Business
         screen where wrong means off screen entirely. */
      revealRow(tr);
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
  setGroup("age", "all");
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
    + refsField()
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
    + '</button><button class="btn tiny qwide" type="button" '
    + 'title="Give this card the full row">wider</button>'
    + '<span class="msg" aria-live="polite"></span>'
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
    b.addEventListener("click", function () {
      /* Only the draft asks. Find existing answer reads what is already
         written, so a note would have nothing to change. */
      if (b.dataset.ai !== "draft") { runAi(wrap, b.dataset.ai, false); return; }
      askContext(q.text || "", function (extra) {
        var full = draftNote(det, extra);
        runAi(wrap, "draft", !!full, full);
      });
    });
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

function runAi(det, mode, force, extra) {
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
    body: JSON.stringify({ id: det.dataset.id, mode: mode, force: !!force,
                           extra: extra || "" }) })
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
      if ((r._txt || "").indexOf(code) !== -1) target = r;
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
      + (q.link ? ' <a class="clink" href="' + esc(q.link) + '" target="_blank" rel="noopener">open where it was asked</a>' : "")
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
/* Everything focusable answers to Enter and Space. Four kinds of row
   carried tabindex="0" and a click handler and nothing else, so a keyboard
   could reach them and then do nothing with them: the product row, the
   short-link row, the video row and the Admin source row. Rather than four
   twins of this handler, one place fires the click those rows already
   listen for. */
document.addEventListener("keydown", function (ev) {
  if (ev.key !== "Enter" && ev.key !== " ") return;
  if (!ev.target.closest) return;
  var tr = ev.target.closest("tr.crow");
  if (tr) { ev.preventDefault(); toggleCustomer(tr); return; }
  var row = ev.target.closest(
    'tr.prodrow, tr.lkrow, .vrow[tabindex], .srow[data-src]');
  if (!row) return;
  /* Space scrolls the page by default, and Enter on a row inside a form
     would submit it. */
  ev.preventDefault();
  var target = row.querySelector(".slug, .nm, .t") || row;
  target.click();
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
  open.slice().reverse().forEach(function (q) {
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
      + (q.link ? '<a class="clink" href="' + esc(q.link) + '" target="_blank" rel="noopener">open it</a> ' : "")
      + '<button class="btn tiny">Answer</button>'
      + "</div></div>";
  });
  if (!open.length) out += '<div class="note">Nothing open. Everyone who asked got an answer.</div>';

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
      + (q.link ? '<a class="clink" href="' + esc(q.link) + '" target="_blank" rel="noopener">open the comment</a> ' : "")
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
    /* The bulk drafter lives on Inbox, next to the system filter. Asked for
       twice from this screen and not found both times, so the way in is
       here too, where the waiting questions actually are. */
    /* Drafting works by system, not by video, so the count here is the
       system's. Saying "all 70" on a video whose system holds 85 promised
       a number the run would not match. */
    + (open.length && open[0].system
        ? '<button class="btn tiny primary" data-vbulk="'
          + esc(open[0].system) + '">Draft answers for ' + esc(open[0].system)
          + "</button>" : "")
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
    reqs.forEach(function (r) {
      out += cev(r.q, ' <span class="tag req">' + (r.kind === "fix" ? "fix ask" : "new ask") + "</span>");
    });
    out += "</div>";
    if (rest.length) out += '<div class="cabout"><span class="clabel">Questions &middot; '
      + rest.length + "</span></div>";
  }
  out += '<div class="ctl">';
  /* Every question, not the first twenty-five. "and 43 more" named the
     ones you could not reach, which on a video with 68 waiting is most of
     the work; the list scrolls instead. */
  rest.forEach(function (q) { out += cev(q); });
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
var CHSPEC = {
  pledges: {
    kind: "stack", keys: ["still", "left"], vars: ["main", "mute"],
    names: ["still paying today", "since left"], unit: "pledges",
    tip: function (r) {
      return r.m + ": " + fmt(r.still + r.left) + " started, " + fmt(r.still) +
             " still paying today";
    },
    why: "Bars are pledges started that month, split by who still pays. " +
         "Not revenue, and not who left that month: nothing records the day " +
         "a leaver left."
  },
  cohort: {
    kind: "area", keys: ["cum"], vars: ["main"],
    names: ["patrons paying today"], unit: "patrons", cumulative: true,
    tip: function (r) {
      return r.m + ": " + fmt(r.cum) + " of today's patrons had joined by then";
    },
    why: "Only the people paying right now, each placed in the month they " +
         "joined. It cannot show how large the base was back then, because " +
         "everyone who has since left is missing from it."
  },
  questions: {
    kind: "stack", keys: ["answered", "waiting"], vars: ["mute", "warn"],
    names: ["answered by now", "still waiting"], unit: "questions",
    tip: function (r) {
      return r.m + ": " + fmt(r.answered + r.waiting) + " asked, " +
             fmt(r.waiting) + " still waiting";
    },
    why: "Counted by the month each question was asked. 'Answered' is its " +
         "state today, not the month an answer was written, which nothing " +
         "records."
  },
  clicks: {
    kind: "stack", keys: ["cnt"], vars: ["main"], names: ["clicks"],
    unit: "clicks", ranges: [[6, "6h"], [12, "12h"], [24, "24h"]], defRange: 24,
    xlab: function (r) { return r.m + "h"; },
    next: function (last, i) {
      var h = (parseInt(last, 10) + i) % 24;
      return (h < 10 ? "0" : "") + h;
    },
    per: "h",
    tip: function (r) {
      return r.m + ":00 - " + fmt(r.cnt) + (r.cnt === 1 ? " click" : " clicks");
    },
    why: "Clicks on your short links, by the hour they happened, live from " +
         "locodev.dev. Twenty-four hours is all the admin API keeps at this " +
         "resolution, so the window ends where its memory does."
  }
};

var CH_RANGES = [[6, "6m"], [12, "12m"], [24, "24m"], [9999, "all"]];
var CH_FC = [[0, "off"], [3, "3m"], [6, "6m"]];
var chState = {};

function chLoad() {
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem("panel.charts") || "{}"); }
  catch (e) { saved = {}; }
  Object.keys(CHSPEC).forEach(function (k) {
    var s = saved[k] || {};
    chState[k] = { range: s.range || CHSPEC[k].defRange || 12,
                   trend: !!s.trend, fc: s.fc || 0 };
  });
}

function chSave() {
  try { localStorage.setItem("panel.charts", JSON.stringify(chState)); }
  catch (e) { /* private mode: the controls still work, they just forget */ }
}

/* Ordinary least squares over the visible window, plus the spread of what
   it failed to explain. That spread is the honest half of a projection:
   without it a straight line reads as a promise. */
function chFit(ys) {
  var n = ys.length, i, sx = 0, sy = 0, sxx = 0, sxy = 0;
  if (n < 4) return null;
  for (i = 0; i < n; i++) { sx += i; sy += ys[i]; sxx += i * i; sxy += i * ys[i]; }
  var den = n * sxx - sx * sx;
  if (!den) return null;
  var b = (n * sxy - sx * sy) / den, a = (sy - b * sx) / n, ss = 0;
  for (i = 0; i < n; i++) { var e = ys[i] - (a + b * i); ss += e * e; }
  return { a: a, b: b, sd: Math.sqrt(ss / Math.max(1, n - 2)), n: n };
}

function chNextMonth(m, k) {
  var y = parseInt(m.slice(0, 4), 10), mo = parseInt(m.slice(5, 7), 10) + k;
  y += Math.floor((mo - 1) / 12);
  mo = ((mo - 1) % 12 + 12) % 12 + 1;
  return String(y) + "-" + (mo < 10 ? "0" : "") + mo;
}

/* For a cumulative series the increments are what actually vary, so the fit
   runs on those and the result is added back up. Fitting the running total
   itself would model an accounting artefact rather than the arrivals. */
function chProject(win, spec, months) {
  if (!months) return null;
  var totals = win.map(function (r) {
    return spec.keys.reduce(function (t, k) { return t + (r[k] || 0); }, 0);
  });
  var base = spec.cumulative
    ? totals.slice(1).map(function (v, i) { return v - totals[i]; })
    : totals;
  var fit = chFit(base);
  if (!fit) return null;
  var out = [], last = totals[totals.length - 1], run = last, i;
  for (i = 1; i <= months; i++) {
    var step = fit.a + fit.b * (base.length - 1 + i);
    // 1.28 standard deviations is an 80% band. Wider would be more nearly
    // certain and too vague to act on.
    var half = 1.28 * fit.sd * Math.sqrt(i);
    var mid, lo, hi;
    if (spec.cumulative) {
      run += Math.max(0, step);
      mid = run;
      /* half already carries sqrt(i) for the widening horizon. Multiplying
         by i again made a six-month band six times too wide: 65 to 128
         where the arithmetic says 91 to 102, and the inflated hi then set
         the whole chart's peak. */
      lo = Math.max(last, run - half);
      hi = run + half;
    } else {
      mid = Math.max(0, step);
      lo = Math.max(0, mid - half);
      hi = mid + half;
    }
    var nxt = (spec.next || chNextMonth)(win[win.length - 1].m, i);
    out.push({ m: nxt, mid: mid, lo: lo, hi: hi });
  }
  return { points: out, fit: fit, from: last };
}

function chSeg(name, kind, opts, cur) {
  return '<span class="seg" role="group">' + opts.map(function (o) {
    return '<button type="button" data-ch="' + name + '" data-set="' + kind +
      '" data-val="' + o[0] + '" aria-pressed="' + (o[0] === cur) + '">' +
      esc(o[1]) + "</button>";
  }).join("") + "</span>";
}

function chStats(spec, win, proj) {
  var totals = win.map(function (r) {
    return spec.keys.reduce(function (t, k) { return t + (r[k] || 0); }, 0);
  });
  var base = spec.cumulative
    ? totals.slice(1).map(function (v, i) { return v - totals[i]; })
    : totals;
  var fit = chFit(base), out = [];

  function cell(k, v, warn) {
    return '<div><span class="k">' + esc(k) + '</span><span class="v' +
      (warn ? " warn" : "") + '">' + v + "</span></div>";
  }

  if (fit) {
    var per = fit.b, dir = per >= 0.05 ? "rising" : per <= -0.05 ? "falling" : "flat";
    out.push(cell("Trend", (per >= 0 ? "+" : "") + per.toFixed(1) +
                  "/" + (spec.per || "mo"), per < -0.05));
    out.push(cell("Direction", dir, dir === "falling"));
  }
  if (proj) {
    var p = proj.points[proj.points.length - 1];
    out.push(cell("Projected " + p.m,
                  fmt(Math.round(p.mid)) + " <small>(" +
                  fmt(Math.round(p.lo)) + " to " + fmt(Math.round(p.hi)) + ")</small>"));
  }
  if (spec.keys.length > 1) {
    var a = 0, b = 0;
    win.forEach(function (r) { a += r[spec.keys[0]] || 0; b += r[spec.keys[1]] || 0; });
    var pct = a + b ? Math.round(a * 100 / (a + b)) : 0;
    out.push(cell(esc(spec.names[0]), pct + "% <small>of " + fmt(a + b) + "</small>",
                  spec.keys[0] === "still" && pct < 25));
  }
  return out.length ? '<div class="figstat">' + out.join("") + "</div>" : "";
}

function chDraw(fig) {
  var name = fig.dataset.chart, spec = CHSPEC[name], rows = CHARTS[name] || [];
  if (!spec) return;
  var st = chState[name] ||
    (chState[name] = { range: spec.defRange || 12, trend: false, fc: 0 });
  var bar = '<div class="figbar"><span class="figlab">show</span>' +
    chSeg(name, "range", spec.ranges || CH_RANGES, st.range) +
    '<span class="figlab">trend</span>' +
    chSeg(name, "trend", [[0, "off"], [1, "on"]], st.trend ? 1 : 0) +
    '<span class="figlab">project</span>' + chSeg(name, "fc", CH_FC, st.fc) +
    "</div>";

  if (rows.length < 2) {
    fig.innerHTML = bar + '<p class="note">Not enough months yet to draw.</p>';
    return;
  }
  var win = st.range >= 999 ? rows.slice() : rows.slice(-st.range);
  var proj = chProject(win, spec, st.fc);
  var wide = !!fig.closest(".card") && fig.closest(".card").classList.contains("wide");

  // The viewBox maps 1:1 to pixels so the type stays at its real size when
  // the card grows; only the plot gains room.
  var W = Math.max(300, Math.round(fig.clientWidth || 520));
  var H = wide ? 300 : 156;
  var L = 40, R = spec.kind === "area" ? 54 : 10, T = 14, B = 22;
  var pw = W - L - R, ph = H - T - B;
  var n = win.length, fn = proj ? proj.points.length : 0, slots = n + fn;

  var peak = 0;
  win.forEach(function (r) {
    var t = spec.keys.reduce(function (a, k) { return a + (r[k] || 0); }, 0);
    if (t > peak) peak = t;
  });
  if (proj) proj.points.forEach(function (p) { if (p.hi > peak) peak = p.hi; });
  peak = peak || 1;

  function yOf(v) { return T + ph - ph * v / peak; }
  var step = pw / slots;

  var svg = ['<svg viewBox="0 0 ' + W + " " + H + '" class="chart" role="img" ' +
             'aria-label="' + esc(spec.names.join(" and ")) + '">'];
  // Two gridlines only: the peak and the middle. More would compete with
  // the marks for attention and this chart is read for shape, not audit.
  /* Only whole steps: the middle line used to sit at peak/2 and carry
     Math.round(peak/2), so with peak 5 it was drawn at 2.5 and labelled 3,
     and a bar worth 3 rose above the line claiming to be 3. */
  var mid2 = Math.round(peak / 2);
  [peak, mid2].filter(function (v, i) { return i === 0 || (v > 0 && v < peak); })
    .forEach(function (v) {
    svg.push('<line x1="' + L + '" y1="' + yOf(v).toFixed(1) + '" x2="' + (W - R) +
             '" y2="' + yOf(v).toFixed(1) + '" class="chgrid"/>');
    svg.push('<text x="' + (L - 6) + '" y="' + (yOf(v) + 4).toFixed(1) +
             '" class="chx" text-anchor="end">' + fmt(Math.round(v)) + "</text>");
  });
  svg.push('<line x1="' + L + '" y1="' + (T + ph) + '" x2="' + (W - R) +
           '" y2="' + (T + ph) + '" class="chaxis"/>');

  if (spec.kind === "stack") {
    var bw = Math.max(2, step - (step > 26 ? 7 : 3));
    win.forEach(function (r, i) {
      var x = L + i * step + (step - bw) / 2, acc = 0;
      var g = ['<g class="chbar"><title>' + esc(spec.tip(r)) + "</title>"];
      spec.keys.forEach(function (k, ki) {
        var v = r[k] || 0;
        if (v <= 0) return;
        var h = ph * v / peak, y = T + ph - acc - h;
        // 2px of surface between segments, so the two series stay apart
        // where their colours cannot: that is what lets one of them be grey.
        /* The 2px gap is taken out of the segment, not added on top of it.
           Adding it moved the upper segment up 2px and advanced acc by 2
           more, so a full stack stood 4px above the gridline labelled with
           its own total. */
        var hh = ki ? Math.max(1, h - 2) : Math.max(1, h);
        g.push('<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) +
               '" width="' + bw.toFixed(1) + '" height="' + hh.toFixed(1) +
               '" rx="2" fill="var(--ch-' + spec.vars[ki] + ')"/>');
        acc += h;
      });
      svg.push(g.join("") + "</g>");
    });
  } else {
    var pts = win.map(function (r, i) {
      return [L + i * step + step / 2, yOf(r[spec.keys[0]] || 0)];
    });
    var line = pts.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ");
    svg.push('<polygon points="' + L + "," + (T + ph) + " " + line + " " +
             pts[pts.length - 1][0].toFixed(1) + "," + (T + ph) + '" class="charea"/>');
    svg.push('<polyline points="' + line + '" class="chline"/>');
    var lp = pts[pts.length - 1];
    svg.push('<circle cx="' + lp[0].toFixed(1) + '" cy="' + lp[1].toFixed(1) +
             '" r="3.5" fill="var(--ch-main)"/>');
    if (!proj) {
      svg.push('<text x="' + (lp[0] + 7).toFixed(1) + '" y="' + (lp[1] + 4).toFixed(1) +
               '" class="chend">' + fmt(win[n - 1][spec.keys[0]] || 0) + "</text>");
    }
    win.forEach(function (r, i) {
      svg.push('<circle cx="' + pts[i][0].toFixed(1) + '" cy="' + pts[i][1].toFixed(1) +
               '" r="9" class="chhit"><title>' + esc(spec.tip(r)) + "</title></circle>");
    });
  }

  if (st.trend) {
    var totals = win.map(function (r) {
      return spec.keys.reduce(function (a, k) { return a + (r[k] || 0); }, 0);
    });
    var tf = chFit(totals);
    if (tf) {
      var x1 = L + step / 2, x2 = L + (n - 1) * step + step / 2;
      svg.push('<line x1="' + x1.toFixed(1) + '" y1="' + yOf(Math.max(0, tf.a)).toFixed(1) +
               '" x2="' + x2.toFixed(1) + '" y2="' +
               yOf(Math.max(0, tf.a + tf.b * (n - 1))).toFixed(1) +
               '" class="chfc"><title>straight-line trend over the ' + n +
               ' months shown</title></line>');
    }
  }

  if (proj) {
    var fx = function (i) { return L + (n + i) * step + step / 2; };
    var startX = L + (n - 1) * step + step / 2;
    var startY = yOf(proj.from);
    var up = [startX.toFixed(1) + "," + startY.toFixed(1)];
    var dn = [];
    proj.points.forEach(function (p, i) {
      up.push(fx(i).toFixed(1) + "," + yOf(p.hi).toFixed(1));
      dn.unshift(fx(i).toFixed(1) + "," + yOf(p.lo).toFixed(1));
    });
    svg.push('<polygon points="' + up.concat(dn).join(" ") + '" class="chband"/>');
    var mid = [startX.toFixed(1) + "," + startY.toFixed(1)];
    proj.points.forEach(function (p, i) {
      mid.push(fx(i).toFixed(1) + "," + yOf(p.mid).toFixed(1));
    });
    svg.push('<polyline points="' + mid.join(" ") + '" class="chfc"/>');
    svg.push('<line x1="' + ((startX + fx(0)) / 2).toFixed(1) + '" y1="' + T +
             '" x2="' + ((startX + fx(0)) / 2).toFixed(1) + '" y2="' + (T + ph) +
             '" class="chnow"/>');
    proj.points.forEach(function (p, i) {
      svg.push('<circle cx="' + fx(i).toFixed(1) + '" cy="' + yOf(p.mid).toFixed(1) +
               '" r="9" class="chhit"><title>' + esc(p.m + ": projected " +
               fmt(Math.round(p.mid)) + " " + spec.unit + ", likely between " +
               fmt(Math.round(p.lo)) + " and " + fmt(Math.round(p.hi))) +
               "</title></circle>");
    });
    var lastP = proj.points[fn - 1];
    svg.push('<text x="' + Math.min(W - 2, fx(fn - 1) + 6).toFixed(1) + '" y="' +
             (yOf(lastP.mid) + 4).toFixed(1) + '" class="chend" text-anchor="' +
             (fn ? "end" : "start") + '">' + fmt(Math.round(lastP.mid)) + "</text>");
  }

  var every = Math.max(1, Math.ceil(slots * 46 / pw));
  win.concat(proj ? proj.points : []).forEach(function (r, i) {
    if ((slots - 1 - i) % every) return;
    svg.push('<text x="' + (L + i * step + step / 2).toFixed(1) + '" y="' + (H - 6) +
             '" class="chx" text-anchor="middle">' +
             esc(spec.xlab ? spec.xlab(r) : r.m.slice(2)) + "</text>");
  });
  svg.push("</svg>");

  var chips = spec.names.map(function (nm, i) {
    return '<span><i style="background:var(--ch-' + spec.vars[i] + ')"></i>' +
      esc(nm) + "</span>";
  });
  if (proj) chips.push('<span><i class="dash"></i>projected, 80% range shaded</span>');
  var legend = spec.names.length > 1 || proj
    ? '<div class="chlegend">' + chips.join("") + "</div>" : "";

  fig.innerHTML = bar + legend + svg.join("") + chStats(spec, win, proj) +
    '<p class="figwhy">' + esc(spec.why) +
    (proj ? " The projection is a straight line through the months shown, " +
            "with the shaded range covering how far past months missed that " +
            "line. It is arithmetic, not a forecast of what people will do." : "") +
    "</p>";
}

function chDrawAll() { $$(".fig").forEach(chDraw); }

/* Cards grow on demand. A card holding a chart is the one that most wants
   the room, but the button goes on every card in the dashboard grids: the
   right-hand column often ends early and the space is there to be used. */
function chMountExpand() {
  $$(".grid2 > .card, .cols2 > .card, .grid3 > .card").forEach(function (card) {
    var h = card.querySelector("h2");
    if (!h || h.querySelector(".expand")) return;
    var key = (h.textContent || "").trim();
    var b = document.createElement("button");
    b.type = "button";
    b.className = "expand";
    b.dataset.card = key;
    card.dataset.card = key;
    var on = false;
    try { on = (JSON.parse(localStorage.getItem("panel.wide") || "[]") || [])
                 .indexOf(key) >= 0; }
    catch (e) { on = false; }
    card.classList.toggle("wide", on);
    b.setAttribute("aria-expanded", String(on));
    b.textContent = on ? "shrink" : "expand";
    h.appendChild(b);
  });
}

/* A card already filling its row has nothing to gain from expanding, and
   a button that visibly does nothing is worse than no button. That happens
   two ways: setView marks a container .solo when one card is left visible,
   and the auto-fit grids collapse to a single column on a narrow window.
   Both show up as one column here, so one check covers them. */
function chSyncExpand() {
  $$(".expand").forEach(function (b) {
    var card = b.closest(".card");
    var cols = getComputedStyle(card.parentElement).gridTemplateColumns;
    var many = cols.split(" ").filter(Boolean).length > 1;
    b.hidden = !many;
    if (!many && card.classList.contains("wide")) card.classList.remove("wide");
  });
}

function chWideSave() {
  try {
    localStorage.setItem("panel.wide", JSON.stringify(
      $$(".card.wide").map(function (c) { return c.dataset.card; })));
  } catch (e) { /* forgetting the layout is survivable */ }
}

document.addEventListener("click", function (ev) {
  var seg = ev.target.closest(".seg button[data-ch]");
  if (seg) {
    var st = chState[seg.dataset.ch];
    var v = parseInt(seg.dataset.val, 10);
    if (seg.dataset.set === "trend") st.trend = !!v; else st[seg.dataset.set] = v;
    chSave();
    chDraw($(".fig[data-chart='" + seg.dataset.ch + "']"));
    return;
  }
  var ex = ev.target.closest(".expand");
  if (ex) {
    ev.stopPropagation();
    var card = ex.closest(".card");
    var on = card.classList.toggle("wide");
    ex.setAttribute("aria-expanded", String(on));
    ex.textContent = on ? "shrink" : "expand";
    chWideSave();
    $$(".fig", card).forEach(chDraw);
  }
});

var chTimer;
addEventListener("resize", function () {
  clearTimeout(chTimer);
  chTimer = setTimeout(function () { chSyncExpand(); chDrawAll(); }, 180);
});

chLoad();
chMountExpand();
chSyncExpand();
chDrawAll();


/* ---- the short-link manager, brought into the panel ----
   The read half already existed. This adds the two writes worth having
   locally, creating a link and repointing one, plus the per-link drilldown.
   Deleting stays in adminlocoILco on purpose: it takes the click history
   with it and the bot's SQLite has nothing behind it to restore from.

   Every call goes to the local /link route, which holds the admin secret
   and the bearer token. The page never sees either. */
var LT_PREFIXES = ["p", "download", "docs", "free", "freebuild", "root"];

function ltPost(body) {
  return fetch("/link", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Panel-Token": PANEL_TOKEN },
    body: JSON.stringify(body)
  }).then(function (r) { return r.json(); });
}

function ltBrowser(ua) {
  if (!ua) return "unknown";
  var has = function (t) { return ua.indexOf(t) >= 0; };
  if (has("Edg/")) return "Edge";
  if (has("OPR/")) return "Opera";
  if (has("Firefox/")) return "Firefox";
  if (has("Chrome/")) return "Chrome";
  if (has("Safari/")) return "Safari";
  var low = ua.toLowerCase();
  if (low.indexOf("bot") >= 0 || low.indexOf("crawl") >= 0 ||
      low.indexOf("spider") >= 0) return "bot";
  return "other";
}

function ltTop(rows, pick) {
  var c = {};
  rows.forEach(function (r) {
    var k = pick(r);
    if (k) c[k] = (c[k] || 0) + 1;
  });
  var best = Object.keys(c).sort(function (a, b) { return c[b] - c[a]; })[0];
  return best ? best + " (" + Math.round(c[best] * 100 / rows.length) + "%)" : "-";
}

function bicon(name, size) {
  if (BRANDS.indexOf(name) < 0) name = "web";
  return '<svg width="' + (size || 14) + '" height="' + (size || 14) +
    '" class="bi" aria-hidden="true"><use href="#bi-' + name + '"></use></svg>';
}

/* Which mark belongs to a host. Everything unknown falls to the globe
   rather than to a wrong logo. */
function ltMark(host) {
  var h = (host || "").toLowerCase();
  if (!h || h === "direct") return "web";
  if (h.indexOf("youtube") >= 0) return "youtube";
  if (h.indexOf("patreon") >= 0) return "patreon";
  if (h.indexOf("discord") >= 0) return "discord";
  if (h.indexOf("docs.google") >= 0) return "gdocs";
  if (h.indexOf("notebooklm") >= 0) return "notebooklm";
  if (h.indexOf("drive.google") >= 0 || h.indexOf("google") >= 0) return "drive";
  if (h.indexOf("mega.nz") >= 0) return "mega";
  if (h.indexOf("gamma.app") >= 0) return "gamma";
  return "web";
}

function ltBrowserMark(name) {
  var n = (name || "").toLowerCase();
  return BRANDS.indexOf(n) >= 0 ? n : "web";
}

/* A click closer than two seconds to the same visitor's previous one was
   not made by a hand. Marking them is the difference between a number you
   can act on and one that flatters you: /root/uecourse reads 8,240 clicks
   and 93% of its recent ones arrive in bursts like this. */
var LT_BURST_SECS = 2;

function ltFlagBursts(clicks) {
  var last = {}, n = 0;
  var asc = clicks.slice().sort(function (a, b) {
    return Date.parse(a.clicked_at) - Date.parse(b.clicked_at);
  });
  asc.forEach(function (c) {
    var t = Date.parse(c.clicked_at), prev = last[c.ip_hash];
    c._burst = prev !== undefined && (t - prev) / 1000 < LT_BURST_SECS;
    if (c._burst) n++;
    last[c.ip_hash] = t;
  });
  return n;
}

function ltShort(prefix, slug) {
  if (prefix === "root") return "locodev.dev/" + (slug === "_root" ? "" : slug);
  return "locodev.dev/" + prefix + "/" + slug;
}

/* One link opened: what its clicks say, and the field that repoints it. */
function ltDetail(box, prefix, slug) {
  box.innerHTML = '<div class="note">reading this link’s clicks…</div>';
  ltPost({ action: "clicks", prefix: prefix, slug: slug }).then(function (r) {
    if (!r.ok) {
      box.innerHTML = '<div class="note">could not read it: ' + esc(r.error) + "</div>";
      return;
    }
    var cl = r.clicks || [], link = r.link || {};
    var uniq = {}, h = "";
    cl.forEach(function (c) { if (c.ip_hash) uniq[c.ip_hash] = 1; });
    var nuniq = Object.keys(uniq).length;
    var capped = (link.total_clicks || 0) > cl.length;
    var bursts = ltFlagBursts(cl);
    var burstPct = cl.length ? Math.round(bursts * 100 / cl.length) : 0;
    var full = ltShort(prefix, slug);

    h += '<div class="lfull"><span class="figlab">short link</span>'
      + '<a href="https://' + esc(full) + '" target="_blank" rel="noopener">https://'
      + esc(full) + "</a>"
      + '<button class="btn tiny" data-copy="https://' + esc(full) + '">copy</button></div>';

    h += '<div class="figstat" style="border-top:0;padding-top:0">'
      + '<div><span class="k">clicks, all time</span><span class="v">'
      + fmt(link.total_clicks || 0) + "</span></div>"
      + '<div><span class="k">people, in this sample</span><span class="v">'
      + fmt(nuniq) + "</span></div>"
      + '<div><span class="k">clicks per person</span><span class="v'
      + (nuniq && cl.length / nuniq >= 4 ? " warn" : "") + '">'
      + (nuniq ? (cl.length / nuniq).toFixed(1) : "-") + "</span></div>"
      + '<div><span class="k">arrived in bursts</span><span class="v'
      + (burstPct >= 20 ? " warn" : "") + '">' + burstPct + "%</span></div>"
      + '<div><span class="k">top browser</span><span class="v">'
      + esc(ltTop(cl, function (c) { return ltBrowser(c.user_agent); })) + "</span></div>"
      + '<div><span class="k">came from</span><span class="v">'
      + esc(ltTop(cl, function (c) { return c.referrer || "direct"; })) + "</span></div>"
      + "</div>";

    h += '<p class="figwhy">Everything except the all-time count is measured '
      + "over the " + fmt(cl.length) + " most recent clicks"
      + (capped ? ", which is all the API returns per link. The rest of the "
                + fmt(link.total_clicks) + " are not in this sample." : ".")
      + " A click is counted as a burst when the same visitor made another "
      + "less than two seconds earlier, which no hand does; "
      + (burstPct >= 20
         ? "at " + burstPct + "% this link's recent traffic is mostly automated, "
           + "so read its totals as a ceiling rather than an audience."
         : "at " + burstPct + "% this one looks like people.") + "</p>";

    h += '<div class="ledit"><label>Points at</label>'
      + '<input type="url" class="lurl" value="' + esc(link.url || "") + '">'
      + '<button class="btn tiny primary lsave">Save</button>'
      + '<span class="note lmsg"></span></div>';

    h += '<p class="lsub">Every click in the sample · ' + fmt(cl.length) + "</p>";
    if (!cl.length) h += '<div class="empty">none yet</div>';
    else {
      h += '<div class="lclicks">';
      cl.forEach(function (c) {
        var br = ltBrowser(c.user_agent);
        var ref = c.referrer || "direct";
        var cc = (c.country_code && c.country_code !== "??") ? c.country_code : "";
        h += '<div class="lclick' + (c._burst ? " burst" : "") + '">'
          + (cc ? '<span class="cc">' + esc(cc) + "</span>"
                : '<span class="cc none" title="no country recorded">--</span>')
          + '<span class="lb">' + bicon(ltBrowserMark(br)) + esc(br) + "</span>"
          + '<span class="lr">' + bicon(ltMark(ref)) + esc(ref) + "</span>"
          + (c._burst ? '<span class="btag">burst</span>' : "")
          + '<span class="n">' + rel(c.clicked_at) + "</span></div>";
      });
      h += "</div>";
    }
    box.innerHTML = h;
    box.dataset.prefix = prefix;
    box.dataset.slug = slug;
  }).catch(function (e) {
    box.innerHTML = '<div class="note">could not read it: ' + esc(e.message) + "</div>";
  });
}

function ltComposer() {
  return '<div class="lask"><span class="figlab">describe it</span>'
    + '<input class="lq" placeholder="weapon system premium" '
    + 'aria-label="Describe the link you want">'
    + '<button class="btn tiny lsuggest">Suggest</button>'
    + '<span class="note lqmsg"></span></div>'
    + '<div class="lqout"></div>'
    + '<div class="lnew"><span class="figlab">new link</span>'
    + '<select class="lnp" aria-label="Prefix">'
    + LT_PREFIXES.map(function (p) { return '<option value="' + p + '">' + p + "</option>"; }).join("")
    + '</select><input class="lns" placeholder="slug" aria-label="Slug">'
    + '<input class="lnu" type="url" placeholder="https://where it should go" aria-label="Destination">'
    + '<button class="btn tiny primary lncreate">Create</button>'
    + '<span class="note lnmsg"></span></div>';
}

/* Suggest reads the convention off the links that already exist rather
   than off the catalog name, then fills the fields. It stops short of the
   destination: a Patreon post URL cannot be derived from a system name, so
   it shows the sibling links and the host they use and leaves the address
   to you. A fabricated URL that 404s would be worse than an empty box. */
function ltSuggest(wrap) {
  var q = $(".lq", wrap).value.trim();
  var msg = $(".lqmsg", wrap);
  var out = $(".lqout");
  msg.textContent = "thinking…";
  ltPost({ action: "suggest", url: q }).then(function (r) {
    if (!r.ok) { msg.textContent = r.error; out.innerHTML = ""; return; }
    msg.textContent = "";
    var form = $(".lnew");
    $(".lnp", form).value = r.prefix;
    $(".lns", form).value = r.slug;
    if (r.host && !$(".lnu", form).value) $(".lnu", form).value = "https://" + r.host + "/";
    var h = '<div class="lqcard"><b>locodev.dev/' + esc(r.prefix) + "/" + esc(r.slug)
      + "</b>" + (r.taken ? ' <span class="lqbad">that one already exists</span>' : "")
      + '<p class="figwhy">' + esc(r.system) + ", tier " + esc(r.tier)
      + ". The slug follows the " + fmt(r.stem_from) + " link"
      + (r.stem_from === 1 ? "" : "s") + " this system already has"
      + (r.stem_from ? "" : ", or the catalog name where it has none")
      + ". " + (r.host ? "Links under " + esc(r.prefix) + " point at "
                + esc(r.host) + " (" + esc(r.host_share) + "), so the box is "
                + "started there; paste the real address, it cannot be "
                + "guessed from a name." : "") + "</p>";
    if (r.siblings && r.siblings.length) {
      h += '<p class="lsub">Where its siblings point</p>';
      r.siblings.forEach(function (sb) {
        h += '<div class="lrow"><span class="slug">/' + esc(sb.short) + "</span>"
          + '<span class="n"><a href="' + esc(sb.url) + '" target="_blank" '
          + 'rel="noopener">' + esc(sb.url.replace(/^https?:../, "").slice(0, 54))
          + "</a></span></div>";
      });
    }
    out.innerHTML = h + "</div>";
  });
}

document.addEventListener("keydown", function (ev) {
  if (ev.key === "Enter" && ev.target.matches(".lq")) {
    ev.preventDefault();
    ltSuggest(ev.target.closest(".lask"));
  }
});

document.addEventListener("click", function (ev) {
  if (ev.target.closest(".qclearq")) {
    $("#q").value = "";
    state.q = "";
    page = 0;
    apply();
    syncUrl();
    return;
  }
  var vb = ev.target.closest("[data-vbulk]");
  if (vb) {
    /* A question carries its system's display name, not its slug, and the
       filter is keyed by slug. Matching on the label is what makes the two
       meet without shipping the slug into every question in the payload. */
    var sys = vb.dataset.vbulk;
    goView("questions");
    var sel = $("#sysSel");
    var hit = sys && [].filter.call(sel.options, function (o) {
      return o.textContent.indexOf(sys + " (") === 0;
    })[0];
    if (!hit) {
      $("#bulkmsg").textContent =
        "these questions are not filed under a catalog system yet";
      return;
    }
    /* Through the filter state, not just the control: the table under the
       run should be showing the same system the run is about to draft. */
    state.sys = hit.value;
    sel.value = hit.value;
    page = 0;
    apply();
    syncUrl();
    var card = $("#questions");
    card.scrollIntoView({ block: "start" });
    card.classList.add("flashcard");
    setTimeout(function () { card.classList.remove("flashcard"); }, 1400);
    /* The button says Draft, so it drafts. It used to only preselect the
       picker, which left you looking at whatever run was on screen from
       before. */
    var run = $("#bulkrun");
    if (run && !run.disabled) run.click();
    return;
  }
  var sug = ev.target.closest(".lsuggest");
  if (sug) { ltSuggest(sug.closest(".lask")); return; }
  var save = ev.target.closest(".lsave");
  if (save) {
    var box = save.closest(".ldet");
    var url = $(".lurl", box).value.trim();
    var msg = $(".lmsg", box);
    msg.textContent = "saving…";
    ltPost({ action: "edit", prefix: box.dataset.prefix, slug: box.dataset.slug, url: url })
      .then(function (r) {
        msg.textContent = r.ok ? "saved · the short link now points there"
                               : "not saved: " + r.error;
        if (r.ok) loadLinks();
      });
    return;
  }
  var mk = ev.target.closest(".lncreate");
  if (mk) {
    var wrap = mk.closest(".lnew");
    var msg2 = $(".lnmsg", wrap);
    msg2.textContent = "creating…";
    ltPost({ action: "create", prefix: $(".lnp", wrap).value,
             slug: $(".lns", wrap).value.trim(), url: $(".lnu", wrap).value.trim() })
      .then(function (r) {
        if (!r.ok) { msg2.textContent = "not created: " + r.error; return; }
        msg2.textContent = "created";
        $(".lns", wrap).value = "";
        $(".lnu", wrap).value = "";
        loadLinks();
      });
    return;
  }
  var ed = ev.target.closest(".lkedit");
  if (ed) {
    /* Opens the same drilldown a click on the row opens, then puts the
       caret in the field that matters, so the button is a shortcut rather
       than a second way of doing it. */
    var erow = ed.closest("tr.lkrow");
    var edet = erow.nextElementSibling;
    if (!edet.classList.contains("open")) {
      edet.classList.add("open");
      erow.setAttribute("aria-expanded", "true");
      ltDetail($(".ldet", edet), erow.dataset.prefix, erow.dataset.slug);
    }
    setTimeout(function () {
      var f = $(".lurl", edet);
      if (f) { f.focus(); f.select(); }
    }, 400);
    return;
  }

  var row = ev.target.closest("tr.lkrow");
  if (row && !ev.target.closest("button")) {
    var det = row.nextElementSibling;
    var open = det.classList.toggle("open");
    row.setAttribute("aria-expanded", String(open));
    if (open) ltDetail($(".ldet", det), row.dataset.prefix, row.dataset.slug);
  }
});

/* Typing filters the whole list rather than the ten that used to show. */
document.addEventListener("input", function (ev) {
  if (ev.target.classList && ev.target.classList.contains("bulkrefs")) {
    /* Remembered so the next render, and the next row, opens on the number
       you last chose rather than resetting under you every two seconds. */
    BULK_REFS = ev.target.value;
    $$(".bulkrefs").forEach(function (b) { if (b !== ev.target) b.value = BULK_REFS; });
    return;
  }
  if (ev.target.id === "bulkfloor") {
    var v = parseInt(ev.target.value, 10);
    if (isNaN(v)) return;               /* mid-edit empty box: wait for a number */
    BULK_CONF_FLOOR = Math.max(0, Math.min(100, v));
    bulkSyncFloor();
    return;
  }
  if (!ev.target.matches(".lfind")) return;
  var q = ev.target.value.toLowerCase();
  $$("tr.lkrow").forEach(function (r) {
    var hit = !q || r.dataset.find.indexOf(q) >= 0;
    r.hidden = !hit;
    if (!hit) r.nextElementSibling.classList.remove("open");
    r.nextElementSibling.hidden = !hit;
  });
});


/* ---- where people are clicking ----
   Eighty-eight rows of slug told you nothing about which system people
   want. These three rankings answer that in the catalog's own words: by
   system, by what kind of page it is, and by country.

   Ranked bars rather than a pie or a line: the question is "which is
   bigger", the categories have no order of their own, and a length against
   a shared baseline is the one comparison people read accurately. One
   series, one hue, so no legend is needed and colour carries no meaning
   the label does not already say. */
function ltBars(rows, total, empty) {
  if (!rows.length) return '<div class="empty">' + esc(empty) + "</div>";
  var top = rows[0][1] || 1;
  return '<div class="bars">' + rows.map(function (r) {
    var pct = total ? Math.round(r[1] * 1000 / total) / 10 : 0;
    return '<div class="bar" title="' + esc(r[0] + ": " + fmt(r[1]) +
      " clicks, " + pct + "% of " + fmt(total)) + '">' +
      '<span class="bl">' + esc(r[0]) + "</span>" +
      '<span class="bt"><i style="width:' +
      Math.max(1, r[1] * 100 / top).toFixed(1) + '%"></i></span>' +
      '<span class="bv">' + fmt(r[1]) + "</span></div>";
  }).join("") + "</div>";
}

function ltRank(links, key, field) {
  var by = {};
  links.forEach(function (l) {
    var k = l[key];
    if (!k) return;
    by[k] = (by[k] || 0) + (l[field] || 0);
  });
  return Object.keys(by).map(function (k) { return [k, by[k]]; })
    .sort(function (a, b) { return b[1] - a[1]; });
}

var LT_CWIN = "all";

function ltCountries(rows, win) {
  var total = rows.reduce(function (t, r) { return t + (r.clicks || 0); }, 0);
  var ranked = rows.map(function (r) {
    return [(r.country && r.country !== "Unknown") ? r.country
            : (r.country_code === "??" ? "not recorded" : r.country_code), r.clicks];
  }).slice(0, 10);
  var seg = '<span class="seg" role="group">' +
    [["24h", "24 hours"], ["7d", "7 days"], ["all", "all time"]].map(function (o) {
      return '<button type="button" class="ltcw" data-win="' + o[0] +
        '" aria-pressed="' + (o[0] === win) + '">' + o[1] + "</button>";
    }).join("") + "</span>";
  var note = "";
  if (!rows.length && win !== "all") {
    note = '<p class="figwhy">No click in this window carries a country. ' +
      "The lookup has been answering Unknown, so recent clicks have no " +
      "country at all; switch to all time to see the ones recorded while " +
      "it worked.</p>";
  } else if (win === "all") {
    note = '<p class="figwhy">All time, which is the only window with ' +
      "countries in it: the lookup has stopped resolving lately, so the " +
      "last few days are missing from this and the newest clicks show as " +
      "not recorded.</p>";
  }
  return '<div class="figbar"><span class="figlab">window</span>' + seg + "</div>" +
    ltBars(ranked, total, "nothing recorded in this window") + note;
}

function ltWhere(d) {
  var links = d.links || [];
  var withSys = links.filter(function (l) { return l.system; });
  var noSys = links.filter(function (l) { return !l.system && l.kind !== "Site"; });
  var sysTotal = withSys.reduce(function (t, l) { return t + (l.total_clicks || 0); }, 0);
  var kinds = ltRank(links, "kind", "total_clicks");
  var kindTotal = kinds.reduce(function (t, r) { return t + r[1]; }, 0);
  var lost = noSys.reduce(function (t, l) { return t + (l.total_clicks || 0); }, 0);

  var h = '<p class="lsub">Which system people click</p>';
  h += ltBars(ltRank(withSys, "system", "total_clicks").slice(0, 12), sysTotal,
              "no link matched a catalog system");
  h += '<p class="figwhy">Clicks on every link that sells a system, all '
    + "time, added up across its Patreon page, its download and its docs. "
    + fmt(withSys.length) + " of " + fmt(links.length) + " links matched a "
    + "system by name. The site's own links are left out on purpose: they "
    + "are the homepage and the course, not a product."
    + (noSys.length ? " " + fmt(noSys.length) + " product links (" + fmt(lost)
       + " clicks) name something the catalog does not have yet, GASP+ALS "
       + "and push-and-pull among them." : "") + "</p>";

  h += '<p class="lsub">What they click on it</p>';
  h += ltBars(kinds, kindTotal, "nothing yet");
  h += '<p class="figwhy">A download means someone already bought or is '
    + "taking the free build; a Patreon page means they are still deciding. "
    + "Anything here outside the usual six prefixes still works, because "
    + "the shortener serves whatever is in its database; the six are a "
    + "naming habit, not a gate.</p>";

  h += '<p class="lsub">Where in the world</p>';
  h += '<div id="ltcountries">' + ltCountries(d.countries || [], LT_CWIN) + "</div>";
  return h;
}

document.addEventListener("click", function (ev) {
  var b = ev.target.closest(".ltcw");
  if (!b) return;
  LT_CWIN = b.dataset.win;
  var box = $("#ltcountries");
  box.innerHTML = '<div class="note">reading…</div>';
  ltPost({ action: "countries", slug: LT_CWIN }).then(function (r) {
    box.innerHTML = ltCountries(r.ok ? (r.countries || []) : [], LT_CWIN);
  });
});


/* ---- answering a whole system ----
   Drafting and sending are two clicks, never one. What comes back from the
   model is text with your name on it going to people who are waiting, so
   the list between the two steps is editable and is the point of the
   feature, not a formality. */
var BULK_POLL = null;
var BULK_GAP = "fast";
/* Midpoint of a gap, and the words for the confirmation, both read off
   BULK_GAPS so a new range needs no second edit here. */
function gapRange(name) { return BULK_GAPS[name] || [50, 300]; }
function gapMid(name) { var r = gapRange(name); return (r[0] + r[1]) / 2; }
function gapLabel(name) { var r = gapRange(name); return r[0] + " to " + r[1] + "s"; }
function gapWords(name) {
  var r = gapRange(name);
  return "one every " + r[0] + " to " + r[1] + " seconds";
}

function bulkPost(body) {
  return fetch("/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Panel-Token": PANEL_TOKEN },
    body: JSON.stringify(body)
  }).then(function (r) { return r.json(); });
}

function bulkSpan(secs) {
  if (secs < 90) return Math.round(secs) + "s";
  if (secs < 5400) return Math.round(secs / 60) + " min";
  return (secs / 3600).toFixed(1) + " hours";
}

/* What the CLI reported for the work so far. Shown because a number
   climbing fast is how a runaway prompt announces itself, and labelled as
   what it is: these run through the Claude Code subscription, so it is a
   meter reading, not a bill. It only warns when a ceiling was deliberately
   set with PANEL_AI_DAILY_USD. */
function bulkMoney(c) {
  if (!c || !c.per_draft) return "";
  var over = c.capped && c.estimate > c.left_today;
  var h = '<div class="figstat"><div><span class="k">a draft reports</span>'
    + '<span class="v">US$ ' + c.per_draft.toFixed(2) + "</span></div>"
    + '<div><span class="k">reported today</span><span class="v">US$ '
    + c.spent_today.toFixed(2) + "</span></div>"
    + (c.to_draft ? '<div><span class="k">' + fmt(c.to_draft)
        + ' still to write</span><span class="v' + (over ? " warn" : "")
        + '">US$ ' + c.estimate.toFixed(2) + "</span></div>" : "")
    + (c.capped ? '<div><span class="k">left of today</span><span class="v'
        + (c.left_today < 1 ? " warn" : "") + '">US$ '
        + c.left_today.toFixed(2) + "</span></div>" : "")
    + "</div>";
  if (over) {
    h += '<p class="figwhy">That is more than today’s ceiling leaves. The '
      + "run will draft what fits, stop, and say so; the rest keep their "
      + "place. Raise it with PANEL_AI_DAILY_USD in clickup-mcp/.env.</p>";
  } else if (!c.capped) {
    h += '<p class="figwhy">What the CLI reports, not a bill: these go '
      + "through the Claude Code subscription. Nothing stops the run on cost. "
      + "Set PANEL_AI_DAILY_USD above zero if you want a daily ceiling "
      + "back.</p>";
  }
  return h;
}

/* Two different questions that were being asked with one expression.
   bulkRunning is about the run: whether starting another would collide.
   bulkBusy is about anything still in flight, a single row's polish
   included. A polish leaves phase at "ready" and moves only the row, so a
   poll that watched the phase alone cleared itself on its first tick and
   the polished text arrived on the server with nothing left to draw it. */
function bulkRunning(st) {
  return st.phase === "drafting" || st.phase === "sending";
}
function bulkBusy(st) {
  if (bulkRunning(st)) return true;
  /* "sending" belongs here too. A single Send this one puts one row into
     "sending" while the run phase stays "ready"; without this a tab opened
     during that send reads the run as settled, stops polling, and shows
     the row's buttons live over an item that is already on its way out. */
  return (st.items || []).some(function (i) {
    return i.state === "polishing" || i.state === "drafting"
        || i.state === "sending"; });
}

/* Counted off the rows rather than off st.done, which counts anything no
   longer waiting, a failure included. */
/* The floor the "send the confident ones" button uses, and the band the
   list is filtered to. Both live here so the button's count and the rows
   you can see are always answering the same question. */
var BULK_CONF_FLOOR = 85;
/* How many videos from Reference/ a draft should cite. Empty means
   let it decide from how many things the question actually names. */
var BULK_REFS = "";
var BULK_CONF_BAND = "all";
function bulkConfOf(it) { return typeof it.conf === "number" ? it.conf : 0; }
function bulkInBand(it, band) {
  var c = bulkConfOf(it);
  if (band === "high") return c >= BULK_CONF_FLOOR;
  if (band === "mid") return c >= 60 && c < BULK_CONF_FLOOR;
  if (band === "low") return c > 0 && c < 60;
  if (band === "none") return c === 0;
  return true;
}
/* The floor moved, so the pieces that quote it move with it. Done in
   place rather than by re-rendering: rebuilding the list would drop any
   reply you had edited by hand but not sent yet, and would take the caret
   out of the box you are typing in. */
function bulkSyncFloor() {
  var st = LAST_BULK;
  if (!st) return;
  var conf = bulkSendable(st).filter(function (i) {
    return bulkConfOf(i) >= BULK_CONF_FLOOR; }).length;
  var n = $("#bulkconfn"), pct = $("#bulkconfpct"), eta = $("#bulkconfeta");
  if (n) n.textContent = fmt(conf);
  if (pct) pct.textContent = BULK_CONF_FLOOR;
  if (eta) eta.textContent = "spaced, about "
    + bulkSpan(gapMid(BULK_GAP) * Math.max(0, conf - 1));
  var btn = $("#bulkconfnow");
  if (btn) btn.disabled = !conf;
  /* The bands are named after the floor, so they follow it and the filter
     keeps agreeing with the button beside it. */
  $$(".bulkband").forEach(function (b) {
    var band = b.dataset.band, label;
    if (band === "high") label = BULK_CONF_FLOOR + "% and up";
    else if (band === "mid") label = "60 to " + (BULK_CONF_FLOOR - 1) + "%";
    else if (band === "low") label = "under 60%";
    else if (band === "none") label = "not drafted yet";
    else label = "all";
    var count = (st.items || []).filter(function (i) {
      return bulkInBand(i, band); }).length;
    b.textContent = label + " " + fmt(count);
  });
  $$(".bulkitem").forEach(function (el) {
    var it = (st.items || []).filter(function (i) {
      return i.id === el.dataset.id; })[0];
    if (it) el.style.display = bulkInBand(it, BULK_CONF_BAND) ? "" : "none";
  });
}

function bulkSendable(st) {
  return (st.items || []).filter(function (i) {
    return i.draft && (i.state === "drafted" || i.state === "failed");
  });
}
function bulkCount(st, state) {
  return (st.items || []).filter(function (i) { return i.state === state; }).length;
}
function bulkDrafted(st) {
  return bulkCount(st, "drafted") + bulkCount(st, "sent")
    + bulkCount(st, "filed");
}
function bulkFiled(st) { return bulkCount(st, "filed"); }
function bulkFailed(st) { return bulkCount(st, "failed"); }

/* How well the vault backed this particular answer, as the model scored
   it. Same component and same 60/30 thresholds as the single-question
   view: a row that reads 24% here should read 24% there, and look it. */
/* Sits beside whichever draft button is on the row. Left empty it changes
   nothing and the draft cites one video per thing the question names; a
   number makes that the target instead. It rides in on the note rather
   than as a parameter of its own, which also means the job key changes
   with it: asking for five after asking for two is a new call, not the
   old answer coming back. */
function refsField() {
  return '<label class="refsbox">refs<input type="number" class="bulkrefs" '
    + 'min="0" max="12" placeholder="auto" value="' + esc(BULK_REFS)
    + '" aria-label="How many video references to cite"></label>';
}

/* What actually reaches the model: the count first, then whatever you
   typed. Both draft buttons go through here so the queue card and the
   inbox row cannot end up meaning different things by the same field. */
function draftNote(container, typed) {
  var want = refsNote(container);
  if (!want) return typed || "";
  return typed ? want + String.fromCharCode(10) + typed : want;
}

function refsNote(row) {
  var box = $(".bulkrefs", row);
  var n = box ? parseInt(box.value, 10) : NaN;
  if (isNaN(n) || n < 1) return "";
  return "Cite " + n + " video reference" + (n === 1 ? "" : "s")
    + " from the vault in this reply, the ones that best fit what the "
    + "message asks about.";
}

function bulkConf(it) {
  if (it.state !== "drafted" && it.state !== "sent") return "";
  var c = typeof it.conf === "number" ? it.conf : 0;
  if (!c) return "";
  var cls = c >= 60 ? "ok" : c >= 30 ? "warn" : "crit";
  return '<span class="conf conf-' + cls + '" title="How well the vault '
    + 'supports this answer. Under 30% usually means it is guessing.">'
    + '<span class="confbar"><i style="width:' + c + '%"></i></span>'
    + c + "%</span>";
}

/* One card, two states: the queue (filters and the table) or the review
   (the run's drafts and the send controls). Never both at once: they are
   the same questions, and showing them twice on one screen was the
   two-card layout this replaces. */
var BULK_MODE = "queue";
function bulkMode(m) {
  BULK_MODE = m;
  var card = $("#questions");
  if (card) card.classList.toggle("reviewing", m === "review");
  if (LAST_BULK) bulkRender(LAST_BULK);
}

/* Edits to review drafts, kept off the DOM so they survive a mode switch,
   a two-second re-render and a full page reload. The textarea alone lost
   them the moment Back to the queue replaced the card, or the panel
   rebuilt and the browser reloaded. Mirrored to sessionStorage by id. */
var BULK_EDITS = (function () {
  try { return JSON.parse(sessionStorage.getItem("lp-bulk-edits") || "{}"); }
  catch (e) { return {}; }
})();
function bulkEditsSave() {
  try { sessionStorage.setItem("lp-bulk-edits", JSON.stringify(BULK_EDITS)); }
  catch (e) {}
}
/* Snapshot whatever is typed into the visible review rows into the map,
   before any render or mode switch wipes them. Only real edits: a textarea
   still holding the server draft is left out so it can update freely. */
function bulkCaptureEdits() {
  var box = $("#bulkbody");
  if (!box) return;
  var moved = false;
  $$(".bulkitem", box).forEach(function (el) {
    var t = $(".bulkdraft", el);
    if (t && t.value !== t.defaultValue) {
      BULK_EDITS[el.dataset.id] = t.value; moved = true;
    }
  });
  if (moved) bulkEditsSave();
}
/* A sent or filed row is done; its edit must not resurrect on the next
   render or outlive the run in storage. */
function bulkPruneSent(st) {
  var moved = false;
  (st.items || []).forEach(function (it) {
    if ((it.state === "sent" || it.state === "filed")
        && BULK_EDITS[it.id] !== undefined) {
      delete BULK_EDITS[it.id]; moved = true;
    }
  });
  if (moved) bulkEditsSave();
}

var LAST_BULK = null;
function bulkRender(st) {
  LAST_BULK = st;
  var box = $("#bulkbody");
  if (!box) return;
  /* Before anything below can replace the card (the queue-mode early
     return included), save what is typed and drop edits for rows that
     have since gone out. */
  bulkCaptureEdits();
  bulkPruneSent(st);
  var busy = bulkRunning(st);
  var run = $("#bulkrun");
  if (run) run.disabled = busy;

  var h = "";
  if (st.phase === "idle") { box.innerHTML = ""; return; }

  /* On the queue, a run folds down to one line above the table; the full
     review only replaces the table when asked for. Rendering both at once
     was the old two-card layout: the same questions listed twice on one
     screen. */
  if (BULK_MODE !== "review") {
    var send = bulkSendable(st).length;
    box.innerHTML = '<div class="figbar bulkslim">'
      + '<span class="note">' + (busy
        ? esc(st.phase === "drafting" ? "Drafting" : "Sending") + " "
          + esc(st.system_name) + ", " + fmt(st.done) + " of "
          + fmt(st.items.length)
        : "Last run: " + esc(st.system_name) + " &middot; "
          + fmt(bulkDrafted(st)) + " of " + fmt(st.items.length) + " drafted"
          + (bulkFailed(st) ? " &middot; " + fmt(bulkFailed(st)) + " failed" : "")
          + (send ? " &middot; " + fmt(send) + " ready to send" : ""))
      + "</span>"
      + '<button class="btn tiny" id="bulkreview">'
      + (busy ? "Watch it run" : "Review and send") + "</button></div>";
    return;
  }

  var n = st.items.length;
  /* The review replaces the queue, so the way back sits where the queue
     went. The old card instead kept a note explaining which run this was,
     because its own picker could name a different system than the run on
     screen; one picker now, so the mismatch it apologised for is gone. */
  h += '<div class="figbar" style="border-top:0;padding-top:0">'
    + '<button class="btn tiny" id="bulkback">&larr; Back to the queue</button></div>';
  h += '<div class="figstat" style="border-top:0;padding-top:0">'
    + '<div><span class="k">system</span><span class="v">' + esc(st.system_name) + "</span></div>"
    + '<div><span class="k">questions</span><span class="v">' + fmt(n) + "</span></div>"
    + '<div><span class="k">drafted</span><span class="v">' + fmt(bulkDrafted(st))
    + "</span></div>"
    /* Failures were only shown once sending began, and st.done counts them
       as progress, so a run could read "drafted 88 of 103" with 38 of those
       88 broken and nothing on the card saying so. */
    + (bulkFailed(st)
       ? '<div><span class="k">failed</span><span class="v warn">'
         + fmt(bulkFailed(st)) + "</span></div>" : "")
    + (st.phase === "sending" || st.phase === "done"
       ? '<div><span class="k">sent</span><span class="v">'
         + fmt(bulkCount(st, "sent")) + "</span></div>"
       : "")
    /* Shown whenever there is one, in any phase: a revoked token turns
       every send into one of these and the run otherwise looks healthy. */
    + (bulkFiled(st)
       ? '<div><span class="k">filed, not delivered</span>'
         + '<span class="v warn">' + fmt(bulkFiled(st)) + "</span></div>" : "")
    + "</div>";

  if (bulkRunning(st)) {
    var pct = n ? Math.round(st.done * 100 / n) : 0;
    h += '<div class="bulkbar" role="progressbar" aria-valuenow="' + pct
      + '" aria-valuemin="0" aria-valuemax="100"><i style="width:' + pct
      + '%"></i></div>'
      + '<p class="figwhy">' + (st.phase === "drafting" ? "Drafting " : "Sending ")
      + fmt(st.done) + " of " + fmt(n) + " · " + pct + "%"
      + (st.per_item ? " · about " + bulkSpan(st.left) + " left, at "
          + st.per_item + "s each" : "")
      + (st.phase === "drafting"
         ? ". Each one is a billed model call, and any already drafted today "
           + "costs nothing again." : ".") + "</p>";
  }
  if (st.waiting)
    h += '<p class="figwhy">Next one goes out in ' + st.waiting + "s.</p>";
  if (st.note) h += '<p class="figwhy">' + esc(st.note) + "</p>";
  h += bulkMoney(st.cost);

  /* Drawn whenever there is something to send and nothing in flight, not
     only in "ready". A stopped run is the same reviewed list with a
     different label on it, and hiding the bar there left no way to send
     the drafts already paid for. */
  if (!bulkRunning(st) && bulkSendable(st).length) {
    var ok = bulkSendable(st).length;
    var mid = gapMid(BULK_GAP);
    var avg = mid * Math.max(0, ok - 1);
    h += '<div class="figbar"><button class="btn tiny primary" id="bulknow">'
      + "Send all " + fmt(ok) + " now</button>"
      + '<button class="btn tiny" id="bulkspaced">Send one at a time</button>'
      + (function () {
          /* Only the ones the vault actually backed. A row with no score is
             not counted as confident: unknown is not high. */
          var conf = bulkSendable(st).filter(function (i) {
            return bulkConfOf(i) >= BULK_CONF_FLOOR;
          }).length;
          /* Drawn even at zero, with the button disabled. Hiding it when
             nothing clears the floor hid the only control that can lower
             the floor, which is the one moment you need it. */
          var mins = gapMid(BULK_GAP) * Math.max(0, conf - 1);
          return '<span class="conffloor"><label for="bulkfloor">at or above</label>'
            + '<input type="number" id="bulkfloor" min="0" max="100" step="5" value="'
            + BULK_CONF_FLOOR + '" aria-label="Confidence floor to send at">'
            + "<span>%</span></span>"
            + '<button class="btn tiny bulkconfsend" id="bulkconfnow"'
            + (conf ? "" : " disabled") + ">Send the "
            + '<b id="bulkconfn">' + fmt(conf) + "</b> above "
            + '<b id="bulkconfpct">' + BULK_CONF_FLOOR + "</b>%</button>"
            + '<span class="note" id="bulkconfeta">spaced, about '
            + bulkSpan(mins) + "</span>";
        })()
      + '<span class="figlab">gap</span><span class="seg" role="group">'
      + Object.keys(BULK_GAPS).map(function (g) {
          return '<button type="button" class="bulkgap" data-gap="' + esc(g)
            + '" aria-pressed="' + (BULK_GAP === g) + '">' + esc(gapLabel(g))
            + "</button>";
        }).join("")
      + "</span>"
      + '<span class="note" id="bulkspacedeta">spaced takes about '
      + bulkSpan(avg) + "</span>"
      + '<span class="note bigmsg" id="bulksendmsg"></span></div>';
  }
  if (bulkRunning(st))
    h += '<div class="figbar"><button class="btn tiny" id="bulkstop">Stop</button></div>';

  /* Filtering hides rows rather than dropping them, so an edit typed into
     a row you then filter away still travels with the send. */
  var bands = [["all", "all"], ["high", BULK_CONF_FLOOR + "% and up"],
               ["mid", "60 to " + (BULK_CONF_FLOOR - 1) + "%"],
               ["low", "under 60%"], ["none", "not drafted yet"]];
  var anyConf = (st.items || []).some(function (i) { return bulkConfOf(i); });
  if (anyConf) {
    h += '<div class="figbar"><span class="figlab">confidence</span>'
      + '<span class="seg" role="group">'
      + bands.map(function (b) {
          var n = (st.items || []).filter(function (i) {
            return bulkInBand(i, b[0]); }).length;
          return '<button type="button" class="bulkband" data-band="' + b[0]
            + '" aria-pressed="' + (BULK_CONF_BAND === b[0]) + '">'
            + esc(b[1]) + " " + fmt(n) + "</button>";
        }).join("")
      + "</span></div>";
  }

  h += '<div class="bulklist">';
  st.items.forEach(function (it) {
    /* A row mid-call keeps its old answer on screen, so without this the
       buttons stay pressable and a second click starts a second billed
       call over the top of the first. */
    var busyRow = it.state === "drafting" || it.state === "polishing";
    var inflight = busyRow ? " disabled" : "";
    var shown = bulkInBand(it, BULK_CONF_BAND);
    h += '<div class="bulkitem" data-id="' + esc(it.id) + '"'
      + (shown ? "" : ' style="display:none"') + ">";
    h += ''
      + '<div class="bulkhead"><span class="slug">' + esc(it.code || "?") + "</span>"
      + '<span class="bulkwho">' + bicon(it.channel, 13) + esc(it.who)
      + (it.date ? ' <span class="note">' + esc(it.date) + "</span>" : "")
      + "</span>"
      + '<span class="bulkst bs-' + esc(it.state) + '">'
      + (it.state === "queued" && st.phase === "sending" ? "waiting its turn"
         : esc(it.state))
      + (it.msg ? " · " + esc(it.msg) : "") + "</span>"
      + bulkConf(it) + "</div>"
      + '<p class="bulkq">' + esc(it.asked) + "</p>"
      + (it.draft || it.state === "drafted"
         ? '<textarea class="bulkdraft" ' + (st.phase === "sending" ? "readonly" : "")
           + ">" + esc(it.draft) + "</textarea>"
           + (it.state === "sent" || it.state === "filed" ? ""
              : '<div class="bulkone">'
                + '<button class="btn tiny bulkpolish"' + inflight
                + ">Polish text</button>"
                /* Same action a waiting row uses. start_ai_job only rejoins
                   a job still running, so this is a fresh read of the vault
                   rather than the cached answer coming back. */
                + '<button class="btn tiny bulkdraft1"' + inflight
                + ">Draft again</button>" + refsField()
                + '<button class="btn tiny bulksend1"' + inflight
                + ">Send this one</button>"
                + (busyRow ? '<span class="note">writing a new one…</span>' : "")
                + '<span class="note b1msg"></span></div>')
         : it.state === "drafting" ? ""
         : '<div class="bulkone"><button class="btn tiny bulkdraft1">'
           + "Draft this one</button>" + refsField()
           + '<span class="note">one call, about US$ 1</span>'
           + '<span class="note b1msg"></span></div>')
      + "</div>";
  });
  /* Keep what you typed. The poll rebuilds this whole card every two
     seconds while the rest of the queue drafts, so an edit made to a
     finished draft was thrown away by the next tick and "Send this one"
     posted the model's original text publicly. The Links card already
     guards its forms this way; the card that posts under your name was the
     one without it.

     Edits win over the server's copy, since the server's copy is what you
     were correcting. */
  var mine = BULK_EDITS;
  var focused = box.contains(document.activeElement) &&
                document.activeElement.classList.contains("bulkdraft")
                ? document.activeElement.closest(".bulkitem").dataset.id : "";
  var caret = focused ? [document.activeElement.selectionStart,
                         document.activeElement.selectionEnd] : null;
  /* The queue scrolls inside .bulklist, not down the page, so replacing
     the card's markup builds a fresh container starting at the top. While
     anything is drafting this render runs every two seconds, which is why
     scrolling down the list kept throwing you back to the first row. */
  var wasList = $(".bulklist", box);
  var listTop = wasList ? wasList.scrollTop : 0;

  box.innerHTML = h + "</div>";
  /* Sized to what is in it rather than to a number picked once. These
     replies run from two lines to five paragraphs, and a fixed height is
     either wasted space or a box you have to scroll inside to read the
     answer you are about to publish. The cap is there so one very long
     draft does not push every other row off the screen; past it the box
     scrolls as before. Only rows on screen: an offscreen textarea reports
     a scrollHeight of zero and would collapse to the floor. */
  $$(".bulkdraft").forEach(function (t) {
    if (t.offsetParent === null) return;
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight + 2, 460) + "px";
  });
  /* After the boxes are sized, not before: the list is short until they
     grow, so a scrollTop set first is clamped to a height that does not
     exist yet and lands near the top anyway. */
  var nowList = $(".bulklist", box);
  if (nowList && listTop) nowList.scrollTop = listTop;

  $$(".bulkitem", box).forEach(function (el) {
    var t = $(".bulkdraft", el);
    if (t && mine[el.dataset.id] !== undefined) t.value = mine[el.dataset.id];
    if (t && el.dataset.id === focused) {
      t.focus();
      if (caret) t.setSelectionRange(caret[0], caret[1]);
    }
  });
}

function bulkTick() {
  bulkPost({ action: "status" }).then(function (st) {
    if (!st.ok) return;
    var busy = bulkBusy(st);
    /* A run mid-flight when the tab opens goes straight to the review:
       the progress is the thing to look at, and the send controls appear
       there the moment it settles. */
    if (busy && !BULK_POLL && BULK_MODE !== "review") bulkMode("review");
    bulkRender(st);
    /* A run started before this tab existed has to be picked up here.
       Without this the one read at load drew a frozen snapshot: the tab
       showed "drafted 1 of 2" for as long as it stayed open, because only
       the buttons ever started the interval. */
    if (busy && !BULK_POLL) BULK_POLL = setInterval(bulkTick, 2000);
    if (!busy && BULK_POLL) { clearInterval(BULK_POLL); BULK_POLL = null; }
  });
}

function bulkWatch() {
  if (BULK_POLL) clearInterval(BULK_POLL);
  BULK_POLL = setInterval(bulkTick, 2000);
  bulkTick();
}

/* One read at load, so a run started before this tab was opened is
   already on screen, and so the idle card explains itself. */
if ($("#bulkbody")) bulkTick();

function bulkEdits() {
  var out = {};
  $$(".bulkitem").forEach(function (el) {
    var t = $(".bulkdraft", el);
    if (t) out[el.dataset.id] = t.value;
  });
  /* A row you edited and then filtered out of view, or that is off screen
     because you are back on the queue, still carries its edit here. */
  Object.keys(BULK_EDITS).forEach(function (id) {
    if (out[id] === undefined) out[id] = BULK_EDITS[id];
  });
  return out;
}

/* Every keystroke in a review draft lands in the persistent map at once, so
   a reload or a mode switch a moment later still has it. */
document.addEventListener("input", function (ev) {
  var t = ev.target;
  if (!t || !t.classList || !t.classList.contains("bulkdraft")) return;
  var it = t.closest(".bulkitem");
  if (!it) return;
  if (t.value !== t.defaultValue) BULK_EDITS[it.dataset.id] = t.value;
  else delete BULK_EDITS[it.dataset.id];
  bulkEditsSave();
});

document.addEventListener("click", function (ev) {
  if (ev.target.closest("#bulkrun")) {
    var sys = $("#sysSel").value;
    if (!sys || sys === "all" || sys === "-") {
      $("#bulkmsg").textContent =
        "pick one system in the filter first; drafting runs a system at a time";
      return;
    }
    $("#bulkmsg").textContent = "";
    bulkPost({ action: "draft", system: sys }).then(function (r) {
      if (!r.ok) { $("#bulkmsg").textContent = r.error; return; }
      bulkMode("review");
      bulkWatch();
    });
    return;
  }
  if (ev.target.closest("#bulkreview")) { bulkMode("review"); return; }
  if (ev.target.closest("#bulkback")) { bulkMode("queue"); return; }
  if (ev.target.closest("#bulkstop")) {
    bulkPost({ action: "stop" }).then(bulkTick);
    return;
  }
  var g = ev.target.closest(".bulkgap");
  if (g) {
    BULK_GAP = g.dataset.gap;
    $$(".bulkgap").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.gap === BULK_GAP)); });
    var whole = LAST_BULK ? bulkSendable(LAST_BULK).length : 0;
    var eta = $("#bulkspacedeta");
    if (eta) eta.textContent = "spaced takes about "
      + bulkSpan(gapMid(BULK_GAP) * Math.max(0, whole - 1));
    bulkSyncFloor();
    return;
  }

  var d1 = ev.target.closest(".bulkdraft1");
  if (d1) {
    var dit = d1.closest(".bulkitem");
    var dmsg = $(".b1msg", dit);
    askContext($(".bulkq", dit).textContent, function (note) {
      dmsg.textContent = "writing… about two minutes";
      /* Left standing rather than cleared on success. Clearing it was the
         only thing on the row that had changed: an already drafted row
         keeps its old text and its buttons while the new one is written,
         so wiping this made a working two-minute call look like a dead
         button. The poll replaces it when the answer lands. */
      bulkPost({ action: "draft_one", id: dit.dataset.id,
                 extra: draftNote(dit, note) })
        .then(function (r) {
          if (!r.ok) { dmsg.textContent = r.error; return; }
          bulkWatch();
        });
    });
    return;
  }

  var pol = ev.target.closest(".bulkpolish");
  if (pol) {
    var pit = pol.closest(".bulkitem");
    var cur = $(".bulkdraft", pit).value;
    var pmsg = $(".b1msg", pit);
    /* The same dialog the draft button uses, so there is one place that
       asks for words. What it sends is whatever is in the box right now,
       not the server's copy: you may have edited it before deciding it
       needed one more change. */
    askPolish(cur, function (instruction) {
      if (!instruction) return;
      pmsg.textContent = "polishing...";
      bulkPost({ action: "polish", id: pit.dataset.id, text: cur,
                 instruction: instruction })
        .then(function (r) {
          if (!r.ok) {
            pmsg.textContent = r.error;
            /* The page kept its render after a run settled, because the
               poll stops then; a restart or a new run since left every id
               on screen pointing at nothing. Redraw rather than leave a
               dead button beside an explanation nobody can act on. */
            if (r.code === "stale") bulkTick();
            return;
          }
          pmsg.textContent = "";
          bulkWatch();
        });
    });
    return;
  }

  var one = ev.target.closest(".bulksend1");
  if (one) {
    var item = one.closest(".bulkitem");
    var txt = $(".bulkdraft", item).value.trim();
    var m1 = $(".b1msg", item);
    if (!confirm("Send this reply publicly? It cannot be taken back.")) return;
    m1.textContent = "sending…";
    one.disabled = true;
    bulkPost({ action: "send_one", id: item.dataset.id, text: txt })
      .then(function (r) {
        m1.textContent = r.ok ? "sent" : r.error;
        one.disabled = false;
        bulkTick();
      });
    return;
  }

  var band = ev.target.closest(".bulkband");
  if (band) {
    BULK_CONF_BAND = band.dataset.band;
    $$(".bulkband").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.band === BULK_CONF_BAND)); });
    bulkSyncFloor();
    return;
  }

  var now = ev.target.closest("#bulknow"), spaced = ev.target.closest("#bulkspaced");
  var confOnly = ev.target.closest("#bulkconfnow");
  if (now || spaced || confOnly) {
    /* The confident subset goes out spaced too. Seventeen replies landing
       in the same second reads as a script whoever receives them, which is
       the thing the gap exists to avoid. */
    var mode = (spaced || confOnly) ? "spaced" : "now";
    var floor = confOnly ? BULK_CONF_FLOOR : 0;
    /* Counted off the same rule the server will apply, so the number in the
       confirmation is the number that goes out. */
    var count = confOnly
      ? (LAST_BULK ? bulkSendable(LAST_BULK).filter(function (i) {
          return bulkConfOf(i) >= BULK_CONF_FLOOR; }).length : 0)
      : $$(".bulkdraft").filter(function (t) { return t.value.trim(); }).length;
    var words = gapWords(BULK_GAP);
    if (!confirm("Send " + count + " public replies"
                 + (confOnly ? " scored " + BULK_CONF_FLOOR + "% or higher" : "")
                 + (spaced ? ", " + words : ", all at once")
                 + "? This posts under your name and cannot be taken back.")) return;
    var sm = $("#bulksendmsg");
    if (sm) sm.textContent = "starting...";
    bulkPost({ action: "send", mode: mode, edits: bulkEdits(), gap: BULK_GAP,
               min_conf: floor })
      .then(function (r) {
        if (!r.ok) {
          /* Beside the button that was pressed. This landed next to the
             system picker at the top of the card, far above the click, so a
             refused send looked like nothing happening at all. */
          if (sm) sm.textContent = "not sent: " + r.error;
          $("#bulkmsg").textContent = r.error;
          return;
        }
        if (sm) sm.textContent = "";
        bulkWatch();
      })
      .catch(function (e) { if (sm) sm.textContent = "not sent: " + e.message; });
  }
});

/* The reply box can be dragged in both directions now, but dragging past
   the card only overlaps what is beside it. This widens the card itself,
   through the same expand the card already carries, so the box has room
   rather than spilling over its neighbour. */
document.addEventListener("click", function (ev) {
  var w = ev.target.closest(".qwide");
  if (!w) return;
  var card = w.closest(".card");
  if (!card) return;
  var ex = card.querySelector(".expand");
  if (ex && !ex.hidden) {
    ex.click();
    w.textContent = card.classList.contains("wide") ? "narrower" : "wider";
    return;
  }
  /* A card that already fills its row cannot get wider, so widen the box
     itself instead of toggling a class with nothing to do. Reporting
     "narrower" while nothing moved was the actual complaint. */
  var box = card.querySelector(".qbox");
  var on = card.classList.toggle("fullrow");
  if (box) box.style.width = on ? "100%" : "";
  w.textContent = on ? "taller" : "wider";
  w.title = on ? "Back to the normal height" : "More room to write";
});


/* ---- a word before the draft ----
   Optional on purpose: Enter or the button with an empty box drafts exactly
   as before. What you type here is your own, so the prompt files it as the
   owner speaking, separate from the public comment, which stays untrusted. */
/* Asking what to change, on top of the draft it will change. Built from
   askContext so the two dialogs behave identically: Escape cancels, Tab
   stays inside, focus comes back. */
function askPolish(draft, onGo) {
  askContext(draft, onGo, {
    title: "What should change?",
    hint: "It edits this reply rather than writing a new one, so anything "
        + "you do not mention comes back unchanged.",
    placeholder: "shorter, and add the link to the devlog",
    go: "Polish",
    skip: "",
  });
}

function askContext(question, onGo, opt) {
  opt = opt || {};
  var back = document.createElement("div");
  back.className = "modalback";
  back.innerHTML =
    '<div class="modal" role="dialog" aria-modal="true" aria-label="Context for this draft">'
    + "<h3>" + esc(opt.title || "Anything Claude should know?") + "</h3>"
    + '<p class="note">' + esc(opt.hint || "Optional. Leave it empty and it "
        + "drafts from the vault alone, exactly as before.") + "</p>"
    + '<blockquote class="mq">' + esc(question) + "</blockquote>"
    + '<textarea class="mctx" rows="4" placeholder="' + esc(opt.placeholder
        || "e.g. they are on 5.6 already, do not tell them to upgrade")
    + '"></textarea>'
    + '<div class="mbtns"><button class="btn tiny primary mgo">'
    + esc(opt.go || "Draft") + "</button>"
    + (opt.skip === "" ? ""
       : '<button class="btn tiny mskip">' + esc(opt.skip
           || "Draft without a note") + "</button>")
    + '<button class="btn tiny mcancel">Cancel</button></div></div>';
  /* Where the focus was, so it can be given back. A dialog that drops
     focus on the body leaves a keyboard user at the top of the document,
     with the row they were working on lost somewhere below. */
  var prev = document.activeElement;
  document.body.appendChild(back);
  var box = back.querySelector(".mctx");
  box.focus();

  function close() {
    document.removeEventListener("keydown", onKey, true);
    back.remove();
    if (prev && prev.isConnected && prev.focus) prev.focus();
  }
  function go(text) { close(); onGo(text); }
  function onKey(ev) {
    if (ev.key === "Escape") { ev.preventDefault(); close(); }
    /* Tab stays inside. Without this it walked out of the dialog into the
       page behind it, which is still there and still clickable, so the
       "modal" was modal only to the mouse. */
    if (ev.key === "Tab") {
      var can = [].slice.call(back.querySelectorAll("textarea, button"));
      if (!can.length) return;
      var first = can[0], last = can[can.length - 1];
      if (ev.shiftKey && document.activeElement === first) {
        ev.preventDefault(); last.focus();
      } else if (!ev.shiftKey && document.activeElement === last) {
        ev.preventDefault(); first.focus();
      }
    }
    /* Ctrl+Enter sends, plain Enter does not: a note is often two lines and
       losing the second one to a stray Return would be worse than a click. */
    if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
      ev.preventDefault();
      go(box.value.trim());
    }
  }
  document.addEventListener("keydown", onKey, true);
  back.querySelector(".mgo").addEventListener("click", function () { go(box.value.trim()); });
  var skip = back.querySelector(".mskip");
  if (skip) skip.addEventListener("click", function () { go(""); });
  back.querySelector(".mcancel").addEventListener("click", close);
  back.addEventListener("click", function (ev) { if (ev.target === back) close(); });
}

/* Recheck reads the vault again and swaps this card's rows, without the
   full-page reload the top Update triggers: what is owed changes while you
   work, and losing your scroll to see it is a poor trade.

   It re-reads. It does not re-collect: Discord and YouTube arrive on their
   own schedules, so the age of the newest question is what the note under
   the button reports, since a card that is fresh from stale sources is the
   thing worth not implying. */
document.addEventListener("click", function (ev) {
  var b = ev.target.closest("#reneeds");
  if (!b) return;
  if (!LIVE) { toast("Static file: this needs the live server.", "bad"); return; }
  b.disabled = true;
  b.classList.add("spin");
  fetch("/needs", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Panel-Token": PANEL_TOKEN },
    body: "{}"
  })
    .then(function (r) { return r.json(); })
    .then(function (j) {
      b.disabled = false;
      b.classList.remove("spin");
      if (!j.ok) { toast("Could not recheck: " + (j.error || "?"), "bad"); return; }
      var box = $("#needsbody");
      if (box) box.innerHTML = j.html;
      toast(j.changed ? "Rechecked, and it changed." : "Rechecked, nothing new.",
            j.changed ? "info" : "ok");
    })
    .catch(function (e) {
      b.disabled = false;
      b.classList.remove("spin");
      toast("Could not reach the panel server.", "bad");
    });
});

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
/* The bell opens a feed of what arrived since the last build and a line per
   source saying when it last synced, rather than jumping straight to the
   list. "See all waiting" inside it keeps the old jump one click away. */
function acAgeH(h) {
  if (h === null || h === undefined) return "no sync yet";
  if (h < 1) return "just now";
  if (h < 24) return Math.round(h) + "h ago";
  return Math.round(h / 24) + "d ago";
}
function acDot(h) {
  if (h === null || h === undefined) return "stale";
  if (h < 2) return "";
  if (h < 24) return "warn";
  return "stale";
}
function acWhen(at) {
  /* "YYYY-MM-DD HH:MM:SS" -> a timestamp ageText understands. The space
     form is parsed unevenly across browsers, so make it ISO first. */
  var ms = Date.parse((at || "").replace(" ", "T"));
  return isNaN(ms) ? esc(at || "") : ageText(ms / 1000);
}
function renderActivity() {
  var box = $("#activitybox");
  if (!box) return;
  var A = (typeof ACTIVITY === "object" && ACTIVITY) || {};
  var sources = A.sources || [], events = A.events || [];
  var h = '<div class="achead"><b>Recent activity</b>'
    + '<span class="acbuilt">rebuilt ' + acWhen(A.built) + "</span></div>";

  h += '<div class="acsync">';
  sources.forEach(function (s) {
    var count = s.count === null || s.count === undefined ? ""
      : fmt(s.count) + (s.open ? " · " + fmt(s.open) + " open" : "");
    h += '<div class="acsrc"><span class="acname">'
      + '<span class="acdot ' + acDot(s.age_h) + '"></span>'
      + bicon(s.name.toLowerCase(), 13) + esc(s.name) + "</span>"
      + '<span class="account">' + count + "</span>"
      + '<span class="acwhen" title="' + esc(s.every) + '">'
      + esc(acAgeH(s.age_h)) + "</span></div>";
  });
  h += "</div>";

  if (!events.length) {
    h += '<div class="acempty">Nothing new since the last rebuild. '
      + "New Discord and YouTube questions land here as they arrive.</div>";
  } else {
    h += '<div class="aclist">';
    events.forEach(function (e) {
      var sys = e.system ? " · " + esc(e.system) : "";
      h += '<div class="acitem" data-id="' + esc(e.id) + '">'
        + '<span class="acav">' + bicon((e.channel || "").toLowerCase(), 15) + "</span>"
        + '<div class="acbody"><div class="acmeta">'
        + '<span class="acwho">' + esc(e.who || "someone") + "</span>"
        + sys + " · " + acWhen(e.at) + "</div>"
        + '<div class="acq">' + esc(e.text || "") + "</div></div></div>";
    });
    h += "</div>";
  }
  h += '<div class="acfoot"><button class="btn tiny" id="acseeall">'
    + "See all waiting \\u2192</button></div>";
  box.innerHTML = h;
}
function acClose() {
  var box = $("#activitybox"), b = $("#bellbtn");
  if (box) box.classList.add("hide");
  if (b) b.setAttribute("aria-expanded", "false");
}
$("#bellbtn").addEventListener("click", function (ev) {
  ev.stopPropagation();
  var box = $("#activitybox");
  if (!box) { goView("questions"); return; }
  var open = box.classList.contains("hide");
  if (open) { renderActivity(); box.classList.remove("hide"); }
  else { box.classList.add("hide"); }
  this.setAttribute("aria-expanded", String(open));
});
$("#activitybox").addEventListener("click", function (ev) {
  ev.stopPropagation();
  if (ev.target.closest("#acseeall")) { acClose(); goView("questions"); return; }
  var item = ev.target.closest(".acitem");
  if (!item) return;
  acClose();
  goView("questions");
  var row = $('.qrow[data-id="' + (window.CSS && CSS.escape
    ? CSS.escape(item.dataset.id) : item.dataset.id) + '"]');
  if (row) {
    row.scrollIntoView({ block: "center" });
    row.classList.add("flashcard");
    setTimeout(function () { row.classList.remove("flashcard"); }, 1400);
  }
});
/* ---- sparkline fill-up: replayable on demand ---- */
function sparkReplay(scope) {
  $$(".spark", scope || document).forEach(function (sv) {
    sv.classList.remove("go");
    void sv.getBoundingClientRect().width;   /* reflow restarts the animation */
    sv.classList.add("go");
  });
}
document.addEventListener("click", function (ev) {
  var tile = ev.target.closest(".tile");
  if (tile) sparkReplay(tile);
});

/* ---- Wingman named tables: filled live so no name is baked into
   panel.html (which the vault carries). ---- */
function wmPill(plan) {
  plan = (plan || "free").toLowerCase();
  var cls = (plan === "premium" || plan === "standard") ? "ok" : "mut";
  return '<span class="pill st-' + cls + '">' + esc(plan) + "</span>";
}
function wmDetail() {
  var top = $("#wm-top"), prem = $("#wm-prem");
  if (!top || !prem || !LIVE) return;
  fetch("/wingman-detail.json", { cache: "no-store" })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d || !d.ok) return;
      var NL = "";
      top.innerHTML = (d.top_users || []).map(function (u) {
        return '<tr><td><span class="nm">' + esc(u.name || "—")
          + "</span></td><td>" + wmPill(u.plan) + '</td><td class="num">'
          + fmt(u.prompts || 0) + "</td></tr>";
      }).join(NL) || '<tr><td colspan="3" class="note">none</td></tr>';
      prem.innerHTML = (d.premium || []).map(function (p) {
        return '<tr><td><span class="nm">' + esc(p.name || "—")
          + "</span></td><td>" + wmPill(p.plan) + '</td><td class="num">'
          + fmt(p.days || 0) + "d</td></tr>";
      }).join(NL) || '<tr><td colspan="3" class="note">none</td></tr>';
    })
    .catch(function () {});
}

/* ---- Email screen: one audience, one message, sent server-side ---- */
var EM_SEG = "", EM_COUNT = 0;
function emBodyHtml() {
  var raw = $("#embody").value.trim();
  if (!raw) return "";
  if (raw.indexOf("<") !== -1) return raw;   /* already HTML */
  /* Built from the char code: a backslash-n written here lives inside a
     Python string and becomes a real newline in the page, snapping the
     regex in half. That exact break is what the build gate just refused
     to ship. */
  var NL = String.fromCharCode(10);
  return raw.split(new RegExp(NL + "{2,}")).map(function (p) {
    return "<p>" + esc(p).split(NL).join("<br>") + "</p>";
  }).join("");
}
function emSyncButton() {
  var b = $("#emsend");
  if (!b) return;
  if (!EM_SEG) { b.disabled = true; b.textContent = "Pick an audience first"; return; }
  if (EM_COUNT <= 0) {
    b.disabled = true; b.textContent = "No one in this audience"; return;
  }
  b.disabled = false;
  b.textContent = "Send to " + fmt(EM_COUNT) + " people";
}
document.addEventListener("click", function (ev) {
  var aud = ev.target.closest(".em-aud");
  if (aud) {
    EM_SEG = aud.dataset.seg;
    EM_COUNT = +aud.dataset.count || 0;
    $$(".em-aud").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b === aud)); });
    sparkReplay(aud);
    emSyncButton();
    return;
  }
  if (ev.target.closest("#emtest")) {
    var to = $("#emtestto").value.trim();
    var html = emBodyHtml(), subj = $("#emsubj").value.trim();
    var m = $("#emmsg");
    if (!to) { m.textContent = "give the test an address"; return; }
    if (!subj || !html) { m.textContent = "write the subject and the message first"; return; }
    m.textContent = "sending the test\u2026";
    fetch("/email", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "send", segment: "test", to: to,
                             subject: subj, html: html }) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        m.textContent = d.ok ? "test sent to " + to : "not sent: " + (d.error || "");
      })
      .catch(function (e) { m.textContent = "not sent: " + e.message; });
    return;
  }
  if (ev.target.closest("#emsend")) {
    var subj2 = $("#emsubj").value.trim(), html2 = emBodyHtml();
    var m2 = $("#emmsg");
    if (!EM_SEG) return;
    if (!subj2 || !html2) { m2.textContent = "write the subject and the message first"; return; }
    if (!confirm('Send "' + subj2 + '" to ' + fmt(EM_COUNT)
                 + " people? Each gets an individual email from Resend. "
                 + "This cannot be taken back.")) return;
    m2.textContent = "sending to " + fmt(EM_COUNT) + " people\u2026";
    var btn = $("#emsend"); btn.disabled = true;
    fetch("/email", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "send", segment: EM_SEG, expect: EM_COUNT,
                             subject: subj2, html: html2 }) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        btn.disabled = false;
        if (d.ok) { m2.textContent = "sent to " + fmt(d.sent) + " people"; }
        else {
          var msg = "problem: " + (d.error || "");
          var extra = [];
          if (d.sent) extra.push(fmt(d.sent) + " did go out");
          if (d.unknown) extra.push(fmt(d.unknown) + " unknown, may have sent");
          if (d.not_attempted) extra.push(fmt(d.not_attempted) + " not attempted");
          if (extra.length) msg += " (" + extra.join(", ") + ")";
          m2.textContent = msg;
        }
      })
      .catch(function (e) { btn.disabled = false; m2.textContent = "failed: " + e.message; });
    return;
  }
});

document.addEventListener("click", function () { acClose(); });
document.addEventListener("keydown", function (ev) {
  if (ev.key === "Escape") acClose();
});

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
/* The hourly clicks go through the same engine as every other chart, so
   they get an axis, labelled hours, a trend and a projection. The old one
   was a 240-unit viewBox stretched to the card's full width with
   preserveAspectRatio none, which squashed every bar by whatever the card
   happened to measure and left no scale to read them against. */
function ltChart(hc) {
  if (!hc.length) return '<div class="empty">no hourly data</div>';
  CHARTS.clicks = hc.map(function (p) { return { m: p.hour, cnt: p.cnt }; });
  return '<div class="fig" data-chart="clicks"></div>';
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
    h += '<div class="mk"><div class="v">' + fmt(kv[0]) + '</div><div class="l">' + kv[1] + "</div>"
      + (LTSPARKS[kv[1]] || "") + "</div>";
  });
  if (s.top_country)
    h += '<div class="mk"><div class="v">' + esc(s.top_country.country)
      + '</div><div class="l">top country \\u00b7 ' + fmt(s.top_country.cnt) + " clicks</div></div>";
  h += '</div><div class="ltgrid"><div>';
  h += '<p class="lsub">Clicks per hour, last 24h</p>' + ltChart(s.hourly_chart || []);
  var links = d.links || [];
  h += ltWhere(d);
  h += ltComposer();
  h += '<p class="lsub">All links</p>'
    + '<input class="lfind" placeholder="filter by slug or destination" aria-label="Filter links">'
    + '<div class="scroll"><table><thead><tr>'
    + "<th>Link</th><th>1h</th><th>7d</th><th>Total</th><th></th></tr></thead><tbody>";
  links.forEach(function (l) {
    var host = "";
    try { host = new URL(l.url).host; } catch (e) {}
    var find = (l.prefix + "/" + l.slug + " " + l.url).toLowerCase();
    h += '<tr class="lkrow" tabindex="0" aria-expanded="false" data-prefix="'
      + esc(l.prefix) + '" data-slug="' + esc(l.slug) + '" data-find="' + esc(find) + '">'
      + '<td><span class="slug">/' + esc(l.prefix) + "/" + esc(l.slug)
      + '</span><br><span class="host">' + esc(host) + "</span></td>"
      + '<td class="num">' + fmt(l.clicks_1h) + "</td>"
      + '<td class="num">' + fmt(l.clicks_7d) + "</td>"
      + '<td class="num">' + fmt(l.total_clicks) + "</td>"
      /* The destination has always been editable, inside the row that
         opens when you click it. Nothing on the row said so, so it read as
         a table you could only copy from. */
      + '<td class="num"><button class="btn tiny lkedit">edit</button>'
      + '<button class="btn tiny" data-copy="'
      + esc(shortUrl(l.prefix, l.slug)) + '">copy</button></td></tr>'
      + '<tr class="lkdet"><td colspan="5"><div class="ldet"></div></td></tr>';
  });
  h += "</tbody>";
  var t1 = 0, t7 = 0, tt = 0;
  links.forEach(function (l) { t1 += l.clicks_1h || 0; t7 += l.clicks_7d || 0; tt += l.total_clicks || 0; });
  h += "<tfoot><tr><td>all " + fmt(links.length) + " links</td><td>" + fmt(t1)
    + "</td><td>" + fmt(t7) + "</td><td>" + fmt(tt) + "</td><td></td></tr></tfoot></table></div>";
  h += "</div><div>";
  h += '<p class="lsub">Recent clicks</p>';
  var rc = (s.recent_clicks || []).slice(0, 8);
  if (!rc.length) h += '<div class="empty">none yet</div>';
  rc.forEach(function (c) {
    h += '<div class="lrow"><span class="slug">/' + esc(c.prefix) + "/" + esc(c.slug)
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
      h += '<div class="lrow"><span>' + esc(r[0]) + '</span><span class="n">' + r[1] + "</span></div>";
    });
  }
  h += "</div></div>";
  /* Not while you are typing in it. The card refreshes every 60 seconds
     and used to replace the whole body, so a destination half typed into
     the new-link box, or an edited "Points at", vanished mid-sentence. */
  var live = body.contains(document.activeElement) &&
             /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  var dirty = $$(".lnu, .lns, .lurl", body).some(function (el) {
    return el.value && el.value !== el.defaultValue;
  });
  if (live || dirty) {
    var st2 = $("#lt-state");
    if (st2) st2.textContent = "paused while you are editing";
    return;
  }
  body.innerHTML = h;
  if (typeof sparkReplay === "function") sparkReplay(body);
  /* The figure is rebuilt on every refresh, so it has to be drawn again
     here: chMountExpand ran once at boot, long before this HTML existed. */
  $$(".fig", body).forEach(chDraw);
}
function scheduleLt() {
  setTimeout(loadLinks, ltFails >= 3 ? 300000 : 60000);
}
function loadLinks() {
  if (!LIVE) { $("#lt-state").textContent = "needs the live watcher (panel.py --watch)"; return; }
  /* The catch is split on purpose. It used to wrap the render too, so any
     exception while drawing this card reported as "local server
     unreachable" and sent you looking at the network for a bug in the
     page. A drawing failure now says so, and says which one. */
  fetch("/links.json", { cache: "no-store" })
    .then(function (r) { return r.json(); })
    .catch(function () {
      ltFails++;
      $("#lt-state").textContent = "local server unreachable";
      scheduleLt();
      return null;
    })
    .then(function (d) {
      if (!d) return;
      ltFails = d.ok ? 0 : ltFails + 1;
      try {
        renderLinks(d);
      } catch (e) {
        $("#lt-state").textContent = "could not draw this card: " + e.message;
        if (window.console) console.error("renderLinks", e);
      }
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
    ready to answer.
    """
    hist = d.get("history") or []
    qs = d["questions"]
    open_qs = [q for q in qs if q["status"] in ("no-source", "escalated")]

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
        # Counts questions, so it says questions. It said "People waiting"
        # over len(open_qs), while the card below said "questions still
        # open" over a headcount: the two labels were swapped, and the
        # headcount now rides along here where it belongs.
        ("hero", "chat", "c-blue", "Questions waiting for an answer",
         _fmt(len(open_qs)),
         f"from {_fmt(sum(1 for p in d['people'] if p['open']))} people, "
         f"nobody has replied yet",
         delta("open", False), _spark(series("open"), "a", "var(--accent)")),
        # Three tiles used to sit here and were dropped as noise. "Asked for
        # you by name" counted one question in fifteen hundred. "You can
        # answer these today" read 754 off a vault-match score nobody acts
        # on per tile. "Waiting the longest" showed a date from 2022, which
        # is a fact about the archive rather than about today; the age
        # filter on the queue answers that better and can be narrowed.
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
            f'Needs attention'
            f'<button class="btn tiny reneeds" id="reneeds" type="button">'
            f'recheck</button></h2>'
            f'<div id="needsbody">{rows}</div></section>')


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

    # Everyone in `people` has written something; only some of it was a
    # question. The label says asked, so the count means asked.
    askers = sum(1 for p in people if p["asked"])
    # Said without this, the number just drops by 158 one afternoon and
    # reads as people lost rather than people recounted.
    only_praise = sum(1 for p in people if not p["asked"] and p["praise"])
    rows = line("people who have asked something", _fmt(askers),
                f"{_fmt(only_praise)} more only left praise" if only_praise else "")
    if pat:
        rows += line("paying right now", _fmt(pat.get("paying", 0)),
                     f"of {_fmt(pat.get('total', 0))} on Patreon")
        rows += line("coming in monthly",
                     f"US$ {pat.get('monthly_cents', 0) / 100:,.0f}")
        rows += line("paid over the years",
                     f"US$ {pat.get('lifetime_cents', 0) / 100:,.0f}")
    # waiting is a headcount, not a question count.
    rows += line("people with an open question", _fmt(waiting))
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



def _chart_payload(d: dict) -> dict:
    """Every chart's full monthly history, for the browser to window.

    Questions are counted by the month they were asked and split by their
    state today, which is the honest reading: nothing records the day an
    answer was written, so this is not "answered that month".
    """
    pat = d.get("patreon") or {}
    joins = pat.get("joins") or []
    qm: dict[str, dict] = {}
    for q in d.get("questions") or []:
        mo = (q.get("date") or "")[:7]
        if len(mo) != 7:
            continue
        row = qm.setdefault(mo, {"m": mo, "answered": 0, "waiting": 0})
        row["answered" if q["status"] == "answered" else "waiting"] += 1
    months = sorted(qm)
    if months:  # months with no question at all must still occupy the axis
        y, mth = int(months[0][:4]), int(months[0][5:7])
        while f"{y:04d}-{mth:02d}" <= months[-1]:
            qm.setdefault(f"{y:04d}-{mth:02d}",
                          {"m": f"{y:04d}-{mth:02d}", "answered": 0, "waiting": 0})
            mth += 1
            if mth == 13:
                y, mth = y + 1, 1
    return {
        "pledges": [{"m": r["m"], "still": r["still"],
                     "left": r["total"] - r["still"]} for r in joins],
        "cohort": pat.get("cohort") or [],
        "questions": [qm[k] for k in sorted(qm)],
    }


def _fig(name: str, title: str) -> str:
    """The shell a chart is drawn into, with its controls.

    Empty on purpose: the marks, the axis, the trend and the projection are
    all built in the browser, because every control here changes geometry.
    """
    return (f'<p class="chtitle">{escape(title)}</p>'
            f'<div class="fig" data-chart="{escape(name, quote=True)}"></div>')



def _business_screen(d: dict, below: str = "") -> str:
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
        # Payment just failed and Stopped used to be repeated here. They are
        # in the funnel below, where a bar puts them next to the stages they
        # came from, which is the reading this card cannot give.
        + _fig("pledges", "Pledges started each month")
        + _fig("cohort", "When today\'s patrons joined")
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
        + _fig("questions", "Questions per month, and what is still waiting")
        + "</section>")

    return (
        f'<section id="business"><div class="grid2">'
        f'{money}{moving}{conv}{work}</div>'
        f'<p class="note">Patreon read {escape(pat.get("read_at") or "?")}. '
        f'WhatsApp and website sales are not here: nothing in this panel can '
        f'see them yet, so every money figure on this screen is Patreon only.</p>'
        f'{below}'
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


def _age_days(iso: str, today: date) -> int:
    """Days since a question was asked. A missing or malformed date reads
    as ancient rather than as today, so it never sneaks into a recent cut."""
    try:
        y, m, d = (int(x) for x in iso[:10].split("-"))
        return (today - date(y, m, d)).days
    except (ValueError, TypeError):
        return 10 ** 6


def _sort_ts(q: dict) -> int:
    """A millisecond instant to order a row by, finer than its date.

    Discord collects only a day, so a dozen messages from one afternoon all
    tie on date and the newest sort leaves them in file order: the message
    posted last shows up in the middle of the day's block, not at the top,
    which reads as "the latest one never arrived". A Discord message id is a
    snowflake that carries its own creation time, so the exact instant is
    already in hand without collecting anything new. YouTube ids are not
    time ordered, so those fall back to the date at midnight and keep the
    behaviour they had.
    """
    from datetime import datetime as _dt
    src = q.get("id", "")
    if src.startswith("dc:"):
        num = src[3:].split("#", 1)[0]
        if num.isdigit():
            return (int(num) >> 22) + 1420070400000   # Discord epoch, ms
    try:
        y, m, d = (int(x) for x in (q.get("date") or "")[:10].split("-"))
        return int(_dt(y, m, d).timestamp() * 1000)
    except (ValueError, TypeError, OverflowError, OSError):
        return 0


def _filters(questions: list, systems: list) -> str:
    ch_counts: dict[str, int] = {}
    st_counts: dict[str, int] = {}
    for q in questions:
        ch_counts[q["channel"]] = ch_counts.get(q["channel"], 0) + 1
        st_counts[q["status"]] = st_counts.get(q["status"], 0) + 1
    statuses = [s for s in ("no-source", "escalated", "answered", "praise",
                            "out-of-scope", "unknown")
                if s in st_counts]

    sys_counts: dict[str, int] = {}
    sys_names: dict[str, str] = {}
    for q in questions:
        if q["system"] == "-":
            continue
        sys_counts[q["system"]] = sys_counts.get(q["system"], 0) + 1
        sys_names[q["system"]] = q["system_name"]
    # Every system in the catalog, not only the ones asked about. Built
    # from questions alone, a system nobody has asked about could not be
    # picked at all, so its empty queue could not even be opened and the
    # filter looked like it had forgotten a product that is on sale. The
    # rule moved here from the bulk card when its picker and this one
    # became the same control.
    for sy in systems or []:
        if sy.get("slug"):
            sys_counts.setdefault(sy["slug"], 0)
            sys_names.setdefault(sy["slug"], sy.get("name") or sy["slug"])

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
    # The counts are of open questions, not of everything in the window:
    # the reason to cut by date is to see how much of the queue is this
    # month's work rather than a backfill's archaeology.
    parts.append('<span class="fsep"></span>')
    parts.append('<span class="fchip on" data-k="age" data-v="all" aria-pressed="true" '
                 'title="Every question, however old">Any time</span>')
    today = date.today()
    for key, days, label in (("30d", 30, "30 days"), ("90d", 90, "90 days"),
                             ("12m", 365, "12 months")):
        cnt = sum(1 for q in questions
                  if q["status"] in ("no-source", "escalated")
                  and 0 <= _age_days(q.get("date", ""), today) <= days)
        if not cnt:
            continue
        parts.append(f'<span class="fchip" data-k="age" data-v="{key}" aria-pressed="false" '
                     f'title="Asked in the last {label}, still open">'
                     f'{label} <span class="fc-n">{_fmt(cnt)}</span></span>')
    older = sum(1 for q in questions
                if q["status"] in ("no-source", "escalated")
                and _age_days(q.get("date", ""), today) > 365)
    if older:
        parts.append('<span class="fchip" data-k="age" data-v="old" aria-pressed="false" '
                     'title="Open for more than a year. Mostly people who have '
                     'long since moved on, kept reachable rather than hidden">'
                     f'over a year <span class="fc-n">{_fmt(older)}</span></span>')
    parts.append('<span class="fsep"></span>')
    parts.append('<select id="sysSel" class="fchip" aria-label="Filter by system">'
                 '<option value="all">All systems</option>'
                 '<option value="-">catalog wide</option>')
    for slug in sorted(sys_counts,
                       key=lambda s: (-sys_counts[s], sys_names[s].lower())):
        parts.append(f'<option value="{escape(slug, quote=True)}">'
                     f'{escape(sys_names[slug])} ({sys_counts[slug]})</option>')
    parts.append('</select>')
    parts.append('<button class="fclear" id="fclear">clear filters</button>')
    # Export lives with the filters because it exports what they describe.
    parts.append(
        '<button class="fexport" id="expbtn" aria-expanded="false">''<svg width="13" height="13" viewBox="0 0 24 24" fill="none" ''stroke="currentColor" stroke-width="2" stroke-linecap="round" ''stroke-linejoin="round" aria-hidden="true">''<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>''<polyline points="7 10 12 15 17 10"/>''<line x1="12" y1="15" x2="12" y2="3"/></svg>Export</button>'
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
            f' data-ts="{_sort_ts(q)}"'
            f' data-who="{escape(q["who"].lower(), quote=True)}"'
            f' data-df="{escape(q.get("difficulty", ""), quote=True)}"'
            f' data-cov="{q.get("coverage", 0)}"></tr>'
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
        f'<span class="cnt">showing <span id="qcount"></span>'
        f'<span id="qnarrow" hidden></span> &middot; '
        f'j/k navigate &middot; n next open &middot; Enter to answer</span></h2>'
        f'{_filters(d["questions"], d.get("systems") or [])}'
        # The bulk run lives here, with the questions, because the two
        # cards were the same list twice: pick the system in the filter,
        # press the button, and the review replaces the table until you
        # come back.
        f'<div class="figbar" id="bulkbar">'
        f'<button class="btn tiny primary" id="bulkrun" title="Draft an '
        f'answer for every question still waiting under the system picked '
        f'in the filter. Nothing is sent until you have read them.">'
        f'Draft answers</button>'
        f'<span class="note" id="bulkmsg"></span></div>'
        f'<div id="bulkbody"></div>'
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
        f'<section class="card" id="people">'
        f'<h2><span class="he">👥</span>Customers'
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


def _links_card(d: dict) -> str:
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
    # The Drive folder the export lands in is not mounted, so from this
    # machine nothing delivered and nothing sent look identical. Saying
    # "Nothing to send" there would be a claim about the bot made from a
    # missing drive letter.
    "unknown": ("no-source", "Cannot tell",
                "Google Drive is not mounted here, so the copy the bot "
                "reads cannot be checked from this machine"),
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


def _wingman_users_card(d: dict) -> str:
    """LocoAI/Wingman accounts: who signed up, who activated, who pays, and
    the email audiences that fall out of that. Reads the Supabase rollup
    collect_wingman.py writes to the private folder (%LOCALAPPDATA%/
    locodev-panel), never the vault; empty and self-explaining until it
    exists."""
    w = d.get("wingman") or {}
    s = w.get("summary") or {}
    if not s:
        return (
            '<section class="card" data-view="business" id="wingman-users">'
            '<h2><span class="he">🪄</span>Wingman accounts</h2>'
            '<p class="note">No account data yet. This reads a Supabase '
            'rollup written by <code>collect_wingman.py</code>. Add '
            'SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, run it once, and the '
            'accounts, activation, premium and email audiences show here.</p>'
            '</section>')

    acc = s.get("accounts", 0) or 0
    gen = s.get("generated", 0) or 0
    never = max(0, acc - gen)
    act = round(gen * 100 / acc) if acc else 0
    prem = s.get("premium", 0) or 0
    conv = round(prem * 100 / acc, 1) if acc else 0

    # The last two carry no trend key: a spark of Cakto subs or emailable
    # count says nothing worth the ink. The first four are the growth story.
    tiles = [
        ("Accounts", _fmt(acc), f'{_fmt(s.get("new_30d", 0))} new in 30 days',
         "wm_acc", "var(--accent)"),
        ("Activated", _fmt(gen), f'{act}% ever generated',
         "wm_gen", "var(--ok)"),
        ("Active in 30d", _fmt(s.get("active_30d", 0)),
         f'{_fmt(s.get("active_7d", 0))} in the last 7', "wm_a30", "var(--info)"),
        ("Premium", _fmt(prem), f'{conv}% of accounts pay',
         "wm_prem", "var(--warn)"),
        ("Cakto subs", _fmt(s.get("cakto_active", 0)), "courses and packs",
         "", ""),
        ("Can email", _fmt(s.get("emailable", 0)), "confirmed address", "", ""),
    ]
    hist = d.get("history") or []

    def _tspark(hk, color):
        # Only points that measured this series; a young or snapshot-skipped
        # history draws fewer points, never a zero. Empty until real data.
        if not hk:
            return ""
        series = [p[hk] for p in hist if hk in p][-60:]
        return _spark(series, f"t{hk}", color, w=340, h=30) if series else ""

    tilehtml = "".join(
        f'<div class="wm-tile"><span class="wm-n">{v}</span>'
        f'<span class="wm-l">{escape(lab)}</span>'
        f'<span class="note">{escape(sub)}</span>{_tspark(hk, color)}</div>'
        for lab, v, sub, hk, color in tiles)

    # The activation gap is the headline number worth acting on.
    gap = (f'<p class="wm-gap"><b>{_fmt(never)}</b> people created an account '
           f'and never generated anything &mdash; that is {100 - act}% of '
           f'everyone. The onboarding audience below is exactly them.</p>')

    seg = w.get("segments") or {}

    def seg_n(k):
        v = seg.get(k) or {}
        return v.get("count", 0) if isinstance(v, dict) else len(v or [])

    seghtml = "".join(
        f'<button type="button" class="wm-seg" data-seg="{s.key}" '
        f'data-count="{seg_n(s.key)}" title="{escape(s.tag)}">'
        f'<span class="wm-segn">{_fmt(seg_n(s.key))}</span>'
        f'<span class="wm-segl">{escape(s.label)}</span>'
        f'<span class="wm-segt">{escape(s.tag)}</span></button>'
        for s in WINGMAN_SEGMENTS)

    # Where signups come from, the named channels only (the untagged
    # majority says nothing worth a bar).
    src = [x for x in (w.get("sources") or [])
           if x.get("label") not in ("direct/unknown", "unknown", None)][:5]
    smax = max((x.get("n", 0) for x in src), default=1) or 1
    srchtml = "".join(
        f'<div class="wm-srow"><span class="wm-sl">{escape(str(x.get("label", "")))}</span>'
        f'{_bar(round(x.get("n", 0) * 100 / smax))}'
        f'<span class="wm-sn">{_fmt(x.get("n", 0))}</span></div>'
        for x in src)

    # The named tables are not rendered here: customer names would land in
    # panel.html, which the vault carries. They fill at runtime from the
    # token-gated /wingman-detail.json instead, so this card stays aggregate.
    loading = '<tr><td colspan="3" class="note">loading…</td></tr>'
    built = w.get("generated_at", "")
    return (
        f'<section class="card" data-view="business" id="wingman-users">'
        f'<h2><span class="he">🪄</span>Wingman accounts'
        f'<span class="cnt">{_fmt(acc)} accounts &middot; {act}% activated '
        f'&middot; {prem} paying</span></h2>'
        f'<div class="wm-tiles">{tilehtml}</div>'
        f'{gap}'
        f'<h3 class="wm-h">Email audiences</h3>'
        f'<p class="note">Who to reach, cut from the same data. These are the '
        f'audience counts; pick one and send it through Resend from the Email '
        f'screen below.</p>'
        f'<div class="wm-segs">{seghtml}</div>'
        f'<div class="wm-cols">'
        f'<div class="wm-col"><h3 class="wm-h">Most active</h3>'
        f'<div class="scroll"><table><thead><tr><th>User</th><th>Plan</th>'
        f'<th class="num">Generations</th></tr></thead>'
        f'<tbody id="wm-top">{loading}</tbody></table></div></div>'
        f'<div class="wm-col"><h3 class="wm-h">Premium, by tenure</h3>'
        f'<div class="scroll"><table><thead><tr><th>User</th><th>Plan</th>'
        f'<th class="num">For</th></tr></thead>'
        f'<tbody id="wm-prem">{loading}</tbody></table></div></div>'
        f'</div>'
        + (f'<h3 class="wm-h">Where they come from</h3><div class="wm-src">{srchtml}</div>'
           if src else "")
        + (f'<p class="note wm-built">{_wm_stamp(w)}</p>'
           if built else "")
        + '</section>')


def _email_card(d: dict) -> str:
    """Write one message, pick one Wingman audience, send it through Resend.

    The page only ever names a segment; the recipient list is resolved
    server-side at send time from the collector's snapshot, so nothing here
    can email a list the page invented. Counts shown come from the same
    snapshot the send will read.
    """
    w = d.get("wingman") or {}
    seg = w.get("segments") or {}

    def n(key):
        v = seg.get(key) or {}
        em = v.get("emails")
        if em is None and key == "churning_premium":
            em = [u.get("email") for u in v.get("users") or []]
        return len([e for e in (em or []) if e])

    hist = d.get("history") or []
    audhtml = "".join(
        f'<button type="button" class="em-aud" data-seg="{s.key}" data-count="{n(s.key)}" '
        f'aria-pressed="false"><span class="wm-segn">{_fmt(n(s.key))}</span>'
        f'<span class="wm-segl">{escape(s.label)}</span>'
        f'<span class="wm-segt">{escape(s.desc)}</span>'
        # Only builds that measured this audience. Treating absence as
        # zero drew a flat floor with a cliff at the end, which reads as
        # growth that never happened; skipped, a young series is simply a
        # flat line at today's value until real movement accumulates.
        + _spark([p[s.hist_key] for p in hist if s.hist_key in p][-60:],
                 f"e{i}", s.color, w=340, h=30)
        + '</button>'
        for i, s in enumerate(WINGMAN_SEGMENTS))

    return (
        f'<section class="card" id="email">'
        f'<h2><span class="he">✉️</span>Email'
        f'<span class="cnt">Wingman audiences, sent through Resend</span></h2>'
        f'<p class="note wm-built">{_wm_stamp(w)}</p>'
        f'<p class="note">Pick who, write once, send. The recipient list is '
        f'resolved on the server at send time from the latest Supabase '
        f'snapshot, every message goes out individually (nobody sees anyone '
        f'else), a footer explains why they got it, and every send is logged '
        f'to <code>email-log.md</code> in the private folder, outside the '
        f'vault.</p>'
        f'<h3 class="wm-h">Who</h3>'
        f'<div class="wm-segs em-auds">{audhtml}</div>'
        f'<h3 class="wm-h">Message</h3>'
        f'<div class="em-form">'
        f'<input id="emsubj" class="em-subj" type="text" maxlength="150" '
        f'placeholder="Subject" aria-label="Email subject">'
        f'<textarea id="embody" class="em-body" rows="10" '
        f'placeholder="Write here. Plain text becomes paragraphs; HTML is '
        f'kept as is."></textarea>'
        f'<div class="figbar">'
        f'<button class="btn tiny primary" id="emsend" disabled>Pick an '
        f'audience first</button>'
        f'<span class="fsep"></span>'
        f'<input id="emtestto" class="em-testto" type="email" '
        f'placeholder="you@example.com" aria-label="Test address">'
        f'<button class="btn tiny" id="emtest">Send a test to this address'
        f'</button>'
        f'<span class="note bigmsg" id="emmsg"></span></div>'
        f'</div></section>')


def _wm_stamp(w: dict) -> str:
    """When the audience data was actually read from Supabase, in the
    reader's own clock, with the cadence beside it so "old" has a meaning.
    The collector stamps UTC; showing that raw read four hours off from the
    wall clock, which is exactly the doubt this line exists to remove."""
    raw = (w or {}).get("generated_at", "")
    try:
        from datetime import datetime as _dt, timezone as _tz
        local = (_dt.strptime(raw, "%Y-%m-%d %H:%M:%S")
                 .replace(tzinfo=_tz.utc).astimezone())
        shown = local.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        shown = raw or "never"
    return (f"audiences read from Supabase at {escape(shown)} "
            f"(your time) &middot; the collector refreshes them every 12 h")


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
    ("business", "grid", "Business", ""),
    ("systems", "flame", "Products", ""),
    ("videos", "video", "Videos", ""),
    ("links", "link", "Links", ""),
    ("sync", "refresh", "Knowledge", "silent"),
    ("wingman", "sparkle", "Writing", ""),
    ("email", "mail", "Email", ""),
    ("sources", "database", "Admin", ""),
]






def _retention_card(d: dict) -> str:
    """Who stayed, who left, and how fast they left.

    Built because "how many patrons" had one answer on this panel and a
    different one on Patreon's own dashboard, and because the shape of the
    leaving matters more than the count: most of the people who ever paid
    paid once.
    """
    pat = d.get("patreon") or {}
    r = pat.get("retention") or {}
    if not r.get("measured"):
        return ""
    rows = r["rows"]
    top = max((x["n"] for x in rows), default=1) or 1

    bars = []
    for x in rows:
        label = ("6 months or more" if x.get("over")
                 else "paid once, same month" if x["months"] == 0
                 else f'{x["months"]} month' + ("s" if x["months"] > 1 else ""))
        width = max(2, round(x["n"] * 100 / top))
        bars.append(
            f'<div class="bar" title="{escape(label, quote=True)}: '
            f'{_fmt(x["n"])} people, US$ {x["cents"] / 100:,.0f} paid">'
            f'<span class="bl">{escape(label)}</span>'
            f'<span class="bt"><i style="width:{width}%"></i></span>'
            f'<span class="bv">{_fmt(x["n"])} &middot; '
            f'US$ {x["cents"] / 100:,.0f}</span></div>')

    def cell(k, v, sub="", warn=False):
        return (f'<div><span class="k">{escape(k)}</span>'
                f'<span class="v{" warn" if warn else ""}">{v}</span>'
                + (f'<span class="k">{escape(sub)}</span>' if sub else "")
                + "</div>")

    return (
        '<section class="card" id="retention">'
        '<h2><span class="he">🧮</span>Who stayed, and how fast the rest '
        'left</h2>'
        '<div class="figstat" style="border-top:0;padding-top:0">'
        + cell("paying right now", _fmt(r["paying_now"]), "the card went through")
        + cell("subscribed right now", _fmt(r["subscribed_now"]),
               f'includes {_fmt(r["declined_now"])} whose card failed')
        + cell("of everyone who ever paid, still here",
               f'{r["kept_pct"]}%', "", r["kept_pct"] < 20)
        + cell("paid once and left", _fmt(r["one_and_out"]),
               f'{r["one_and_out_pct"]}% of those who left', True)
        + "</div>"
        '<p class="figwhy">Two counts, because they answer different '
        "questions and this panel used to show only the first. Patreon's own "
        'dashboard counts the second: a declined patron has not cancelled, '
        'their card failed and they are still subscribed.</p>'
        '<p class="lsub">How long the people who left had stayed</p>'
        '<div class="bars">' + "".join(bars) + "</div>"
        f'<p class="figwhy">Measured on {_fmt(r["measured"])} of the '
        f'{_fmt(r["left"])} who left'
        + (f', the other {_fmt(r["undated"])} having no charge on record'
           if r.get("undated") else "")
        + '. Nothing in the export says the day somebody cancelled, so this '
        'is the months between joining and their last charge, which '
        'undercounts by whatever part of a month they stayed after paying '
        'for the last time. The first bar is people whose joining month and '
        'last charge month are the same: they paid once. That is what taking '
        "a tier's content and leaving looks like from here, though it is "
        'not proof of why.</p>'
        "</section>")



def _period_card(d: dict) -> str:
    """This week, month and year against the one before."""
    pat = d.get("patreon") or {}
    pc = pat.get("period_change") or {}
    rows = pc.get("rows") or []
    if not rows:
        return ""

    def pct(v):
        if v is None:
            return '<span class="v">-</span>'
        return f'<span class="v{" warn" if v < 0 else ""}">{v:+d}%</span>'

    body = "".join(
        f'<div class="prow2"><span class="olabel">{escape(r["label"])}'
        f'<span class="note"> &middot; {r["days"]} days</span></span>'
        f'<span class="pcell"><span class="k">people who started paying</span>'
        f'{pct(r["pct"])}<span class="k">{_fmt(r["now"])} against '
        f'{_fmt(r["prev"])}</span></span>'
        f'<span class="pcell"><span class="k">new monthly revenue</span>'
        f'{pct(r["money_pct"])}<span class="k">US$ {_fmt(r["money_now"])} '
        f'against US$ {_fmt(r["money_prev"])}</span></span>'
        f'<span class="pcell"><span class="k">videos published</span>'
        f'<span class="v">{r["videos_now"]}</span>'
        f'<span class="k">against {r["videos_prev"]}</span></span></div>'
        for r in rows)

    year = next((r for r in rows if r["label"].startswith("this year")), None)
    note = ""
    if year and year["videos_prev"] and year["pct"] is not None:
        drop = round((year["videos_prev"] - year["videos_now"]) * 100
                     / year["videos_prev"])
        note = (f'<p class="figwhy">The year is the row worth sitting with. '
                f'{drop}% fewer videos went out than by this day last year, '
                f'and {abs(year["pct"])}% fewer people started paying'
                + (f', while the money those people bring each month is '
                   f'{year["money_pct"]:+d}%' if year["money_pct"] is not None
                   else "")
                + '. Publishing far less cost far less than the effort '
                  'suggests, and who joined mattered more than how many.</p>')

    return (
        '<section class="card" id="periods">'
        '<h2><span class="he">📆</span>Against the period before</h2>'
        f'{body}{note}'
        f'<p class="figwhy">Each side counts the same number of elapsed days, '
        f'so a month half lived is compared with the same half of the month '
        f'before rather than with a whole one. Through '
        f'{escape(pc.get("through") or "?")}. New monthly revenue is what the '
        f'people who joined in that period pay per month.</p>'
        "</section>")


def _effect_years(v: dict) -> str:
    """The comparison that survives: a week with a video against one without.

    Put first because the ratios further down measure against the period
    average, and that average contains the video weeks, so they compare
    publishing with a mixture of publishing and silence. This compares it
    with silence.
    """
    rows = [q for q in (v.get("quiet") or []) if q["videos"] >= 10]
    if not rows:
        return ""
    top = max(q["ratio"] for q in rows) or 1
    bars = "".join(
        f'<div class="bar" title="{q["year"]}: {q["with_video"]} a day in a '
        f'week holding a video, {q["without"]} in one holding none, from '
        f'{q["videos"]} videos">'
        f'<span class="bl">{q["year"]} &middot; {q["videos"]} videos</span>'
        f'<span class="bt"><i style="width:'
        f'{max(2, round(q["ratio"] * 100 / top))}%"></i></span>'
        f'<span class="bv">{q["ratio"]}x '
        f'<small>+{q["extra_week"]}/week</small></span></div>'
        for q in rows)
    yrs = ", ".join(q["year"] for q in rows)
    return (
        '<p class="lsub">A week with a video, against a week without</p>'
        f'<div class="bars">{bars}</div>'
        f'<p class="figwhy">Each year on its own, so channel size is held '
        f'still. {escape(yrs)} agree on about a fifth more people starting to '
        f'pay in a week that carried a video, across years holding very '
        f'different numbers of them. That agreement is what makes this the '
        f'number to trust, and the ones below the ones to read carefully.</p>')


def _effect_card(d: dict) -> str:
    """Does publishing bring patrons, as bars against the ordinary week."""
    pat = d.get("patreon") or {}
    v = pat.get("video_effect") or {}
    if not v.get("kinds"):
        return ""
    base = v["baseline"] or 1

    def bars(rows, thin=5):
        top = max([r["ratio"] for r in rows] + [1.0])
        out = []
        for r in rows:
            w = max(2, round(r["ratio"] * 100 / top))
            weak = r["n"] < thin
            out.append(
                f'<div class="bar" title="{escape(r["label"], quote=True)}: '
                f'{r["median"]} in the week, {r["ratio"]}x the usual '
                f'{v["baseline"]}, from {r["n"]} videos">'
                f'<span class="bl">{escape(r["label"])}</span>'
                f'<span class="bt"><i style="width:{w}%;'
                f'{"opacity:.45" if weak else ""}"></i>'
                f'<b class="bbase" style="left:{min(99, round(100 / top))}%"></b>'
                f'</span>'
                f'<span class="bv">{r["ratio"]}x '
                f'<small>n={r["n"]}{" ?" if weak else ""}</small></span></div>')
        return '<div class="bars">' + "".join(out) + "</div>"

    legend = (
        '<div class="chlegend">'
        '<span><i style="background:var(--ch-main)"></i>joins in the week after, '
        'against the ordinary week</span>'
        '<span><i class="basetick"></i>where an ordinary week sits</span>'
        '<span><i style="background:var(--ch-main);opacity:.45"></i>'
        'fewer than five videos, read as a hint not a number</span></div>')

    fair = ""
    for y in v.get("fair") or []:
        inner = "".join(
            f'<div class="bar"><span class="bl">{escape(k["label"])}</span>'
            f'<span class="bt"><i style="width:'
            f'{max(2, round(k["ratio"] * 60))}%"></i></span>'
            f'<span class="bv">{k["ratio"]}x <small>n={k["n"]}</small></span></div>'
            for k in y["kinds"])
        fair += (f'<p class="lsub">Inside {escape(y["year"])} alone, where both '
                 f'exist</p><div class="bars">{inner}</div>')

    topics = ""
    if v.get("topics"):
        topics = ('<p class="lsub">By topic</p>' + bars(v["topics"], thin=5)
                  + f'<p class="figwhy">Only {_fmt(v["tagged"])} of '
                    f'{_fmt(v["videos"])} videos carry a topic, and only one has '
                    f'more than a handful, so every bar but Ledge System is a '
                    f'hint. Tagging more of them in the vault is what would '
                    f'make this readable.</p>')

    return (
        '<section class="card" id="effect">'
        '<h2><span class="he">🎬</span>Does publishing bring patrons</h2>'
        + _effect_years(v)
        + legend
        + '<p class="lsub">By what was published</p>'
        + bars(v["kinds"])
        + '<div class="bars"><div class="bar">'
          '<span class="bl">Patreon post</span>'
          '<span class="bt"><i style="width:0"></i></span>'
          '<span class="bv"><small>no data</small></span></div></div>'
        + '<p class="figwhy">Counted on people who went on to pay, in the '
          + str(v["window"]) + ' days after each of ' + _fmt(v["videos"])
        + ' videos, against the ' + str(v["baseline"]) + ' an ordinary week '
          'brings. Patreon posts have no bar because the collector reads '
          'members and not posts: that row is missing data, not a zero.</p>'
        + fair
        + '<p class="figwhy">The two readings disagree, and the second is the '
          'honest one. Across the whole history livestreams look far better '
          'than uploads, but every livestream here was streamed in 2025 and '
          'most uploads came before it, so that comparison is a bigger '
          'channel against a smaller one wearing the label of format. Inside '
          '2025 the two are level. What the data supports is that publishing '
          'lifts joins; it does not support choosing live over upload.</p>'
        + topics
        + "</section>")


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
        f'<button class="btn primary" id="updbtn" '
        f'aria-label="Pull the latest Discord questions and rebuild" '
        f'title="Fetches the latest Discord questions, then rebuilds">'
        f'{_icon("refresh", 14)}Update</button>'
        f'<button class="btn icon" id="filtbtn" aria-label="Jump to filters" title="Filters">'
        f'{_icon("filter", 15)}</button>'
        f'<button class="btn" id="themebtn" aria-label="Switch color theme">'
        f'{theme_icons}<span class="tlabel">Auto</span></button>'
        f'<div class="bellwrap">'
        f'<button class="btn icon bell" id="bellbtn" aria-haspopup="true" '
        f'aria-expanded="false" aria-label="Recent activity and sync status" '
        f'title="What came in, and when each source last synced">'
        f'{_icon("bell", 15)}'
        f'<span class="badge">{_fmt(d["open_q"])}</span></button>'
        f'<div id="activitybox" class="actbox hide" role="region" '
        f'aria-label="Recent activity"></div></div></div>'
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

    subs = {
        "__EPOCH__": str(d["epoch"]),
        "__LIVE__": "true" if live else "false",
        "__PAGE__": str(PAGE),
        "__BULK_GAPS__": embed(d.get("bulk_gaps") or {}),
        "__TOKEN__": token,
        "__AI_CACHE__": embed(d.get("ai_cache") or {}),
        "__QDATA__": embed(_question_payload(d["questions"])),
        "__LOOKUPS__": embed(_row_lookups()),
        "__ACTIVITY__": embed(d.get("activity_payload") or {}),
        "__LTSPARKS__": embed({
            label: _spark([p[k] for p in (d.get("history") or []) if k in p][-60:],
                          f"l{i}", "var(--accent)", w=340, h=24)
            for i, (k, label) in enumerate((
                ("lt1", "clicks 1h"), ("lt24", "clicks 24h"),
                ("lt7", "clicks 7d"), ("ltn", "links")))}),
        "__SRCDET__": embed(d.get("source_details") or {}),
        "__CHARTS__": embed(_chart_payload(d)),
        "__BRANDS__": embed(list(_BRAND)),
        "__MANUAL_STATUS__": embed(list(manual_status)),
        "__CRM__": embed({
            p["who"]: {"status": (p.get("note") or {}).get("status", ""),
                       "next": (p.get("note") or {}).get("next", ""),
                       "tags": (p.get("note") or {}).get("tags", []),
                       "notes": (p.get("note") or {}).get("notes", ""),
                       "derived": p.get("status", "")}
            for p in d["people"]
            if (p.get("note") or p.get("status"))}),
        "__PATRONS__": embed({
            h: {"name": p["name"], "tiers": p["tiers"],
                "monthly": p["monthly_cents"], "lifetime": p["lifetime_cents"],
                "since": p["since"], "paying": p["paying"]}
            for h, p in (d.get("patrons") or {}).items()}),
    }
    # One pass over the template, not a chain of .replace() calls. Each later
    # replace in the chain rescanned everything the earlier ones had already
    # inserted, so a question whose text contained a token like __LOOKUPS__
    # (a commenter can type it) had that token, sitting inside the QDATA JSON
    # string, replaced with a raw JSON object: invalid JavaScript, and the
    # whole page went dead. re.sub never reprocesses what the replacement
    # returns, so an inserted value carrying a token is left exactly as is.
    js = re.sub(r"__[A-Z_]+__", lambda m: subs.get(m.group(0), m.group(0)), JS)

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
{_stamp_views(_tiles(d, len(d["systems"]), _overview_cards(d)))}
{_stamp_views(_questions_card(d))}
<div class="cols2">
{_stamp_views(_answers_card(d) + _system_pressure_card(d, facets))}
</div>
{_stamp_views(_business_screen(d, _period_card(d) + _sales_card(d)
                                 + _wingman_users_card(d)
                                 + _retention_card(d) + _effect_card(d)
                                 + _people_card(d))
              + _links_card(d) + _sync_card(d) + _wingman_card(d)
              + _email_card(d))}
<div class="grid3">
{_stamp_views(_videos_card(d) + _sources_card(instrumentation, d) + _health_card(d))}
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
