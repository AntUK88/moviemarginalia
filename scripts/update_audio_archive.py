#!/usr/bin/env python3
"""
Scans audio/ for files not yet in _data/audio_archive.json, fetches
metadata from Letterboxd via JSON-LD (no API key required), then
appends new entries and writes the updated JSON.

Filename convention: <letterboxd-slug>.m4a
Example:             the-godfather.m4a
"""

import json
import datetime
import re
from pathlib import Path

import requests
from mutagen import File as MutagenFile

REPO_ROOT = Path(__file__).parent.parent
AUDIO_DIR = REPO_ROOT / "audio"
ARCHIVE_PATH = REPO_ROOT / "_data" / "audio_archive.json"

LETTERBOXD_BASE = "https://letterboxd.com/film"
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".ogg", ".opus", ".wav", ".aac", ".flac"}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; moviemarginalia-archiver/1.0)"}


def load_archive():
    if ARCHIVE_PATH.exists():
        with open(ARCHIVE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_archive(entries):
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")


def get_duration(path):
    try:
        audio = MutagenFile(path)
        if audio is not None and audio.info is not None:
            return int(audio.info.length)
    except Exception:
        pass
    return None


def letterboxd_metadata(slug):
    url = f"{LETTERBOXD_BASE}/{slug}/"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()

    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        r.text, re.DOTALL
    )
    if not match:
        return None

    data = json.loads(match.group(1))

    title = data.get("name")
    year_raw = data.get("datePublished", "")
    year = int(str(year_raw)[:4]) if year_raw else None
    poster = data.get("image")

    directors = data.get("director", [])
    if isinstance(directors, list):
        director = directors[0].get("name") if directors else None
    elif isinstance(directors, dict):
        director = directors.get("name")
    else:
        director = None

    return {
        "title": title,
        "year": year,
        "director": director,
        "poster": poster,
        "letterboxd_url": url,
    }


def process_file(path, existing_filenames):
    filename = path.name
    if filename in existing_filenames:
        return None

    slug = path.stem
    print(f"  Processing {filename} (slug: {slug})")

    try:
        meta = letterboxd_metadata(slug)
    except Exception as e:
        print(f"    Error fetching Letterboxd metadata: {e}")
        meta = None

    if not meta:
        print(f"    No Letterboxd metadata found, using slug as title fallback")
        meta = {
            "title": slug.replace("-", " ").title(),
            "year": None,
            "director": None,
            "poster": None,
            "letterboxd_url": f"{LETTERBOXD_BASE}/{slug}/",
        }

    print(f"    {meta['title']} ({meta['year']}), dir. {meta['director']}")
    return {
        "letterboxd_slug": slug,
        "letterboxd_url": meta["letterboxd_url"],
        "title": meta["title"],
        "year": meta["year"],
        "director": meta["director"],
        "poster": meta["poster"],
        "filename": filename,
        "date_added": datetime.date.today().isoformat(),
        "duration_seconds": get_duration(path),
    }


def main():
    archive = load_archive()
    existing_filenames = {e["filename"] for e in archive}

    audio_files = sorted(
        p for p in AUDIO_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS and not p.name.startswith(".")
    )

    new_entries = []
    for path in audio_files:
        entry = process_file(path, existing_filenames)
        if entry:
            new_entries.append(entry)

    if new_entries:
        archive.extend(new_entries)
        save_archive(archive)
        print(f"\nAdded {len(new_entries)} new {'entry' if len(new_entries) == 1 else 'entries'}.")
    else:
        print("\nNo new audio files found.")


if __name__ == "__main__":
    main()
