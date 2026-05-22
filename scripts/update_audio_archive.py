#!/usr/bin/env python3
"""
update_audio_archive.py
-----------------------
Scans audio/ for files not yet in _data/audio_archive.json, fetches
metadata from TMDb, then appends new entries and writes the updated JSON.

Filename convention: <imdb_id> <Title> <Year>.<ext>
Example:             tt0068646 The Godfather 1972.m4a
"""

import os
import re
import json
import datetime
from pathlib import Path

import requests
from mutagen import File as MutagenFile

REPO_ROOT = Path(__file__).parent.parent
AUDIO_DIR = REPO_ROOT / "audio"
ARCHIVE_PATH = REPO_ROOT / "_data" / "audio_archive.json"

TMDB_API_KEY = os.environ["TMDB_API_KEY"]
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w185"

AUDIO_EXTENSIONS = {".m4a", ".mp3", ".ogg", ".opus", ".wav", ".aac", ".flac"}
IMDB_RE = re.compile(r"^(tt\d+)")


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


def tmdb_find(imdb_id):
    url = f"{TMDB_BASE}/find/{imdb_id}"
    r = requests.get(
        url,
        params={"api_key": TMDB_API_KEY, "external_source": "imdb_id"},
        timeout=15,
    )
    r.raise_for_status()
    results = r.json().get("movie_results", [])
    return results[0] if results else None


def tmdb_director(tmdb_id):
    url = f"{TMDB_BASE}/movie/{tmdb_id}/credits"
    r = requests.get(url, params={"api_key": TMDB_API_KEY}, timeout=15)
    r.raise_for_status()
    crew = r.json().get("crew", [])
    directors = [m["name"] for m in crew if m.get("job") == "Director"]
    return directors[0] if directors else None


def process_file(path, existing_filenames):
    filename = path.name
    if filename in existing_filenames:
        return None

    stem = path.stem
    m = IMDB_RE.match(stem)
    if not m:
        print(f"  Skipping {filename}: no IMDb ID prefix")
        return None

    imdb_id = m.group(1)
    print(f"  Processing {filename} ({imdb_id})")

    movie = tmdb_find(imdb_id)

    if not movie:
        print(f"    No TMDb result for {imdb_id}, using filename fallback")
        remainder = stem[len(imdb_id):].strip()
        year_m = re.search(r"\b(\d{4})\b", remainder)
        year = int(year_m.group(1)) if year_m else None
        title = re.sub(r"\s*\d{4}\s*$", "", remainder).strip()
        return {
            "imdb_id": imdb_id,
            "title": title,
            "year": year,
            "director": None,
            "poster": None,
            "filename": filename,
            "date_added": datetime.date.today().isoformat(),
            "duration_seconds": get_duration(path),
        }

    tmdb_id = movie["id"]
    title = movie.get("title", "")
    release_date = movie.get("release_date", "")
    year = int(release_date[:4]) if release_date else None
    poster_path = movie.get("poster_path")
    poster = (TMDB_IMG_BASE + poster_path) if poster_path else None
    director = tmdb_director(tmdb_id)

    print(f"    {title} ({year}), dir. {director}")
    return {
        "imdb_id": imdb_id,
        "title": title,
        "year": year,
        "director": director,
        "poster": poster,
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
