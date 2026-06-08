# National Affairs "Findings" → RSS

National Affairs publishes Kevin Lewis's daily **Findings** study roundups at
<https://www.nationalaffairs.com/blog/findings-a-daily-roundup> but offers no
RSS feed. This repo generates one.

A small Python script scrapes the latest roundups and writes a standard
**RSS 2.0** `feed.xml` (full text of each roundup). A GitHub Actions cron job
runs it daily and publishes the feed via GitHub Pages, so you can subscribe in
NetNewsWire (or any reader) at a stable URL — and it keeps working whether or
not your Mac is on.

## How it works

- `build_feed.py` — fetches the Findings index, then each recent post, and
  emits `feed.xml` + a small `index.html` landing page.
  - **Stateless:** every run rebuilds the feed from the latest `MAX_ITEMS`
    posts. Each item's GUID is its permanent URL, so readers dedupe
    automatically — re-running never creates duplicates, and there's no state
    file to corrupt.
  - **No browser needed:** the site is server-rendered, so plain
    `requests` + `BeautifulSoup` suffice.
- `.github/workflows/build-feed.yml` — runs the script daily at 13:00 UTC
  (~8–9am US Eastern), then commits `feed.xml`/`index.html` if they changed.

## One-time setup (GitHub Actions + Pages)

1. **Create a public repo** (e.g. `na-findings-rss`) and push these files:
   ```sh
   git init -b main
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/<you>/na-findings-rss.git
   git push -u origin main
   ```
   (Pages is free for public repos; private repos need a paid plan.)
2. **Allow the workflow to commit:** repo **Settings → Actions → General →
   Workflow permissions → "Read and write permissions" → Save.**
3. **Turn on Pages:** repo **Settings → Pages → Build and deployment →
   Source: "Deploy from a branch" → Branch: `main` / `(root)` → Save.**
4. **Run it once now:** repo **Actions → "Build Findings RSS feed" →
   Run workflow.** (The cron only fires going forward.)
5. Your feed is at:
   ```
   https://<you>.github.io/na-findings-rss/feed.xml
   ```

## Subscribe in NetNewsWire

NetNewsWire → **File → New Feed…** (or `⌘N`) → paste the feed URL above. New
roundups appear automatically each day; if you use NNW on iPhone/iPad too, it
syncs there as well.

## Notes & knobs (top of `build_feed.py`)

- `FULL_TEXT = True` — the full roundup appears in each item. Because a Pages
  feed is **publicly reachable**, set this to `False` to publish a short
  excerpt + "Read on National Affairs" link instead (the more courteous option
  for a public URL). The feed URL is unlisted but not secret.
- `MAX_ITEMS` (default 15) — how many recent roundups to include.
- `REQUEST_DELAY` (default 1.0s) — politeness delay between requests. Daily
  load on the site is ~1 index request + ~15 article fetches.
- The scheduled workflow won't be auto-disabled for inactivity: Findings posts
  ~daily, so the bot commits regularly and keeps the repo active.
- If National Affairs changes its HTML, the script exits with a clear error
  ("parsed zero entries…") rather than publishing an empty feed; update the
  CSS selectors in `collect_entries()` / `extract_body()`.

## Run locally (optional)

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python build_feed.py   # writes feed.xml + index.html
```
