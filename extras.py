"""Short reads, the First Lines game and audiobooks from LibriVox.

Connected to the main app with two lines at the very end of app.py:
    from extras import extras
    app.register_blueprint(extras)
"""
import random
import re

import requests
from flask import Blueprint, abort, jsonify, redirect, render_template, request

from gutenberg import chapters, find_free_book, load_pages

# app.py imports this file at its very end, so everything below already exists there
from app import count, get_book, search_book

extras = Blueprint("extras", __name__)

WORDS_PER_MINUTE = 230

# Stories short enough for one evening: (title, author, one line about it)
SHORT_READS = [
    ("The Gift of the Magi", "O. Henry", "Two gifts, one Christmas, and nothing left to spare."),
    ("The Story of an Hour", "Kate Chopin", "One hour can change everything, twice."),
    ("The Cask of Amontillado", "Edgar Allan Poe", "A carnival, a cellar, and a promise of rare wine."),
    ("The Masque of the Red Death", "Edgar Allan Poe", "A masked ball behind locked gates."),
    ("The Tell-Tale Heart", "Edgar Allan Poe", "The narrator insists he is perfectly calm."),
    ("The Lady, or the Tiger?", "Frank R. Stockton", "Two doors. The story will not tell you which."),
    ("The Monkey's Paw", "W. W. Jacobs", "Three wishes, and every one comes true."),
    ("An Occurrence at Owl Creek Bridge", "Ambrose Bierce", "A rope, a river, and a long way home."),
    ("The Yellow Wallpaper", "Charlotte Perkins Gilman", "A summer rest cure and a pattern that moves."),
    ("The Fall of the House of Usher", "Edgar Allan Poe", "An old friend, an older house, and a storm."),
]

# Opening lines of free classics for the game: (line, title, author)
FIRST_LINES = [
    ("It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.",
     "Pride and Prejudice", "Jane Austen"),
    ("There was no possibility of taking a walk that day.",
     "Jane Eyre", "Charlotte Brontë"),
    ("“Christmas won't be Christmas without any presents,” grumbled Jo, lying on the rug.",
     "Little Women", "Louisa May Alcott"),
    ("Alice was beginning to get very tired of sitting by her sister on the bank, and of having nothing to do.",
     "Alice's Adventures in Wonderland", "Lewis Carroll"),
    ("All children, except one, grow up.",
     "Peter Pan", "J. M. Barrie"),
    ("Happy families are all alike; every unhappy family is unhappy in its own way.",
     "Anna Karenina", "Leo Tolstoy"),
    ("Marley was dead: to begin with.",
     "A Christmas Carol", "Charles Dickens"),
    ("Call me Ishmael.",
     "Moby-Dick", "Herman Melville"),
    ("It was the best of times, it was the worst of times.",
     "A Tale of Two Cities", "Charles Dickens"),
    ("In my younger and more vulnerable years my father gave me some advice that I've been turning over in my mind ever since.",
     "The Great Gatsby", "F. Scott Fitzgerald"),
    ("You will rejoice to hear that no disaster has accompanied the commencement of an enterprise which you have regarded with such evil forebodings.",
     "Frankenstein", "Mary Shelley"),
    ("When Mary Lennox was sent to Misselthwaite Manor to live with her uncle everybody said she was the most disagreeable-looking child ever seen.",
     "The Secret Garden", "Frances Hodgson Burnett"),
    ("Dorothy lived in the midst of the great Kansas prairies, with Uncle Henry, who was a farmer, and Aunt Em, who was the farmer's wife.",
     "The Wonderful Wizard of Oz", "L. Frank Baum"),
    ("To Sherlock Holmes she is always the woman.",
     "The Adventures of Sherlock Holmes", "Arthur Conan Doyle"),
    ("The studio was filled with the rich odour of roses.",
     "The Picture of Dorian Gray", "Oscar Wilde"),
    ("You don't know about me without you have read a book by the name of The Adventures of Tom Sawyer; but that ain't no matter.",
     "Adventures of Huckleberry Finn", "Mark Twain"),
    ("“Tom!” No answer.",
     "The Adventures of Tom Sawyer", "Mark Twain"),
    ("Whether I shall turn out to be the hero of my own life, or whether that station will be held by anybody else, these pages must show.",
     "David Copperfield", "Charles Dickens"),
    ("Mrs. Rachel Lynde lived just where the Avonlea main road dipped down into a little hollow.",
     "Anne of Green Gables", "L. M. Montgomery"),
    ("Squire Trelawney, Dr. Livesey, and the rest of these gentlemen having asked me to write down the whole particulars about Treasure Island.",
     "Treasure Island", "Robert Louis Stevenson"),
    ("Mr. Sherlock Holmes, who was usually very late in the mornings, save upon those not infrequent occasions when he was up all night, was seated at the breakfast table.",
     "The Hound of the Baskervilles", "Arthur Conan Doyle"),
    ("Left Munich at 8:35 P.M., on 1st May, arriving at Vienna early next morning.",
     "Dracula", "Bram Stoker"),
]

