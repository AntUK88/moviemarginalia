#!/usr/bin/env python3
"""
import_review.py
----------------
Given a Letterboxd review URL, scrapes the review text and creates
a Jekyll post in _selected/ ready to appear on the Selected Pieces page.
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

SPOILER_WARNING = "This review may contain spoilers. I can handle the truth."


def fetch_page(url):
    session = requests.Session()
    session.get("https://letterboxd.com/", headers=HEADERS, timeout=15)

    if not url.endswith("/"):
        url = url + "/"

    # Try spoiler-bypass URL first
    spoiler_url = url + "reveal-spoilers/"
    r = session.get(spoiler_url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        r = session.get(url, headers=HEADERS, timeout=15)

    r.raise_for_status()
    canonical = r.url.replace("reveal-spoilers/", "")
    return r.text, canonical


def html_to_markdown(element):
    """Convert an HTML element's contents to markdown, preserving italics."""
    result = []
    for node in element.children:
        if hasattr(node, 'name'):
            text = node.get_text()
            if node.name in ('em', 'i'):
                result.append(f"*{text}*")
            elif node.name in ('strong', 'b'):
                result.append(f"**{text}**")
            else:
                result.append(text)
        else:
            # Plain text node
            result.append(str(node))
    # Clean up non-breaking spaces
    return "".join(result).replace("\u00a0", " ").strip()


def parse_review(html, url):
    soup = BeautifulSoup(html, "html.parser")

    # --- Film title: h2.primaryname.prettify > a ---
    film_title = "Unknown Film"
    title_el = soup.select_one("h2.primaryname a") or soup.select_one("h2.prettify a")
    if title_el:
        film_title = title_el.get_text(strip=True)

    # --- Film year: span.releasedate > a ---
    film_year = ""
    year_el = soup.select_one("span.releasedate a") or soup.select_one("span.releasedate")
    if year_el:
        film_year = year_el.get_text(strip=True).strip("()")

    # --- Star rating ---
    rating_text = ""
    for sel in ["span.rating", ".js-review-rating", ".review-rating span"]:
        el = soup.select_one(sel)
        if el:
            rating_text = el.get_text(strip=True)
            if rating_text:
                break

    # --- Review date ---
    review_date = datetime.today().strftime("%Y-%m-%d")
    for sel in ["time[datetime]", "span.date time", "._nobr time"]:
        el = soup.select_one(sel)
        if el and el.get("datetime"):
            raw = el["datetime"][:10]
            if re.match(r"\d{4}-\d{2}-\d{2}", raw):
                review_date = raw
                break

    # --- Review body ---
    body_el = (
        soup.select_one(".js-review-body")
        or soup.select_one(".review .body-text")
        or soup.select_one("div.body-text")
    )

    if not body_el:
        raise ValueError("Could not find review body.")

    # Remove spoiler banners
    for el in body_el.select(".contains-spoilers, .spoiler-warning"):
        el.decompose()

    # Convert paragraphs to markdown, preserving italics/bold
    paragraphs = []
    for p in body_el.find_all("p"):
        text = html_to_markdown(p)
        text = text.replace(SPOILER_WARNING, "").strip()
        if text:
            paragraphs.append(text)

    if not paragraphs:
        raw = body_el.get_text(separator="\n").strip()
        raw = raw.replace(SPOILER_WARNING, "").replace("\u00a0", " ").strip()
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

    front_matter_parts = [
        "---",
        "layout: post",
        f'title: "{data["film_title"]}"',
    ]
    if data["film_year"]:
        front_matter_parts.append(f'year: "{data["film_year"]}"')
    if data["rating"]:
        front_matter_parts.append(f'rating: "{data["rating"]}"')
    front_matter_parts += [
        f'date: {data["date"]}',
        f'letterboxd: "{data["letterboxd_url"]}"',
        "categories: selected",
        "---",
    ]

    front_matter = "\n".join(front_matter_parts)
    footer = (
        f'\n\n---\n\n*Originally published on '
        f'[Letterboxd]({data["letterboxd_url"]}).*'
    )

    return filename, front_matter + "\n\n" + data["body"] + footer


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/import_review.py <letterboxd-review-url>")
        sys.exit(1)

    url = sys.argv[1].strip()
    if "letterboxd.com" not in url:
        print("Error: URL must be a Letterboxd URL")
        sys.exit(1)

    print(f"Fetching: {url}")
    html, canonical_url = fetch_page(url)

    print("Parsing review...")
    data = parse_review(html, canonical_url)

    print(f"  Film:   {data['film_title']} ({data['film_year']})")
    print(f"  Rating: {data['rating']}")
    print(f"  Date:   {data['date']}")
    print(f"  Words:  {len(data['body'].split())}")

    if data['film_title'] == "Unknown Film":
        print("WARNING: Could not find film title.")
    if len(data['body'].split()) < 5:
        print("WARNING: Review body very short — spoiler wall may still be blocking.")

    filename, content = build_jekyll_post(data)

    output_dir = Path("_selected")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / filename

    if output_path.exists():
        print(f"Note: overwriting {output_path}")

    output_path.write_text(content, encoding="utf-8")
    print(f"\nCreated: {output_path}")
    print("\n--- Preview ---")
    print(content[:600])
    print("...")


if __name__ == "__main__":
    main()
