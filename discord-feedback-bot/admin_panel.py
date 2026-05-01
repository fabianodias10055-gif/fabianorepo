"""
Admin dashboard for locodev.dev link management.
Served at /admin — protected by ADMIN_SECRET env var (Bearer token auth).
All link CRUD and analytics are exposed as JSON API endpoints.
"""
import logging
import secrets
from datetime import datetime, timezone

from aiohttp import web

logger = logging.getLogger("admin_panel")

_admin_secret: str = ""
_session_token: str = secrets.token_hex(32)   # fresh on each server start


# ── Auth ──────────────────────────────────────────────────────────────────────

def _check_token(request: web.Request) -> bool:
    auth = request.headers.get("Authorization", "")
    return auth.startswith("Bearer ") and secrets.compare_digest(auth[7:], _session_token)


async def handle_login(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON")
    password = body.get("password", "")
    if not _admin_secret or not secrets.compare_digest(password, _admin_secret):
        raise web.HTTPUnauthorized(text="Invalid password")
    return web.json_response({"token": _session_token})


# ── Stats ─────────────────────────────────────────────────────────────────────

async def handle_stats(request: web.Request) -> web.Response:
    if not _check_token(request):
        raise web.HTTPUnauthorized()
    from shortener import _conn
    with _conn() as db:
        clicks_1h = db.execute(
            "SELECT COUNT(*) FROM clicks WHERE clicked_at >= datetime('now', '-1 hour')"
        ).fetchone()[0]
        clicks_24h = db.execute(
            "SELECT COUNT(*) FROM clicks WHERE clicked_at >= datetime('now', '-24 hours')"
        ).fetchone()[0]
        clicks_7d = db.execute(
            "SELECT COUNT(*) FROM clicks WHERE clicked_at >= datetime('now', '-7 days')"
        ).fetchone()[0]
        total_links = db.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        top_country = db.execute(
            """SELECT country, COUNT(*) cnt FROM clicks
               WHERE clicked_at >= datetime('now','-7 days')
                 AND country IS NOT NULL AND country != 'Unknown'
               GROUP BY country ORDER BY cnt DESC LIMIT 1"""
        ).fetchone()
        hourly_rows = db.execute(
            """SELECT strftime('%H', clicked_at) hour, COUNT(*) cnt
               FROM clicks WHERE clicked_at >= datetime('now', '-24 hours')
               GROUP BY hour ORDER BY hour"""
        ).fetchall()
        recent = db.execute(
            """SELECT l.prefix, l.slug, c.clicked_at, c.country, c.country_code, c.referrer
               FROM clicks c JOIN links l ON c.link_id = l.id
               ORDER BY c.clicked_at DESC LIMIT 30"""
        ).fetchall()

    hourly_map = {r["hour"]: r["cnt"] for r in hourly_rows}
    now_hour = int(datetime.now(timezone.utc).strftime("%H"))
    chart = [
        {"hour": f"{(now_hour - 23 + i) % 24:02d}", "cnt": 0}
        for i in range(24)
    ]
    for entry in chart:
        entry["cnt"] = hourly_map.get(entry["hour"], 0)

    return web.json_response({
        "clicks_1h": clicks_1h,
        "clicks_24h": clicks_24h,
        "clicks_7d": clicks_7d,
        "total_links": total_links,
        "top_country": dict(top_country) if top_country else None,
        "hourly_chart": chart,
        "recent_clicks": [dict(r) for r in recent],
    })


# ── Links CRUD ────────────────────────────────────────────────────────────────

async def handle_list_links(request: web.Request) -> web.Response:
    if not _check_token(request):
        raise web.HTTPUnauthorized()
    from shortener import _conn
    with _conn() as db:
        rows = db.execute(
            """SELECT l.prefix, l.slug, l.url, l.created_at,
                      COUNT(c.id) total_clicks,
                      SUM(CASE WHEN c.clicked_at >= datetime('now','-7 days') THEN 1 ELSE 0 END) clicks_7d,
                      SUM(CASE WHEN c.clicked_at >= datetime('now','-1 hour')  THEN 1 ELSE 0 END) clicks_1h
               FROM links l LEFT JOIN clicks c ON c.link_id = l.id
               GROUP BY l.id ORDER BY total_clicks DESC"""
        ).fetchall()
    return web.json_response([dict(r) for r in rows])


async def handle_create_link(request: web.Request) -> web.Response:
    if not _check_token(request):
        raise web.HTTPUnauthorized()
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON")
    prefix = body.get("prefix", "p").strip().lower()
    slug = body.get("slug", "").strip()
    url = body.get("url", "").strip()
    if not slug or not url:
        raise web.HTTPBadRequest(text="slug and url are required")
    from shortener import create_link
    if not create_link(slug, url, prefix):
        raise web.HTTPConflict(text=f"/{prefix}/{slug} already exists")
    logger.info("Admin created link: /%s/%s → %s", prefix, slug, url)
    return web.json_response({"ok": True})


async def handle_update_link(request: web.Request) -> web.Response:
    if not _check_token(request):
        raise web.HTTPUnauthorized()
    prefix = request.match_info["prefix"]
    slug = request.match_info["slug"]
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON")
    url = body.get("url", "").strip()
    if not url:
        raise web.HTTPBadRequest(text="url is required")
    from shortener import update_link
    if not update_link(slug, url, prefix):
        raise web.HTTPNotFound(text="Link not found")
    logger.info("Admin updated link: /%s/%s → %s", prefix, slug, url)
    return web.json_response({"ok": True})


async def handle_delete_link(request: web.Request) -> web.Response:
    if not _check_token(request):
        raise web.HTTPUnauthorized()
    prefix = request.match_info["prefix"]
    slug = request.match_info["slug"]
    from shortener import delete_link
    if not delete_link(slug, prefix):
        raise web.HTTPNotFound(text="Link not found")
    logger.info("Admin deleted link: /%s/%s", prefix, slug)
    return web.json_response({"ok": True})


# ── HTML dashboard ────────────────────────────────────────────────────────────

async def handle_admin_html(request: web.Request) -> web.Response:
    return web.Response(text=_ADMIN_HTML, content_type="text/html", charset="utf-8")


# ── Route registration ────────────────────────────────────────────────────────

def setup_admin_routes(app: web.Application, secret: str):
    global _admin_secret
    _admin_secret = secret
    if not secret:
        logger.warning("ADMIN_SECRET not set — admin panel disabled")
        return
    # Admin routes must be registered BEFORE shortener catch-all routes
    app.router.add_get("/admin", handle_admin_html)
    app.router.add_post("/admin/login", handle_login)
    app.router.add_get("/admin/api/links", handle_list_links)
    app.router.add_post("/admin/api/links", handle_create_link)
    app.router.add_put("/admin/api/link/{prefix}/{slug:.+}", handle_update_link)
    app.router.add_delete("/admin/api/link/{prefix}/{slug:.+}", handle_delete_link)
    app.router.add_get("/admin/api/stats", handle_stats)
    logger.info("Admin panel registered at /admin")


# ── Dashboard HTML ────────────────────────────────────────────────────────────

_ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LocoDev Admin — Links</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh}
a{color:inherit;text-decoration:none}