ROUNDS = 10

listen_cache = {}
minutes_cache = {}


def short_reads():
    """The short stories that were found on Project Gutenberg"""
    stories = []
    for title, author, line in SHORT_READS:
        found = find_free_book(title, author)
        if found:
            stories.append({"id": found["id"], "title": title, "author": author, "line": line, "free": found})
    return stories


def short_read(book_id):
    """One story from the list above (other Gutenberg books can't be opened this way)"""
    for story in short_reads():
        if story["id"] == book_id:
            return story
    return None


@extras.route("/short")
def short():
    count("short")
    return render_template("short.html", stories=short_reads())


@extras.route("/api/minutes/<int:book_id>")
def api_minutes(book_id):
    """How many minutes a story takes to read"""
    if book_id not in minutes_cache:
        story = short_read(book_id)
        if not story:
            abort(404)
        try:
            pages = load_pages(story["free"])
        except requests.RequestException:
            return jsonify({"minutes": None})
        words = sum(len(p["text"].split()) for page in pages for p in page)
        minutes_cache[book_id] = max(1, round(words / WORDS_PER_MINUTE))
    return jsonify({"minutes": minutes_cache[book_id]})


@extras.route("/read/pg<int:book_id>")
def read_short(book_id):
    """The same cozy reader, for a short story"""
    story = short_read(book_id)
    if not story:
        abort(404)
    try:
        pages = load_pages(story["free"])
    except requests.RequestException:
        return render_template("message.html", title="The pages got lost in the dark",
                               text="We couldn't load this story. Please try again in a moment.")

    page = request.args.get("page", 1, type=int)
    page = max(1, min(page, len(pages)))
    count("read")
    offset = sum(len(p) for p in pages[:page - 1])
    info = {"id": f"pg{book_id}", "title": story["title"], "cover": None, "palette": [], "mood_key": None}

    return render_template(
        "read.html",
        info=info,
        free=story["free"],
        paragraphs=pages[page - 1],
        offset=offset,
        page=page,
        total=len(pages),
        contents=chapters(pages),
        words_left=sum(len(p["text"].split()) for rest in pages[page - 1:] for p in rest),
        work_id=f"pg{book_id}",
        has_page="page" in request.args
    )


@extras.route("/book/pg<int:book_id>")
def book_short(book_id):
    """Short stories have no book page, so the links in the reader lead back to the list"""
    return redirect("/short")


@extras.route("/first-lines")
def first_lines():
    count("game")
    rounds = random.sample(FIRST_LINES, ROUNDS)
    titles = [(title, author) for _, title, author in FIRST_LINES]
    questions = []
    for line, title, author in rounds:
        wrong = random.sample([t for t in titles if t[0] != title], 3)
        options = wrong + [(title, author)]
        random.shuffle(options)
        questions.append({
            "line": line,
            "answer": title,
            "author": author,
            "options": [{"title": t, "author": a} for t, a in options],
        })
    return render_template("first_lines.html", questions=questions)


@extras.route("/open")
def open_book():
    """From the game straight to the first page of a book"""
    title = request.args.get("title", "")
    author = request.args.get("author", "")
    found = search_book(title, author) if title else None
    if found:
        return redirect(f"/read/{found['id']}")
    return redirect("/search?q=" + requests.utils.quote(title))


def simple(text):
    """'The Picture of Dorian Gray!' -> 'picture of dorian gray'"""
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower().replace("’", "'").replace("'", ""))
    return " ".join(w for w in text.split() if w not in ("the", "a", "an"))


@extras.route("/api/listen/<work_id>")
def api_listen(work_id):
    """A free audiobook of this book from LibriVox, read by volunteers"""
    if work_id in listen_cache:
        return jsonify(listen_cache[work_id])

    try:
        title = get_book(work_id)["title"]
        response = requests.get(
            "https://librivox.org/api/feed/audiobooks/",
            params={"title": "^" + title, "format": "json", "extended": 1, "limit": 10},
            timeout=15
        )
        books = response.json().get("books", []) if response.ok else []
    except (requests.RequestException, ValueError):
        return jsonify({"found": False})

    for book in books:
        if simple(book.get("title", "")) != simple(title) or not book.get("sections"):
            continue
        chapters = []
        for section in book["sections"]:
            url = (section.get("listen_url") or "").replace("http://", "https://")
            if url:
                seconds = int(section.get("playtime") or 0)
                chapters.append({"title": section.get("title") or f"Part {len(chapters) + 1}",
                                 "url": url, "minutes": max(1, round(seconds / 60))})
        if chapters:
            listen_cache[work_id] = {"found": True, "page": book.get("url_librivox"), "chapters": chapters}
            return jsonify(listen_cache[work_id])

    listen_cache[work_id] = {"found": False}
    return jsonify(listen_cache[work_id])
