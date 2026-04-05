"""
One-time migration script to import Dub CSV export into the shortener DB.
Run: python migrate_dub.py dub_links.csv
"""
import csv
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from shortener import init_db, create_link

ROOT_REDIRECT = "_root"  # Special slug for locodev.dev → Patreon

def migrate(csv_path: str):
    init_db()
    imported = 0
    skipped = 0
    ignored = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            short_link = row.get("Short link", "").strip()
            dest_url   = row.get("Destination URL", "").strip()

            if not short_link or not dest_url:
                skipped += 1
                continue

            # Skip dub.sh links — different domain, can't serve from locodev.dev
            if "dub.sh" in short_link:
                print(f"  ⏭️  Skipping dub.sh link: {short_link}")
                ignored += 1
                continue

            # Extract path after locodev.dev
            path = short_link.split("locodev.dev", 1)[-1].strip("/")

            # Root domain (locodev.dev with no path)
            if not path:
                prefix, slug = "root", ROOT_REDIRECT
            else:
                # Split into at most prefix + slug (handles /download/build/slug as prefix=download, slug=build/slug)
                parts = path.split("/", 1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    prefix, slug = parts[0], parts[1]
                elif parts[0]:
                    prefix, slug = "root", parts[0]
                else:
                    skipped += 1
                    continue

            ok = create_link(slug, dest_url, prefix)
            if ok:
                print(f"  ✅ /{prefix}/{slug} → {dest_url}")
                imported += 1
            else:
                print(f"  ⚠️  /{prefix}/{slug} already exists, skipped")
                skipped += 1

    print(f"\nDone! Imported: {imported}, Skipped: {skipped}, Ignored (dub.sh): {ignored}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrate_dub.py <path_to_csv>")
        sys.exit(1)
    migrate(sys.argv[1])