/* ── Auth ── */
#auth{display:flex;align-items:center;justify-content:center;min-height:100vh}
.auth-card{background:#1a1d27;border:1px solid #2d3148;border-radius:14px;padding:44px 40px;width:360px}
.auth-card h1{font-size:1.5rem;color:#4ade80;margin-bottom:6px}
.auth-card p{color:#64748b;font-size:.9rem;margin-bottom:28px}
#login-err{color:#f87171;font-size:.85rem;margin-top:10px;display:none}

/* ── Dashboard ── */
#dash{display:none;max-width:1280px;margin:0 auto;padding:28px 24px}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid #2d3148}
header h1{font-size:1.25rem;color:#4ade80;letter-spacing:-.01em}
.hdr-right{display:flex;gap:10px;align-items:center}
#last-upd{font-size:.78rem;color:#475569}

/* ── Cards ── */
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}
.card{background:#1a1d27;border:1px solid #2d3148;border-radius:10px;padding:20px}
.card .lbl{font-size:.72rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}
.card .val{font-size:2.1rem;font-weight:700;color:#4ade80;line-height:1}
.card .sub{font-size:.78rem;color:#64748b;margin-top:6px}

/* ── Two-col ── */
.row2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}

/* ── Panels ── */
.panel{background:#1a1d27;border:1px solid #2d3148;border-radius:10px;padding:20px}
.panel h2{font-size:.78rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:16px}

/* ── Chart ── */
svg.chart{width:100%;height:110px;display:block}
.chart-hrs{display:flex;justify-content:space-between;font-size:.68rem;color:#475569;margin-top:4px;padding:0 2px}

/* ── Feed ── */
.feed{max-height:290px;overflow-y:auto}
.fi{display:grid;grid-template-columns:150px 70px 130px 1fr;gap:8px;padding:7px 0;border-bottom:1px solid #1e2235;font-size:.82rem;align-items:center}
.fi:last-child{border:none}
.fi-slug{color:#4ade80;font-family:monospace;font-size:.8rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fi-time{color:#64748b;font-size:.75rem}
.fi-country{color:#94a3b8}
.fi-ref{color:#475569;font-size:.75rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ── Table ── */
.tbl-wrap{background:#1a1d27;border:1px solid #2d3148;border-radius:10px;padding:20px;margin-bottom:20px;overflow-x:auto}
.tbl-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.tbl-hdr h2{font-size:.78rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em}
table{width:100%;border-collapse:collapse;font-size:.855rem}
th{text-align:left;padding:9px 12px;color:#475569;font-weight:600;font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #2d3148;white-space:nowrap;cursor:pointer;user-select:none}
th:hover{color:#94a3b8}
td{padding:9px 12px;border-bottom:1px solid #1a1d27;color:#cbd5e1;vertical-align:middle}
tr:hover td{background:#1e2235}
.td-slug{color:#4ade80;font-family:monospace;font-size:.82rem;white-space:nowrap}
.td-url{max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#64748b;font-size:.78rem}
.td-num{text-align:right;color:#94a3b8;white-space:nowrap}
.td-num.hot{color:#4ade80;font-weight:700}
.td-act{white-space:nowrap}

/* ── Create form ── */
.create{background:#1a1d27;border:1px solid #2d3148;border-radius:10px;padding:20px}
.create h2{font-size:.78rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:16px}
.form-row{display:grid;grid-template-columns:140px 200px 1fr auto;gap:10px;align-items:end}
label{display:block;font-size:.72rem;color:#64748b;margin-bottom:5px;text-transform:uppercase;letter-spacing:.04em}
input,select{width:100%;background:#0d0f18;border:1px solid #2d3148;border-radius:6px;padding:8px 12px;color:#e2e8f0;font-size:.875rem;outline:none;font-family:inherit}
input:focus,select:focus{border-color:#4ade80}

/* ── Buttons ── */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:5px;padding:8px 16px;border-radius:6px;border:none;cursor:pointer;font-size:.85rem;font-weight:500;transition:opacity .15s;font-family:inherit;white-space:nowrap}
.btn:hover{opacity:.8}
.btn-green{background:#4ade80;color:#0f1117}
.btn-red{background:#f87171;color:#fff}
.btn-gray{background:#2d3148;color:#94a3b8}
.btn-sm{padding:4px 10px;font-size:.78rem}
.edit-inp{background:#0d0f18;border:1px solid #4ade80;border-radius:4px;padding:4px 8px;color:#e2e8f0;font-size:.82rem;width:260px;font-family:inherit}

/* ── Toast ── */
#toast{position:fixed;bottom:24px;right:24px;background:#1a1d27;border:1px solid #2d3148;border-radius:8px;padding:12px 20px;font-size:.875rem;opacity:0;transition:opacity .25s;pointer-events:none;z-index:999}
#toast.show{opacity:1}
#toast.ok{border-color:#4ade80;color:#4ade80}
#toast.err{border-color:#f87171;color:#f87171}

@media(max-width:960px){.cards{grid-template-columns:repeat(2,1fr)}.row2{grid-template-columns:1fr}.form-row{grid-template-columns:1fr 1fr}}
@media(max-width:600px){.cards{grid-template-columns:1fr 1fr}.form-row{grid-template-columns:1fr}.form-row>*:last-child{grid-column:unset}}
</style>
</head>
<body>

<!-- ── Login ── -->
<div id="auth">
  <div class="auth-card">
    <h1>LocoDev Admin</h1>
    <p>Link management &amp; analytics</p>
    <label for="pw">Password</label>
    <input id="pw" type="password" placeholder="Enter admin password" autocomplete="current-password">
    <div style="margin-top:14px">
      <button class="btn btn-green" id="login-btn" style="width:100%">Sign in</button>
    </div>
    <div id="login-err">Incorrect password.</div>
  </div>
</div>

<!-- ── Dashboard ── -->
<div id="dash">
  <header>
    <h1>LocoDev &middot; Links Admin</h1>
    <div class="hdr-right">
      <span id="last-upd"></span>
      <button class="btn btn-gray btn-sm" onclick="refresh()">&#x21BB; Refresh</button>
      <button class="btn btn-gray btn-sm" onclick="logout()">Logout</button>
    </div>
  </header>

  <!-- Stats cards -->
  <div class="cards">
    <div class="card"><div class="lbl">Clicks &middot; Last Hour</div><div class="val" id="c1h">&mdash;</div></div>
    <div class="card"><div class="lbl">Clicks &middot; Last 24h</div><div class="val" id="c24h">&mdash;</div></div>
    <div class="card"><div class="lbl">Clicks &middot; Last 7d</div><div class="val" id="c7d">&mdash;</div></div>
    <div class="card">
      <div class="lbl">Total Links</div>
      <div class="val" id="clinks">&mdash;</div>
      <div class="sub" id="ctop"></div>
    </div>
  </div>

  <!-- Chart + feed -->
  <div class="row2">
    <div class="panel">
      <h2>Clicks per hour &mdash; last 24 hours</h2>
      <svg class="chart" id="hchart" viewBox="0 0 480 100" preserveAspectRatio="none"></svg>
      <div class="chart-hrs" id="hrlabels"></div>
    </div>
    <div class="panel">
      <h2>Recent clicks <span style="color:#2d3148;font-weight:400">(auto-refresh 30s)</span></h2>
      <div class="feed" id="feed"></div>
    </div>
  </div>

  <!-- Links table -->
  <div class="tbl-wrap">
    <div class="tbl-hdr">
      <h2>All Links</h2>
      <input id="search" type="search" placeholder="Filter&#x2026;" style="width:220px">
    </div>
    <table>
      <thead>
        <tr>
          <th onclick="sort('slug')">Short Link</th>
          <th onclick="sort('url')">Destination</th>
          <th onclick="sort('clicks_1h')" style="text-align:right">1h</th>
          <th onclick="sort('clicks_7d')" style="text-align:right">7d</th>
          <th onclick="sort('total_clicks')" style="text-align:right">Total</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

  <!-- Create form -->
  <div class="create">
    <h2>Create New Short Link</h2>
    <div class="form-row">
      <div>
        <label>Prefix</label>
        <select id="npfx">
          <option value="p">p &mdash; Patreon</option>
          <option value="download">download</option>
          <option value="docs">docs</option>
          <option value="free">free</option>
          <option value="freebuild">freebuild</option>
          <option value="root">root (no prefix)</option>
        </select>
      </div>
      <div>
        <label>Slug</label>
        <input id="nslug" type="text" placeholder="e.g. weaponstandard">
      </div>
      <div>
        <label>Destination URL</label>
        <input id="nurl" type="url" placeholder="https://&hellip;">
      </div>
      <div>
        <label>&nbsp;</label>
        <button class="btn btn-green" onclick="createLink()">+ Create</button>
      </div>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
'use strict';
let TOKEN = localStorage.getItem('adm_tok') || '';
let links = [];
let sKey = 'total_clicks', sDir = -1;
let timer = null;

// ── Auth ─────────────────────────────────────────────────────────────────────
async function tryLogin() {
  const pw = document.getElementById('pw').value;
  try {
    const r = await fetch('/admin/login', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({password:pw})
    });
    if (r.ok) {
      TOKEN = (await r.json()).token;
      localStorage.setItem('adm_tok', TOKEN);
      boot();
    } else {
      document.getElementById('login-err').style.display = 'block';
    }
  } catch(e) { toast('Connection error', 'err'); }
}

function logout() {
  TOKEN = ''; localStorage.removeItem('adm_tok');
  clearInterval(timer);
  document.getElementById('dash').style.display = 'none';
  document.getElementById('auth').style.display = 'flex';
}

document.getElementById('login-btn').onclick = tryLogin;
document.getElementById('pw').onkeydown = e => e.key === 'Enter' && tryLogin();

function boot() {
  document.getElementById('auth').style.display = 'none';
  document.getElementById('dash').style.display = 'block';
  refresh();
  timer = setInterval(refresh, 30000);
}

// ── API ───────────────────────────────────────────────────────────────────────
async function req(method, path, body) {
  const o = { method, headers:{'Authorization':'Bearer '+TOKEN} };
  if (body) { o.headers['Content-Type']='application/json'; o.body=JSON.stringify(body); }
  const r = await fetch(path, o);
  if (r.status === 401) { logout(); return null; }
  return r;
}

// ── Refresh ───────────────────────────────────────────────────────────────────
async function refresh() {
  const [rs, rl] = await Promise.all([
    req('GET', '/admin/api/stats'),
    req('GET', '/admin/api/links'),
  ]);
  if (!rs || !rl) return;
  const stats = await rs.json();
  links = await rl.json();
  renderStats(stats);
  renderLinks();
  document.getElementById('last-upd').textContent = 'Updated ' + new Date().toLocaleTimeString();
}

// ── Stats ──────────────────────────────────────────────────────────────────────
function renderStats(s) {
  document.getElementById('c1h').textContent    = s.clicks_1h;
  document.getElementById('c24h').textContent   = s.clicks_24h;
  document.getElementById('c7d').textContent    = s.clicks_7d;
  document.getElementById('clinks').textContent = s.total_links;
  const tc = s.top_country;
  document.getElementById('ctop').textContent   = tc ? '\\uD83C\\uDF0D Top: ' + tc.country : '';
  renderChart(s.hourly_chart);
  renderFeed(s.recent_clicks);
}

function renderChart(data) {
  const svg = document.getElementById('hchart');
  const lbl = document.getElementById('hrlabels');
  const max = Math.max(...data.map(d => d.cnt), 1);
  const W=480, H=100, n=data.length, bw=W/n, pd=1.5;
  let out = '';
  data.forEach((d,i) => {
    const bh = Math.max((d.cnt/max)*(H-18), d.cnt>0?3:0);
    const x=(i*bw+pd).toFixed(1), w=(bw-pd*2).toFixed(1);
    const y=(H-bh-8).toFixed(1);
    const col = d.cnt>0 ? '#4ade80' : '#1e2235';
    out += `<rect x="${x}" y="${y}" width="${w}" height="${bh.toFixed(1)}" fill="${col}" rx="2"/>`;
    if (d.cnt>0) out += `<text x="${(i*bw+bw/2).toFixed(1)}" y="${(parseFloat(y)-2).toFixed(1)}" fill="#94a3b8" font-size="8" text-anchor="middle">${d.cnt}</text>`;
  });
  svg.innerHTML = out;
  lbl.innerHTML = data.map((d,i) => i%3===0 ? `<span>${d.hour}h</span>` : '<span></span>').join('');
}

function renderFeed(clicks) {
  const el = document.getElementById('feed');
  if (!clicks.length) { el.innerHTML='<div style="color:#475569;font-size:.85rem">No recent clicks.</div>'; return; }
  el.innerHTML = clicks.map(c => {
    const cc = (c.country_code||'').toUpperCase();
    let flag = '\\uD83C\\uDF0E';
    if (cc && cc !== '??' && cc.length===2) {
      try { flag = String.fromCodePoint(...[...cc].map(ch => 0x1F1E6+ch.charCodeAt(0)-65)); } catch(e){}
    }
    const slug = c.prefix && c.prefix!=='root' ? `/\${c.prefix}/\${c.slug}` : `/\${c.slug}`;
    const t = (c.clicked_at||'').slice(11,19);
    return `<div class="fi">
      <span class="fi-slug">\${slug}</span>
      <span class="fi-time">\${t}</span>
      <span class="fi-country">\${flag} \${c.country||'??'}</span>
      <span class="fi-ref">\${c.referrer||'direct'}</span>
    </div>`;
  }).join('');
}

// ── Links table ────────────────────────────────────────────────────────────────
function sort(k) {
  if (sKey===k) sDir*=-1; else { sKey=k; sDir=-1; }
  renderLinks();
}

function renderLinks() {
  const q = document.getElementById('search').value.toLowerCase();
  let data = links.filter(l => !q ||
    l.slug.toLowerCase().includes(q) || l.prefix.includes(q) || l.url.toLowerCase().includes(q)
  );
  data.sort((a,b) => {
    const av=a[sKey]??'', bv=b[sKey]??'';
    return typeof av==='number' ? (av-bv)*sDir : String(av).localeCompare(String(bv))*sDir;
  });
  document.getElementById('tbody').innerHTML = data.map(l => {
    const short = l.prefix==='root' ? '/'+l.slug : '/'+l.prefix+'/'+l.slug;
    return `<tr>
      <td class="td-slug"><a href="https://locodev.dev\${short}" target="_blank">\${short}</a></td>
      <td class="td-url" title="\${l.url}"><a href="\${l.url}" target="_blank">\${l.url}</a></td>
      <td class="td-num \${l.clicks_1h>0?'hot':''}">\${l.clicks_1h||0}</td>
      <td class="td-num \${l.clicks_7d>4?'hot':''}">\${l.clicks_7d||0}</td>
      <td class="td-num">\${l.total_clicks||0}</td>
      <td class="td-act">
        <button class="btn btn-gray btn-sm" onclick="startEdit('\${l.prefix}','\${l.slug}',\`\${l.url.replace(/\`/g,'')}\`)">Edit</button>
        <button class="btn btn-red btn-sm" style="margin-left:4px" onclick="delLink('\${l.prefix}','\${l.slug}')">Del</button>
      </td>
    </tr>`;
  }).join('');
}

document.getElementById('search').addEventListener('input', renderLinks);

function startEdit(pfx, slg, url) {
  const rows = document.getElementById('tbody').querySelectorAll('tr');
  const short = pfx==='root' ? '/'+slg : '/'+pfx+'/'+slg;
  for (const row of rows) {
    if (row.cells[0].textContent.trim()===short) {
      row.cells[1].innerHTML =
        `<input class="edit-inp" id="ei-\${pfx}-\${slg}" value="">` +
        `<button class="btn btn-green btn-sm" style="margin-left:6px" onclick="saveEdit('\${pfx}','\${slg}')">Save</button>` +
        `<button class="btn btn-gray btn-sm" style="margin-left:4px" onclick="renderLinks()">&#x2715;</button>`;
      const inp = document.getElementById('ei-'+pfx+'-'+slg);
      inp.value = url;
      inp.focus();
      break;
    }
  }
}

async function saveEdit(pfx, slg) {
  const inp = document.getElementById('ei-'+pfx+'-'+slg);
  if (!inp) return;
  const r = await req('PUT', '/admin/api/link/'+pfx+'/'+slg, {url:inp.value.trim()});
  if (r && r.ok) { toast('Updated', 'ok'); refresh(); }
  else toast('Update failed', 'err');
}

async function delLink(pfx, slg) {
  const short = pfx==='root' ? '/'+slg : '/'+pfx+'/'+slg;
  if (!confirm('Delete '+short+'?')) return;
  const r = await req('DELETE', '/admin/api/link/'+pfx+'/'+slg);
  if (r && r.ok) { toast('Deleted', 'ok'); refresh(); }
  else toast('Delete failed', 'err');
}

// ── Create ─────────────────────────────────────────────────────────────────────
async function createLink() {
  const pfx  = document.getElementById('npfx').value;
  const slg  = document.getElementById('nslug').value.trim();
  const url  = document.getElementById('nurl').value.trim();
  if (!slg || !url) { toast('Slug and URL required', 'err'); return; }
  const r = await req('POST', '/admin/api/links', {prefix:pfx, slug:slg, url});
  if (r && r.ok) {
    toast('Created!', 'ok');
    document.getElementById('nslug').value = '';
    document.getElementById('nurl').value = '';
    refresh();
  } else if (r && r.status===409) { toast('Slug already exists', 'err'); }
  else toast('Create failed', 'err');
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'show '+(type||'');
  setTimeout(()=>t.className='', 2800);
}

// ── Boot ─────────────────────────────────────────────────────────────────────
if (TOKEN) boot();
</script>
</body>
</html>"""
