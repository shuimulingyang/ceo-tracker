"""
fetcher.py — Fetches CEO-related news from free RSS sources.
No API keys required.
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from database import save_article, update_last_fetch

# ---------------------------------------------------------------------------
# CEO definitions
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Topic tags — keyword → tag name
# ---------------------------------------------------------------------------
TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "监管 Regulation": ["regulation", "regulatory", "sec", "cftc", "compliance", "legal", "law", "government", "congress", "legislation"],
    "Bitcoin": ["bitcoin", "btc", "satoshi", "halving"],
    "Ethereum": ["ethereum", "eth", "smart contract", "vitalik"],
    "DeFi": ["defi", "decentralized finance", "protocol", "yield", "liquidity pool", "amm", "dex"],
    "市场 Market": ["market", "bull", "bear", "price", "rally", "crash", "dump", "pump", "outlook", "forecast"],
    "ETF": ["etf", "spot bitcoin etf", "bitcoin etf", "exchange-traded fund"],
    "Web3": ["web3", "nft", "metaverse", "blockchain gaming", "dao"],
    "安全 Security": ["hack", "hacker", "security", "breach", "exploit", "vulnerability", "fraud", "scam", "phishing"],
    "机构 Institutional": ["institutional", "fund", "hedge fund", "asset manager", "blackrock", "fidelity", "investment"],
    "AI": ["artificial intelligence", "ai", "machine learning", "llm", "chatgpt", "openai"],
    "稳定币 Stablecoin": ["stablecoin", "usdt", "usdc", "dai", "pegged"],
    "Layer2": ["layer2", "layer 2", "l2", "rollup", "optimism", "arbitrum", "zk-proof"],
}

# ---------------------------------------------------------------------------
# Crypto-specific RSS feeds
# ---------------------------------------------------------------------------
CRYPTO_RSS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outbound/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CeoTrackerBot/1.0)"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_tags(text: str) -> List[str]:
    text_lower = text.lower()
    tags = []
    for tag, keywords in TOPIC_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            tags.append(tag)
    return tags[:6]


def clean_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator=" ", strip=True)


def extract_key_quote(raw_content: str, max_len: int = 250) -> str:
    """Try to pull a direct quote, else return first meaningful sentence."""
    text = clean_html(raw_content)
    # Look for direct quote patterns (curved or straight quotes)
    patterns = [
        r'["\u201c\u2018]([^"\u201d\u2019]{40,250})["\u201d\u2019]',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()[:max_len]
    # Fallback: first sentence > 60 chars
    for sent in re.split(r"(?<=[.!?])\s+", text):
        sent = sent.strip()
        if len(sent) > 60:
            return sent[:max_len]
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


def ceo_mentioned(text: str, search_terms: List[str]) -> bool:
    text_lower = text.lower()
    return any(term.lower() in text_lower for term in search_terms)


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

async def fetch_google_news(ceo_name: str, search_terms: List[str]) -> List[dict]:
    """Fetch from Google News RSS for each search term."""
    articles = []
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
        for term in search_terms:
            url = (
                "https://news.google.com/rss/search"
                f"?q={term.replace(' ', '+')}"
                "&hl=en-US&gl=US&ceid=US:en"
            )
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:15]:
                    title = entry.get("title", "")
                    # Strip " - Source Name" suffix Google News appends
                    source_match = re.search(r" - (.{3,60})$", title)
                    source = source_match.group(1) if source_match else "Google News"
                    clean_title = re.sub(r" - .{3,60}$", "", title).strip()

                    content = entry.get("summary", "") or entry.get("description", "")
                    full_text = clean_title + " " + content

                    if not ceo_mentioned(full_text, search_terms):
                        continue

                    articles.append({
                        "title": clean_title,
                        "content": content,
                        "url": entry.get("link", ""),
                        "source": source,
                        "ceo_name": ceo_name,
                        "exchange": CEOS[ceo_name]["exchange"],
                        "published_at": parse_date(entry),
                        "tags": extract_tags(full_text),
                        "key_quote": extract_key_quote(content),
                    })
            except Exception as e:
                print(f"[Google News] Error for {ceo_name}/{term}: {e}")
    return articles


async def fetch_crypto_feeds(ceo_name: str, search_terms: List[str]) -> List[dict]:
    """Fetch from major crypto RSS feeds and filter for CEO mentions."""
    articles = []
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
        for feed_name, feed_url in CRYPTO_RSS_FEEDS:
            try:
                resp = await client.get(feed_url)
                if resp.status_code != 200:
                    continue
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:30]:
                    title = entry.get("title", "")
                    content = (
                        entry.get("content", [{}])[0].get("value", "")
                        or entry.get("summary", "")
                        or entry.get("description", "")
                    )
                    full_text = title + " " + content

                    if not ceo_mentioned(full_text, search_terms):
                        continue

                    articles.append({
                        "title": title.strip(),
                        "content": content,
                        "url": entry.get("link", ""),
                        "source": feed_name,
                        "ceo_name": ceo_name,
                        "exchange": CEOS[ceo_name]["exchange"],
                        "published_at": parse_date(entry),
                        "tags": extract_tags(full_text),
                        "key_quote": extract_key_quote(content),
                    })
            except Exception as e:
                print(f"[CryptoRSS] Error for {feed_name}: {e}")
    return articles


# ---------------------------------------------------------------------------
# Main refresh
# ---------------------------------------------------------------------------

async def fetch_all_news() -> int:
    """Fetch news for all CEOs from all sources. Returns number of new articles."""
    print(f"[{datetime.utcnow().isoformat()}] Starting news fetch...")

    tasks = []
    for ceo_name, info in CEOS.items():
        tasks.append(fetch_google_news(ceo_name, info["search_terms"]))
        tasks.append(fetch_crypto_feeds(ceo_name, info["search_terms"]))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles: List[dict] = []
    for r in results:
        if isinstance(r, list):
            all_articles.extend(r)
        elif isinstance(r, Exception):
            print(f"[fetch_all_news] Task error: {r}")

    new_count = sum(1 for a in all_articles if save_article(a))
    update_last_fetch()

    print(f"[{datetime.utcnow().isoformat()}] Fetched {len(all_articles)} articles, {new_count} new.")
    return new_count
