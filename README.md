# reddit-to-epub

Download text stories from any subreddit and package them as a clean, well-formatted EPUB file — no API key required.

Designed for e-ink readers, but works with any EPUB reader.

---

## Installation

**1. Clone or download the repository**

**2. Create a virtual environment** (recommended)

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

**3. Install dependencies**

```bash
pip install requests ebooklib markdown
```

---

## Usage

```
python reddit_to_epub.py [SOURCE] [FILTERS] [OUTPUT OPTIONS]
```

You must provide exactly one source (`--sub`, `--series`, or `--url`). Everything else is optional.

---

## Sources

### `--sub SUBREDDIT`
Fetch the top posts from a subreddit. Combine with `--time` and `--limit` to control what you get.

```bash
python reddit_to_epub.py --sub hfy
python reddit_to_epub.py --sub nosleep
```

### `--series WIKI_URL`
Fetch all posts in a series using an r/HFY wiki page. The script reads the wiki, extracts all linked posts in order, and downloads them as numbered chapters — ideal for multi-part stories.

```bash
python reddit_to_epub.py --series https://www.reddit.com/r/hfy/wiki/series/the_deathworlders
python reddit_to_epub.py --series https://www.reddit.com/r/hfy/wiki/series/chrysalis
```

You can find series wiki pages at: `reddit.com/r/hfy/wiki/series`

### `--url URL`
Fetch a single Reddit post by its URL.

```bash
python reddit_to_epub.py --url "https://www.reddit.com/r/hfy/comments/abc123/title/"
```

---

## Filters

### `--time {hour|day|week|month|year|all}`
Sets the time period for top-post sorting. Only applies when using `--sub`.

| Value | What you get |
|-------|-------------|
| `all` | Best posts of all time (default) |
| `year` | Best posts from the past year |
| `month` | Best posts from the past month |
| `week` | Best posts from the past week |
| `day` | Best posts from the past 24 hours |
| `hour` | Best posts from the past hour |

```bash
python reddit_to_epub.py --sub hfy --time year
python reddit_to_epub.py --sub nosleep --time month
```

### `--limit N`
Maximum number of stories to include. Default is `25`. Reddit returns at most 100 posts per page; the script paginates automatically to reach your target.

```bash
python reddit_to_epub.py --sub hfy --limit 10
python reddit_to_epub.py --sub hfy --limit 100
```

### `--min-words N`
Skip any post with fewer than N words. Useful for filtering out short posts, announcements, or stubs that aren't full stories.

```bash
# Only include stories of at least 500 words
python reddit_to_epub.py --sub hfy --min-words 500

# Only long-form stories (1000+ words)
python reddit_to_epub.py --sub nosleep --min-words 1000
```

### `--flair TEXT`
Only include posts that have a specific flair. The match is case-insensitive and partial — `OC` will match `[OC]`, `OC Story`, etc.

```bash
# Only original content from r/hfy
python reddit_to_epub.py --sub hfy --flair OC

# Only a specific flair category
python reddit_to_epub.py --sub WritingPrompts --flair WP
```

### `--author USERNAME`
Only include posts by a specific Reddit user. Use with `--sub` to get all of a particular author's stories in a subreddit, sorted chronologically (oldest first).

```bash
python reddit_to_epub.py --sub hfy --author Ralts_Bloodthorne --limit 200
python reddit_to_epub.py --sub nosleep --author PenPalHorror --limit 50
```

### `--sort-chapters {original|score|date}`
Controls the order chapters appear inside the finished EPUB.

| Value | Order |
|-------|-------|
| `original` | Same order as fetched from Reddit (default) |
| `score` | Highest-voted stories first |
| `date` | Chronological — oldest post first |

```bash
# Best stories first
python reddit_to_epub.py --sub hfy --sort-chapters score

# Chronological — good for following a story arc
python reddit_to_epub.py --sub hfy --author SomeAuthor --sort-chapters date
```

---

## Output Options

### `--title "TITLE"`
Set a custom title for the EPUB book. If not provided, a title is auto-generated from the source and filters used.

```bash
python reddit_to_epub.py --sub hfy --title "My HFY Collection"
```

### `--output FILE`
Set the output filename. If not provided, a filename is auto-generated (e.g. `r_hfy_top_all.epub`).

```bash
python reddit_to_epub.py --sub hfy --output my_reading_list.epub
```

---

## Examples

```bash
# Top 25 stories from r/HFY of all time
python reddit_to_epub.py --sub hfy --time all --limit 25

# Top 50 from r/nosleep this year, long stories only
python reddit_to_epub.py --sub nosleep --time year --limit 50 --min-words 1000

# All posts by one author, chronological
python reddit_to_epub.py --sub hfy --author Ralts_Bloodthorne --limit 200 --sort-chapters date

# Full series, in wiki order
python reddit_to_epub.py --series https://www.reddit.com/r/hfy/wiki/series/the_deathworlders

# OC posts from r/hfy this month, sorted by score, custom title
python reddit_to_epub.py --sub hfy --time month --flair OC --limit 30 --sort-chapters score --title "HFY – Best of this Month"

# Single post
python reddit_to_epub.py --url "https://www.reddit.com/r/hfy/comments/abc123/title/"
```

---

## Each chapter includes

- **Title** — as a heading
- **Subtitle** — subreddit · series (if applicable) · date posted · upvote count · author

---

## Notes

- Only text posts (`self` posts) are downloaded — link posts and image posts are automatically skipped.
- Deleted and removed posts are silently skipped.
- The script uses Reddit's public JSON API and requires no authentication.
- A short delay between requests is built in to avoid hitting Reddit's rate limits.
- The output is a standard EPUB 3 file compatible with most e-readers.

---

## Requirements

- Python 3.10+
- `requests`
- `ebooklib`
- `markdown`
