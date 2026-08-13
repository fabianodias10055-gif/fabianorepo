"""
Simple URL shortener — stores links + click analytics in SQLite.
Routes are registered on the existing aiohttp server (port 8080).
"""

import asyncio
import csv
import hashlib
import hmac
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

# A referrer is just a hostname; strip anything that isn't host-safe so a crafted
# Referer header can't smuggle HTML (e.g. <img onerror=...>) into the admin UI.
_REF_SANITIZE = re.compile(r"[^A-Za-z0-9.\-:_\[\]]")

import aiohttp
from aiohttp import web

logger = logging.getLogger("shortener")

DB_PATH = "/app/data/shortener.db"

# Salt used to hash visitor IPs before storing them. Set via Railway env var.
# Never rotate — rotating would orphan all previously-stored visitor identifiers.
_IP_SALT = os.environ.get("IP_HASH_SALT", "")


def hash_ip(ip: str) -> str:
    """Returns a stable opaque identifier for a visitor IP, or '' if unhashable."""
    if not ip or not _IP_SALT:
        return ""
    # HMAC (keyed) rather than a bare hash: a plain SHA-256 over the small IPv4
    # space is trivially rainbow-tabled if the DB and salt ever leak.
    return hmac.new(_IP_SALT.encode("utf-8"), ip.encode("utf-8"), hashlib.sha256).hexdigest()


def is_safe_http_url(url: str) -> bool:
    """Storage choke point: only http/https destinations may be persisted.
    Blocks javascript:, data:, file: etc. that would become clickable XSS when
    rendered as an <a href> in the admin dashboard."""
    try:
        return urlparse(url).scheme.lower() in ("http", "https")
    except Exception:
        return False


# ── Database ──────────────────────────────────────────────────────────────────

def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # WAL lets readers (analytics) and a writer (click logging) proceed
    # concurrently; busy_timeout bounds how long a contended call blocks the
    # shared event loop instead of the default indefinite/rollback stall.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
    except Exception:
        pass
    return conn


def _migrate_clicks_columns(db: sqlite3.Connection):
    """Idempotent: adds ip_hash, user_agent, timezone columns if missing."""
    cur = db.execute("PRAGMA table_info(clicks)")
    existing = {row[1] for row in cur.fetchall()}
    for col in ("ip_hash", "user_agent", "timezone"):
        if col not in existing:
            db.execute(f"ALTER TABLE clicks ADD COLUMN {col} TEXT")
            logger.info("Migrated clicks: added column %s", col)
    db.commit()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS links (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                prefix     TEXT NOT NULL DEFAULT 'p',
                slug       TEXT NOT NULL,
                url        TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_links ON links(prefix, slug)"
        )
        db.execute("""
            CREATE TABLE IF NOT EXISTS clicks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id      INTEGER NOT NULL,
                clicked_at   TEXT NOT NULL,
                country      TEXT,
                country_code TEXT,
                referrer     TEXT,
                ip_hash      TEXT,
                user_agent   TEXT,
                timezone     TEXT,
                FOREIGN KEY (link_id) REFERENCES links(id)
            )
        """)
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_clicks_link ON clicks(link_id)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_clicks_time ON clicks(clicked_at)"
        )
        # Idempotent: ensures pre-existing DBs get the new columns too.
        _migrate_clicks_columns(db)
        db.commit()
    logger.info("Shortener DB initialised at %s", DB_PATH)


# ── Link CRUD ─────────────────────────────────────────────────────────────────

def create_link(slug: str, url: str, prefix: str = "p") -> bool:
    """Returns True if created, False if slug already taken (or url unsafe)."""
    if not is_safe_http_url(url):
        logger.warning("Refused to create link with non-http(s) url: %.80s", url)
        return False
    try:
        with _conn() as db:
            db.execute(
                "INSERT INTO links (prefix, slug, url, created_at) VALUES (?,?,?,?)",
                (prefix.lower(), slug, url, datetime.now(timezone.utc).isoformat()),
            )
            db.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_link(slug: str, prefix: str = "p") -> dict | None:
    with _conn() as db:
        row = db.execute(
            "SELECT * FROM links WHERE prefix=? AND slug=?",
            (prefix.lower(), slug),
        ).fetchone()
    return dict(row) if row else None


