#!/usr/bin/env python3
"""
reddit_to_epub.py  –  Reddit → EPUB
=====================================

Downloads self-post stories from any subreddit and packages them as a
clean, well-formatted EPUB file. No API key required.

Installation:
    pip install requests ebooklib markdown

─────────────────────────────────────────────────────────────────────
EXAMPLES
─────────────────────────────────────────────────────────────────────

  # Top 25 posts from r/HFY of all time
  python reddit_to_epub.py --sub hfy --time all --limit 25

  # Top 50 from r/nosleep this year, OC flair only
  python reddit_to_epub.py --sub nosleep --time year --limit 50 --flair OC

  # All posts by a specific author in a subreddit (chronological)
  python reddit_to_epub.py --sub hfy --author Ralts_Bloodthorne --limit 100

  # A full series via the HFY wiki
  python reddit_to_epub.py --series https://www.reddit.com/r/hfy/wiki/series/the_deathworlders

  # A single post by URL
  python reddit_to_epub.py --url "https://reddit.com/r/hfy/comments/abc123/title/"

  # Sort alphabetically so series parts group together
  python reddit_to_epub.py --sub hfy --time all --limit 50 --sort-chapters title
"""

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import markdown as md_lib
from ebooklib import epub

# ─────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────

HEADERS       = {"User-Agent": "reddit-to-epub/2.0 (github.com)"}
REQUEST_DELAY = 1.2   # seconds between requests
REDDIT_BASE   = "https://www.reddit.com"

# Estimated words per page on Xteink X4 at medium font size (480x800px)
WORDS_PER_PAGE = 180

# ─────────────────────────────────────────────────────────────────────
# CSS – clean, airy layout optimised for e-ink displays
# ─────────────────────────────────────────────────────────────────────

CSS = """
body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 1em;
    line-height: 1.8;
    color: #111;
    margin: 0;
    padding: 0 0.5em;
}

h1.story-title {
    font-size: 1.3em;
    font-weight: bold;
    margin-top: 1.5em;
    margin-bottom: 0.2em;
    line-height: 1.3;
}

p.story-meta {
    font-size: 0.72em;
    color: #555;
    margin-top: 0;
    margin-bottom: 2em;
    font-style: italic;
    line-height: 1.6;
}

hr.divider {
    border: none;
    border-top: 1px solid #ccc;
    margin: 0 0 2em 0;
}

p {
    margin: 0 0 0.9em 0;
    text-indent: 1.4em;
}

p:first-of-type,
p.no-indent {
    text-indent: 0;
}

blockquote {
    border-left: 3px solid #bbb;
    margin: 1.2em 0 1.2em 0.5em;
    padding-left: 1em;
    color: #444;
    font-style: italic;
}

em     { font-style: italic; }
strong { font-weight: bold; }
"""

# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
           "Jul","Aug","Sep","Oct","Nov","Dec"]


def _format_date(utc_timestamp: float) -> str:
    """Format a UTC timestamp as 'Jan 05, 2023' — always in English."""
    dt = datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
    return f"{_MONTHS[dt.month - 1]} {dt.day:02d}, {dt.year}"


