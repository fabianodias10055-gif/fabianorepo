"""
One-time migration script to import Dub CSV export into the shortener DB.
Run: python migrate_dub.py "Dub Links Export - ....csv"
"""
import csv
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from shortener import init_db, create_link

def migrate(csv_path: str):
    init_db()
    imported = 0
    skipped = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            short_link = row.get("Short link", "").strip()
            dest_url   = row.get("Destination URL", "").strip()

            if not short_link or not dest_url:
                skipped += 1
                continue

            # Extract prefix and slug from full short link
            # e.g. https://locodev.dev/freebuild/gaspals → prefix=freebuild, slug=gaspals
            # e.g. https://locodev.dev/uecourse          → prefix=root, slug=uecourse
            path = short_link.split("locodev.dev", 1)[-1].strip("/")
            parts = path.split("/", 1)
            if len(parts) == 2:
                prefix, slug = parts[0], parts[1]
            else:
                prefix, slug = "root", parts[0]

            ok = create_link(slug, dest_url, prefix)
            if ok:
                print(f"  ✅ /{prefix}/{slug} → {dest_url}")
                imported += 1
            else:
                print(f"  ⚠️  /{prefix}/{slug} already exists, skipped")
                skipped += 1

    print(f"\nDone! Imported: {imported}, Skipped: {skipped}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrate_dub.py <path_to_csv>")
        sys.exit(1)
    migrate(sys.argv[1])
