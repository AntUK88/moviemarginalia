#!/usr/bin/env python3
"""
add_photo.py
------------
Adds a new photo entry to the JSON block inside pages/Photography.html.

Usage:
    python3 scripts/add_photo.py <image_path> [description] [notes]
"""

import sys
import json
import re
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/add_photo.py <image_path> [description] [notes]")
        sys.exit(1)

    image_path = sys.argv[1].strip()
    description = sys.argv[2].strip() if len(sys.argv) > 2 else ""
    notes = sys.argv[3].strip() if len(sys.argv) > 3 else ""

    # Ensure path starts with /assets/img/
    if not image_path.startswith("/"):
        image_path = "/assets/img/" + image_path

    photography_path = Path("pages/Photography.html")
    if not photography_path.exists():
        print("Error: pages/Photography.html not found.")
        sys.exit(1)

    content = photography_path.read_text(encoding="utf-8")

    # Find the JSON block between the script tags
    pattern = r'(<script id="photo-data" type="application/json">\s*)(.*?)(\s*</script>)'
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        print("Error: Could not find photo-data JSON block in Photography.html.")
        sys.exit(1)

    existing_json = match.group(2).strip()
    photos = json.loads(existing_json)

    # Check for duplicates
    if any(p["src"] == image_path for p in photos):
        print(f"Warning: {image_path} already exists in the gallery. Skipping.")
        sys.exit(0)

    # Add new photo
    new_photo = {"src": image_path, "description": description, "notes": notes}
    photos.append(new_photo)

    # Write back
    new_json = json.dumps(photos, indent=2, ensure_ascii=False)
    new_content = re.sub(
        pattern,
        lambda m: m.group(1) + new_json + m.group(3),
        content,
        flags=re.DOTALL
    )

    photography_path.write_text(new_content, encoding="utf-8")
    print(f"Added: {image_path}")
    print(f"  Description: {description or '(none)'}")
    print(f"  Notes: {notes or '(none)'}")
    print(f"  Total photos: {len(photos)}")

if __name__ == "__main__":
    main()
