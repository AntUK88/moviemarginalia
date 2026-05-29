#!/usr/bin/env python3
"""
Scans audio/ for files not yet in _data/audio_archive.json, fetches
metadata from TMDb, then appends new entries and writes the updated JSON.

Filename convention: <letterboxd-slug>.m4a
Example:             the-godfather.m4a  /  sabrina-1995.m4a

The slug is converted to a title search query. If the slug ends with a
4-digit year (e.g. sabrina-1995), that year is used to filter results.

Usage:
  python3 update_audio_archive.py                        # normal scan
  python3 update_audio_archive.py --reprocess <slug> <tmdb_id>
"""

import os
import re
import sys
import json
import datetime
from pathlib import Path

import requests
from mutagen import File as MutagenFile

REPO_ROOT = Path(__file__).parent.parent
AUDIO_DIR = REPO_ROOT / "audio"
ARCHIVE_PATH = REPO_ROOT / "_data" / "audio_archive.json"

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w185"
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".ogg", ".opus", ".wav", ".aac", ".flac"}

BEARER_TOKEN = os.environ["TMDB_API_KEY"]
HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}", "Accept": "application/json"}

YEAR_SUFFIX_RE = re.compile(r"^(.*)-(\d{4})$")


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


def slug_to_title_and_year(slug):
    m = YEAR_SUFFIX_RE.match(slug)
    if m:
        return m.group(1).replace("-", " "), int(m.group(2))
    return slug.replace("-", " "), None


def tmdb_search(title, year=None):
    params = {"query": title, "include_adult": False}
    if year:
        params["primary_release_year"] = year
    r = requests.get(f"{TMDB_BASE}/search/movie", headers=HEADERS, params=params, timeout=15)
    r.raise_for_status()
    results = r.json().get("results", [])
    return results[0] if results else None


def tmdb_fetch_by_id(tmdb_id):
    r = requests.get(f"{TMDB_BASE}/movie/{tmdb_id}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def tmdb_director(tmdb_id):
    r = requests.get(f"{TMDB_BASE}/movie/{tmdb_id}/credits", headers=HEADERS, timeout=15)
    r.raise_for_status()
    crew = r.json().get("crew", [])
    directors = [m["name"] for m in crew if m.get("job") == "Director"]
    return directors[0] if directors else None


def build_entry_from_movie(movie, slug, path):
    tmdb_id = movie["id"]
    tmdb_title = movie.get("title", slug.replace("-", " ").title())
    release_date = movie.get("release_date", "")
    tmdb_year = int(release_date[:4]) if release_date else None
    poster_path = movie.get("poster_path")
    poster = (TMDB_IMG_BASE + poster_path) if poster_path else None

    try:
        director = tmdb_director(tmdb_id)
    except Exception:
        director = None

    print(f"    {tmdb_title} ({tmdb_year}), dir. {director}")
    return {
        "letterboxd_slug": slug,
        "title": tmdb_title,
        "year": tmdb_year,
        "director": director,
        "poster": poster,
        "filename": path.name,
        "date_added": datetime.date.today().isoformat(),
        "duration_seconds": get_duration(path),
        "file_size_bytes": path.stat().st_size,
    }


def process_file(path, existing_filenames):
    filename = path.name
    if filename in existing_filenames:
        return None

    slug = path.stem
    title, year = slug_to_title_and_year(slug)
    print(f"  Processing {filename} → searching '{title}'" + (f" ({year})" if year else ""))

    try:
        movie = tmdb_search(title, year)
    except Exception as e:
        print(f"    TMDb search error: {e}")
        movie = None

    if not movie:
        print(f"    No TMDb result, using slug fallback")
        return {
            "letterboxd_slug": slug,
            "title": title.title(),
            "year": year,
            "director": None,
            "poster": None,
            "filename": filename,
            "date_added": datetime.date.today().isoformat(),
            "duration_seconds": get_duration(path),
            "file_size_bytes": path.stat().st_size,
        }

    return build_entry_from_movie(movie, slug, path)


def reprocess(slug, tmdb_id):
    """Re-fetch TMDb metadata for an existing entry using a specific movie ID."""
    archive = load_archive()
    idx = next((i for i, e in enumerate(archive) if e["letterboxd_slug"] == slug), None)
    if idx is None:
        print(f"No entry found for slug: {slug}")
        sys.exit(1)

    entry = archive[idx]
    audio_path = AUDIO_DIR / entry["filename"]

    print(f"Re-processing '{slug}' with TMDb ID {tmdb_id}…")
    try:
        movie = tmdb_fetch_by_id(tmdb_id)
    except Exception as e:
        print(f"TMDb fetch error: {e}")
        sys.exit(1)

    release_date = movie.get("release_date", "")
    year = int(release_date[:4]) if release_date else None
    poster_path = movie.get("poster_path")
    poster = (TMDB_IMG_BASE + poster_path) if poster_path else None

    try:
        director = tmdb_director(tmdb_id)
    except Exception:
        director = None

    entry["title"] = movie.get("title", slug.replace("-", " ").title())
    entry["year"] = year
    entry["director"] = director
    entry["poster"] = poster

    print(f"  → {entry['title']} ({year}), dir. {director}")
    save_archive(archive)
    print("Archive updated.")


def main():
    archive = load_archive()
    existing_filenames = {e["filename"] for e in archive}

    audio_files = sorted(
        p for p in AUDIO_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS and not p.name.startswith(".")
    )
    present_filenames = {p.name for p in audio_files}

    # Remove entries whose files have been deleted
    kept = [e for e in archive if e["filename"] in present_filenames]
    removed = len(archive) - len(kept)
    if removed:
        print(f"Removed {removed} deleted {'entry' if removed == 1 else 'entries'}.")

    # Backfill file_size_bytes for existing entries that don't have it
    backfilled = 0
    for entry in kept:
        if entry.get("file_size_bytes") is None:
            path = AUDIO_DIR / entry["filename"]
            if path.exists():
                entry["file_size_bytes"] = path.stat().st_size
                backfilled += 1
    if backfilled:
        print(f"Backfilled file_size_bytes for {backfilled} existing {'entry' if backfilled == 1 else 'entries'}.")

    # Add entries for new files
    new_entries = []
    for path in audio_files:
        entry = process_file(path, existing_filenames)
        if entry:
            new_entries.append(entry)

    if new_entries:
        print(f"\nAdded {len(new_entries)} new {'entry' if len(new_entries) == 1 else 'entries'}.")

    if removed or new_entries or backfilled:
        save_archive(kept + new_entries)
    else:
        print("No changes.")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--reprocess":
        reprocess(sys.argv[2], int(sys.argv[3]))
    else:
        main()
