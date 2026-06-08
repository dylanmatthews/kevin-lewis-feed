#!/usr/bin/env python3
"""Generate an RSS 2.0 feed for National Affairs' "Findings" daily roundups
(compiled by Kevin Lewis), which the site does not offer natively.

Design notes
------------
* **Stateless / idempotent.** Each run rebuilds the feed from the latest
  ``MAX_ITEMS`` posts on the index page. Every item's GUID is its permanent
  post URL, so feed readers (NetNewsWire) dedupe automatically and nothing
  needs to be tracked between runs. Re-running can't create duplicates.
* **No JavaScript needed.** The Findings index and the article bodies are
  fully server-rendered, so plain requests + BeautifulSoup is enough.
* **Polite.** One index request per page plus one request per article, with a
  short delay and a descriptive User-Agent.

Run:  ``python build_feed.py``  ->  writes ``feed.xml`` and ``index.html``.
"""

from __future__ import annotations

import datetime as dt
import sys
import time

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# --- Configuration ----------------------------------------------------------

BASE = "https://www.nationalaffairs.com"
INDEX_PATH = "/blog/findings-a-daily-roundup"
DETAIL_PREFIX = "/blog/detail/findings-a-daily-roundup/"

MAX_ITEMS = 15          # how many recent roundups to include in the feed
MAX_INDEX_PAGES = 4     # how many index pages to walk to collect MAX_ITEMS
REQUEST_DELAY = 1.0     # seconds to wait between requests (be polite)
TIMEOUT = 30            # per-request timeout in seconds

# Set to False to publish a short excerpt + "Read on National Affairs" link
# instead of the full roundup. The courteous choice if the feed URL is public.
FULL_TEXT = True
EXCERPT_CHARS = 500     # excerpt length when FULL_TEXT is False

USER_AGENT = (
    "NA-Findings-RSS/1.0 (personal RSS generator for NetNewsWire; "
    "not affiliated with National Affairs)"
)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


# --- Helpers ----------------------------------------------------------------

def fetch(url: str) -> str:
    resp = session.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_date(text: str) -> dt.datetime | None:
    """Parse 'June 08, 2026' (any case) into an aware UTC datetime."""
    cleaned = " ".join(text.split()).title()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(cleaned, fmt).replace(
                tzinfo=dt.timezone.utc
            )
        except ValueError:
            continue
    return None


def index_url(page: int) -> str:
    base = BASE + INDEX_PATH
    return base if page <= 1 else f"{base}?page={page}"


def collect_entries() -> list[dict]:
    """Walk index pages newest-first and return up to MAX_ITEMS posts."""
    entries: list[dict] = []
    seen: set[str] = set()
    for page in range(1, MAX_INDEX_PAGES + 1):
        html = fetch(index_url(page))
        soup = BeautifulSoup(html, "html.parser")
        page_count = 0
        for art in soup.find_all("article"):
            a = art.find(
                "a",
                href=lambda h: h and DETAIL_PREFIX in h,
            )
            if not a:
                continue
            href = a["href"]
            url = href if href.startswith("http") else BASE + href
            if url in seen:
                continue
            seen.add(url)
            page_count += 1

            h2 = a.find("h2")
            h5 = a.find("h5")
            h3 = a.find("h3")
            title = h2.get_text(strip=True) if h2 else a.get_text(strip=True)
            subtitle = h3.get_text(" ", strip=True) if h3 else ""
            date = parse_date(h5.get_text()) if h5 else None

            entries.append(
                {"title": title, "subtitle": subtitle, "url": url, "date": date}
            )
            if len(entries) >= MAX_ITEMS:
                return entries
        if page_count == 0:
            break  # ran out of pages
        time.sleep(REQUEST_DELAY)
    return entries


