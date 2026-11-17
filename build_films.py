import csv
import gzip
import sqlite3

MIN_VOTES = 5000

# 1. Ratings: keep only films that many people rated
ratings = {}
with gzip.open("data/title.ratings.tsv.gz", "rt", encoding="utf-8") as file:
    reader = csv.DictReader(file, delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in reader:
        votes = int(row["numVotes"])
        if votes >= MIN_VOTES:
            ratings[row["tconst"]] = (float(row["averageRating"]), votes)

# 2. Database
db = sqlite3.connect("films.db")
db.execute("DROP TABLE IF EXISTS films")
db.execute("""
    CREATE TABLE films (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        year INTEGER,
        genres TEXT,
        rating REAL,
        votes INTEGER
    )
""")

# 3. Movies with a rating and genres
count = 0
with gzip.open("data/title.basics.tsv.gz", "rt", encoding="utf-8") as file:
    reader = csv.DictReader(file, delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in reader:
        if row["titleType"] != "movie" or row["tconst"] not in ratings:
            continue
        if row["genres"] == "\\N" or row["startYear"] == "\\N":
            continue
        rating, votes = ratings[row["tconst"]]
        db.execute(
            "INSERT INTO films VALUES (?, ?, ?, ?, ?, ?)",
            (row["tconst"], row["primaryTitle"], int(row["startYear"]), row["genres"], rating, votes),
        )
        count += 1

db.commit()
db.close()
print(f"Saved {count} films")
