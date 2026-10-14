"""Private content-addressed objects and durable, fenced cloud job state."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from marketpulse.cloud_connections import database_uri, s3_client
from marketpulse.storage import canonical_bytes

BUCKET = "research-artifacts"
MAX_OBJECT_BYTES = 64 * 1024 * 1024


class CloudState:
    def __init__(self, values):
        import psycopg

        self.db = psycopg.connect(
            database_uri(values["MARKETPULSE_DATABASE_URL"], "marketpulse_worker"),
            connect_timeout=10, autocommit=True,
        )
        self.storage = s3_client(values)

    def close(self):
        self.db.close()

    def put(self, content: bytes, kind: str) -> str:
        if not content or len(content) > MAX_OBJECT_BYTES:
            raise ValueError("private object size out of bounds")
        if kind not in {"projection", "checkpoint", "model", "input", "archive"}:
            raise ValueError("unsupported private object kind")
        key = hashlib.sha256(content).hexdigest()
        object_key = f"immutable/{key[:2]}/{key}"
        # Repeating this immutable, digest-bound write is safe; never upload arbitrary paths.
        self.storage.put_object(Bucket=BUCKET, Key=object_key, Body=content,
                                ContentType="application/octet-stream")
        if self.get(key) != content:
            raise ValueError("private object read-back differs")
        self.db.execute(
            "INSERT INTO marketpulse.objects(sha256,object_key,size_bytes,kind,verified_at) "
            "VALUES(%s,%s,%s,%s,%s) ON CONFLICT(sha256) DO NOTHING",
            (key, object_key, len(content), kind, datetime.now(timezone.utc)),
        )
        return key

    def get(self, key: str) -> bytes:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("invalid private object digest")
        response = self.storage.get_object(Bucket=BUCKET, Key=f"immutable/{key[:2]}/{key}")
        stream = response["Body"]
        try:
            if response["ContentLength"] > MAX_OBJECT_BYTES:
                raise ValueError("private object exceeds read bound")
            content = stream.read(MAX_OBJECT_BYTES + 1)
        finally:
            stream.close()
        if len(content) > MAX_OBJECT_BYTES or hashlib.sha256(content).hexdigest() != key:
            raise ValueError("private object checksum mismatch")
        return content

    def claim(self, key: str, kind: str, lease_seconds=3600) -> str | None:
        if not 60 <= lease_seconds <= 14400:
            raise ValueError("lease duration out of bounds")
        owner = str(uuid.uuid4())
        row = self.db.execute(
            "INSERT INTO marketpulse.jobs(job_key,kind,status,owner,lease_until) "
            "VALUES(%s,%s,'RUNNING',%s,now()+%s*interval '1 second') "
            "ON CONFLICT(job_key) DO NOTHING RETURNING owner",
            (key, kind, owner, lease_seconds),
        ).fetchone()
        if row:
            return owner
        prior = self.db.execute(
            "SELECT status,lease_until<now() FROM marketpulse.jobs WHERE job_key=%s", (key,)
        ).fetchone()
        if prior[0] == "COMPLETE":
            return None
        if prior == ("RUNNING", True):
            self.db.execute(
                "UPDATE marketpulse.jobs SET status='UNKNOWN',updated_at=now() "
                "WHERE job_key=%s AND status='RUNNING' AND lease_until<now()", (key,)
            )
        # An expired task is retained; not reset, stolen or silently re-executed.
        raise ValueError("cloud job is owned or retained; reconcile before retry")

    def heartbeat(self, key: str, owner: str, seconds=3600):
        if not 60 <= seconds <= 14400:
            raise ValueError("lease duration out of bounds")
        changed = self.db.execute(
            "UPDATE marketpulse.jobs SET lease_until=now()+%s*interval '1 second',updated_at=now() "
            "WHERE job_key=%s AND owner=%s AND status='RUNNING' AND lease_until>now()",
            (seconds, key, owner),
        ).rowcount
        if changed != 1:
            raise ValueError("cloud writer fence expired or changed")

    def checkpoint(self, key: str, owner: str, checkpoint_hash: str):
        changed = self.db.execute(
            "UPDATE marketpulse.jobs SET checkpoint_hash=%s,updated_at=now() "
            "WHERE job_key=%s AND owner=%s AND status='RUNNING' AND lease_until>now()",
            (checkpoint_hash, key, owner),
        ).rowcount
        if changed != 1:
            raise ValueError("checkpoint writer fence expired or changed")

    def complete(self, key: str, owner: str, checkpoint_hash: str, result_hash: str,
                 projection_id: str | None = None, payload: dict | None = None):
        from psycopg.types.json import Jsonb

        with self.db.transaction():
            updated = self.db.execute(
                "UPDATE marketpulse.jobs SET status='COMPLETE',checkpoint_hash=%s,"
                "result_hash=%s,updated_at=now() WHERE job_key=%s AND owner=%s "
                "AND status='RUNNING' AND lease_until>now() RETURNING job_key",
                (checkpoint_hash, result_hash, key, owner),
            ).fetchone()
            if not updated:
                raise ValueError("completion writer fence expired or changed")
            if projection_id is not None:
                if (payload is None or
                        hashlib.sha256(canonical_bytes(payload)).hexdigest() != result_hash):
                    raise ValueError("projection differs from verified private object")
                self.db.execute(
                    "INSERT INTO marketpulse.projections(projection_id,kind,object_hash,job_key,"
                    "payload) VALUES(%s,%s,%s,%s,%s)",
                    (projection_id, payload["kind"], result_hash, key, Jsonb(payload)),
                )


def sqlite_checkpoint(path: Path) -> bytes:
    """Use SQLite backup to include committed WAL pages, never copy an active WAL database."""
    with tempfile.TemporaryDirectory(prefix="marketpulse-checkpoint-") as directory:
        backup = Path(directory) / "native.sqlite3"
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(backup)) as target:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("native checkpoint integrity failed")
        return backup.read_bytes()
