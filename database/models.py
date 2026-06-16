import aiosqlite
from datetime import datetime, date

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    daily_limit INTEGER DEFAULT 20,
    downloads_today INTEGER DEFAULT 0,
    last_reset TEXT,
    extra_downloads INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    url TEXT,
    platform TEXT,
    title TEXT,
    file_size INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS stats (
    date TEXT PRIMARY KEY,
    total_downloads INTEGER DEFAULT 0,
    total_users INTEGER DEFAULT 0,
    by_platform TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS direct_links (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    platform TEXT,
    title TEXT,
    file_path TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    expires_at TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
"""

async def init_db(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(DB_SCHEMA)
        await db.commit()
