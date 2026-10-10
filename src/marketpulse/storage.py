from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return encoded.encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class RawStore:
    """Immutable local content-addressed provider captures."""

    def __init__(self, root: Path):
        self.root = root

    def put(self, value: Any) -> str:
        content = canonical_bytes(value)
        key = hashlib.sha256(content).hexdigest()
        path = self.root / key[:2] / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(content)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError("content-addressed artifact collision or corruption") from None
        return key

    def get(self, key: str) -> Any:
        if len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
            raise ValueError("invalid artifact digest")
        content = (self.root / key[:2] / f"{key}.json").read_bytes()
        if hashlib.sha256(content).hexdigest() != key:
            raise ValueError("raw artifact digest mismatch")
        return json.loads(content)


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS extraction_jobs (
  job_key TEXT PRIMARY KEY,
  session TEXT NOT NULL,
  run_id TEXT,
  status TEXT NOT NULL,
  manifest_json TEXT
);
CREATE TABLE IF NOT EXISTS source_pages (
  digest TEXT PRIMARY KEY,
  job_key TEXT NOT NULL,
  source TEXT NOT NULL,
  received_at TEXT NOT NULL,
  request_id TEXT,
  FOREIGN KEY(job_key) REFERENCES extraction_jobs(job_key)
);
CREATE TABLE IF NOT EXISTS article_versions (
  version_hash TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL,
  symbols_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  received_at TEXT NOT NULL,
  headline TEXT NOT NULL,
  summary TEXT,
  raw_page_digest TEXT NOT NULL,
  FOREIGN KEY(raw_page_digest) REFERENCES source_pages(digest)
);
CREATE TABLE IF NOT EXISTS job_article_versions (
  job_key TEXT NOT NULL,
  version_hash TEXT NOT NULL,
  raw_page_digest TEXT NOT NULL,
  received_at TEXT NOT NULL,
  PRIMARY KEY(job_key, version_hash),
  FOREIGN KEY(job_key) REFERENCES extraction_jobs(job_key),
  FOREIGN KEY(version_hash) REFERENCES article_versions(version_hash),
  FOREIGN KEY(raw_page_digest) REFERENCES source_pages(digest)
);
CREATE TABLE IF NOT EXISTS price_bars (
  version_hash TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  bar_time TEXT NOT NULL,
  feed TEXT NOT NULL,
  adjustment TEXT NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL,
  received_at TEXT NOT NULL,
  raw_page_digest TEXT NOT NULL,
  FOREIGN KEY(raw_page_digest) REFERENCES source_pages(digest)
);
CREATE TABLE IF NOT EXISTS job_price_bars (
  job_key TEXT NOT NULL,
  version_hash TEXT NOT NULL,
  raw_page_digest TEXT NOT NULL,
  received_at TEXT NOT NULL,
  PRIMARY KEY(job_key, version_hash),
  FOREIGN KEY(job_key) REFERENCES extraction_jobs(job_key),
  FOREIGN KEY(version_hash) REFERENCES price_bars(version_hash),
  FOREIGN KEY(raw_page_digest) REFERENCES source_pages(digest)
);
CREATE TABLE IF NOT EXISTS web_captures (
  digest TEXT PRIMARY KEY,
  job_key TEXT NOT NULL,
  url TEXT NOT NULL,
  received_at TEXT NOT NULL,
  raw_digest TEXT NOT NULL,
  FOREIGN KEY(job_key) REFERENCES extraction_jobs(job_key)
);
CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_hash TEXT PRIMARY KEY,
  job_key TEXT NOT NULL,
  session TEXT NOT NULL,
  symbol TEXT NOT NULL,
  cutoff_utc TEXT NOT NULL,
  availability_tier TEXT NOT NULL,
  fresh_for_0900 INTEGER NOT NULL,
  article_hashes_json TEXT NOT NULL,
  bar_hashes_json TEXT NOT NULL,
  spy_bar_hashes_json TEXT NOT NULL,
  news_count INTEGER NOT NULL,
  FOREIGN KEY(job_key) REFERENCES extraction_jobs(job_key)
);
CREATE INDEX IF NOT EXISTS ix_bars_symbol_time ON price_bars(symbol, bar_time);
CREATE INDEX IF NOT EXISTS ix_snapshots_session_symbol ON snapshots(session, symbol);
CREATE TABLE IF NOT EXISTS session_outcomes (
  outcome_hash TEXT PRIMARY KEY,
  job_key TEXT NOT NULL UNIQUE,
  manifest_json TEXT NOT NULL,
  FOREIGN KEY(job_key) REFERENCES extraction_jobs(job_key)
);
CREATE TABLE IF NOT EXISTS dataset_rows (
  row_hash TEXT PRIMARY KEY,
  contract_hash TEXT NOT NULL,
  session TEXT NOT NULL,
  symbol TEXT NOT NULL,
  UNIQUE(contract_hash, session, symbol)
);
"""


class ExtractionStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def get_job(self, key: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM extraction_jobs WHERE job_key=?", (key,)).fetchone()
        return dict(row) if row else None

    def reserve_job(self, key: str, session: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO extraction_jobs(job_key,session,status) VALUES (?,?,?)",
                (key, session, "PENDING"),
            )

    def set_run_id(self, key: str, run_id: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE extraction_jobs SET run_id=? WHERE job_key=? AND run_id IS NULL",
                (run_id, key),
            )

    def set_status(self, key: str, status: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE extraction_jobs SET status=? WHERE job_key=?", (status, key))

    def commit_extract(
        self,
        key: str,
        manifest: dict[str, Any],
        pages: list[dict[str, Any]],
        articles: list[dict[str, Any]],
        bars: list[dict[str, Any]],
        web: list[dict[str, Any]],
        snapshots: list[dict[str, Any]],
    ) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for page in pages:
                db.execute(
                    "INSERT OR IGNORE INTO source_pages VALUES (?,?,?,?,?)",
                    (page["digest"], key, page["source"], page["received_at"], page["request_id"]),
                )
            for article in articles:
                db.execute(
                    "INSERT OR IGNORE INTO article_versions VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        article["version_hash"], article["provider_id"],
                        json.dumps(article["symbols"]), article["created_at"],
                        article["updated_at"], article["received_at"],
                        article["headline"], article["summary"], article["raw_page_digest"],
                    ),
                )
                db.execute(
                    "INSERT OR IGNORE INTO job_article_versions VALUES (?,?,?,?)",
                    (key, article["version_hash"], article["raw_page_digest"],
                     article["received_at"]),
                )
            for bar in bars:
                db.execute(
                    "INSERT OR IGNORE INTO price_bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        bar["version_hash"], bar["symbol"], bar["bar_time"], bar["feed"],
                        bar["adjustment"], bar["open"], bar["high"], bar["low"],
                        bar["close"], bar["volume"], bar["received_at"],
                        bar["raw_page_digest"],
                    ),
                )
                db.execute(
                    "INSERT OR IGNORE INTO job_price_bars VALUES (?,?,?,?)",
                    (key, bar["version_hash"], bar["raw_page_digest"], bar["received_at"]),
                )
            for item in web:
                db.execute(
                    "INSERT OR IGNORE INTO web_captures VALUES (?,?,?,?,?)",
                    (item["digest"], key, item["url"], item["received_at"], item["raw_digest"]),
                )
            for item in snapshots:
                db.execute(
                    "INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        item["snapshot_hash"], key, item["session"], item["symbol"],
                        item["cutoff_utc"], item["availability_tier"],
                        int(item["fresh_for_0900"]),
                        json.dumps(item["article_hashes"]), json.dumps(item["bar_hashes"]),
                        json.dumps(item["spy_bar_hashes"]), item["news_count"],
                    ),
                )
            db.execute(
                "UPDATE extraction_jobs SET status='COMPLETE', manifest_json=? WHERE job_key=?",
                (json.dumps(manifest, sort_keys=True), key),
            )

    def commit_audit_pages(
        self, key: str, manifest: dict[str, Any], pages: list[dict[str, Any]]
    ) -> None:
        """Keep outcome-source probes out of prediction article/bar tables."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for page in pages:
                db.execute(
                    "INSERT OR IGNORE INTO source_pages VALUES (?,?,?,?,?)",
                    (page["digest"], key, page["source"],
                     page["received_at"], page["request_id"]),
                )
            db.execute(
                "UPDATE extraction_jobs SET status='COMPLETE', manifest_json=? WHERE job_key=?",
                (json.dumps(manifest, sort_keys=True), key),
            )

    def commit_outcome(self, key: str, manifest: dict, pages: list[dict]) -> None:
        """Atomically append verified outcomes; never write prediction price tables."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for page in pages:
                db.execute(
                    "INSERT OR IGNORE INTO source_pages VALUES (?,?,?,?,?)",
                    (page["digest"], key, page["source"],
                     page["received_at"], page["request_id"]),
                )
            encoded = json.dumps(manifest, sort_keys=True)
            db.execute("INSERT INTO session_outcomes VALUES (?,?,?)",
                       (digest(manifest), key, encoded))
            db.execute(
                "UPDATE extraction_jobs SET status='COMPLETE', manifest_json=? WHERE job_key=?",
                (encoded, key),
            )

    def append_dataset_row(self, row_hash: str, contract_hash: str, row: dict) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT row_hash FROM dataset_rows WHERE contract_hash=? AND session=? "
                "AND symbol=?", (contract_hash, row["session"], row["symbol"]),
            ).fetchone()
            if existing and existing["row_hash"] != row_hash:
                raise ValueError("dataset row conflict: create a new contract, never overwrite")
            db.execute("INSERT OR IGNORE INTO dataset_rows VALUES (?,?,?,?)",
                       (row_hash, contract_hash, row["session"], row["symbol"]))
