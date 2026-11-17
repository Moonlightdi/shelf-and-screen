# Parts of this file written with help from Claude.
import hmac
import json
import os
import random
import re
import secrets
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, redirect, render_template, request, url_for
import requests

from gutenberg import find_free_book, load_pages
from moods import MOODS, detect_mood, get_films
from palette import get_palette

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NOTES_DB = os.path.join(BASE_DIR, "notes.db")
CACHE_FILE = os.path.join(BASE_DIR, "cache.json")

# The secret key for the admin page: set it with   export ADMIN_KEY=your-secret-word
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")

# A note disappears after this many readers report it
REPORTS_TO_HIDE = 3

# Words that are not allowed on the margins (add more if you need)
BAD_WORDS = re.compile(
    r"(fuck|shit|bitch|cunt|pussy|whore|slut|nigg|fag|retard|"
    r"хуй|хуе|хуё|пизд|ебат|ебан|ёбан|бляд|блят|сука|суки|мудак|гандон|пидор|пидар|шлюх|долбо)",
    re.IGNORECASE
)

# Books for the "tonight's picks" shelf on the home page: (title, author)
FEATURED_BOOKS = [
    ("Little Women", "Louisa May Alcott"),
    ("Pride and Prejudice", "Jane Austen"),
    ("Jane Eyre", "Charlotte Brontë"),
    ("The Little Prince", "Antoine de Saint-Exupéry"),
    ("Dracula", "Bram Stoker"),
    ("The Great Gatsby", "F. Scott Fitzgerald"),
    ("Anna Karenina", "Leo Tolstoy"),
    ("Alice's Adventures in Wonderland", "Lewis Carroll"),
]

# The secret shelf: it only appears after midnight
NIGHT_BOOKS = [
    ("Frankenstein", "Mary Shelley"),
    ("Carmilla", "Joseph Sheridan Le Fanu"),
    ("The Strange Case of Dr. Jekyll and Mr. Hyde", "Robert Louis Stevenson"),
    ("The Turn of the Screw", "Henry James"),
    ("The Picture of Dorian Gray", "Oscar Wilde"),
    ("The Hound of the Baskervilles", "Arthur Conan Doyle"),
]

# Blind dates with a book: (title, author, three hints). All of them are free to read.
BLIND_DATES = [
    ("Pride and Prejudice", "Jane Austen", ["ballrooms", "first impressions", "a slow burn"]),
    ("Jane Eyre", "Charlotte Brontë", ["an orphan", "a locked attic", "a fierce heart"]),
    ("Frankenstein", "Mary Shelley", ["lightning", "loneliness", "who is the monster?"]),
    ("The Secret Garden", "Frances Hodgson Burnett", ["a hidden door", "roses", "healing"]),
    ("Little Women", "Louisa May Alcott", ["four sisters", "winter", "growing up"]),
    ("Alice's Adventures in Wonderland", "Lewis Carroll", ["a rabbit hole", "a tea party", "nonsense"]),
    ("Anne of Green Gables", "L. M. Montgomery", ["red braids", "big words", "a new home"]),
    ("The Picture of Dorian Gray", "Oscar Wilde", ["a portrait", "beauty", "a secret sin"]),
    ("Treasure Island", "Robert Louis Stevenson", ["a map", "pirates", "the sea"]),
    ("Peter Pan", "J. M. Barrie", ["an open window", "flying", "never growing up"]),
    ("The Wonderful Wizard of Oz", "L. Frank Baum", ["a storm", "silver shoes", "going home"]),
    ("The Adventures of Sherlock Holmes", "Arthur Conan Doyle", ["fog", "clues", "a violin"]),
    ("Gitanjali", "Rabindranath Tagore", ["songs", "prayer", "the infinite"]),
    ("The Prophet", "Kahlil Gibran", ["a ship", "a farewell", "wisdom"]),
]

# Things we already found are remembered, so pages open faster.
# Books are also saved to cache.json, so the site remembers them even after a restart.
readable_cache = {}
last_note_time = {}
cache_lock = threading.RLock()


def load_cache():
    """Read the books we remembered last time"""
    try:
        with open(CACHE_FILE) as file:
            saved = json.load(file)
        return saved.get("search", {}), saved.get("books", {})
    except (OSError, ValueError):
        return {}, {}


def save_cache():
    """Write the remembered books to cache.json"""
    with cache_lock:
        data = json.dumps({"search": search_cache, "books": book_cache})
        temporary = CACHE_FILE + ".tmp"
        with open(temporary, "w") as file:
            file.write(data)
        os.replace(temporary, CACHE_FILE)


search_cache, book_cache = load_cache()


