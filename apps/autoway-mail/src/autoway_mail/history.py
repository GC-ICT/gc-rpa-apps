from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

QUARANTINE_THRESHOLD = 3
QUARANTINE_RETRY = timedelta(hours=24)

SCHEMA = """
CREATE TABLE IF NOT EXISTS mail (
    key            TEXT PRIMARY KEY,
    mid            TEXT NOT NULL DEFAULT '',
    sender         TEXT NOT NULL DEFAULT '',
    subject        TEXT NOT NULL DEFAULT '',
    received_at    TEXT NOT NULL DEFAULT '',
    document_no    TEXT NOT NULL DEFAULT '',
    failures       INTEGER NOT NULL DEFAULT 0,
    last_error     TEXT NOT NULL DEFAULT '',
    last_failed_at TEXT NOT NULL DEFAULT '',
    secured        INTEGER NOT NULL DEFAULT 0,
    updated_at     TEXT NOT NULL DEFAULT ''
)
"""


@dataclass(frozen=True)
class Record:
    key: str
    mid: str
    sender: str
    subject: str
    received_at: str
    document_no: str
    failures: int
    last_error: str
    last_failed_at: str
    secured: bool

    @property
    def registered(self) -> bool:
        return bool(self.document_no)

    @property
    def label(self) -> str:
        return f"[{self.sender}] {self.subject}"


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def to_record(row: sqlite3.Row) -> Record:
    return Record(
        key=row["key"],
        mid=row["mid"],
        sender=row["sender"],
        subject=row["subject"],
        received_at=row["received_at"],
        document_no=row["document_no"],
        failures=int(row["failures"]),
        last_error=row["last_error"],
        last_failed_at=row["last_failed_at"],
        secured=bool(row["secured"]),
    )


class History:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def find(self, key: str) -> Record | None:
        if not key:
            return None
        row = self.connection.execute("SELECT * FROM mail WHERE key = ?", (key,)).fetchone()
        return None if row is None else to_record(row)

    def remember(self, key: str, *, mid: str, sender: str, subject: str, received_at: str) -> None:
        self.connection.execute(
            """
            INSERT INTO mail (key, mid, sender, subject, received_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                mid = excluded.mid,
                sender = excluded.sender,
                subject = excluded.subject,
                received_at = excluded.received_at,
                updated_at = excluded.updated_at
            """,
            (key, mid, sender, subject, received_at, now_text()),
        )
        self.connection.commit()

    def _update(self, key: str, **fields: object) -> None:
        assignments = ", ".join(f"{column} = ?" for column in fields)
        self.connection.execute(
            f"UPDATE mail SET {assignments}, updated_at = ? WHERE key = ?",
            (*fields.values(), now_text(), key),
        )
        self.connection.commit()

    def mark_registered(self, key: str, document_no: str) -> None:
        self._update(key, document_no=document_no)

    def mark_done(self, key: str) -> None:
        self._update(key, failures=0, last_error="", last_failed_at="")

    def mark_secured(self, key: str) -> None:
        self._update(key, secured=1)

    def mark_failed(self, key: str, error: str) -> int:
        self.connection.execute(
            """
            UPDATE mail
               SET failures = failures + 1, last_error = ?, last_failed_at = ?, updated_at = ?
             WHERE key = ?
            """,
            (error[:500], now_text(), now_text(), key),
        )
        self.connection.commit()
        found = self.find(key)
        return found.failures if found else 1

    def quarantine(self, key: str, error: str) -> None:
        self._update(
            key,
            failures=QUARANTINE_THRESHOLD,
            last_error=error[:500],
            last_failed_at=now_text(),
        )

    def quarantined(self, record: Record | None, *, moment: datetime | None = None) -> bool:
        if record is None or record.failures < QUARANTINE_THRESHOLD:
            return False
        if not record.last_failed_at:
            return True
        try:
            failed_at = datetime.fromisoformat(record.last_failed_at)
        except ValueError:
            return True
        return (moment or datetime.now()) - failed_at < QUARANTINE_RETRY

    def _select(self, where: str, *params: object) -> tuple[Record, ...]:
        rows = self.connection.execute(f"SELECT * FROM mail WHERE {where}", params).fetchall()
        return tuple(to_record(row) for row in rows)

    def secured_mails(self) -> tuple[Record, ...]:
        return self._select("secured = 1 ORDER BY received_at DESC")

    def quarantined_mails(self) -> tuple[Record, ...]:
        return self._select(
            "failures >= ? ORDER BY last_failed_at DESC",
            QUARANTINE_THRESHOLD,
        )


@contextmanager
def opened(path: Path) -> Iterator[History]:
    history = History(path)
    try:
        yield history
    finally:
        history.close()
