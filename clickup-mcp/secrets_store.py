#!/usr/bin/env python3
"""Read secrets from the Windows credential store instead of a plaintext file.

Everything that can act on your behalf lived together in one .env: the
Discord bot token, the YouTube refresh token, the ClickUp token, the
shortener admin secret. Any process running as this user could read that
file, and every one of those values is enough to post as you.

The Windows credential store keeps them encrypted under the account, so a
file copied off the disk is worth nothing without the account, and a stray
`cat .env` shows names rather than credentials.

Config stays in .env. Channel ids, model names and budgets are not secrets
and are far easier to read and edit as text.

Usage:
    python secrets_store.py --status          what lives where
    python secrets_store.py --migrate --dry-run
    python secrets_store.py --migrate         move them, then blank the file
    python secrets_store.py --set NAME        type one in without echoing it
"""

import argparse
import os
import re
import subprocess
import sys
from getpass import getpass
from pathlib import Path

try:
    import keyring
except ImportError:
    keyring = None

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
SERVICE = "locodev-panel"

# Values that can act on your behalf. Everything else in .env is settings.
SECRET_KEYS = (
    "CLICKUP_API_TOKEN",
    "YOUTUBE_API_KEY",
    "YOUTUBE_OAUTH_CLIENT_ID",
    "YOUTUBE_OAUTH_CLIENT_SECRET",
    "YOUTUBE_REFRESH_TOKEN",
    "DISCORD_BOT_TOKEN",
    "PATREON_ACCESS_TOKEN",
    # An access token dies after about a month. These three are what mints a
    # new one without anyone noticing it expired.
    "PATREON_REFRESH_TOKEN",
    "PATREON_CLIENT_ID",
    "PATREON_CLIENT_SECRET",
    "LOCODEV_ADMIN_SECRET",
    "RESEND_API_KEY",
    # The account for the Resend send to come from, e.g. LocoDev
    # <hello@locodev.dev>. Not a secret, but it lives with the key it is
    # paired with so one lookup covers both.
    "RESEND_FROM",
    # Reading the LocoAI/Wingman accounts for the panel's Wingman card. The
    # service-role key bypasses RLS, so it is a real secret and belongs here
    # rather than in a plaintext file.
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "DISCORD_WEBHOOK_URL",
    "ANTHROPIC_API_KEY",
)

_cache: dict[str, str] = {}


def get_secret(name: str, default: str = "") -> str:
    """A secret, from the environment first and the credential store next.

    Environment first so a one-off override still works and so nothing
    breaks for anyone who has not migrated; the store is where they should
    live. Cached because the panel asks for the same token on every request
    and each lookup is a Windows API call.
    """
    val = os.getenv(name, "").strip()
    # A value that is only a comment came from a mangled .env line, not from
    # anyone's credential; treating it as one produced auth errors that
    # looked like a revoked token.
    if val and not val.startswith("#"):
        return val
    if name in _cache:
        return _cache[name]
    if keyring is None:
        return default
    try:
        stored = keyring.get_password(SERVICE, name) or ""
    except Exception:  # noqa: BLE001 - a locked store must not crash a collector
        stored = ""
    stored = stored.strip()
    if stored:
        _cache[name] = stored
    return stored or default


def forget_secret(name: str) -> None:
    """Drop the cached copy so the next read goes back to the store.

    The cache exists because the panel asks for the same token on every
    request and each miss is a Windows API call. It also means a credential
    replaced while the panel is running stays invisible to it: signing in
    again wrote a fresh refresh token to the store and the process kept
    presenting the revoked one until somebody restarted it. Whoever learns
    a secret has stopped working calls this, and the next attempt sees
    whatever is there now.
    """
    _cache.pop(name, None)


def looks_like_secret(value: str) -> str:
    """Empty when the value could be a credential, else why it cannot be.

    Reading the clipboard has one obvious failure that costs an hour to
    find: the last thing copied is usually the command you pasted to run
    this, so the command gets stored and every call fails with 401 as if
    the token were revoked. A credential has no spaces and is not a path,
    and refusing here turns that hour into a sentence.
    """
    if not value:
        return "it is empty"
    if any(c.isspace() for c in value):
        return "it contains spaces or line breaks"
    if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("\\\\", "./", ".\\")):
        return "it looks like a file path"
    if len(value) > 600:
        return f"it is {len(value)} characters, which is longer than any token"
    return ""


def set_secret(name: str, value: str) -> bool:
    if keyring is None:
        return False
    keyring.set_password(SERVICE, name, value)
    _cache[name] = value
    return True


