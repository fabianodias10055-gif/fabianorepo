#!/usr/bin/env python3
"""Put one secret into the Windows Credential Manager, safely.

    python store_secret.py SUPABASE_SERVICE_ROLE_KEY

It prompts for the value with echo off, so the key never appears on
screen, never lands in the shell history, and never touches a file. That
is the whole reason this script exists: pasting a key into a command line
or into .env leaves a plaintext copy behind, and the Credential Manager
is where every other secret of this repo already lives.

Run with no argument to see the known key names. An unknown name still
works (get_secret looks any name up), it just asks you to confirm first.
"""
import getpass
import sys

import secrets_store as ss


def main() -> int:
    if len(sys.argv) < 2:
        print("Which secret? One of the names this repo already knows:\n")
        for name in ss.SECRET_KEYS:
            have = "stored" if ss.get_secret(name) else "-"
            print(f"  {name:32} {have}")
        print("\nUsage: python store_secret.py <NAME>")
        return 1

    name = sys.argv[1].strip().upper()
    if name not in ss.SECRET_KEYS:
        ok = input(f"{name} is not in the known list. Store it anyway? [y/N] ")
        if ok.strip().lower() != "y":
            return 1

    value = getpass.getpass(f"Paste the value for {name} (hidden): ").strip()
    if not value:
        print("Nothing entered; nothing stored.")
        return 1

    if not ss.set_secret(name, value):
        print("ERROR: could not write to the Credential Manager "
              "(is keyring installed in this venv?)")
        return 1

    # Confirm by shape only. Printing the value would undo the point.
    back = ss.get_secret(name)
    print(f"Stored {name} in Windows Credential Manager "
          f"(service: {ss.SERVICE}).")
    print(f"Verified read-back: {len(back)} chars, starts with "
          f"{back[:4]!r}." if back else "WARNING: read-back came empty.")
    print("Restart the panel watcher if the panel should pick it up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
