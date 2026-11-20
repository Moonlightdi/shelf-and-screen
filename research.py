# Can you judge a book by its cover?
# Collects covers from Open Library by genre, finds their colors with palette.py,
# and checks whether colors alone can tell the genre.
#   python research.py            collect covers (resumable) and analyze
#   python research.py analyze    only analyze the covers already collected
# Parts of this file written with help from Claude.
import colorsys
import csv
import json
import math
import os
import random
import sys
import time

import requests

from moods import detect_mood, hex_to_rgb
from palette import get_palette

GENRES = {
    "horror": "Horror",
    "romance": "Romance",
    "fantasy": "Fantasy",
    "science_fiction": "Science fiction",
    "mystery_and_detective_stories": "Mystery",
    "humor": "Humor",
    "poetry": "Poetry",
    "historical_fiction": "Historical fiction",
}
PER_GENRE = 150
DATA = "research_covers.csv"
RESULTS = "research_results.json"
FIELDS = ["genre", "cover_id", "title", "year", "palette", "mood", "brightness", "saturation", "hue"]
MOOD_NAMES = ["dark", "warm", "calm", "soft"]


# ---------- collecting ----------

def describe(palette):
    """Numbers that describe a cover: bigger colors count more"""
    weights = [5, 4, 3, 2, 1][:len(palette)]
    rgbs = [hex_to_rgb(c) for c in palette]
    total = sum(weights)
    brightness = sum(w * sum(c) / 3 for w, c in zip(weights, rgbs)) / total
    saturation = sum(w * (max(c) - min(c)) for w, c in zip(weights, rgbs)) / total
    r, g, b = rgbs[0]
    hue = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0] * 360
    return round(brightness, 1), round(saturation, 1), round(hue, 1)


