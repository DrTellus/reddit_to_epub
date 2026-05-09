#!/usr/bin/env python3
"""
reddit_to_epub.py  –  Reddit → EPUB for Xteink X4
===================================================

Laster ned tekstposter fra Reddit og pakker dem som en pen EPUB-fil.
Ingen API-nøkkel nødvendig.

Installasjon:
    pip install requests ebooklib markdown

─────────────────────────────────────────────────────────────────────
EKSEMPLER
─────────────────────────────────────────────────────────────────────

  # Topp 25 fra r/hfy noensinne
  python reddit_to_epub.py --sub hfy --time all --limit 25

  # Topp 50 fra r/nosleep dette året, kun OC-flair
  python reddit_to_epub.py --sub nosleep --time year --limit 50 --flair OC

  # Alle poster av én forfatter i en subreddit (kronologisk)
  python reddit_to_epub.py --sub hfy --author Ralts_Bloodthorne --limit 100

  # En hel serie via HFY-wiki
  python reddit_to_epub.py --series https://www.reddit.com/r/hfy/wiki/series/the_deathworlders

  # Enkelt post via URL
  python reddit_to_epub.py --url "https://reddit.com/r/hfy/comments/abc123/tittel/"

  # Med egendefinert tittel og minimumsordtelling
  python reddit_to_epub.py --sub hfy --time all --limit 50 --min-words 1000 --title "HFY Beste 50"
"""

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import markdown as md_lib
from ebooklib import epub

# ─────────────────────────────────────────────────────────────────────
# KONFIGURASJON
# ─────────────────────────────────────────────────────────────────────

HEADERS      = {"User-Agent": "reddit-to-epub/2.0 (personal use)"}
REQUEST_DELAY = 1.2
REDDIT_BASE   = "https://www.reddit.com"

# ─────────────────────────────────────────────────────────────────────
# CSS – luftig og lesevennlig for e-ink
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
# HJELPE-FUNKSJONER
# ─────────────────────────────────────────────────────────────────────