def clean_description(text):
    """Remove Open Library's extra notes and links from a description"""
    text = re.split(r"\s*(?:\\?-{2,}|\(\[source\]|Also contained in)", text)[0]
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip() or "No description yet."


def search_book(title, author):
    """Find one book on Open Library by title and author (remembered after the first time)"""
    key = title + "|" + author
    if key in search_cache:
        return search_cache[key]

    try:
        response = requests.get(
            "https://openlibrary.org/search.json",
            params={"title": title, "author": author, "limit": 1, "fields": "key,title,cover_i"},
            timeout=10
        )
        response.raise_for_status()
        doc = response.json()["docs"][0]
    except (requests.RequestException, IndexError, KeyError, ValueError):
        return None

    if not doc.get("cover_i"):
        return None

    found = {
        "id": doc["key"].split("/")[-1],
        "title": title,
        "author": author,
        "cover": f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg"
    }
    with cache_lock:
        search_cache[key] = found
        save_cache()
    return found


def get_shelf(books):
    """A list of (title, author) -> a list of books with covers.
    All the books are asked for at the same time, not one by one, so the page opens fast."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        found = list(pool.map(lambda book: search_book(*book), books))
    return [book for book in found if book]


def get_book(work_id):
    """Everything about one book: description, cover, palette and mood"""
    if work_id in book_cache:
        return book_cache[work_id]

    response = requests.get(
        f"https://openlibrary.org/works/{work_id}.json",
        timeout=15
    )
    response.raise_for_status()
    work = response.json()

    description = work.get("description", "No description yet.")
    if isinstance(description, dict):
        description = description.get("value", "")

    covers = [c for c in work.get("covers", []) if c and c > 0]
    cover = f"https://covers.openlibrary.org/b/id/{covers[0]}-L.jpg" if covers else None

    palette = []
    if cover:
        try:
            palette = get_palette(cover)
        except Exception:
            palette = []

    mood_key = detect_mood(palette) if palette else None

    info = {
        "id": work_id,
        "title": work.get("title", "Untitled"),
        "description": clean_description(description),
        "cover": cover,
        "palette": palette,
        "mood_key": mood_key,
    }
    with cache_lock:
        book_cache[work_id] = info
        save_cache()
    return info


def find_readable(work_id):
    """A free copy of this book on Project Gutenberg, or None"""
    if work_id in readable_cache:
        return readable_cache[work_id]

    info = get_book(work_id)
    found = find_free_book(info["title"])
    readable_cache[work_id] = found
    return found


def notes_db():
    """Open the database of margin notes and visits (and create it the first time)"""
    db = sqlite3.connect(NOTES_DB)
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_id TEXT NOT NULL,
            paragraph INTEGER NOT NULL,
            text TEXT NOT NULL,
            place TEXT,
            created TEXT NOT NULL,
            reports INTEGER NOT NULL DEFAULT 0
        )
    """)
    # notes made before reports existed get the new column
    columns = [row["name"] for row in db.execute("PRAGMA table_info(notes)")]
    if "reports" not in columns:
        db.execute("ALTER TABLE notes ADD COLUMN reports INTEGER NOT NULL DEFAULT 0")
    db.execute("CREATE INDEX IF NOT EXISTS notes_by_book ON notes (work_id, paragraph)")

    # anonymous events for the counter: who = a random id from a cookie, never a name or an address
    db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            visitor TEXT NOT NULL,
            kind TEXT NOT NULL
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS events_by_day ON events (day, kind)")
    return db


def count(kind):
    """Remember that something happened: a visit, a page read, an unwrapped blind date..."""
    visitor = request.cookies.get("reader") or getattr(request, "new_reader", "")
    db = notes_db()
    db.execute(
        "INSERT INTO events (day, visitor, kind) VALUES (?, ?, ?)",
        (datetime.now(timezone.utc).date().isoformat(), visitor, kind)
    )
    db.commit()
    db.close()


@app.before_request
def give_reader_id():
    """Every new reader gets a random anonymous id, so we can count readers without knowing who they are"""
    if not request.cookies.get("reader"):
        request.new_reader = secrets.token_hex(8)


