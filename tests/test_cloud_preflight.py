from __future__ import annotations

import json

import pytest

from marketpulse import cloud_preflight


def test_ci_checks_only_named_hosts_and_never_returns_credentials(monkeypatch):
    monkeypatch.setattr(cloud_preflight, 'inspect_connections',
                        lambda values, worker_only: {'checks': {'db': 'PASS'}})
    values = dict.fromkeys(('VERCEL_TOKEN', 'APCA_API_KEY_ID', 'APCA_API_SECRET_KEY'),
                          'test-sensitive-value')
    visited = []

    def request(url, **kwargs):
        visited.append(url)
        assert kwargs['allow_redirects'] is False
        assert kwargs['timeout'] == (10, 20)
        from types import SimpleNamespace
        data = ({'news': []} if 'news' in url else
                {'bars': {'AAPL': [{'c': 1}]}} if 'alpaca' in url else
                {'id': 'prj_Gto0aVFyeStSCSyOezczGk8myTWx',
                 'accountId': 'team_75Ikyytg6OGvW0iRj2fKq0Gg', 'name': 'marketpulse'})
        return SimpleNamespace(status_code=200, json=lambda: data)

    report = cloud_preflight.inspect(values, request=request)
    assert len(visited) == 3
    assert report['status'] == 'PASS'
    assert 'test-sensitive-value' not in json.dumps(report)
    assert report['writes_performed'] is False


def test_provider_failure_fails_closed_without_logging_body(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise ValueError('test-sensitive-value')
    monkeypatch.setattr(cloud_preflight, 'inspect', fail)
    assert cloud_preflight.main() == 1
    assert 'test-sensitive-value' not in capsys.readouterr().out


def test_redirect_is_not_accepted(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(cloud_preflight, 'inspect_connections',
                        lambda values, worker_only: {'checks': {}})
    values = dict.fromkeys(('APCA_API_KEY_ID', 'APCA_API_SECRET_KEY'), 'test-only')
    with pytest.raises(ValueError, match='Alpaca'):
        cloud_preflight.inspect(values, request=lambda *a, **k: SimpleNamespace(status_code=302))


def test_only_reviewed_fixed_failure_reason_is_reported(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise ValueError('Vercel project authentication failed')
    monkeypatch.setattr(cloud_preflight, 'inspect', fail)
    assert cloud_preflight.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report['safe_reason'] == 'Vercel project authentication failed'
