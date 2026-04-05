"""
Simple URL shortener — stores links + click analytics in SQLite.
Routes are registered on the existing aiohttp server (port 8080).
"""

import asyncio
import csv
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import aiohttp
from aiohttp import web

logger = logging.getLogger("shortener")

DB_PATH = "/app/shortener.db"


# ── Database ──────────────────────────────────────────────────────────────────

def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
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
                FOREIGN KEY (link_id) REFERENCES links(id)
            )
        """)
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_clicks_link ON clicks(link_id)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_clicks_time ON clicks(clicked_at)"
        )
        db.commit()
    logger.info("Shortener DB initialised at %s", DB_PATH)


# ── Link CRUD ─────────────────────────────────────────────────────────────────

def create_link(slug: str, url: str, prefix: str = "p") -> bool:
    """Returns True if created, False if slug already taken."""
    try:
        with _conn() as db:
            db.execute(
                "INSERT INTO links (prefix, slug, url, created_at) VALUES (?,?,?,?)",
                (prefix.lower(), slug.lower(), url, datetime.now(timezone.utc).isoformat()),
            )
            db.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_link(slug: str, prefix: str = "p") -> dict | None:
    with _conn() as db:
        row = db.execute(
            "SELECT * FROM links WHERE prefix=? AND slug=?",
            (prefix.lower(), slug.lower()),
        ).fetchone()
    return dict(row) if row else None


def update_link(slug: str, new_url: str, prefix: str = "p") -> bool:
    with _conn() as db:
        cur = db.execute(
            "UPDATE links SET url=? WHERE prefix=? AND slug=?",
            (new_url, prefix.lower(), slug.lower()),
        )
        db.commit()
    return cur.rowcount > 0


def delete_link(slug: str, prefix: str = "p") -> bool:
    with _conn() as db:
        cur = db.execute(
            "DELETE FROM links WHERE prefix=? AND slug=?",
            (prefix.lower(), slug.lower()),
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

def log_click(link_id: int, country: str, country_code: str, referrer: str):
    with _conn() as db:
        db.execute(
            "INSERT INTO clicks (link_id, clicked_at, country, country_code, referrer) VALUES (?,?,?,?,?)",
            (link_id, datetime.now(timezone.utc).isoformat(), country, country_code, referrer),
        )
        db.commit()


async def lookup_country(ip: str) -> tuple[str, str]:
    """Returns (country_name, country_code). Fails silently."""
    try:
        timeout = aiohttp.ClientTimeout(total=2)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"http://ip-api.com/json/{ip}?fields=country,countryCode"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("country", "Unknown"), data.get("countryCode", "??")
    except Exception:
        pass
    return "Unknown", "??"


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


# ── aiohttp route ─────────────────────────────────────────────────────────────

async def _do_redirect(request: web.Request, slug: str, prefix: str) -> web.Response:
    link = get_link(slug, prefix)
    if not link:
        raise web.HTTPNotFound(text=f"Short link not found.")

    forwarded = request.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.remote or "")
    raw_ref = request.headers.get("Referer", "") or request.headers.get("Referrer", "") or ""
    try:
        referrer = urlparse(raw_ref).netloc or "direct"
    except Exception:
        referrer = "direct"

    async def _log():
        try:
            country, code = await lookup_country(ip)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, log_click, link["id"], country, code, referrer)
        except Exception as exc:
            logger.warning("Click log error: %s", exc)

    asyncio.create_task(_log())
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


def setup_routes(app: web.Application):
    init_db()
    app.router.add_get("/{prefix}/{slug}", handle_redirect)
    app.router.add_get("/{slug}", handle_redirect_root)
    logger.info("URL shortener routes registered")
