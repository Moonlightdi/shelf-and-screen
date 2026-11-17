# Parts of this file written with help from Claude.
import sqlite3

MOODS = {
    "dark": {"name": "dark & mysterious", "emoji": "🌑", "genres": ["Mystery", "Thriller", "Horror"]},
    "warm": {"name": "warm & cozy", "emoji": "🔥", "genres": ["Comedy", "Family", "Music"]},
    "calm": {"name": "calm & dreamy", "emoji": "🌊", "genres": ["Fantasy", "Animation", "Adventure"]},
    "soft": {"name": "soft & romantic", "emoji": "🌸", "genres": ["Romance", "Drama"]},
}


def hex_to_rgb(color):
    """'#e3452f' -> (227, 69, 47)"""
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def detect_mood(palette):
    """Decide the mood of a book from the colors of its cover"""
    scores = {"dark": 0, "warm": 0, "calm": 0, "soft": 0}

    for color in palette:
        r, g, b = hex_to_rgb(color)
        brightness = (r + g + b) / 3
        saturation = max(r, g, b) - min(r, g, b)

        if brightness < 70:
            # Very dark colors set the mood strongly, so their vote counts twice
            scores["dark"] += 2
        elif brightness > 210:
            scores["soft"] += 1
        elif saturation < 35:
            # Grey colors are like paper: neutral, they don't vote
            continue
        elif r > b:
            scores["warm"] += 1
        else:
            scores["calm"] += 1

    # If there is a tie, the first mood in the list wins (dark first)
    return max(scores, key=scores.get)


def get_films(mood_key, limit=8):
    """Pick random popular, well-rated films with genres of this mood"""
    genres = MOODS[mood_key]["genres"]
    conditions = " OR ".join("genres LIKE ?" for _ in genres)
    query = f"""
        SELECT id, title, year, rating FROM films
        WHERE rating >= 7.0 AND votes >= 100000 AND ({conditions})
        ORDER BY RANDOM() LIMIT ?
    """
    db = sqlite3.connect("films.db")
    db.row_factory = sqlite3.Row
    rows = db.execute(query, [f"%{g}%" for g in genres] + [limit]).fetchall()
    db.close()
    return [dict(row) for row in rows]