def read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_PATH.is_file():
        return out
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def blank_in_env(names: list[str]) -> int:
    """Leave the key, drop the value, say where it went.

    Deleting the line would hide that the setting exists at all; a reader
    should be able to see what the panel expects and where to find it.
    """
    if not ENV_PATH.is_file():
        return 0
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    done = 0
    for i, line in enumerate(lines):
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line.strip())
        if m and m.group(1) in names and m.group(2).strip():
            # The note goes above, not after the '=': python-dotenv reads an
            # inline comment as part of the value, so "KEY=  # moved" made
            # the comment itself the credential and every call failed auth.
            lines[i] = (f"# moved to Windows Credential Manager ({SERVICE})"
                        + "\n" + f"{m.group(1)}=")
            done += 1
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return done


def status() -> None:
    env = read_env()
    print(f"credential store: {'available' if keyring else 'keyring NOT installed'}")
    if keyring:
        print(f"backend: {keyring.get_keyring().__class__.__name__}")
    print(f"service name: {SERVICE}\n")
    print(f"{'secret':<30} {'.env':<12} {'store':<10}")
    print("-" * 54)
    for k in SECRET_KEYS:
        in_env = "plaintext" if env.get(k) else "-"
        stored = ""
        if keyring:
            try:
                stored = keyring.get_password(SERVICE, k) or ""
            except Exception:  # noqa: BLE001
                stored = ""
        print(f"{k:<30} {in_env:<12} {'yes' if stored else '-':<10}")
    extra = [k for k in env if k not in SECRET_KEYS and env[k]]
    print(f"\nsettings left in .env as plain text: {len(extra)}")
    print("  " + ", ".join(sorted(extra)))


def migrate(dry: bool) -> int:
    if keyring is None:
        print("ERROR: keyring is not installed. pip install keyring")
        return 1
    env = read_env()
    moving = [k for k in SECRET_KEYS if env.get(k)]
    if not moving:
        print("nothing to move: no secret in .env carries a value")
        return 0

    print(f"secrets to move: {len(moving)}")
    for k in moving:
        print(f"  {k}: {len(env[k])} chars")

    if dry:
        print("\n(simulation: nothing written, nothing blanked)")
        return 0

    verified = []
    for k in moving:
        try:
            keyring.set_password(SERVICE, k, env[k])
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED to store {k}: {type(exc).__name__}")
            continue
        # Read it back before touching the file: a secret blanked from .env
        # and missing from the store is a credential lost, not moved.
        if (keyring.get_password(SERVICE, k) or "") == env[k]:
            verified.append(k)
        else:
            print(f"  FAILED to verify {k}; leaving it in .env")

    print(f"\nstored and verified: {len(verified)} of {len(moving)}")
    if verified:
        n = blank_in_env(verified)
        print(f"blanked in .env: {n}")
    if len(verified) != len(moving):
        print("Some secrets stayed in .env because they could not be verified.")
        return 1
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--migrate", action="store_true")
    ap.add_argument("--set", metavar="NAME")
    ap.add_argument("--set-from-clipboard", metavar="NAME",
                    help="take the value from the clipboard instead of typing "
                         "it; getpass shows nothing at all while you type, "
                         "which in some terminals is indistinguishable from "
                         "a prompt that is not accepting input")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.set_from_clipboard:
        if keyring is None:
            print("ERROR: keyring is not installed. pip install keyring")
            return 1
        # Straight from the clipboard: never typed, never echoed, and never
        # left in shell history, which is one better than a prompt.
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=15)
            value = (out.stdout or "").strip()
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"ERROR: could not read the clipboard: {type(exc).__name__}")
            return 1
        why = looks_like_secret(value)
        if why:
            print(f"The clipboard does not hold a credential: {why}.")
            print("The usual cause is that the last thing copied was the "
                  "command you pasted to run this. Copy the token, then "
                  "press the up arrow to recall this command and Enter.")
            return 1
        set_secret(args.set_from_clipboard, value)
        # Length and the first characters only: enough to confirm the right
        # thing was pasted, useless to anyone reading over your shoulder.
        print(f"{args.set_from_clipboard} stored in {SERVICE}: "
              f"{len(value)} characters, starts with {value[:4]}...")
        return 0

    if args.set:
        if keyring is None:
            print("ERROR: keyring is not installed. pip install keyring")
            return 1
        # Said out loud because a prompt that shows nothing at all, not even
        # dots, is indistinguishable from one that is ignoring the keyboard.
        print("Type or paste, then press Enter. Nothing will appear on screen "
              "while you type. That is deliberate, not a frozen prompt.")
        value = getpass(f"value for {args.set} (not echoed): ").strip()
        why = looks_like_secret(value)
        if why:
            print(f"That is not a credential: {why}. Nothing was stored.")
            return 1
        set_secret(args.set, value)
        print(f"{args.set} stored in {SERVICE}: {len(value)} characters")
        return 0

    if args.migrate:
        return migrate(args.dry_run)

    status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