@app.after_request
def save_reader_id(response):
    new_reader = getattr(request, "new_reader", None)
    if new_reader:
        response.set_cookie("reader", new_reader, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return response


def is_admin(key):
    return bool(ADMIN_KEY) and hmac.compare_digest(key or "", ADMIN_KEY)


def warm_up():
    """When the site starts, quietly prepare the home page books and their colors"""
    shelf = get_shelf(FEATURED_BOOKS + NIGHT_BOOKS)
    for book in shelf:
        try:
            get_book(book["id"])
        except requests.RequestException:
            pass


threading.Thread(target=warm_up, daemon=True).start()


@app.route("/")
def index():
    count("visit")
    return render_template(
        "index.html",
        books=get_shelf(FEATURED_BOOKS),
        night_books=get_shelf(NIGHT_BOOKS)
    )


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()

    if not q:
        return index()

    try:
        response = requests.get(
            "https://openlibrary.org/search.json",
            params={"title": q, "limit": 12},
            timeout=20
        )
        response.raise_for_status()
        docs = response.json().get("docs", [])
    except requests.RequestException:
        return render_template("results.html", books=[], query=q, error=True)

    books = []

    for doc in docs:
        if not doc.get("cover_i"):
            continue

        books.append({
            "id": doc["key"].split("/")[-1],
            "title": doc.get("title", "Untitled"),
            "author": ", ".join(doc.get("author_name", ["Unknown author"])),
            "year": doc.get("first_publish_year"),
            "cover": f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg"
        })

    return render_template("results.html", books=books, query=q, error=False)


@app.route("/book/<work_id>")
def book(work_id):
    try:
        info = get_book(work_id)
    except requests.RequestException:
        return render_template("message.html", title="The book got lost in the dark",
                               text="Open Library didn't answer. Please try again in a moment.")

    count("book")
    mood = MOODS[info["mood_key"]] if info["mood_key"] else None
    films = get_films(info["mood_key"]) if info["mood_key"] else []

    return render_template(
        "book.html",
        title=info["title"],
        description=info["description"],
        cover=info["cover"],
        palette=info["palette"],
        mood=mood,
        films=films,
        work_id=work_id
    )


@app.route("/read/<work_id>")
def read(work_id):
    """A cozy reading page for free public-domain books"""
    try:
        info = get_book(work_id)
        free = find_readable(work_id)
    except requests.RequestException:
        return render_template("message.html", title="The book got lost in the dark",
                               text="We couldn't open this book. Please try again in a moment.")

    if not free:
        return render_template("read.html", info=info, free=None, work_id=work_id)

    try:
        pages = load_pages(free)
    except requests.RequestException:
        return render_template("message.html", title="The pages got lost in the dark",
                               text="We couldn't load the text of this book. Please try again in a moment.")

    page = request.args.get("page", 1, type=int)
    page = max(1, min(page, len(pages)))
    count("read")

    # Every paragraph of the book has its own number, so notes stay in the right place
    offset = sum(len(p) for p in pages[:page - 1])

    return render_template(
        "read.html",
        info=info,
        free=free,
        paragraphs=pages[page - 1],
        offset=offset,
        page=page,
        total=len(pages),
        work_id=work_id,
        has_page="page" in request.args
    )


@app.route("/blind")
def blind():
    """A blind date with a book: three hints, a melody, and a wrapped cover"""
    skip = request.args.get("skip", "")
    choices = [date for date in BLIND_DATES if date[0] != skip]
    random.shuffle(choices)

    for title, author, hints in choices[:4]:
        found = search_book(title, author)
        if not found:
            continue
        try:
            info = get_book(found["id"])
        except requests.RequestException:
            continue
        mood = MOODS[info["mood_key"]] if info["mood_key"] else None
        count("blind")
        return render_template("blind.html", book=found, info=info, hints=hints, mood=mood)

    return render_template("message.html", title="All the dates are asleep",
                           text="We couldn't wrap a book right now. Please try again in a moment.")


@app.route("/shelf")
def shelf():
    count("shelf")
    return render_template("shelf.html")


@app.route("/api/readable/<work_id>")
def api_readable(work_id):
    """Tells the book page if this book can be read for free"""
    try:
        free = find_readable(work_id)
    except requests.RequestException:
        free = None
    return jsonify({"readable": free is not None})


@app.route("/api/book/<work_id>")
def api_book(work_id):
    """Short info about a book, used by the "+" button to add it to the shelf"""
    try:
        info = get_book(work_id)
    except requests.RequestException:
        return jsonify({"error": "could not load this book"}), 502

    return jsonify({
        "id": info["id"],
        "title": info["title"],
        "cover": info["cover"],
        "palette": info["palette"],
        "mood": MOODS[info["mood_key"]]["name"] if info["mood_key"] else ""
    })


@app.route("/api/event/<kind>", methods=["POST"])
def api_event(kind):
    """Small things that happen in the browser: unwrapping a blind date, downloading a sky poster"""
    if kind in ("unwrap", "poster", "sound"):
        count(kind)
    return jsonify({"ok": True})


@app.route("/api/notes/<work_id>", methods=["GET"])
def get_notes(work_id):
    """All margin notes for a range of paragraphs of one book"""
    start = request.args.get("start", 0, type=int)
    end = request.args.get("end", 0, type=int)

    db = notes_db()
    rows = db.execute(
        "SELECT id, paragraph, text, place, created FROM notes "
        "WHERE work_id = ? AND paragraph BETWEEN ? AND ? AND reports < ? ORDER BY created",
        (work_id, start, end, REPORTS_TO_HIDE)
    ).fetchall()
    db.close()

    notes = {}
    for row in rows:
        notes.setdefault(str(row["paragraph"]), []).append({
            "id": row["id"],
            "text": row["text"],
            "place": row["place"],
            "created": row["created"],
        })
    return jsonify({"notes": notes})


@app.route("/api/notes/<work_id>", methods=["POST"])
def add_note(work_id):
    """Leave an anonymous note on the margin of a paragraph"""
    data = request.get_json(silent=True) or {}
    text = " ".join(str(data.get("text", "")).split())
    place = " ".join(str(data.get("place", "")).split())[:40]
    paragraph = data.get("paragraph")

    if not isinstance(paragraph, int) or paragraph < 0:
        return jsonify({"error": "unknown paragraph"}), 400
    if not 1 <= len(text) <= 140:
        return jsonify({"error": "a note must be 1 to 140 characters"}), 400
    if re.search(r"https?://|www\.", text, re.IGNORECASE):
        return jsonify({"error": "links are not allowed in notes"}), 400
    if BAD_WORDS.search(text) or BAD_WORDS.search(place):
        return jsonify({"error": "let's keep the margins kind ☾"}), 400

    # One note every 10 seconds from one person, so nobody can flood the margins
    visitor = request.cookies.get("reader") or request.headers.get("X-Forwarded-For", request.remote_addr or "")
    now = time.time()
    if now - last_note_time.get(visitor, 0) < 10:
        return jsonify({"error": "take a breath and try again in a few seconds"}), 429
    last_note_time[visitor] = now

    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db = notes_db()
    cursor = db.execute(
        "INSERT INTO notes (work_id, paragraph, text, place, created) VALUES (?, ?, ?, ?, ?)",
        (work_id, paragraph, text, place, created)
    )
    note_id = cursor.lastrowid
    db.commit()
    db.close()
    count("note")

    return jsonify({"note": {"id": note_id, "text": text, "place": place, "created": created}})


@app.route("/api/notes/report/<int:note_id>", methods=["POST"])
def report_note(note_id):
    """A reader thinks a note is unkind: after a few reports it disappears"""
    db = notes_db()
    db.execute("UPDATE notes SET reports = reports + 1 WHERE id = ?", (note_id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/admin")
def admin():
    """Diana's page: how many readers came, and all the notes (with a delete button)"""
    key = request.args.get("key", "")
    if not is_admin(key):
        return render_template("message.html", title="Nothing here ☾",
                               text="This page is only for the keeper of the library."), 404

    db = notes_db()
    week_ago = (datetime.now(timezone.utc).date() - timedelta(days=6)).isoformat()

    def number(sql, *args):
        return db.execute(sql, args).fetchone()[0]

    stats = {
        "readers": number("SELECT COUNT(DISTINCT visitor) FROM events"),
        "readers_week": number("SELECT COUNT(DISTINCT visitor) FROM events WHERE day >= ?", week_ago),
        "pages_read": number("SELECT COUNT(*) FROM events WHERE kind = 'read'"),
        "books_opened": number("SELECT COUNT(*) FROM events WHERE kind = 'book'"),
        "unwrapped": number("SELECT COUNT(*) FROM events WHERE kind = 'unwrap'"),
        "posters": number("SELECT COUNT(*) FROM events WHERE kind = 'poster'"),
        "notes": number("SELECT COUNT(*) FROM notes WHERE reports < ?", REPORTS_TO_HIDE),
        "places": number("SELECT COUNT(DISTINCT place) FROM notes WHERE place != ''"),
    }
    days = db.execute(
        "SELECT day, COUNT(DISTINCT visitor) AS readers FROM events "
        "WHERE day >= ? GROUP BY day ORDER BY day", (week_ago,)
    ).fetchall()
    notes = db.execute(
        "SELECT id, work_id, text, place, created, reports FROM notes ORDER BY reports DESC, created DESC LIMIT 200"
    ).fetchall()
    db.close()

    return render_template("admin.html", stats=stats, days=days, notes=notes, key=key,
                           reports_to_hide=REPORTS_TO_HIDE)


@app.route("/admin/delete/<int:note_id>", methods=["POST"])
def admin_delete(note_id):
    key = request.form.get("key", "")
    if not is_admin(key):
        return "", 404
    db = notes_db()
    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()
    db.close()
    return redirect(url_for("admin", key=key))

from extras import extras
app.register_blueprint(extras)
