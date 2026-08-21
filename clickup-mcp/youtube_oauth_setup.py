#!/usr/bin/env python3
"""One-time setup so the panel's Reply button can actually post to YouTube.

Reading comments only needs the plain YOUTUBE_API_KEY that collect_youtube.py
already uses. POSTING a reply is a write action against YOUR channel, and
YouTube requires OAuth for that: you sign in as the channel owner, in your own
browser, and grant this script permission to manage comments. Nothing here can
do that sign-in for you.

Steps:
  1. console.cloud.google.com, same project as the API key.
     APIs & Services > Credentials > Create Credentials > OAuth client ID.
     Application type: Desktop app. Download the JSON, save it next to this
     script as client_secret.json.
  2. First time only, the OAuth consent screen needs your channel's Google
     account added as a test user (APIs & Services > OAuth consent screen >
     Test users), unless the app is already published.
  3. Run this script:
         python youtube_oauth_setup.py
     It opens your browser to a Google sign-in and consent page. Approve it.
     A local page on 127.0.0.1 catches the redirect; closing that tab when it
     says "You can close this window" is safe.
  4. The script writes YOUTUBE_OAUTH_CLIENT_ID, YOUTUBE_OAUTH_CLIENT_SECRET
     and YOUTUBE_REFRESH_TOKEN into clickup-mcp/.env. The refresh token does
     not expire from use; it stops working only if you revoke access in your
     Google account or leave the OAuth consent screen in unpublished testing
     mode for more than 7 days without re-approving.

client_secret.json is your credential to prove this script is really you.
Never commit it; it is covered by .gitignore already the same way .env is.
"""

import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib import error, parse, request

BASE_DIR = Path(__file__).resolve().parent
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
ENV_PATH = BASE_DIR / ".env"

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
REDIRECT_PORT = 8766


def load_client_secret() -> dict:
    if not CLIENT_SECRET_PATH.is_file():
        print(f"ERROR: {CLIENT_SECRET_PATH} not found.")
        print("Download it from Google Cloud Console (OAuth client ID, Desktop app type)")
        print("and save it next to this script under that exact name.")
        sys.exit(1)
    data = json.loads(CLIENT_SECRET_PATH.read_text(encoding="utf-8"))
    return data.get("installed") or data.get("web") or data


def wait_for_code() -> str:
    """A tiny local server just to catch the OAuth redirect once."""
    holder = {}

    class Catch(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            qs = parse.urlparse(self.path).query
            params = parse.parse_qs(qs)
            holder["code"] = params.get("code", [""])[0]
            holder["error"] = params.get("error", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            msg = "Authorization failed, check the terminal." if holder["error"] \
                else "Signed in. You can close this window."
            self.wfile.write(f"<html><body><p>{msg}</p></body></html>".encode())

        def log_message(self, *a):
            pass

    # Wait as long as the sign-in actually takes. The old three-minute cap
    # kept expiring while the consent screen was being sorted out, so the
    # approval landed on a server that had already given up. Ctrl+C is the
    # way out; the loop reports every minute so it never looks hung.
    httpd = HTTPServer(("127.0.0.1", REDIRECT_PORT), Catch)
    thread = threading.Thread(target=httpd.handle_request, daemon=True)
    thread.start()
    waited = 0
    while thread.is_alive():
        thread.join(timeout=60)
        if thread.is_alive():
            waited += 1
            print(f"still waiting for you to approve in the browser "
                  f"({waited} min)... Ctrl+C to stop.", flush=True)
    httpd.server_close()
    if holder.get("error"):
        print(f"ERROR: Google returned an error: {holder['error']}")
        sys.exit(1)
    if not holder.get("code"):
        print("ERROR: timed out waiting for you to approve access in the browser.")
        sys.exit(1)
    return holder["code"]


def exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    body = parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }).encode()
    req = request.Request(TOKEN_URL, data=body, method="POST")
    try:
        with request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except error.HTTPError as exc:
        print(f"ERROR exchanging code: {exc.code} {exc.read().decode(errors='replace')}")
        sys.exit(1)


def save_to_env(client_id: str, client_secret: str, refresh_token: str) -> None:
    """Straight into the credential store when it is available.

    Writing a refresh token back into a plaintext file would undo the point
    of having moved the others out of one.
    """
    try:
        from secrets_store import set_secret
        stored = all(set_secret(k, v) for k, v in (
            ("YOUTUBE_OAUTH_CLIENT_ID", client_id),
            ("YOUTUBE_OAUTH_CLIENT_SECRET", client_secret),
            ("YOUTUBE_REFRESH_TOKEN", refresh_token),
        ))
        if stored:
            print("Saved to Windows Credential Manager (locodev-panel).")
            return
    except Exception:  # noqa: BLE001 - fall back to the file below
        pass

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.is_file() else []
    values = {
        "YOUTUBE_OAUTH_CLIENT_ID": client_id,
        "YOUTUBE_OAUTH_CLIENT_SECRET": client_secret,
        "YOUTUBE_REFRESH_TOKEN": refresh_token,
    }
    seen = set()
    for i, line in enumerate(lines):
        for key, val in values.items():
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={val}"
                seen.add(key)
    for key, val in values.items():
        if key not in seen:
            lines.append(f"{key}={val}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _stored_client() -> dict:
    """The client id and secret kept from the last successful setup.

    A refresh token is the part that gets revoked; the client credentials
    behind it do not change. Asking someone to go back to the Cloud Console
    and re-download a file whose contents are already on this machine is a
    dead end at the exact moment they need this to work, so the JSON file
    is the first place looked and no longer the only one.
    """
    try:
        from secrets_store import get_secret
    except ImportError:
        import os
        def get_secret(name, default=""):        # noqa: E306
            return os.getenv(name, default)
    return {"client_id": get_secret("YOUTUBE_OAUTH_CLIENT_ID") or "",
            "client_secret": get_secret("YOUTUBE_OAUTH_CLIENT_SECRET") or ""}


def main() -> int:
    if CLIENT_SECRET_PATH.is_file():
        secret = load_client_secret()
    else:
        secret = _stored_client()
        if secret.get("client_id"):
            print("Using the client id and secret saved by the last setup; "
                  "only the refresh token is being replaced.")
    client_id = secret.get("client_id", "")
    client_secret = secret.get("client_secret", "")
    if not (client_id and client_secret):
        load_client_secret()      # prints where to get the file, then exits
        return 1

    redirect_uri = f"http://127.0.0.1:{REDIRECT_PORT}/"
    auth_url = AUTH_URL + "?" + parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri,
        "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent",
    })

    print("Opening your browser to sign in as the channel owner...")
    print(f"If it does not open, visit this URL yourself:\n{auth_url}\n")
    webbrowser.open(auth_url)

    code = wait_for_code()
    token = exchange_code(client_id, client_secret, redirect_uri, code)
    refresh_token = token.get("refresh_token", "")
    if not refresh_token:
        print("ERROR: Google did not return a refresh token.")
        print("This usually means access was already granted before without")
        print("'prompt=consent'. Revoke access at myaccount.google.com/permissions")
        print("for this app and run this script again.")
        return 1

    save_to_env(client_id, client_secret, refresh_token)
    print(f"\nDone. Saved to {ENV_PATH}.")
    print("Restart the panel watcher (LocoDev Panel Watcher scheduled task) so it")
    print("picks up the new .env values, then Reply will post to YouTube for real.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