def _get(url: str, params: dict = None) -> dict:
    """Make a GET request to the Reddit JSON API."""
    r = requests.get(url, headers=HEADERS, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _clean(text: str):
    """Return None if the post body is empty, removed, or deleted."""
    t = text.strip()
    return None if (not t or t in ("[removed]", "[deleted]")) else t


def _esc(s: str) -> str:
    """Minimal HTML escaping for metadata strings."""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def _make_post(data: dict, series_name: str = None) -> dict | None:
    """
    Convert raw Reddit API post data into a clean dict.
    Returns None for link posts, removed posts, and empty posts.
    """
    text = _clean(data.get("selftext", ""))
    if not text or not data.get("is_self"):
        return None
    return {
        "title":       data.get("title", "Untitled"),
        "author":      data.get("author", "unknown"),
        "subreddit":   data.get("subreddit", ""),
        "series":      series_name,
        "text":        text,
        "score":       data.get("score", 0),
        "created_utc": data.get("created_utc", 0),
        "created_str": _format_date(data.get("created_utc", 0)),
        "flair":       data.get("link_flair_text") or "",
        "url":         REDDIT_BASE + data.get("permalink", ""),
        "word_count":  len(text.split()),
    }


def _make_filename(args) -> str:
    """
    Build a descriptive filename that includes all active filters.
    Example: reddit_hfy_top_all_limit50_minwords500_flair_OC.epub
    """
    if args.url:
        return "reddit_single_post.epub"
    if args.series:
        slug = args.series.rstrip("/").split("/")[-1]
        return f"reddit_series_{slug}.epub"

    parts = ["reddit", args.sub]

    if args.author:
        parts.append(f"author_{args.author}")
    else:
        parts.append(f"top_{args.time_filter}")
        parts.append(f"limit{args.limit}")
        if args.min_words:
            parts.append(f"minwords{args.min_words}")
        if args.flair:
            parts.append(f"flair_{args.flair}")
        if args.sort_chapters != "original":
            parts.append(f"sort_{args.sort_chapters}")

    return "_".join(parts) + ".epub"


# ─────────────────────────────────────────────────────────────────────
# FETCHING
# ─────────────────────────────────────────────────────────────────────

def fetch_subreddit_posts(
    subreddit:   str,
    time_filter: str = "all",
    limit:       int = 25,
    min_words:   int = 0,
    flair:       str = None,
    author:      str = None,
) -> list[dict]:
    """Fetch text posts from a subreddit sorted by top."""
    posts  = []
    after  = None
    budget = min(limit * 5, 500) if (flair or author or min_words) else limit

    print(f"\n📥 Fetching from r/{subreddit}  [top/{time_filter}, max {limit}]")

    while len(posts) < limit and budget > 0:
        page_size = min(100, budget)
        params    = {"limit": page_size, "t": time_filter}
        if after:
            params["after"] = after

        data     = _get(f"{REDDIT_BASE}/r/{subreddit}/top.json", params)
        children = data.get("data", {}).get("children", [])
        after    = data.get("data", {}).get("after")
        budget  -= len(children)

        if not children:
            break

        for child in children:
            post = _make_post(child["data"])
            if post is None:
                continue
            if min_words and post["word_count"] < min_words:
                continue
            if flair     and flair.lower() not in post["flair"].lower():
                continue
            if author    and post["author"].lower() != author.lower():
                continue
            posts.append(post)
            if len(posts) >= limit:
                break

        if not after:
            break
        time.sleep(REQUEST_DELAY)

    print(f"   ✓ {len(posts)} posts found")
    return posts[:limit]


def fetch_user_posts(
    subreddit: str,
    author:    str,
    limit:     int = 100,
    min_words: int = 0,
) -> list[dict]:
    """Fetch all posts by a specific user in a subreddit (chronological)."""
    posts = []
    after = None

    print(f"\n📥 Fetching posts by u/{author} in r/{subreddit}")

    while len(posts) < limit:
        params = {"limit": 100, "sort": "new"}
        if after:
            params["after"] = after

        data     = _get(f"{REDDIT_BASE}/user/{author}/submitted.json", params)
        children = data.get("data", {}).get("children", [])
        after    = data.get("data", {}).get("after")

        if not children:
            break

        for child in children:
            d = child["data"]
            if d.get("subreddit", "").lower() != subreddit.lower():
                continue
            post = _make_post(d)
            if post is None:
                continue
            if min_words and post["word_count"] < min_words:
                continue
            posts.append(post)

        if not after:
            break
        time.sleep(REQUEST_DELAY)

    posts.sort(key=lambda p: p["created_utc"])
    print(f"   ✓ {len(posts)} posts found")
    return posts[:limit]


def fetch_single_post(url: str, series_name: str = None) -> dict | None:
    """Fetch a single Reddit post by its full URL."""
    data = _get(url.rstrip("/") + ".json")
    return _make_post(data[0]["data"]["children"][0]["data"], series_name)


def fetch_series_from_wiki(wiki_url: str, min_words: int = 0) -> list[dict]:
    """
    Fetch all posts in a series using an HFY wiki page.
    Example: https://www.reddit.com/r/hfy/wiki/series/the_deathworlders
    """
    series_name = wiki_url.rstrip("/").split("/")[-1].replace("_", " ").title()
    print(f"\n📥 Fetching series '{series_name}' from wiki")

    data    = _get(wiki_url.rstrip("/") + ".json")
    wiki_md = data["data"]["content_md"]

    links_raw = re.findall(
        r'https?://(?:www\.)?reddit\.com/r/\w+/comments/\w+/[^\s\)\]"\']*',
        wiki_md,
    )
    seen, links = set(), []
    for link in links_raw:
        if link not in seen:
            seen.add(link)
            links.append(link)

    print(f"   Found {len(links)} links")

    posts = []
    for i, link in enumerate(links, 1):
        slug = link.split("/comments/")[1][:45] if "/comments/" in link else link
        print(f"   [{i:3d}/{len(links)}] {slug}...")
        try:
            post = fetch_single_post(link, series_name)
            if post and (not min_words or post["word_count"] >= min_words):
                posts.append(post)
        except Exception as e:
            print(f"          ⚠ Skipped: {e}")
        time.sleep(REQUEST_DELAY)

    print(f"   ✓ {len(posts)} chapters fetched")
    return posts


# ─────────────────────────────────────────────────────────────────────
# FORMATTING
# ─────────────────────────────────────────────────────────────────────

def reddit_md_to_html(text: str) -> str:
    """Convert Reddit-flavoured Markdown to HTML."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    return md_lib.markdown(text, extensions=["extra", "nl2br"])


def post_to_xhtml(post: dict) -> str:
    """Build a complete XHTML chapter for a single post."""
    meta_parts = [f"r/{post['subreddit']}"]
    if post.get("series"):
        meta_parts.append(f"Series: {post['series']}")
    meta_parts.append(f"Posted {post['created_str']}")
    meta_parts.append(f"\u2191 {post['score']:,} upvotes")
    meta_parts.append(f"u/{post['author']}")
    meta_str = "  \u00b7  ".join(meta_parts)

    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8"/>
  <title>{_esc(post['title'])}</title>
  <link rel="stylesheet" type="text/css" href="../Styles/style.css"/>
</head>
<body>
  <h1 class="story-title">{_esc(post['title'])}</h1>
  <p class="story-meta">{_esc(meta_str)}</p>
  <hr class="divider"/>
  {reddit_md_to_html(post['text'])}
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────
# EPUB BUILDER
# ─────────────────────────────────────────────────────────────────────

def build_epub(posts: list[dict], output_path: Path, book_title: str) -> None:
    """Assemble and write the final EPUB file."""
    book = epub.EpubBook()
    book.set_identifier(f"reddit-epub-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    book.set_title(book_title)
    book.set_language("en")

    style = epub.EpubItem(
        uid="main-css",
        file_name="Styles/style.css",
        media_type="text/css",
        content=CSS,
    )
    book.add_item(style)

    chapters, toc, total_words = [], [], 0
    cumulative_words = 0
    print(f"\n📖 Building EPUB with {len(posts)} chapters...")

    for i, post in enumerate(posts, 1):
        # Estimated page number based on X4 screen at medium font
        est_page = max(1, round(cumulative_words / WORDS_PER_PAGE) + 1)

        chap = epub.EpubHtml(
            title=post["title"],
            file_name=f"Text/chap_{i:04d}.xhtml",
            lang="en",
        )
        chap.content = post_to_xhtml(post).encode("utf-8")
        chap.add_item(style)
        book.add_item(chap)
        chapters.append(chap)

        # TOC entry includes estimated page number
        toc_title = f"{post['title']}  (~p. {est_page})"
        toc.append(epub.Link(f"Text/chap_{i:04d}.xhtml", toc_title, f"chap{i}"))

        cumulative_words += post["word_count"]
        total_words      += post["word_count"]

    book.toc   = toc
    book.spine = ["nav"] + chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(str(output_path), book)

    size_kb = output_path.stat().st_size // 1024
    print(f"\n✅ Done!")
    print(f"   File:     {output_path}")
    print(f"   Chapters: {len(posts)}")
    print(f"   Words:    {total_words:,}")
    print(f"   Size:     {size_kb} KB")


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Download Reddit stories and package them as a clean EPUB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  %(prog)s --sub hfy --time all --limit 50
  %(prog)s --sub nosleep --time year --limit 30 --min-words 500
  %(prog)s --sub hfy --author Ralts_Bloodthorne --limit 100
  %(prog)s --series https://www.reddit.com/r/hfy/wiki/series/the_deathworlders
  %(prog)s --url "https://reddit.com/r/hfy/comments/abc123/title/"
  %(prog)s --sub hfy --time all --limit 50 --sort-chapters title
        """,
    )

    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--sub",    metavar="SUBREDDIT",
                     help="Subreddit to fetch from (without r/)")
    src.add_argument("--series", metavar="WIKI_URL",
                     help="HFY wiki URL for a full series")
    src.add_argument("--url",    metavar="URL",
                     help="URL to a single Reddit post")

    p.add_argument("--author",    metavar="USERNAME",
                   help="Only include posts by this user (use with --sub)")
    p.add_argument("--flair",     metavar="TEXT",
                   help="Only include posts with this flair text (e.g. OC)")
    p.add_argument("--time",
                   choices=["hour", "day", "week", "month", "year", "all"],
                   default="all", dest="time_filter",
                   help="Time filter for top sorting (default: all)")
    p.add_argument("--limit",     type=int, default=25,
                   help="Maximum number of stories to fetch (default: 25)")
    p.add_argument("--min-words", type=int, default=0, metavar="N",
                   help="Skip posts shorter than N words")
    p.add_argument("--sort-chapters",
                   choices=["score", "date", "original", "title"],
                   default="original",
                   help="Chapter order: score | date | title | original (default: original)")
    p.add_argument("--title",  metavar="TITLE",
                   help="Custom book title (default: auto-generated)")
    p.add_argument("--output", metavar="FILE",
                   help="Output filename (default: auto-generated from filters)")
    return p.parse_args()


