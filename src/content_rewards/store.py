"""Durable local state. Every mutation is transactional and scheduler claims are atomic."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, payload TEXT NOT NULL,
                PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at TEXT, kind TEXT,
                entity_id TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS schedules(id TEXT PRIMARY KEY, action TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL, next_run REAL NOT NULL, lease_until REAL NOT NULL DEFAULT 0,
                lease_token TEXT, payload TEXT NOT NULL);
            """)
            # Additive migration for early local databases.
            columns = {row[1] for row in db.execute("PRAGMA table_info(schedules)")}
            if "lease_token" not in columns:
                db.execute("ALTER TABLE schedules ADD COLUMN lease_token TEXT")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def put(self, kind: str, key: str, payload: dict):
        with self.connect() as db:
            db.execute("INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload",
                       (kind, key, json.dumps(payload, allow_nan=False)))

    def get(self, kind: str, key: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        if row is None:
            raise KeyError(f"Unknown {kind}: {key}")
        return json.loads(row[0])

    def list(self, kind: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM records WHERE kind=? ORDER BY id", (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def claim_job(self, key: str, expected: str, updated: dict, previous: dict | None = None) -> bool:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM records WHERE kind='job' AND id=?", (key,)).fetchone()
            if row is None or json.loads(row[0])["state"] != expected:
                return False
            if previous is not None and json.loads(row[0]) != previous:
                return False
            db.execute("UPDATE records SET payload=? WHERE kind='job' AND id=?", (json.dumps(updated), key))
        return True

    def create_candidate(self, job: dict) -> bool:
        """Reserve an automatic campaign/platform candidate in the same transaction as its job."""
        key = job["campaign_id"] + ":" + job["platform"]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute("INSERT OR IGNORE INTO records VALUES('candidate',?,?)",
                                (key, json.dumps({"job_id": job["id"]})))
            if result.rowcount != 1:
                return False
            db.execute("INSERT INTO records VALUES('job',?,?)", (job["id"], json.dumps(job)))
        return True

    def event(self, kind: str, entity_id: str, payload: dict):
        with self.connect() as db:
            db.execute("INSERT INTO events(at,kind,entity_id,payload) VALUES(?,?,?,?)",
                       (utcnow(), kind, entity_id, json.dumps(payload, allow_nan=False)))

    def schedule(self, key: str, action: str, interval: int, payload: dict, now: float):
        if action not in {"rank", "metrics", "publish", "discover", "prepare"} or interval < 60:
            raise ValueError("Supported actions: discover/rank/prepare/metrics/publish; interval must be >=60 seconds")
        with self.connect() as db:
            db.execute("INSERT INTO schedules(id,action,interval_seconds,next_run,payload) VALUES(?,?,?,?,?) "
                       "ON CONFLICT(id) DO NOTHING", (key, action, interval, now, json.dumps(payload)))

    def claim_due(self, now: float, limit: int | None = None) -> list[dict]:
        claimed = []
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT * FROM schedules WHERE next_run<=? AND lease_until<=? ORDER BY next_run,id LIMIT ?",
                              (now, now, limit if limit is not None else 1)).fetchall()
            for row in rows:
                token = uuid4().hex
                # Leases exceed the worker's maximum operation timeout.
                db.execute("UPDATE schedules SET lease_until=?,lease_token=? WHERE id=?", (now + 1800, token, row["id"]))
                item = dict(row)
                item["lease_token"] = token
                claimed.append(item)
        return claimed

    def finish_schedule(self, key: str, token: str, now: float):
        with self.connect() as db:
            db.execute("UPDATE schedules SET next_run=?+interval_seconds,lease_until=0,lease_token=NULL "
                       "WHERE id=? AND lease_token=?", (now, key, token))

    def schedules(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,action,interval_seconds,next_run,lease_until,payload FROM schedules ORDER BY id")]

    def cancel_schedule(self, key: str):
        with self.connect() as db:
            db.execute("DELETE FROM schedules WHERE id=?", (key,))