def _get(url: str, params: dict = None) -> dict:
    r = requests.get(url, headers=HEADERS, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _clean(text: str):
    t = text.strip()
    return None if (not t or t in ("[removed]", "[deleted]")) else t


def _esc(s: str) -> str:
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


def _make_post(data: dict, series_name: str = None) -> dict | None:
    text = _clean(data.get("selftext", ""))
    if not text or not data.get("is_self"):
        return None
    return {
        "title":       data.get("title", "Uten tittel"),
        "author":      data.get("author", "ukjent"),
        "subreddit":   data.get("subreddit", ""),
        "series":      series_name,
        "text":        text,
        "score":       data.get("score", 0),
        "created_utc": data.get("created_utc", 0),
        "created_str": datetime.fromtimestamp(
                           data.get("created_utc", 0), tz=datetime.now().astimezone().tzinfo
                       ).strftime("%d. %b %Y"),
        "flair":       data.get("link_flair_text") or "",
        "url":         REDDIT_BASE + data.get("permalink", ""),
        "word_count":  len(text.split()),
    }


# ─────────────────────────────────────────────────────────────────────
# REDDIT-HENTING
# ─────────────────────────────────────────────────────────────────────

def fetch_subreddit_posts(
    subreddit:   str,
    time_filter: str = "all",
    limit:       int = 25,
    min_words:   int = 0,
    flair:       str = None,
    author:      str = None,
) -> list[dict]:
    """Henter tekstposter fra en subreddit sortert etter top."""
    posts = []
    after = None
    # Hent ekstra buffer hvis vi filtrerer, ellers nøyaktig antall
    budget = min(limit * 5, 500) if (flair or author or min_words) else limit

    print(f"\n📥 Henter fra r/{subreddit}  [top/{time_filter}, maks {limit}]")

    while len(posts) < limit and budget > 0:
        page_size = min(100, budget)
        params = {"limit": page_size, "t": time_filter}
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
            if min_words  and post["word_count"] < min_words:
                continue
            if flair      and flair.lower() not in post["flair"].lower():
                continue
            if author     and post["author"].lower() != author.lower():
                continue
            posts.append(post)
            if len(posts) >= limit:
                break

        if not after:
            break
        time.sleep(REQUEST_DELAY)

    print(f"   ✓ {len(posts)} poster funnet")
    return posts[:limit]


def fetch_user_posts(
    subreddit: str,
    author:    str,
    limit:     int = 100,
    min_words: int = 0,
) -> list[dict]:
    """Henter alle poster av én bruker i en subreddit (kronologisk)."""
    posts = []
    after = None

    print(f"\n📥 Henter poster av u/{author} i r/{subreddit}")

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

    posts.sort(key=lambda p: p["created_utc"])   # kronologisk
    print(f"   ✓ {len(posts)} poster funnet")
    return posts[:limit]


def fetch_single_post(url: str, series_name: str = None) -> dict | None:
    """Henter én enkelt post via full Reddit-URL."""
    data = _get(url.rstrip("/") + ".json")
    return _make_post(data[0]["data"]["children"][0]["data"], series_name)


def fetch_series_from_wiki(wiki_url: str, min_words: int = 0) -> list[dict]:
    """
    Henter alle poster i en serie via en HFY wiki-side.
    Eks.: https://www.reddit.com/r/hfy/wiki/series/the_deathworlders
    """
    series_name = wiki_url.rstrip("/").split("/")[-1].replace("_", " ").title()
    print(f"\n📥 Henter serie «{series_name}» fra wiki")

    data    = _get(wiki_url.rstrip("/") + ".json")
    wiki_md = data["data"]["content_md"]

    # Finn alle Reddit-post-lenker i wikiteksten
    links_raw = re.findall(
        r'https?://(?:www\.)?reddit\.com/r/\w+/comments/\w+/[^\s\)\]"\']*',
        wiki_md,
    )
    # Dedupliser, bevar rekkefølge
    seen, links = set(), []
    for l in links_raw:
        if l not in seen:
            seen.add(l)
            links.append(l)

    print(f"   Fant {len(links)} lenker")

    posts = []
    for i, link in enumerate(links, 1):
        slug = link.split("/comments/")[1][:45] if "/comments/" in link else link
        print(f"   [{i:3d}/{len(links)}] {slug}...")
        try:
            post = fetch_single_post(link, series_name)
            if post and (not min_words or post["word_count"] >= min_words):
                posts.append(post)
        except Exception as e:
            print(f"          ⚠ Hoppet over: {e}")
        time.sleep(REQUEST_DELAY)

    print(f"   ✓ {len(posts)} kapitler hentet")
    return posts


# ─────────────────────────────────────────────────────────────────────
# INNHOLDSFORMATERING
# ─────────────────────────────────────────────────────────────────────

def reddit_md_to_html(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    return md_lib.markdown(text, extensions=["extra", "nl2br"])


def post_to_xhtml(post: dict) -> str:
    meta_parts = [f"r/{post['subreddit']}"]
    if post.get("series"):
        meta_parts.append(f"Serie: {post['series']}")
    meta_parts.append(f"Publisert {post['created_str']}")
    meta_parts.append(f"↑ {post['score']:,} upvotes")
    meta_parts.append(f"u/{post['author']}")
    meta_str = "  ·  ".join(meta_parts)

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
# EPUB-BYGGING
# ─────────────────────────────────────────────────────────────────────

def build_epub(posts: list[dict], output_path: Path, book_title: str) -> None:
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
    print(f"\n📖 Bygger EPUB med {len(posts)} kapitler...")

    for i, post in enumerate(posts, 1):
        chap = epub.EpubHtml(
            title=post["title"],
            file_name=f"Text/chap_{i:04d}.xhtml",
            lang="en",
        )
        chap.content = post_to_xhtml(post).encode("utf-8")
        chap.add_item(style)
        book.add_item(chap)
        chapters.append(chap)
        toc.append(epub.Link(f"Text/chap_{i:04d}.xhtml", post["title"], f"chap{i}"))
        total_words += post["word_count"]

    book.toc   = toc
    book.spine = ["nav"] + chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(str(output_path), book)

    size_kb = output_path.stat().st_size // 1024
    print(f"\n✅ Ferdig!")
    print(f"   Fil:       {output_path}")
    print(f"   Kapitler:  {len(posts)}")
    print(f"   Ord:       {total_words:,}")
    print(f"   Størrelse: {size_kb} KB")


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Last ned Reddit-historier og pakk dem som EPUB for Xteink X4.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EKSEMPLER:
  %(prog)s --sub hfy --time all --limit 50
  %(prog)s --sub nosleep --time year --limit 30 --min-words 500
  %(prog)s --sub hfy --author Ralts_Bloodthorne --limit 100
  %(prog)s --series https://www.reddit.com/r/hfy/wiki/series/the_deathworlders
  %(prog)s --url "https://reddit.com/r/hfy/comments/abc123/tittel/"
        """,
    )

    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--sub",    metavar="SUBREDDIT",
                     help="Subreddit å hente fra (uten r/)")
    src.add_argument("--series", metavar="WIKI_URL",
                     help="HFY wiki-URL til en hel serie")
    src.add_argument("--url",    metavar="URL",
                     help="URL til én enkelt Reddit-post")

    p.add_argument("--author",    metavar="BRUKERNAVN",
                   help="Kun poster fra denne brukeren (kombineres med --sub)")
    p.add_argument("--flair",     metavar="TEKST",
                   help="Kun poster med denne flair-teksten (f.eks. OC)")
    p.add_argument("--time",
                   choices=["hour","day","week","month","year","all"],
                   default="all", dest="time_filter",
                   help="Tidsperiode for top-sortering (standard: all)")
    p.add_argument("--limit", type=int, default=25,
                   help="Maks antall historier (standard: 25)")
    p.add_argument("--min-words", type=int, default=0, metavar="N",
                   help="Filtrer bort historier kortere enn N ord")
    p.add_argument("--sort-chapters",
                   choices=["score","date","original"],
                   default="original",
                   help="Rekkefølge i boken: score | date | original (standard: original)")
    p.add_argument("--title",  metavar="TITTEL",
                   help="Egendefinert boktittel")
    p.add_argument("--output", metavar="FIL",
                   help="Output-filnavn (standard: auto-generert)")
    return p.parse_args()


def main():
    for pkg in ("requests", "ebooklib", "markdown"):
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            print(f"Mangler pakke: {pkg}\nKjør:  pip install requests ebooklib markdown")
            sys.exit(1)

    args = parse_args()

    # ── Hent poster ──────────────────────────────────────────────────
    if args.url:
        post = fetch_single_post(args.url)
        posts         = [post] if post else []
        default_title = posts[0]["title"] if posts else "Reddit post"
        default_file  = "reddit_post.epub"

    elif args.series:
        posts         = fetch_series_from_wiki(args.series, min_words=args.min_words)
        series_slug   = args.series.rstrip("/").split("/")[-1]
        default_title = series_slug.replace("_", " ").title()
        default_file  = f"{series_slug}.epub"

    else:
        if args.author:
            posts = fetch_user_posts(
                subreddit=args.sub,
                author=args.author,
                limit=args.limit,
                min_words=args.min_words,
            )
            default_title = f"u/{args.author} – r/{args.sub}"
            default_file  = f"r_{args.sub}_{args.author}.epub"
        else:
            posts = fetch_subreddit_posts(
                subreddit=args.sub,
                time_filter=args.time_filter,
                limit=args.limit,
                min_words=args.min_words,
                flair=args.flair,
                author=args.author,
            )
            suffix        = f"_{args.flair}" if args.flair else ""
            default_title = f"r/{args.sub} – top {args.time_filter}{suffix}"
            default_file  = f"r_{args.sub}_top_{args.time_filter}{suffix}.epub"

    if not posts:
        print("\n✗ Ingen poster funnet.")
        sys.exit(1)

    # ── Sortering innad i dokumentet ─────────────────────────────────
    if args.sort_chapters == "score":
        posts.sort(key=lambda p: p["score"], reverse=True)
    elif args.sort_chapters == "date":
        posts.sort(key=lambda p: p["created_utc"])

    # ── Bygg EPUB ────────────────────────────────────────────────────
    build_epub(
        posts,
        Path(args.output or default_file),
        args.title or default_title,
    )


if __name__ == "__main__":
    main()
