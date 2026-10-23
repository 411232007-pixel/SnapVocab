"""SQLite persistence. Every read is scoped by user_id; all queries are parameterised."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..models import CARD_FIELDS, Card, en_key, ja_key
from ..timefmt import now_utc

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    {", ".join(f"{name} TEXT NOT NULL" for name in CARD_FIELDS)},
    en_key TEXT NOT NULL,
    ja_key TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_user_id ON records (user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_records_user_key ON records (user_id, en_key, ja_key);
"""


@dataclass(frozen=True)
class Record:
    id: int
    user_id: str
    created_at: str
    card: Card
    en_key: str
    ja_key: str


@dataclass(frozen=True)
class SaveResult:
    record: Record
    times_seen: int  # including this save
    first_seen_at: str  # ISO UTC of the first record with the same word pair


@dataclass(frozen=True)
class Stats:
    total: int
    distinct: int


def _row_to_record(row: sqlite3.Row) -> Record:
    return Record(
        id=row["id"],
        user_id=row["user_id"],
        created_at=row["created_at"],
        card=Card(**{name: row[name] for name in CARD_FIELDS}),
        en_key=row["en_key"],
        ja_key=row["ja_key"],
    )


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._keep: sqlite3.Connection | None = None
        if self.path == ":memory:":  # one shared connection so tests see their own data
            self._keep = self._new_connection()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _connect(self):
        if self._keep is not None:
            return _Shared(self._keep)
        return _Owned(self._new_connection())

    def add_record(self, user_id: str, card: Card) -> SaveResult:
        ek, jk = en_key(card.en_word), ja_key(card.ja_word)
        created = now_utc()
        with self._connect() as conn:
            prior = conn.execute(
                "SELECT COUNT(*) AS n, MIN(created_at) AS first_at FROM records "
                "WHERE user_id = ? AND en_key = ? AND ja_key = ?",
                (user_id, ek, jk),
            ).fetchone()
            cols = ["user_id", "created_at", *CARD_FIELDS, "en_key", "ja_key"]
            cur = conn.execute(
                f"INSERT INTO records ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                [user_id, created, *card.as_dict().values(), ek, jk],
            )
            conn.commit()
            record = Record(cur.lastrowid, user_id, created, card, ek, jk)
        return SaveResult(record, prior["n"] + 1, prior["first_at"] or created)

    def get(self, user_id: str, record_id: int) -> Record | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM records WHERE user_id = ? AND id = ?", (user_id, record_id)
            ).fetchone()
        return _row_to_record(row) if row else None

    def recent(self, user_id: str, limit: int = 10) -> list[Record]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM records WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def all_records(self, user_id: str) -> list[Record]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM records WHERE user_id = ? ORDER BY id", (user_id,)
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def stats(self, user_id: str) -> Stats:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total, "
                "(SELECT COUNT(*) FROM (SELECT DISTINCT en_key, ja_key FROM records "
                " WHERE user_id = ?)) AS distinct_n FROM records WHERE user_id = ?",
                (user_id, user_id),
            ).fetchone()
        return Stats(row["total"], row["distinct_n"])


class _Owned:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, *exc) -> None:
        self.conn.close()


class _Shared:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, *exc) -> None:
        return None
