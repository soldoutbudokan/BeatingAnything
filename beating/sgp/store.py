"""SQLite cache with append-only attempts and source-order invalidation."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from .models import book_revision, digest, scope, timestamp


class QuoteStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS inventories (
                scope TEXT PRIMARY KEY, revision TEXT NOT NULL, captured_at TEXT NOT NULL,
                epoch INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL,
                request TEXT NOT NULL, started_at TEXT NOT NULL, result TEXT,
                epoch INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS attempts_key ON attempts(key, id);
        """)
        # Preserve early local ledgers as the cache schema gains generations.
        for table in ("inventories", "attempts"):
            if "epoch" not in {row["name"] for row in self.db.execute(f"PRAGMA table_info({table})")}:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN epoch INTEGER NOT NULL DEFAULT 0")
        self.db.commit()

    def close(self):
        self.db.close()

    def register(self, board, book):
        key, inventory = digest(scope(board, book)), board["books"][book]
        revision, captured_at = book_revision(inventory), inventory["captured_at"]
        row = self.db.execute("SELECT * FROM inventories WHERE scope=?", (key,)).fetchone()
        if row and timestamp(captured_at) < timestamp(row["captured_at"]):
            raise ValueError("older inventory cannot replace a newer scope")
        if row and timestamp(captured_at) == timestamp(row["captured_at"]) and revision != row["revision"]:
            raise ValueError("conflicting inventory revision at same capture time")
        epoch = (row["epoch"] + int(row["revision"] != revision)) if row else 0
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO inventories(scope,revision,captured_at,epoch) VALUES (?,?,?,?)",
                            (key, revision, captured_at, epoch))
        return bool(row and row["revision"] != revision)

    def active(self, request):
        row = self.db.execute("SELECT revision FROM inventories WHERE scope=?", (request["scope_key"],)).fetchone()
        return row is not None and row["revision"] == request["revision"]

    def begin(self, request, now):
        row = self.db.execute("SELECT epoch,revision FROM inventories WHERE scope=?", (request["scope_key"],)).fetchone()
        if row is None or row["revision"] != request["revision"]:
            raise ValueError("cannot collect an inactive inventory revision")
        with self.db:
            cursor = self.db.execute("INSERT INTO attempts(key,request,started_at,epoch) VALUES(?,?,?,?)",
                                     (request["key"], json.dumps(request, sort_keys=True), now, row["epoch"]))
        return cursor.lastrowid

    def finish(self, attempt_id, result):
        # Late responses retain evidence but never supersede a later attempt.
        with self.db:
            changed = self.db.execute("UPDATE attempts SET result=? WHERE id=? AND result IS NULL",
                                      (json.dumps(result, sort_keys=True, allow_nan=False), attempt_id)).rowcount
        if changed != 1:
            raise ValueError("attempt missing or already completed")

    def get(self, request, now, ttl):
        if not self.active(request):
            return None
        current = self.db.execute("SELECT epoch FROM inventories WHERE scope=?", (request["scope_key"],)).fetchone()
        row = self.db.execute("SELECT result,epoch FROM attempts WHERE key=? ORDER BY id DESC LIMIT 1",
                              (request["key"],)).fetchone()
        if not row or row["result"] is None or row["epoch"] != current["epoch"]:
            return None
        result = json.loads(row["result"])
        # Latest unavailable/error replaces earlier prices; failures aren't
        # rescued by falling back to a profitable old response.
        age = (timestamp(now) - timestamp(result["received_at"])).total_seconds()
        if not 0 <= age <= ttl:
            return None
        return result
