# Parts of this file written with help from Claude.
import csv
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

from flask import Flask, jsonify, redirect, render_template, request, url_for, Response, send_from_directory
import requests

from gutenberg import chapters, find_free_book, load_pages
from moods import MOODS, detect_mood, get_films
from palette import get_palette
from research import GENRES, features as cover_features

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
    found = find_free_book(info["title"], work_author(work_id))
    readable_cache[work_id] = found
    return found


def work_author(work_id):
    """The name of the first author of a book on Open Library, or None"""
    work = requests.get(f"https://openlibrary.org/works/{work_id}.json", timeout=15).json()
    for entry in work.get("authors", []):
        key = (entry.get("author") or {}).get("key")
        if key:
            return requests.get(f"https://openlibrary.org{key}.json", timeout=15).json().get("name")
    return None


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

    # answers from the "beat the computer" game on the research page
    db.execute("""
        CREATE TABLE IF NOT EXISTS guesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            visitor TEXT NOT NULL,
            cover_id TEXT NOT NULL,
            genre TEXT NOT NULL,
            guess TEXT NOT NULL,
            correct INTEGER NOT NULL,
            computer_correct INTEGER NOT NULL
        )
    """)
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


@app.route("/sw.js")
def service_worker():
    """The service worker has to live at the root so it can look after every page"""
    response = send_from_directory(os.path.join(BASE_DIR, "static"), "sw.js", mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/offline")
def offline():
    return render_template("offline.html")


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
        contents=chapters(pages),
        words_left=sum(len(p["text"].split()) for rest in pages[page - 1:] for p in rest),
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


# ---------- "Beat the computer": people guess a genre from cover colors ----------

GAME = {}


def game_data():
    """Load the research covers once, and prepare the computer's 'judge'"""
    if "rows" in GAME:
        return GAME
    rows, seen = [], set()
    try:
        with open(os.path.join(BASE_DIR, "research_covers.csv"), newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["cover_id"] not in seen:
                    seen.add(row["cover_id"])
                    rows.append(row)
    except OSError:
        pass
    GAME["rows"] = rows
    GAME["by_id"] = {row["cover_id"]: row for row in rows}
    if rows:
        X = [cover_features(row) for row in rows]
        n = len(X[0])
        mean = [sum(x[i] for x in X) / len(X) for i in range(n)]
        std = [max(1e-9, (sum((x[i] - mean[i]) ** 2 for x in X) / len(X)) ** 0.5) for i in range(n)]
        GAME["z"] = {row["cover_id"]: [(x[i] - mean[i]) / std[i] for i in range(n)] for row, x in zip(rows, X)}
        GAME["sums"], GAME["counts"] = {}, {}
        for row in rows:
            g, z = row["genre"], GAME["z"][row["cover_id"]]
            GAME["sums"][g] = [a + b for a, b in zip(GAME["sums"].get(g, [0] * n), z)]
            GAME["counts"][g] = GAME["counts"].get(g, 0) + 1
    return GAME


def computer_guess(cover_id):
    """The same nearest-centroid judge as research.py. It never learns from the cover it is guessing."""
    g = game_data()
    z = g["z"][cover_id]
    own = g["by_id"][cover_id]["genre"]
    best, best_distance = None, None
    for genre, total in g["sums"].items():
        n = g["counts"][genre]
        if genre == own:
            if n < 2:
                continue
            center = [(a - b) / (n - 1) for a, b in zip(total, z)]
        else:
            center = [a / n for a in total]
        distance = sum((a - b) ** 2 for a, b in zip(z, center))
        if best_distance is None or distance < best_distance:
            best, best_distance = genre, distance
    return best


def guess_stats():
    db = notes_db()
    row = db.execute("SELECT COUNT(*) AS n, SUM(correct) AS h, SUM(computer_correct) AS c, COUNT(DISTINCT visitor) AS p FROM guesses").fetchone()
    db.close()
    n = row["n"] or 0
    return {
        "total": n,
        "players": row["p"] or 0,
        "human_pct": round(100 * (row["h"] or 0) / n) if n else None,
        "computer_pct": round(100 * (row["c"] or 0) / n) if n else None,
    }


@app.route("/api/guess/next")
def guess_next():
    rows = game_data()["rows"]
    if not rows:
        return jsonify({"error": "no covers yet"}), 404
    row = random.choice(rows)
    return jsonify({"id": row["cover_id"], "palette": row["palette"].split()})


def clue_text(row, n):
    """Clue 2: when the book was first published. Clue 3: the shape of its title."""
    if n == 2:
        year = row["year"]
        return f"first published in the {int(year) // 10 * 10}s" if year.isdigit() else "the year of publication is lost"
    words = row["title"].split()
    first = row["title"].strip()[:1].upper() or "?"
    return f"title: {len(words)} word{'s' if len(words) != 1 else ''}, begins with \u201c{first}\u201d"


@app.route("/api/guess", methods=["POST"])
def guess_answer():
    """One guess at one clue. Only first-clue guesses (colors alone) go into the research data."""
    data = request.get_json(silent=True) or {}
    cover_id, guess = str(data.get("id", "")), str(data.get("guess", ""))
    try:
        clue = min(3, max(1, int(data.get("clue", 1))))
    except (TypeError, ValueError):
        clue = 1
    row = game_data()["by_id"].get(cover_id)
    if not row or guess not in GENRES:
        return jsonify({"error": "bad guess"}), 400
    correct = guess == row["genre"]
    computer = computer_guess(cover_id)
    computer_correct = computer == row["genre"]
    if clue == 1:
        visitor = request.cookies.get("reader") or getattr(request, "new_reader", "")
        db = notes_db()
        db.execute(
            "INSERT INTO guesses (day, visitor, cover_id, genre, guess, correct, computer_correct) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).date().isoformat(), visitor, cover_id, row["genre"], guess, int(correct), int(computer_correct))
        )
        db.commit()
        db.close()
    if not correct and clue < 3:
        return jsonify({"correct": False, "next_clue": clue_text(row, clue + 1)})
    return jsonify({
        "correct": correct, "points": (4 - clue) if correct else 0,
        "genre": row["genre"], "genre_name": GENRES[row["genre"]], "title": row["title"], "year": row["year"],
        "computer": computer, "computer_name": GENRES.get(computer, "?"), "computer_correct": computer_correct,
        "stats": guess_stats(),
    })


DAILY_START = datetime(2026, 11, 24, tzinfo=timezone.utc).date()


@app.route("/api/daily")
def daily_books():
    """Five covers of the day: the same for everyone, like Wordle"""
    rows = sorted(game_data()["rows"], key=lambda row: row["cover_id"])
    if not rows:
        return jsonify({"error": "no covers yet"}), 404
    today = datetime.now(timezone.utc).date()
    picks = random.Random(today.isoformat()).sample(rows, min(5, len(rows)))
    return jsonify({
        "number": (today - DAILY_START).days + 1,
        "books": [{"id": row["cover_id"], "palette": row["palette"].split()} for row in picks],
    })


@app.route("/api/guess/stats")
def guess_stats_api():
    return jsonify(guess_stats())


@app.route("/research")
@app.route("/daily")
def research():
    """Can you judge a book by its cover? Results made by research.py"""
    try:
        with open(os.path.join(BASE_DIR, "research_results.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    count("research")
    return render_template("research.html", data=data, daily=request.path == "/daily")


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
    if kind in ("unwrap", "poster", "sound", "share"):
        count(kind)
    return jsonify({"ok": True})


@app.route("/api/cover/<int:cover_id>")
def cover_image(cover_id):
    """Pass an Open Library cover through our own site, so the share card can draw it"""
    try:
        r = requests.get(f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg", timeout=10)
        r.raise_for_status()
    except requests.RequestException:
        return Response(status=404)
    return Response(r.content, mimetype=r.headers.get("Content-Type", "image/jpeg"),
                    headers={"Cache-Control": "public, max-age=86400"})


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
