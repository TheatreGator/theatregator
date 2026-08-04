"""
News/Gossip Digest Generator
-----------------------------
Pulls headlines from RSS feeds and Reddit, then builds a static HTML
digest page. Each item has a "Tweet this" button that opens X's compose
window pre-filled with credited text — you review and post manually.

No X API key needed at all, since nothing posts automatically.

Setup:
1. pip install -r requirements.txt
2. Edit config.py to list your RSS feeds and subreddits.
3. Run: python digest_generator.py
4. Open docs/index.html in a browser.
"""

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import feedparser
import requests

import config

STATE_FILE = Path("seen.json")
OUTPUT_DIR = Path("docs")
OUTPUT_FILE = OUTPUT_DIR / "index.html"
TWEET_MAX_LEN = 280
MAX_ITEMS_PER_SOURCE = 5


# ---------- State (avoid showing the same item every run) ----------

def load_seen():
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def save_seen(seen_ids):
    trimmed = list(seen_ids)[-3000:]
    STATE_FILE.write_text(json.dumps(trimmed))


# ---------- Collectors ----------

def fetch_rss_items():
    items = []
    for feed_url in config.RSS_FEEDS:
        parsed = feedparser.parse(feed_url)
        source_name = parsed.feed.get("title", feed_url)
        for entry in parsed.entries[:MAX_ITEMS_PER_SOURCE]:
            items.append({
                "id": entry.get("id", entry.get("link")),
                "title": entry.get("title", "").strip(),
                "url": entry.get("link"),
                "source": f"via {source_name}",
            })
    return items


def fetch_reddit_items():
    items = []
    headers = {"User-Agent": "news-gossip-digest/1.0 (personal project)"}
    for sub in config.SUBREDDITS:
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub}/top.json",
                params={"limit": MAX_ITEMS_PER_SOURCE, "t": "day"},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            posts = resp.json()["data"]["children"]
        except (requests.RequestException, KeyError, ValueError):
            continue

        for post in posts:
            data = post["data"]
            if data.get("stickied"):
                continue
            items.append({
                "id": data["id"],
                "title": data["title"].strip(),
                "url": f"https://reddit.com{data['permalink']}",
                "source": f"via u/{data['author']} on r/{sub}",
            })
    return items


# ---------- Formatting ----------

def format_tweet(item):
    title, source, url = item["title"], item["source"], item["url"]
    suffix = f" {source} {url}"
    available = TWEET_MAX_LEN - len(suffix)
    if len(title) > available:
        title = title[: max(available - 1, 0)].rstrip() + "…"
    return f"{title}{suffix}"


def build_html(items):
    rows = []
    for item in items:
        tweet_text = format_tweet(item)
        intent_url = "https://twitter.com/intent/tweet?text=" + quote(tweet_text)
        rows.append(f"""
        <div class="card">
          <p class="title">{html.escape(item['title'])}</p>
          <p class="meta">{html.escape(item['source'])}</p>
          <p class="preview">{html.escape(tweet_text)}</p>
          <div class="actions">
            <a class="btn tweet" href="{intent_url}" target="_blank" rel="noopener">Tweet this</a>
            <a class="btn link" href="{html.escape(item['url'])}" target="_blank" rel="noopener">Open article</a>
            <button class="btn copy" onclick="navigator.clipboard.writeText({json.dumps(tweet_text)})">Copy text</button>
          </div>
        </div>""")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>News & Gossip Digest</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; background: #f5f5f7; margin: 0; padding: 16px; color: #1a1a1a; }}
  h1 {{ font-size: 1.3rem; margin-bottom: 4px; }}
  .updated {{ color: #666; font-size: 0.85rem; margin-bottom: 20px; }}
  .card {{ background: white; border-radius: 12px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .title {{ font-weight: 600; margin: 0 0 4px; }}
  .meta {{ color: #666; font-size: 0.85rem; margin: 0 0 8px; }}
  .preview {{ font-size: 0.85rem; color: #444; background: #f9f9f9; border-radius: 8px; padding: 8px; margin: 0 0 10px; white-space: pre-wrap; }}
  .actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .btn {{ border: none; border-radius: 20px; padding: 8px 14px; font-size: 0.85rem; text-decoration: none; cursor: pointer; }}
  .tweet {{ background: #1d9bf0; color: white; }}
  .link {{ background: #eee; color: #1a1a1a; }}
  .copy {{ background: #eee; color: #1a1a1a; }}
  .empty {{ color: #666; padding: 40px 0; text-align: center; }}
</style>
</head>
<body>
  <h1>News & Gossip Digest</h1>
  <p class="updated">Updated {generated_at}</p>
  {"".join(rows) if rows else '<p class="empty">No new items this run.</p>'}
</body>
</html>"""


def main():
    seen = load_seen()
    candidates = fetch_rss_items() + fetch_reddit_items()
    fresh = [c for c in candidates if c["id"] not in seen]

    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(build_html(fresh))
    (OUTPUT_DIR / ".nojekyll").touch()  # tell GitHub Pages to skip Jekyll processing

    for item in fresh:
        seen.add(item["id"])
    save_seen(seen)

    print(f"Wrote {len(fresh)} items to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
