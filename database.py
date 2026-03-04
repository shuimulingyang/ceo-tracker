import sqlite3
import json
from datetime import datetime
from typing import List, Optional

DB_PATH = "ceo_tracker.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            url TEXT UNIQUE,
            source TEXT,
            ceo_name TEXT,
            exchange TEXT,
            published_at TEXT,
            tags TEXT DEFAULT '[]',
            key_quote TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS last_fetch (
            id INTEGER PRIMARY KEY,
            fetched_at TEXT
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ceo_name ON articles(ceo_name)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_published_at ON articles(published_at DESC)
    """)
    conn.commit()
    conn.close()


def save_article(article: dict) -> bool:
    """Save article to DB. Return True if new record was inserted."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO articles
                (title, content, url, source, ceo_name, exchange, published_at, tags, key_quote)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            article.get("title", ""),
            article.get("content", ""),
            article.get("url", ""),
            article.get("source", ""),
            article.get("ceo_name", ""),
            article.get("exchange", ""),
            article.get("published_at", ""),
            json.dumps(article.get("tags", []), ensure_ascii=False),
            article.get("key_quote", ""),
        ))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"DB save error: {e}")
        return False
    finally:
        conn.close()


def get_articles(
    ceo: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[dict]:
    conn = get_db()
    cursor = conn.cursor()

    conditions = []
    params: list = []

    if ceo and ceo != "all":
        conditions.append("ceo_name = ?")
        params.append(ceo)

    if search and search.strip():
        conditions.append("(title LIKE ? OR key_quote LIKE ? OR tags LIKE ?)")
        term = f"%{search.strip()}%"
        params.extend([term, term, term])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    cursor.execute(
        f"""
        SELECT * FROM articles
        {where}
        ORDER BY published_at DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    )
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        article = dict(row)
        try:
            article["tags"] = json.loads(article.get("tags", "[]"))
        except Exception:
            article["tags"] = []
        result.append(article)
    return result


def get_stats() -> dict:
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total FROM articles")
    total = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT ceo_name, COUNT(*) AS cnt
        FROM articles
        GROUP BY ceo_name
        ORDER BY cnt DESC
    """)
    by_ceo = {row["ceo_name"]: row["cnt"] for row in cursor.fetchall()}

    cursor.execute(
        "SELECT fetched_at FROM last_fetch WHERE id = 1"
    )
    row = cursor.fetchone()
    last_updated = row["fetched_at"] if row else None

    conn.close()
    return {"total": total, "by_ceo": by_ceo, "last_updated": last_updated}


def update_last_fetch():
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO last_fetch (id, fetched_at) VALUES (1, ?)",
        (datetime.utcnow().isoformat(),),
    )
    conn.commit()
    conn.close()