def update_link(slug: str, new_url: str, prefix: str = "p") -> bool:
    if not is_safe_http_url(new_url):
        logger.warning("Refused to update link with non-http(s) url: %.80s", new_url)
        return False
    with _conn() as db:
        cur = db.execute(
            "UPDATE links SET url=? WHERE prefix=? AND slug=?",
            (new_url, prefix.lower(), slug),
        )
        db.commit()
    return cur.rowcount > 0


def delete_link(slug: str, prefix: str = "p") -> bool:
    with _conn() as db:
        cur = db.execute(
            "DELETE FROM links WHERE prefix=? AND slug=?",
            (prefix.lower(), slug),
        )
        db.commit()
    return cur.rowcount > 0


def list_links() -> list[dict]:
    with _conn() as db:
        rows = db.execute(
            "SELECT prefix, slug, url, created_at FROM links ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Click logging ─────────────────────────────────────────────────────────────

def log_click(
    link_id: int,
    country: str,
    country_code: str,
    referrer: str,
    ip_hash: str = "",
    user_agent: str = "",
    timezone_name: str | None = None,
) -> int | None:
    """Insert a click row and return its rowid."""
    try:
        with _conn() as db:
            cur = db.execute(
                """INSERT INTO clicks
                   (link_id, clicked_at, country, country_code, referrer,
                    ip_hash, user_agent, timezone)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    link_id,
                    datetime.now(timezone.utc).isoformat(),
                    country,
                    country_code,
                    referrer,
                    ip_hash,
                    user_agent,
                    timezone_name,
                ),
            )
            db.commit()
            return cur.lastrowid
    except Exception as exc:
        logger.warning("log_click error: %s", exc)
        return None


def update_click_geo(
    click_id: int,
    country: str,
    country_code: str,
    timezone_name: str | None = None,
):
    """Updates country, country_code and (optionally) timezone on a click row."""
    try:
        with _conn() as db:
            db.execute(
                "UPDATE clicks SET country=?, country_code=?, timezone=? WHERE id=?",
                (country, country_code, timezone_name, click_id),
            )
            db.commit()
    except Exception as exc:
        logger.warning("update_click_geo error: %s", exc)


def _clean_geo(value, maxlen: int = 64) -> str:
    """Clamp a geo field returned by the upstream API to a safe short string."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^A-Za-z0-9 .,'\-_/]", "", value)[:maxlen]


async def lookup_geo(ip: str) -> tuple[str, str, str | None]:
    """Returns (country_name, country_code, timezone_name). Fails silently."""
    # Only query with a syntactically valid IP so a spoofed X-Forwarded-For
    # can't steer the request path/query on the upstream service.
    try:
        import ipaddress
        ipaddress.ip_address(ip)
    except Exception:
        return "Unknown", "??", None
    try:
        timeout = aiohttp.ClientTimeout(total=2)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # http, not https, on purpose: ip-api.com's free tier rejects SSL
            # with 403 "SSL unavailable for this endpoint". The https switch
            # (f574ffd security pass) silently killed all geo enrichment from
            # 2026-07-07 onward. If plaintext to the geo provider is ever
            # unacceptable, the fix is their paid pro endpoint, never https
            # on this one.
            async with session.get(
                f"http://ip-api.com/json/{ip}?fields=country,countryCode,timezone"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    country = _clean_geo(data.get("country")) or "Unknown"
                    code = _clean_geo(data.get("countryCode"), 4) or "??"
                    tz = _clean_geo(data.get("timezone")) or None
                    return country, code, tz
                # Never log the IP itself; the status code is what matters.
                logger.warning("geo lookup failed: HTTP %s", resp.status)
    except Exception as exc:
        logger.warning("geo lookup error: %s", type(exc).__name__)
    return "Unknown", "??", None


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_stats(slug: str, prefix: str = "p", days: int = 30) -> dict | None:
    link = get_link(slug, prefix)
    if not link:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as db:
        total = db.execute(
            "SELECT COUNT(*) FROM clicks WHERE link_id=? AND clicked_at>=?",
            (link["id"], cutoff),
        ).fetchone()[0]

        by_country = db.execute(
            """SELECT country, country_code, COUNT(*) cnt
               FROM clicks WHERE link_id=? AND clicked_at>=?
               GROUP BY country ORDER BY cnt DESC LIMIT 10""",
            (link["id"], cutoff),
        ).fetchall()

        by_referrer = db.execute(
            """SELECT referrer, COUNT(*) cnt
               FROM clicks WHERE link_id=? AND clicked_at>=?
               GROUP BY referrer ORDER BY cnt DESC LIMIT 5""",
            (link["id"], cutoff),
        ).fetchall()

        daily = db.execute(
            """SELECT substr(clicked_at,1,10) day, COUNT(*) cnt
               FROM clicks WHERE link_id=? AND clicked_at>=?
               GROUP BY day ORDER BY day DESC LIMIT 7""",
            (link["id"], (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()),
        ).fetchall()

    return {
        "link": link,
        "total": total,
        "days": days,
        "by_country": [dict(r) for r in by_country],
        "by_referrer": [dict(r) for r in by_referrer],
        "daily": [dict(r) for r in daily],
    }


def get_top_links(days: int = 7, limit: int = 5) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as db:
        rows = db.execute(
            """SELECT l.prefix, l.slug, l.url, COUNT(c.id) clicks
               FROM links l
               LEFT JOIN clicks c ON c.link_id=l.id AND c.clicked_at>=?
               GROUP BY l.id ORDER BY clicks DESC LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ── CSV import (from Dub export) ──────────────────────────────────────────────

def import_from_csv(csv_path: str) -> tuple[int, int]:
    """
    Import links from a Dub CSV export.
    Dub columns: key, url  (key may be 'p/slug' or just 'slug')
    Returns (imported, skipped).
    """
    imported = skipped = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("url") or row.get("destinationUrl") or ""
            key = row.get("key") or row.get("slug") or ""
            if not url or not key:
                skipped += 1
                continue
            if "/" in key:
                prefix, slug = key.split("/", 1)
            else:
                prefix, slug = "p", key
            if create_link(slug, url, prefix):
                imported += 1
            else:
                skipped += 1
    return imported, skipped


# Hold strong references to background geo-lookup tasks so GC doesn't kill them.
_bg_tasks: set = set()


# ── aiohttp route ─────────────────────────────────────────────────────────────

async def _do_redirect(request: web.Request, slug: str, prefix: str) -> web.Response:
    link = get_link(slug, prefix)
    if not link:
        raise web.HTTPNotFound(text="Short link not found.")

    forwarded = request.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.remote or "")
    raw_ref = request.headers.get("Referer", "") or request.headers.get("Referrer", "") or ""
    try:
        referrer = _REF_SANITIZE.sub("", urlparse(raw_ref).netloc)[:128] or "direct"
    except Exception:
        referrer = "direct"

    # Strip HTML-significant and control chars so a crafted UA can't inject markup
    # into any dashboard that renders it (defense in depth, like `referrer` above).
    user_agent = re.sub(r"[<>\x00-\x1f\x7f]", "", request.headers.get("User-Agent", ""))[:512]
    ip_h = hash_ip(ip)

    # Always log the click immediately (synchronous DB write, sub-ms).
    click_id = log_click(
        link["id"], "Unknown", "??", referrer,
        ip_hash=ip_h, user_agent=user_agent,
    )

    # Resolve country + timezone in background and update the row.
    if click_id and ip:
        async def _geo(cid=click_id, addr=ip):
            country, code, tz = await lookup_geo(addr)
            if country != "Unknown" or tz:
                update_click_geo(cid, country, code, tz)

        task = asyncio.create_task(_geo())
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)

    raise web.HTTPFound(link["url"])


async def handle_redirect(request: web.Request) -> web.Response:
    """Handles /{prefix}/{slug}"""
    prefix = request.match_info["prefix"]
    slug   = request.match_info["slug"]
    return await _do_redirect(request, slug, prefix)


async def handle_redirect_root(request: web.Request) -> web.Response:
    """Handles /{slug} with no prefix (stored as prefix='root')"""
    slug = request.match_info["slug"]
    return await _do_redirect(request, slug, "root")


async def handle_redirect_domain_root(request: web.Request) -> web.Response:
    """Handles locodev.dev with no path at all (stored as prefix='root', slug='_root')"""
    return await _do_redirect(request, "_root", "root")


def setup_routes(app: web.Application):
    init_db()
    app.router.add_get("/", handle_redirect_domain_root)
    app.router.add_get("/{prefix}/{slug:.+}", handle_redirect)
    app.router.add_get("/{slug:.+}", handle_redirect_root)
    logger.info("URL shortener routes registered")
