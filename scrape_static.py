"""
scrape_static.py — Standalone scraper for GitHub Pages deployment.

Fetches CEO news from free RSS sources and writes results to
docs/data/articles.json so GitHub Pages can serve them statically.

Usage:
    python scrape_static.py

GitHub Actions runs this script on a schedule automatically.
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUTPUT_DIR   = Path("docs/data")
ARTICLES_FILE = OUTPUT_DIR / "articles.json"
CEOS_FILE    = OUTPUT_DIR / "ceos.json"
MAX_ARTICLES = 500   # keep latest N articles across all CEOs

CEOS: Dict[str, dict] = {
    "Brian Armstrong": {
        "exchange": "Coinbase",
        "role": "CEO",
        "twitter": "brian_armstrong",
        "color": "#0052FF",
        "search_terms": ["Brian Armstrong", "Coinbase CEO"],
    },
    "CZ": {
        "exchange": "Binance",
        "role": "Founder / Former CEO",
        "twitter": "cz_binance",
        "color": "#F0B90B",
        "search_terms": ["CZ Binance", "Changpeng Zhao"],
    },
    "Richard Teng": {
        "exchange": "Binance",
        "role": "CEO",
        "twitter": "_RichardTeng",
        "color": "#e8a500",
        "search_terms": ["Richard Teng", "Binance CEO Richard"],
    },
    "Ben Zhou": {
        "exchange": "Bybit",
        "role": "CEO",
        "twitter": "benbybit",
        "color": "#1DA462",
        "search_terms": ["Ben Zhou Bybit", "Bybit CEO"],
    },
    "Star Xu": {
        "exchange": "OKX",
        "role": "Founder",
        "twitter": "staroversea",
        "color": "#2E59DA",
        "search_terms": ["Star Xu OKX", "OKX CEO", "徐明星 OKX"],
    },
}

TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "监管 Regulation": ["regulation", "regulatory", "sec", "cftc", "compliance", "legal", "government", "congress"],
    "Bitcoin": ["bitcoin", "btc", "satoshi", "halving"],
    "Ethereum": ["ethereum", "eth", "smart contract", "vitalik"],
    "DeFi": ["defi", "decentralized finance", "protocol", "yield", "liquidity pool", "amm", "dex"],
    "市场 Market": ["market", "bull", "bear", "price", "rally", "crash", "outlook", "forecast"],
    "ETF": ["etf", "spot bitcoin etf", "bitcoin etf", "exchange-traded fund"],
    "Web3": ["web3", "nft", "metaverse", "dao"],
    "安全 Security": ["hack", "security", "breach", "exploit", "fraud", "scam", "phishing"],
    "机构 Institutional": ["institutional", "fund", "hedge fund", "blackrock", "fidelity"],
    "AI": ["artificial intelligence", " ai ", "machine learning", "llm"],
    "稳定币 Stablecoin": ["stablecoin", "usdt", "usdc", "dai"],
    "Layer2": ["layer2", "layer 2", "l2", "rollup"],
}

CRYPTO_RSS_FEEDS = [
    ("CoinDesk",        "https://www.coindesk.com/arc/outbound/rss/"),
    ("CoinTelegraph",   "https://cointelegraph.com/rss"),
    ("Decrypt",         "https://decrypt.co/feed"),
    ("The Block",       "https://www.theblock.co/rss.xml"),
    ("Bitcoin Magazine","https://bitcoinmagazine.com/.rss/full/"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CeoTrackerBot/1.0)"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def extract_tags(text: str) -> List[str]:
    t = text.lower()
    return [tag for tag, kws in TOPIC_KEYWORDS.items() if any(kw in t for kw in kws)][:6]


def clean_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)


def extract_key_quote(raw: str, max_len: int = 250) -> str:
    text = clean_html(raw)
    m = re.search(r'["\u201c\u2018]([^"\u201d\u2019]{40,250})["\u201d\u2019]', text)
    if m:
        return m.group(1).strip()[:max_len]
    for sent in re.split(r"(?<=[.!?])\s+", text):
        s = sent.strip()
        if len(s) > 60:
            return s[:max_len]
    return text[:max_len]


def parse_date(entry) -> str:
    for attr in ("published", "updated", "created"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return date_parser.parse(val).astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.utcnow().isoformat()


def ceo_mentioned(text: str, terms: List[str]) -> bool:
    t = text.lower()
    return any(term.lower() in t for term in terms)


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------
async def fetch_google_news(ceo_name: str, terms: List[str]) -> List[dict]:
    articles = []
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
        for term in terms:
            url = (
                "https://news.google.com/rss/search"
                f"?q={term.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
            )
            try:
                r = await client.get(url)
                if r.status_code != 200:
                    continue
                feed = feedparser.parse(r.text)
                for entry in feed.entries[:15]:
                    title = entry.get("title", "")
                    sm = re.search(r" - (.{3,60})$", title)
                    source = sm.group(1) if sm else "News"
                    clean_title = re.sub(r" - .{3,60}$", "", title).strip()
                    content = entry.get("summary", "") or entry.get("description", "")
                    if not ceo_mentioned(clean_title + " " + content, terms):
                        continue
                    articles.append({
                        "title": clean_title,
                        "content": content,
                        "url": entry.get("link", ""),
                        "source": source,
                        "ceo_name": ceo_name,
                        "exchange": CEOS[ceo_name]["exchange"],
                        "published_at": parse_date(entry),
                        "tags": extract_tags(clean_title + " " + content),
                        "key_quote": extract_key_quote(content),
                    })
            except Exception as e:
                print(f"  [GoogleNews] {ceo_name}/{term}: {e}")
    return articles


async def fetch_crypto_feeds(ceo_name: str, terms: List[str]) -> List[dict]:
    articles = []
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
        for feed_name, feed_url in CRYPTO_RSS_FEEDS:
            try:
                r = await client.get(feed_url)
                if r.status_code != 200:
                    continue
                feed = feedparser.parse(r.text)
                for entry in feed.entries[:30]:
                    title = entry.get("title", "")
                    content = (
                        entry.get("content", [{}])[0].get("value", "")
                        or entry.get("summary", "")
                        or entry.get("description", "")
                    )
                    if not ceo_mentioned(title + " " + content, terms):
                        continue
                    articles.append({
                        "title": title.strip(),
                        "content": content,
                        "url": entry.get("link", ""),
                        "source": feed_name,
                        "ceo_name": ceo_name,
                        "exchange": CEOS[ceo_name]["exchange"],
                        "published_at": parse_date(entry),
                        "tags": extract_tags(title + " " + content),
                        "key_quote": extract_key_quote(content),
                    })
            except Exception as e:
                print(f"  [CryptoRSS] {feed_name}: {e}")
    return articles


async def scrape_all() -> List[dict]:
    tasks = []
    for ceo_name, info in CEOS.items():
        tasks.append(fetch_google_news(ceo_name, info["search_terms"]))
        tasks.append(fetch_crypto_feeds(ceo_name, info["search_terms"]))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    articles: List[dict] = []
    for r in results:
        if isinstance(r, list):
            articles.extend(r)
    return articles


# ---------------------------------------------------------------------------
# Data management
# ---------------------------------------------------------------------------
def load_existing() -> List[dict]:
    if ARTICLES_FILE.exists():
        try:
            with open(ARTICLES_FILE, encoding="utf-8") as f:
                return json.load(f).get("articles", [])
        except Exception:
            pass
    return []


def merge(existing: List[dict], new: List[dict]) -> List[dict]:
    seen = {a["url"] for a in existing if a.get("url")}
    added = 0
    for a in new:
        if a.get("url") and a["url"] not in seen:
            existing.append(a)
            seen.add(a["url"])
            added += 1
    print(f"  +{added} new articles (total before trim: {len(existing)})")
    existing.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return existing[:MAX_ARTICLES]


def save(articles: List[dict]):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    by_ceo: Dict[str, int] = {}
    for a in articles:
        name = a.get("ceo_name", "Unknown")
        by_ceo[name] = by_ceo.get(name, 0) + 1

    payload = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(articles),
        "by_ceo": by_ceo,
        "articles": articles,
    }
    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  Saved {len(articles)} articles → {ARTICLES_FILE}")


def save_ceos():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        name: {k: v for k, v in info.items() if k != "search_terms"}
        for name, info in CEOS.items()
    }
    with open(CEOS_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  Saved CEO definitions → {CEOS_FILE}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    print(f"[{datetime.utcnow().isoformat()}Z] Starting scrape...")
    save_ceos()
    existing = load_existing()
    print(f"  Loaded {len(existing)} existing articles")
    fresh = await scrape_all()
    print(f"  Fetched {len(fresh)} articles from feeds")
    merged = merge(existing, fresh)
    save(merged)
    print(f"[{datetime.utcnow().isoformat()}Z] Done. Total: {len(merged)} articles.")


if __name__ == "__main__":
    asyncio.run(main())
