# Shelf & Screen

#### Video Demo: https://youtu.be/Gh4zDBMH5gw

# Live site: *coming soon*

> 📚 Find a book's mood in its cover colors, hear it as a melody, read classics for free, listen to audiobooks, and find films that feel the same.

#### Description:

My mom is a librarian, so I grew up surrounded by books, and I always noticed that covers have a mood before you even read the first page. Shelf & Screen is a web app built around that feeling. You search for a book, and the app looks at the colors of its cover, decides what mood the book has, plays it as a little melody and suggests films with the same feeling. If the book is old enough to be in the public domain, you can read it right on the site.

I wanted the whole site to feel like a library at night, so the design is a dark sky with stars, and the moon in the corner shows the real phase of the moon tonight.

The project uses Python and Flask on the back end, Jinja templates, SQLite, and HTML, CSS and JavaScript on the front end. Book data and covers come from Open Library, book texts come from Project Gutenberg, and the films come from IMDb's datasets.

## What it can do

When you open a book, the app finds the five main colors of the cover using k-means clustering. Those colors decide the mood: dark & mysterious, warm & cozy, calm & dreamy, or soft & romantic. Each color is also turned into a note from a pentatonic scale, so every book has its own short music-box tune. Under that, the app picks random well-rated films whose genres fit the mood, from a local database of about 19,000 films.

The reader was the part I cared about most. You can switch between night, light and sepia themes, change the text size, and the site remembers the page where you stopped. While you scroll, the app counts "weather words" like rain, snow, fire, sea or night in the paragraphs on your screen and changes the sky behind the page to match, with optional sound. Readers can also leave short anonymous notes in the margins, like pencil notes in a library book. Notes with bad words are blocked, anyone can report a note, and after three reports it disappears.

There's also a "blind date with a book": you get three hints and the book's melody, and the cover is only revealed when you unwrap it. On "my shelf", every saved book becomes a star in the color of its cover, and the stars connect into your own constellation, which you can download as a picture. Between midnight and 5 am a secret shelf of night stories appears on the home page. After the CS50 version, I kept building. I read that only 14% of 13-year-olds in the US read for fun almost every day, down from 27% in 2012 (NAEP), so I wanted to make reading feel less like homework:

- **Short reads**: ten classic short stories (O. Henry, Poe, Chopin, Jacobs and others), each with a little clock that shows how many minutes it takes to finish. You can read a whole story on a bus ride.
- **First Lines**: a ten-round game where you see the famous first line of a novel and guess which book it opens. Your best score is saved in the browser.
- **Audiobooks**: if a public-domain book has a free recording on LibriVox, a player appears on its page. You can pick a chapter, the site remembers where you stopped, and the next chapter starts on its own.

Finally, there's a private statistics page where I can see anonymous visitor counts and delete notes if I need to.

## Files

**app.py** is the Flask app with all the routes: the home page, search, book page, reader, blind date, shelf and the statistics page, plus small JSON routes that the JavaScript uses. It saves books it has already loaded in `cache.json`, so the site opens faster after a restart, and it loads the home page books in parallel.

**palette.py** does the k-means clustering from scratch. It downloads the cover, shrinks it to 100×100 pixels, groups the pixels into five clusters and returns their colors, biggest cluster first.

**moods.py** turns those colors into a mood. Every color "votes": very dark colors count twice for dark, very light ones vote for soft, greys don't vote at all, and the rest vote warm or calm depending on whether there's more red or blue. It also picks the films from `films.db` with SQL.

**gutenberg.py** looks up the book in the Project Gutenberg catalog (`pg_catalog.csv`), downloads the text, cuts off the license and the table of contents, finds the chapter titles and splits the book into pages.

**build_films.py** is a script I ran once to build `films.db` from the IMDb data, keeping only films with at least 5,000 votes.

**extras.py** is a Flask Blueprint with the newer features: short reads, the First Lines game and the audiobook search. It looks a book up in the LibriVox API by its exact title and returns its chapters, and it estimates reading time at 230 words per minute.

**templates/** has all the pages, with `layout.html` holding the shared design, the header and the moon. **static/music.js** plays the melodies, **static/sky.js** draws the living sky and makes its sounds, and **static/listen.js** is the audiobook player.

`notes.db` and `cache.json` are created automatically when the site runs.

## Run it yourself

```bash
git clone https://github.com/Moonlightdi/shelf-and-screen
cd shelf-and-screen
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
flask run
```

On the first run the app downloads the Project Gutenberg catalog by itself, so the first book may take a few seconds to open. In production it runs with gunicorn: `gunicorn --workers 1 --threads 4 app:app`.

## Design choices

I could have used a library to get the colors of a cover, but I wanted to actually understand how it works, so palette.py implements k-means directly. While testing, I noticed that almost every old cover has grey or beige paper, which made every book come out with the same mood, so greys are ignored when deciding the mood.

For films, I chose a local SQLite database instead of a film API. APIs need keys and have limits, while a local database is fast and lets me filter by rating and number of votes in one query.

I didn't want people to need an account, so the shelf is saved in the browser with localStorage. The only thing stored on the server is the notes, because those are meant to be shared. Visitors are counted with a random id in a cookie, and the site never stores names or emails.

The reader only works for public-domain books from Project Gutenberg, so everything people read here is legal. For other books, the site suggests finding them at a library.

## Credits

Book data and covers from Open Library. Free book texts from Project Gutenberg. Free public-domain audiobooks from LibriVox volunteers, hosted by the Internet Archive. Film information courtesy of IMDb (imdb.com), used with permission. Font: Nunito (Google Fonts). The sound generation and few parts of the code were written with help from Claude.

## License

Code is released under the MIT License. Book texts and audiobooks are in the public domain; film data belongs to IMDb.