def collect():
    done = set()
    seen_ids = {}
    if os.path.exists(DATA):
        with open(DATA, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add((row["genre"], row["cover_id"]))
                seen_ids[row["cover_id"]] = row["genre"]
    new_file = not os.path.exists(DATA)
    out = open(DATA, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(out, fieldnames=FIELDS)
    if new_file:
        writer.writeheader()

    for subject, name in GENRES.items():
        have = sum(1 for g, _ in done if g == subject)
        offset = 0
        print(f"\n{name}: {have}/{PER_GENRE}")
        while have < PER_GENRE and offset < 1200:
            try:
                works = requests.get(f"https://openlibrary.org/subjects/{subject}.json",
                                     params={"limit": 50, "offset": offset}, timeout=20).json().get("works", [])
            except (requests.RequestException, ValueError):
                print("  Open Library didn't answer, waiting...")
                time.sleep(5)
                continue
            if not works:
                break
            offset += 50
            for work in works:
                cover_id = str(work.get("cover_id") or "")
                if not cover_id or (subject, cover_id) in done or have >= PER_GENRE:
                    continue
                if cover_id in seen_ids:
                    # The same book in two genres would confuse the test
                    continue
                try:
                    palette = get_palette(f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg")
                except Exception:
                    continue
                brightness, saturation, hue = describe(palette)
                writer.writerow({
                    "genre": subject, "cover_id": cover_id, "title": work.get("title", ""),
                    "year": work.get("first_publish_year") or "", "palette": " ".join(palette),
                    "mood": detect_mood(palette), "brightness": brightness, "saturation": saturation, "hue": hue,
                })
                out.flush()
                done.add((subject, cover_id))
                seen_ids[cover_id] = subject
                have += 1
                print(f"  {have}/{PER_GENRE}  {work.get('title', '')[:50]}")
                time.sleep(0.2)
    out.close()


# ---------- analyzing ----------

def kmeans(colors, k=5, iterations=12):
    """The same k-means as palette.py, but for all the colors of a genre"""
    random.seed(7)
    centers = random.sample(colors, min(k, len(colors)))
    groups = []
    for _ in range(iterations):
        groups = [[] for _ in centers]
        for c in colors:
            i = min(range(len(centers)), key=lambda j: sum((a - b) ** 2 for a, b in zip(c, centers[j])))
            groups[i].append(c)
        centers = [tuple(sum(ch) // len(g) for ch in zip(*g)) if g else centers[i] for i, g in enumerate(groups)]
    order = sorted(range(len(centers)), key=lambda i: len(groups[i]), reverse=True)
    return ["#{:02x}{:02x}{:02x}".format(*centers[i]) for i in order]


def features(row):
    """What the 'judge' is allowed to look at: only colors"""
    palette = row["palette"].split()
    rgbs = [hex_to_rgb(c) for c in palette]
    hue = float(row["hue"]) / 360 * 6.2832
    sat = float(row["saturation"]) / 255
    return [
        float(row["brightness"]) / 255,
        sat,
        sum(c[0] for c in rgbs) / len(rgbs) / 255,
        sum(c[1] for c in rgbs) / len(rgbs) / 255,
        sum(c[2] for c in rgbs) / len(rgbs) / 255,
        math.cos(hue) * sat,
        math.sin(hue) * sat,
        sum(1 for c in rgbs if sum(c) / 3 < 70) / len(rgbs),
        sum(1 for c in rgbs if sum(c) / 3 > 210) / len(rgbs),
    ]


def judge_test(rows, folds=5):
    """Nearest-centroid 'judge': learns the average colors of each genre, then guesses new covers"""
    random.seed(1)
    rows = rows[:]
    random.shuffle(rows)
    X = [features(r) for r in rows]
    n = len(X[0])
    mean = [sum(x[i] for x in X) / len(X) for i in range(n)]
    std = [max(1e-9, (sum((x[i] - mean[i]) ** 2 for x in X) / len(X)) ** 0.5) for i in range(n)]
    X = [[(x[i] - mean[i]) / std[i] for i in range(n)] for x in X]
    y = [r["genre"] for r in rows]
    right = 0
    per = {g: [0, 0] for g in GENRES}
    for f in range(folds):
        train = [i for i in range(len(X)) if i % folds != f]
        test = [i for i in range(len(X)) if i % folds == f]
        centroids = {}
        for g in GENRES:
            pts = [X[i] for i in train if y[i] == g]
            if pts:
                centroids[g] = [sum(p[j] for p in pts) / len(pts) for j in range(n)]
        for i in test:
            guess = min(centroids, key=lambda g: sum((a - b) ** 2 for a, b in zip(X[i], centroids[g])))
            per[y[i]][1] += 1
            if guess == y[i]:
                right += 1
                per[y[i]][0] += 1
    return right / len(X), {g: round(100 * a / b) for g, (a, b) in per.items() if b}


def analyze():
    with open(DATA, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 40:
        print("Not enough covers yet. Run: python research.py")
        return
    genres = []
    for subject, name in GENRES.items():
        g = [r for r in rows if r["genre"] == subject]
        if not g:
            continue
        colors = [hex_to_rgb(c) for r in g for c in r["palette"].split()]
        moods = {m: round(100 * sum(1 for r in g if r["mood"] == m) / len(g)) for m in MOOD_NAMES}
        genres.append({
            "key": subject, "name": name, "count": len(g),
            "brightness": round(sum(float(r["brightness"]) for r in g) / len(g), 1),
            "saturation": round(sum(float(r["saturation"]) for r in g) / len(g), 1),
            "colors": kmeans(colors),
            "moods": moods,
            "examples": [r["cover_id"] for r in g[:6]],
        })

    decades = []
    by_decade = {}
    for r in rows:
        if r["year"].isdigit() and 1850 <= int(r["year"]) <= 2029:
            by_decade.setdefault(int(r["year"]) // 10 * 10, []).append(r)
    for d in sorted(by_decade):
        if len(by_decade[d]) >= 15:
            ds = by_decade[d]
            decades.append({"decade": d, "count": len(ds),
                            "brightness": round(sum(float(r["brightness"]) for r in ds) / len(ds), 1),
                            "saturation": round(sum(float(r["saturation"]) for r in ds) / len(ds), 1)})

    accuracy, per_genre = judge_test(rows)
    for g in genres:
        g["recognized"] = per_genre.get(g["key"], 0)

    darkest = min(genres, key=lambda g: g["brightness"])
    brightest = max(genres, key=lambda g: g["brightness"])
    colorful = max(genres, key=lambda g: g["saturation"])
    known = max(genres, key=lambda g: g["recognized"])
    hidden = min(genres, key=lambda g: g["recognized"])
    findings = [
        f"{darkest['name']} has the darkest covers, {brightest['name']} the brightest.",
        f"{colorful['name']} covers are the most colorful.",
        f"Colors alone guessed the genre {round(accuracy * 100)}% of the time. Random guessing would get {round(100 / len(genres))}%.",
        f"{known['name']} is the easiest genre to recognize by color ({known['recognized']}%), {hidden['name']} the hardest ({hidden['recognized']}%).",
    ]
    if len(decades) >= 3:
        first, last = decades[0], decades[-1]
        trend = "darker" if last["brightness"] < first["brightness"] else "brighter"
        findings.append(f"Covers of books first published in the {last['decade']}s are {trend} than those from the {first['decade']}s.")

    result = {"total": len(rows), "genres": genres, "decades": decades,
              "accuracy": round(accuracy * 100, 1), "chance": round(100 / len(genres), 1),
              "findings": findings, "updated": time.strftime("%Y-%m-%d")}
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print("\n".join(["", "RESULTS:"] + ["  • " + x for x in findings]))
    print(f"\nSaved {RESULTS}. Open /research on the site to see the charts.")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "analyze":
        collect()
    analyze()
