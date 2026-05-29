#!/usr/bin/env python3
"""
Scans audio/ for files not yet in _data/audio_archive.json, fetches
metadata from TMDb, then appends new entries and writes the updated JSON.

Filename convention: <letterboxd-slug>.m4a
Example:             the-godfather.m4a  /  sabrina-1995.m4a

Usage:
  python3 update_audio_archive.py                        # normal scan
  python3 update_audio_archive.py --reprocess <slug> <tmdb_id>
  python3 update_audio_archive.py --check-reviews        # find new LB reviews
"""

import os
import re
import sys
import json
import time
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

LB_USER = "moviemarginalia"
LB_BASE = "https://letterboxd.com"
LB_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; archive-bot/1.0)"}

YEAR_SUFFIX_RE = re.compile(r"^(.*)-(\d{4})$")


def tmdb_headers():
    token = os.environ.get("TMDB_API_KEY")
    if not token:
        raise EnvironmentError("TMDB_API_KEY is not set")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


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


def check_letterboxd_review(slug):
    """Return the review URL if the user has a written review for this slug, else None."""
    url = f"{LB_BASE}/{LB_USER}/film/{slug}/"
    try:
        r = requests.get(url, headers=LB_HEADERS, timeout=10)
        if r.status_code == 200 and "body-text -prose" in r.text:
            return url
    except Exception:
        pass
    return None


def tmdb_search(title, year=None):
    params = {"query": title, "include_adult": False}
    if year:
        params["primary_release_year"] = year
    r = requests.get(f"{TMDB_BASE}/search/movie", headers=tmdb_headers(), params=params, timeout=15)
    r.raise_for_status()
    results = r.json().get("results", [])
    return results[0] if results else None


def tmdb_fetch_by_id(tmdb_id):
    r = requests.get(f"{TMDB_BASE}/movie/{tmdb_id}", headers=tmdb_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def tmdb_director(tmdb_id):
    r = requests.get(f"{TMDB_BASE}/movie/{tmdb_id}/credits", headers=tmdb_headers(), timeout=15)
    r.raise_for_status()
    crew = r.json().get("crew", [])
    directors = [m["name"] for m in crew if m.get("job") == "Director"]
    return directors[0] if directors else None


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

    if movie:
        tmdb_id = movie["id"]
        tmdb_title = movie.get("title", title.title())
        release_date = movie.get("release_date", "")
        tmdb_year = int(release_date[:4]) if release_date else year
        poster_path = movie.get("poster_path")
        poster = (TMDB_IMG_BASE + poster_path) if poster_path else None
        try:
            director = tmdb_director(tmdb_id)
        except Exception:
            director = None
        print(f"    {tmdb_title} ({tmdb_year}), dir. {director}")
    else:
        print(f"    No TMDb result, using slug fallback")
        tmdb_title = title.title()
        tmdb_year = year
        poster = None
        director = None

    print(f"    Checking Letterboxd review…")
    lb_review = check_letterboxd_review(slug)
    print(f"    {'Found' if lb_review else 'No'} review at {LB_BASE}/{LB_USER}/film/{slug}/")

    return {
        "letterboxd_slug": slug,
        "title": tmdb_title,
        "year": tmdb_year,
        "director": director,
        "poster": poster,
        "filename": filename,
        "date_added": datetime.date.today().isoformat(),
        "duration_seconds": get_duration(path),
        "file_size_bytes": path.stat().st_size,
        "letterboxd_review_url": lb_review,
    }


def reprocess(slug, tmdb_id):
    """Re-fetch TMDb metadata for an existing entry using a specific movie ID."""
    archive = load_archive()
    idx = next((i for i, e in enumerate(archive) if e["letterboxd_slug"] == slug), None)
    if idx is None:
        print(f"No entry found for slug: {slug}")
        sys.exit(1)

    entry = archive[idx]
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

    print(f"  Checking Letterboxd review…")
    entry["letterboxd_review_url"] = check_letterboxd_review(slug)

    print(f"  → {entry['title']} ({year}), dir. {director}")
    save_archive(archive)
    print("Archive updated.")


def check_reviews():
    """Check Letterboxd for reviews on entries that currently have none."""
    archive = load_archive()
    pending = [e for e in archive if not e.get("letterboxd_review_url")]

    if not pending:
        print("All entries already have Letterboxd review URLs.")
        return

    print(f"Checking {len(pending)} {'entry' if len(pending) == 1 else 'entries'} with no review link…")
    updated = 0
    for entry in pending:
        slug = entry["letterboxd_slug"]
        print(f"  '{slug}'…", end=" ", flush=True)
        url = check_letterboxd_review(slug)
        if url:
            entry["letterboxd_review_url"] = url
            print("found.")
            updated += 1
        else:
            print("none.")
        time.sleep(0.5)

    if updated:
        save_archive(archive)
        print(f"\nUpdated {updated} {'entry' if updated == 1 else 'entries'}.")
    else:
        print("No new reviews found.")


def main():
    archive = load_archive()
    existing_filenames = {e["filename"] for e in archive}

    audio_files = sorted(
        p for p in AUDIO_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS and not p.name.startswith(".")
    )
    present_filenames = {p.name for p in audio_files}

    kept = [e for e in archive if e["filename"] in present_filenames]
    removed = len(archive) - len(kept)
    if removed:
        print(f"Removed {removed} deleted {'entry' if removed == 1 else 'entries'}.")

    backfilled = 0
    for entry in kept:
        if entry.get("file_size_bytes") is None:
            path = AUDIO_DIR / entry["filename"]
            if path.exists():
                entry["file_size_bytes"] = path.stat().st_size
                backfilled += 1

    lb_checked = 0
    for entry in kept:
        if "letterboxd_review_url" not in entry:
            slug = entry["letterboxd_slug"]
            print(f"  Checking Letterboxd review for '{slug}'…")
            entry["letterboxd_review_url"] = check_letterboxd_review(slug)
            lb_checked += 1
            time.sleep(0.5)

    if backfilled:
        print(f"Backfilled file_size_bytes for {backfilled} existing {'entry' if backfilled == 1 else 'entries'}.")
    if lb_checked:
        print(f"Backfilled letterboxd_review_url for {lb_checked} existing {'entry' if lb_checked == 1 else 'entries'}.")

    new_entries = []
    for path in audio_files:
        entry = process_file(path, existing_filenames)
        if entry:
            new_entries.append(entry)
            time.sleep(0.5)

    if new_entries:
        print(f"\nAdded {len(new_entries)} new {'entry' if len(new_entries) == 1 else 'entries'}.")

    if removed or new_entries or backfilled or lb_checked:
        save_archive(kept + new_entries)
    else:
        print("No changes.")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--reprocess":
        reprocess(sys.argv[2], int(sys.argv[3]))
    elif len(sys.argv) == 2 and sys.argv[1] == "--check-reviews":
        check_reviews()
    else:
        main()
