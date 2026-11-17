# Parts of this file written with help from Claude.
import csv
import os
import re

import requests

PAGE_SIZE = 3500  # about one comfortable screen of text

# The Project Gutenberg catalog: a list of all ~75,000 free books
CATALOG_URL = "https://aleph.pglaf.org/cache/epub/feeds/pg_catalog.csv"
CATALOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pg_catalog.csv")

# Remembered after the first time
catalog = {}
pages_cache = {}

# "CHAPTER I", "Chapter 1", "I", "Letter 1", "Stave One"... = the real start of a book
FIRST_CHAPTER = re.compile(
    r"^(?:(?:chapter|letter|stave|book|part|volume)\s+)?(?:i|1|one)(?:[.:\s].*)?$"
)
# a line made only of dashes, stars or underscores = a break between scenes
DIVIDER = re.compile(r"^[\s\-*_=~.]{3,}$")


def clean_title(title):
    """'The Picture of Dorian Gray: a novel' -> 'picture of dorian gray'"""
    title = title.lower().replace("’", "'")
    title = re.split(r"[:;(\n\r]", title)[0]
    title = re.sub(r"[^a-z0-9' ]", " ", title)
    title = re.sub(r"^(the|a|an) ", "", title.strip())
    return " ".join(title.split())


def nice_author(authors):
    """'Fitzgerald, F. Scott (Francis Scott), 1896-1940' -> 'F. Scott Fitzgerald'"""
    first = re.sub(r"\s*\(.*?\)", "", authors.split(";")[0])
    parts = [p.strip() for p in first.split(",") if p.strip() and not any(ch.isdigit() for ch in p)]
    if len(parts) >= 2:
        return parts[1] + " " + parts[0]
    return parts[0] if parts else "Unknown"


def load_catalog():
    """Read the Project Gutenberg catalog once and remember it"""
    if catalog:
        return
    if not os.path.exists(CATALOG_FILE):
        response = requests.get(CATALOG_URL, timeout=120)
        response.raise_for_status()
        with open(CATALOG_FILE, "wb") as file:
            file.write(response.content)

    with open(CATALOG_FILE, encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("Type") != "Text" or "en" not in row.get("Language", ""):
                continue
            key = clean_title(row["Title"])
            if not key:
                continue
            book_id = int(row["Text#"])
            # many editions of one book: keep the oldest (usually the classic one)
            if key not in catalog or book_id < catalog[key]["id"]:
                catalog[key] = {
                    "id": book_id,
                    "title": row["Title"].split("\n")[0].strip(),
                    "author": nice_author(row.get("Authors", "")),
                }


def find_free_book(title):
    """Find a free public-domain copy of this book on Project Gutenberg"""
    load_catalog()
    found = catalog.get(clean_title(title))
    if not found:
        return None
    return {
        "id": found["id"],
        "title": found["title"],
        "author": found["author"],
        "url": f"https://aleph.pglaf.org/cache/epub/{found['id']}/pg{found['id']}.txt",
    }


def skip_front_matter(paragraphs):
    """Start the book at chapter one, without the title page and table of contents"""
    for i, paragraph in enumerate(paragraphs):
        line = paragraph["text"].lower()
        if len(line) > 60 or not FIRST_CHAPTER.match(line) or line.startswith("i ii"):
            continue
        # a real chapter is followed by real text, a table of contents is not
        following = paragraphs[i + 1:i + 6]
        if any(len(p["text"]) > 200 for p in following):
            return paragraphs[i:]
    return paragraphs


def load_pages(book):
    """Download the text and cut it into pages of paragraphs"""
    if book["id"] in pages_cache:
        return pages_cache[book["id"]]

    response = requests.get(book["url"], timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"
    text = response.text.replace("\r\n", "\n")

    # Keep only the book itself, without the Project Gutenberg header and license
    start = re.search(r"\*\*\* ?START OF.*?\*\*\*", text)
    if start:
        text = text[start.end():]
    end = re.search(r"\*\*\* ?END OF", text)
    if end:
        text = text[:end.start()]

    # Paragraphs are separated by empty lines
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        line = " ".join(block.split())
        if not line:
            continue
        if DIVIDER.match(line):
            paragraphs.append({"text": "", "heading": False, "divider": True})
            continue
        heading = len(line) < 60 and (
            line.isupper() or line.lower().startswith(("chapter", "book ", "part ", "letter ", "stave "))
        )
        paragraphs.append({"text": line, "heading": heading, "divider": False})

    paragraphs = skip_front_matter(paragraphs)

    # Group paragraphs into pages; a new chapter starts a new page
    pages = []
    page = []
    size = 0
    for paragraph in paragraphs:
        if paragraph["heading"] and size > PAGE_SIZE * 0.4:
            pages.append(page)
            page = []
            size = 0
        page.append(paragraph)
        size += len(paragraph["text"])
        if size >= PAGE_SIZE:
            pages.append(page)
            page = []
            size = 0
    if page:
        pages.append(page)

    pages_cache[book["id"]] = pages
    return pages
