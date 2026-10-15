"""SQLite storage for tracked products, their platform listings and price history."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    platform_id TEXT NOT NULL,
    url TEXT,
    title TEXT,
    brand TEXT,
    variant TEXT,
    eans TEXT,
    model TEXT,
    mrp REAL,
    price REAL,
    currency TEXT DEFAULT 'INR',
    -- unverified | live | manual | unavailable | error
    status TEXT NOT NULL DEFAULT 'unverified',
    -- where the price came from: 'Amazon Creators API' or 'Manual check'
    source TEXT,
    note TEXT,
    verified_at TEXT,
    last_checked_at TEXT,
    role TEXT NOT NULL,              -- source | match
    match_state TEXT NOT NULL,       -- confirmed | suggested
    match_score INTEGER,
    match_reasons TEXT,
    UNIQUE (product_id, platform)
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    mrp REAL,
    price REAL,
    status TEXT NOT NULL,
    source TEXT,
    recorded_at TEXT NOT NULL
);
"""


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path=None):
    path = path or config.db_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
