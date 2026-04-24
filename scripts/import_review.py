#!/usr/bin/env python3
"""
import_review.py
----------------
Given a Letterboxd review URL, scrapes the review text and creates
a Jekyll post in _selected/ ready to appear on the Selected Pieces page.

Usage:
    python3 scripts/import_review.py https://letterboxd.com/moviemarginalia/film/little-buddha/

How it works:
    1. Fetches the page with browser-like headers
    2. Parses the review body, film title, rating, and date
    3. Strips the spoiler warning banner if present
    4. Writes a Jekyll Markdown post to _selected/YYYY-MM-DD-slug.md
"""

import sys
import re
import os
from datetime import datetime
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing dependencies...")
    os.system("pip install requests beautifulsoup4 -q")
    import requests
    from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://letterboxd.com/",
}

# Spoiler warning text Letterboxd prepends — strip it
SPOILER_WARNING = "This review may contain spoilers. I can handle the truth."


def fetch_page(url):
    session = requests.Session()
    # Warm up with a homepage visit to get cookies
    session.get("https://letterboxd.com/", headers=HEADERS, timeout=15)
    r = session.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.text


def parse_review(html, url):
    soup = BeautifulSoup(html, "html.parser")

    # --- Film title ---
    title_el = (
        soup.select_one("h1.headline-1 a")
        or soup.select_one(".film-title-wrapper h1")
        or soup.select_one("h1.headline-1")
    )
    film_title = title_el.get_text(strip=True) if title_el else "Unknown Film"

    # --- Film year ---
    year_el = soup.select_one("h1.headline-1 small") or soup.select_one(".film-title-wrapper small")
    film_year = year_el.get_text(strip=True).strip("()") if year_el else ""

    # --- Star rating ---
    rating_el = soup.select_one(".rating .rating") or soup.select_one("span.rating")
    rating_text = rating_el.get_text(strip=True) if rating_el else ""

    # --- Review date ---
    date_el = soup.select_one("time.date") or soup.select_one("span._nobr time")
    if date_el and date_el.get("datetime"):
        raw_date = date_el["datetime"][:10]  # YYYY-MM-DD
        review_date = raw_date
    else:
        review_date = datetime.today().strftime("%Y-%m-%d")

    # --- Review body ---
    body_el = (
        soup.select_one(".review .body-text")
        or soup.select_one("div.body-text")
        or soup.select_one(".js-review-body")
    )

    if not body_el:
        raise ValueError("Could not find review body. The page structure may have changed.")

    # Remove spoiler toggle button/banner if present
    for el in body_el.select(".contains-spoilers, .spoiler-warning, p.contains-spoilers"):
        el.decompose()

    # Get paragraphs as plain text, preserve line breaks
    paragraphs = []
    for p in body_el.find_all("p"):
        text = p.get_text(separator="\n").strip()
        # Strip the spoiler warning sentence if it crept in
        text = text.replace(SPOILER_WARNING, "").strip()
        if text:
            paragraphs.append(text)

    if not paragraphs:
        # Fallback: just get all text
        raw = body_el.get_text(separator="\n").strip()
        raw = raw.replace(SPOILER_WARNING, "").strip()
        paragraphs = [raw]

    review_body = "\n\n".join(paragraphs)

    return {
        "film_title": film_title,
        "film_year": film_year,
        "rating": rating_text,
        "date": review_date,
        "body": review_body,
        "letterboxd_url": url,
    }


def slugify(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def build_jekyll_post(data):
    slug = slugify(data["film_title"])
    filename = f"{data['date']}-{slug}.md"

    rating_line = f'rating: "{data["rating"]}"' if data["rating"] else ""
    year_line = f'year: "{data["film_year"]}"' if data["film_year"] else ""

    front_matter_parts = [
        "---",
        "layout: post",
        f'title: "{data["film_title"]}"',
    ]
    if year_line:
        front_matter_parts.append(year_line)
    if rating_line:
        front_matter_parts.append(rating_line)
    front_matter_parts += [
        f'date: {data["date"]}',
        f'letterboxd: "{data["letterboxd_url"]}"',
        "categories: selected",
        "---",
    ]

    front_matter = "\n".join(front_matter_parts)
    body = data["body"]

    footer = (
        f'\n\n---\n\n*Originally published on '
        f'[Letterboxd]({data["letterboxd_url"]}).*'
    )

    return filename, front_matter + "\n\n" + body + footer


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/import_review.py <letterboxd-review-url>")
        sys.exit(1)

    url = sys.argv[1].strip()
    if "letterboxd.com" not in url:
        print("Error: URL must be a Letterboxd URL")
        sys.exit(1)

    print(f"Fetching: {url}")
    html = fetch_page(url)

    print("Parsing review...")
    data = parse_review(html, url)

    print(f"  Film:   {data['film_title']} ({data['film_year']})")
    print(f"  Rating: {data['rating']}")
    print(f"  Date:   {data['date']}")
    print(f"  Words:  {len(data['body'].split())}")

    filename, content = build_jekyll_post(data)

    output_dir = Path("_selected")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / filename

    if output_path.exists():
        print(f"Warning: {output_path} already exists — overwriting.")

    output_path.write_text(content, encoding="utf-8")
    print(f"\nCreated: {output_path}")
    print("\n--- Preview ---")
    print(content[:600])
    print("...")


if __name__ == "__main__":
    main()