def main():
    missing = [pkg for pkg in ("requests", "ebooklib", "markdown")
               if not __import__("importlib").util.find_spec(pkg)]
    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        print(f"Run:  pip install {' '.join(missing)}")
        sys.exit(1)

    args = parse_args()

    # ── Fetch posts ───────────────────────────────────────────────────
    if args.url:
        post          = fetch_single_post(args.url)
        posts         = [post] if post else []
        default_title = posts[0]["title"] if posts else "Reddit post"

    elif args.series:
        posts         = fetch_series_from_wiki(args.series, min_words=args.min_words)
        series_name   = args.series.rstrip("/").split("/")[-1].replace("_", " ").title()
        default_title = series_name

    else:
        if args.author:
            posts = fetch_user_posts(
                subreddit=args.sub,
                author=args.author,
                limit=args.limit,
                min_words=args.min_words,
            )
            default_title = f"u/{args.author} – r/{args.sub}"
        else:
            posts = fetch_subreddit_posts(
                subreddit=args.sub,
                time_filter=args.time_filter,
                limit=args.limit,
                min_words=args.min_words,
                flair=args.flair,
                author=args.author,
            )
            suffix        = f" [{args.flair}]" if args.flair else ""
            default_title = f"r/{args.sub} – top {args.time_filter}, limit {args.limit}{suffix}"

    if not posts:
        print("\n✗ No posts found. Check the subreddit name and your connection.")
        sys.exit(1)

    # ── Sort chapters ─────────────────────────────────────────────────
    if args.sort_chapters == "score":
        posts.sort(key=lambda p: p["score"], reverse=True)
    elif args.sort_chapters == "date":
        posts.sort(key=lambda p: p["created_utc"])
    elif args.sort_chapters == "title":
        posts.sort(key=lambda p: p["title"].lower())

    # ── Build EPUB ────────────────────────────────────────────────────
    output_path = Path(args.output or _make_filename(args))
    build_epub(posts, output_path, args.title or default_title)


if __name__ == "__main__":
    main()
