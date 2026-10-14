from __future__ import annotations

import json

import pytest

from marketpulse.cloud_deploy import deployment_url, stage

URL = 'https://marketpulse-reviewed-codera647s-projects.vercel.app'


def test_supported_cli_stdout_shapes_have_same_verified_origin():
    assert deployment_url(URL + '\n') == URL
    assert deployment_url(json.dumps({'deployment': {'url': URL}})) == URL


@pytest.mark.parametrize('output', ['https://other.example', URL + '/api', URL + '?token=test',
                                    URL + '#fragment', 'https://user:pass@' + URL[8:],
                                    'unrelated output', URL + ':444',
                                    'https://marketpulse-test-other.vercel.app'])
def test_arbitrary_origins_and_secret_url_components_are_rejected(output):
    with pytest.raises(ValueError):
        deployment_url(output)


def test_wrong_link_refused_before_authentication(tmp_path):
    (tmp_path / '.vercel').mkdir()
    (tmp_path / 'deploy').mkdir()
    (tmp_path / '.vercel/project.json').write_text(
        json.dumps({'projectId': 'other', 'orgId': 'other'}))
    (tmp_path / 'deploy/cloud.json').write_text(json.dumps({'vercel': {
        'project_id': 'approved', 'org_id': 'approved'}}))
    with pytest.raises(ValueError, match='target differs'):
        stage(tmp_path)


@pytest.mark.parametrize('protection', [None, {'deploymentType': 'preview'}])
def test_public_production_refused_before_deployment(tmp_path, monkeypatch, protection):
    from marketpulse import cloud_deploy
    config = {'project_id': 'approved', 'org_id': 'approved', 'team_slug': 'approved'}
    (tmp_path / '.vercel').mkdir()
    (tmp_path / 'deploy').mkdir()
    (tmp_path / '.vercel/project.json').write_text(
        json.dumps({'projectId': 'approved', 'orgId': 'approved'}))
    (tmp_path / 'deploy/cloud.json').write_text(json.dumps({'vercel': config}))
    monkeypatch.setenv('GITHUB_REPOSITORY', 'codera647/MarketPulse')
    monkeypatch.setenv('GITHUB_REF', 'refs/heads/main')
    monkeypatch.setenv('GITHUB_SHA', 'a'*40)
    calls = []

    def run(args):
        calls.append(args)
        return json.dumps({'id': 'approved', 'accountId': 'approved', 'rootDirectory': 'web',
                           'ssoProtection': protection})
    monkeypatch.setattr(cloud_deploy, 'run', run)
    with pytest.raises(ValueError, match='protection'):
        stage(tmp_path)
    assert len(calls) == 1 and calls[0][0] == 'api'
