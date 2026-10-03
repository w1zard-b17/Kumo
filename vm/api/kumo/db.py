"""SQLite (WAL) on the VM's local disk: library metadata, jobs queue, playback state."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    color     TEXT NOT NULL DEFAULT '#2be080',
    icon      TEXT NOT NULL DEFAULT 'film',
    position  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tags (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    color  TEXT NOT NULL DEFAULT '#ffffff'
);
CREATE TABLE IF NOT EXISTS videos (
    id             INTEGER PRIMARY KEY,
    youtube_id     TEXT NOT NULL UNIQUE,
    url            TEXT NOT NULL,
    title          TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    channel        TEXT NOT NULL DEFAULT '',
    duration       INTEGER NOT NULL DEFAULT 0,
    thumbnail_url  TEXT,
    file_id        TEXT,
    poster_file_id TEXT,
    file_size      INTEGER NOT NULL DEFAULT 0,
    resolution     TEXT,
    storage_path   TEXT,
    type           TEXT NOT NULL DEFAULT 'documentary',
    category_id    INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    subcategory    TEXT NOT NULL DEFAULT '',
    year           INTEGER,
    language       TEXT NOT NULL DEFAULT '',
    rating         INTEGER NOT NULL DEFAULT 0,
    classified     INTEGER NOT NULL DEFAULT 1,
    status         TEXT NOT NULL DEFAULT 'pending',   -- pending | ready | failed
    chapters       TEXT NOT NULL DEFAULT '[]',
    added_at       REAL NOT NULL,
    updated_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS videos_category ON videos(category_id);
CREATE INDEX IF NOT EXISTS videos_added ON videos(added_at);
CREATE TABLE IF NOT EXISTS video_tags (
    video_id  INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    tag_id    INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (video_id, tag_id)
);
CREATE TABLE IF NOT EXISTS subtitles (
    id        INTEGER PRIMARY KEY,
    video_id  INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    lang      TEXT NOT NULL,
    label     TEXT NOT NULL,
    file_id   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collections (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description  TEXT NOT NULL DEFAULT '',
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS collection_items (
    collection_id  INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    video_id       INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    added_at       REAL NOT NULL,
    PRIMARY KEY (collection_id, video_id)
);
CREATE TABLE IF NOT EXISTS jobs (
    id               INTEGER PRIMARY KEY,
    video_id         INTEGER REFERENCES videos(id) ON DELETE SET NULL,
    url              TEXT NOT NULL,
    title            TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'queued',
        -- queued | downloading | converting | uploading | paused | done | failed | canceled
    control          TEXT,                             -- pause | cancel, set by the API
    progress         REAL NOT NULL DEFAULT 0,
    speed            REAL,
    eta              INTEGER,
    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
    total_bytes      INTEGER,
    options          TEXT NOT NULL DEFAULT '{}',
    error            TEXT,
    attempts         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at  REAL,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL,
    finished_at      REAL
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
CREATE TABLE IF NOT EXISTS playback (
    video_id        INTEGER PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    position        REAL NOT NULL DEFAULT 0,
    duration        REAL NOT NULL DEFAULT 0,
    watched         INTEGER NOT NULL DEFAULT 0,
    last_played_at  REAL
);
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""

TYPES = {
    "documentary": "Documentary",
    "docuseries": "Docuseries",
    "short": "Short doc",
    "lecture": "Lecture",
}

DEFAULT_CATEGORIES = [
    ("Nature", "leaf"), ("Science", "atom"), ("History", "scroll"), ("Society", "users"),
    ("Tech", "cpu"), ("Crime", "fingerprint"), ("Biography", "user"), ("Art", "palette"),
    ("Sports", "trophy"), ("Other", "dots"),
]

DEFAULT_SETTINGS = {
    "quality": "1080",          # 720 | 1080 | best
    "subtitles": False,
    "sub_lang": "en",
    "auto_subs": True,          # fall back to YouTube auto-captions
    "audio_fallback": True,
    "naming": "{title}",        # {title} {year} {channel} {youtube_id}
    "language": "",
    "autoplay_next": True,
}

UNSORTED_DIR = "Unsorted"


def now() -> float:
    return time.time()


def connect() -> sqlite3.Connection:
    c = sqlite3.connect(settings.db, timeout=15, isolation_level=None, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=15000")
    return c


@contextmanager
def tx(c: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
    except BaseException:
        c.execute("ROLLBACK")
        raise
    c.execute("COMMIT")


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one short-lived connection per request."""
    c = connect()
    try:
        yield c
    finally:
        c.close()


def init() -> None:
    settings.db.parent.mkdir(parents=True, exist_ok=True)
    settings.tmp.mkdir(parents=True, exist_ok=True)
    c = connect()
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM categories LIMIT 1").fetchone():
            c.executemany(
                "INSERT INTO categories(name, icon, color, position) VALUES (?,?,?,?)",
                [(n, i, "#2be080", p) for p, (n, i) in enumerate(DEFAULT_CATEGORIES)],
            )
        for k, v in DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)", (k, json.dumps(v)))
    finally:
        c.close()


def get_settings(c: sqlite3.Connection) -> dict:
    out = dict(DEFAULT_SETTINGS)
    for r in c.execute("SELECT key, value FROM settings"):
        try:
            out[r["key"]] = json.loads(r["value"])
        except ValueError:
            pass
    return out


def set_tags(c: sqlite3.Connection, video_id: int, names: list[str], replace: bool = True) -> None:
    if replace:
        c.execute("DELETE FROM video_tags WHERE video_id=?", (video_id,))
    for name in {n.strip() for n in names if n and n.strip()}:
        c.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name[:40],))
        tag = c.execute("SELECT id FROM tags WHERE name=?", (name[:40],)).fetchone()
        c.execute("INSERT OR IGNORE INTO video_tags(video_id, tag_id) VALUES (?,?)", (video_id, tag["id"]))