def extract_body(html: str) -> str:
    """Return cleaned inner HTML of a Findings detail page's body."""
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find(
        "article", class_=lambda c: c and "medium-centered" in c
    ) or soup.find("article")
    if not article:
        return ""

    # Remove page chrome, leaving only the study summaries.
    for el in article.select(
        "address, fieldset, .article-social-bar, .author-bio, script, style"
    ):
        el.decompose()

    # Drop the article's own headline; it duplicates the feed item's title.
    first_h1 = article.find("h1")
    if first_h1:
        first_h1.decompose()

    # Make relative links absolute so they work inside a feed reader.
    for a in article.find_all("a", href=True):
        if a["href"].startswith("/"):
            a["href"] = BASE + a["href"]

    return article.decode_contents().strip()


def make_excerpt(body_html: str, url: str) -> str:
    text = BeautifulSoup(body_html, "html.parser").get_text(" ", strip=True)
    snippet = text[:EXCERPT_CHARS].rstrip()
    if len(text) > EXCERPT_CHARS:
        snippet += "…"
    return f'<p>{snippet}</p><p><a href="{url}">Read the full roundup on National Affairs</a></p>'


# --- Feed assembly ----------------------------------------------------------

def build() -> None:
    entries = collect_entries()
    if not entries:
        sys.exit(
            "ERROR: parsed zero entries from the index — the site's HTML "
            "structure has probably changed; selectors in build_feed.py "
            "need updating."
        )

    fg = FeedGenerator()
    fg.id(BASE + INDEX_PATH)
    fg.title("National Affairs — Findings (Kevin Lewis)")
    fg.link(href=BASE + INDEX_PATH, rel="alternate")
    fg.description(
        "Daily roundups of academic studies, compiled by Kevin Lewis for "
        "National Affairs. Unofficial reader-generated feed."
    )
    fg.language("en")
    fg.author({"name": "Kevin Lewis"})
    fg.generator("na-findings-rss")

    for e in entries:
        try:
            body = extract_body(fetch(e["url"]))
        except Exception as exc:  # noqa: BLE001 - keep going on one bad post
            print(f"WARN: failed to fetch {e['url']}: {exc}", file=sys.stderr)
            body = ""
        time.sleep(REQUEST_DELAY)

        title = e["title"]
        if e["subtitle"]:
            title = f"{e['title']} — {e['subtitle']}"

        if body:
            content = body if FULL_TEXT else make_excerpt(body, e["url"])
        else:
            content = f'<p><a href="{e["url"]}">Read on National Affairs</a></p>'

        fe = fg.add_entry()
        fe.guid(e["url"], permalink=True)
        fe.id(e["url"])
        fe.title(title)
        fe.link(href=e["url"])
        fe.author({"name": "Kevin Lewis"})
        if e["date"]:
            fe.published(e["date"])  # -> <pubDate> in RSS
        # Full HTML in <description> is what RSS readers (incl. NNW) render.
        fe.description(content)
        fe.content(content, type="CDATA")  # also emit content:encoded

    dates = [e["date"] for e in entries if e["date"]]
    fg.lastBuildDate(max(dates) if dates else dt.datetime.now(dt.timezone.utc))

    fg.rss_file("feed.xml", pretty=True)
    write_landing(entries)
    print(f"Wrote feed.xml ({len(entries)} items) and index.html")


def write_landing(entries: list[dict]) -> None:
    rows = "\n".join(
        f'    <li><a href="{e["url"]}">{e["title"]}</a>'
        f'{(" — " + e["subtitle"]) if e["subtitle"] else ""}</li>'
        for e in entries
    )
    html = f"""<!doctype html>
<meta charset="utf-8">
<title>National Affairs Findings — unofficial RSS</title>
<style>body{{font:16px/1.5 -apple-system,system-ui,sans-serif;max-width:42rem;margin:3rem auto;padding:0 1rem}}</style>
<h1>National Affairs &ldquo;Findings&rdquo; — unofficial RSS</h1>
<p>Daily academic-study roundups compiled by Kevin Lewis. This is a
reader-generated feed (the site offers none).</p>
<p><strong>Feed URL:</strong> <a href="feed.xml">feed.xml</a> &mdash; paste it
into your RSS reader.</p>
<h2>Latest</h2>
<ul>
{rows}
</ul>
"""
    with open("index.html", "w", encoding="utf-8") as fh:
        fh.write(html)


if __name__ == "__main__":
    build()
