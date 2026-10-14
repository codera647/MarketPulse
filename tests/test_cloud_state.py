from __future__ import annotations

import hashlib
import io
import sqlite3
from contextlib import closing

import pytest

from marketpulse.cloud_migrate import HOSTS, direct_uri
from marketpulse.cloud_state import CloudState, sqlite_checkpoint


def owner_uri(host=HOSTS['review'], role='marketpulse_owner'):
    return f"postgresql://{role}:test-password@{host}/marketpulse?sslmode=require"


@pytest.mark.parametrize('target', HOSTS)
def test_migrations_use_only_direct_existing_owner_endpoint(target):
    direct = owner_uri(HOSTS[target])
    pooled = direct.replace('.c-13.', '-pooler.c-13.')
    assert direct_uri(pooled, target) == direct


@pytest.mark.parametrize('uri', [
    owner_uri(role='marketpulse_worker'), owner_uri(host='unrelated.neon.tech'),
    owner_uri().replace('require', 'disable'), owner_uri() + '&sslmode=disable',
    owner_uri() + '#fragment', owner_uri().replace('/marketpulse?', '/neondb?'),
])
def test_migrations_reject_other_roles_targets_or_ambiguous_tls(uri):
    with pytest.raises(ValueError):
        direct_uri(uri, 'review')


def test_wal_checkpoint_carries_committed_rows_and_checks_integrity(tmp_path):
    path = tmp_path / 'native.sqlite3'
    with closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE receipts(n int)')
        db.execute('INSERT INTO receipts VALUES(7)')
        db.commit()
        content = sqlite_checkpoint(path)
    restored = tmp_path / 'restored.sqlite3'
    restored.write_bytes(content)
    with closing(sqlite3.connect(restored)) as db:
        assert db.execute('SELECT n FROM receipts').fetchone() == (7,)


class Storage:
    def __init__(self, content):
        self.content = content
        self.stream = None

    def get_object(self, **kwargs):
        assert kwargs['Bucket'] == 'research-artifacts'
        assert kwargs['Key'].startswith('immutable/')
        self.stream = io.BytesIO(self.content)
        return {'ContentLength': len(self.content), 'Body': self.stream}


def state(storage):
    result = CloudState.__new__(CloudState)
    result.storage = storage
    return result


def test_private_reads_validate_digest_and_close_stream():
    content = b'verified checkpoint'
    storage = Storage(content)
    assert state(storage).get(hashlib.sha256(content).hexdigest()) == content
    assert storage.stream.closed


def test_private_corruption_is_rejected():
    storage = Storage(b'corrupted')
    with pytest.raises(ValueError, match='checksum'):
        state(storage).get(hashlib.sha256(b'expected').hexdigest())
    assert storage.stream.closed


@pytest.mark.parametrize('digest', ['', '../other', 'f'*63, 'X'*64])
def test_private_reads_reject_paths_and_invalid_digests(digest):
    with pytest.raises(ValueError, match='digest'):
        state(Storage(b'')).get(digest)
