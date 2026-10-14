from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from marketpulse.cloud_deploy import deployment_url, prepare, stage

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
    monkeypatch.setenv('VERCEL_PROJECT_ID', 'approved')
    monkeypatch.setenv('VERCEL_ORG_ID', 'approved')
    calls = []

    def run(args):
        calls.append(args)
        return json.dumps({'id': 'approved', 'accountId': 'approved', 'rootDirectory': 'web',
                           'ssoProtection': protection})
    monkeypatch.setattr(cloud_deploy, 'run', run)
    with pytest.raises(ValueError, match='protection'):
        stage(tmp_path)
    assert len(calls) == 1 and calls[0][0] == 'api'


@pytest.fixture
def reviewed(tmp_path, monkeypatch):
    config = {'project_id': 'approved', 'org_id': 'approved', 'team_slug': 'approved'}
    (tmp_path / 'deploy').mkdir()
    (tmp_path / 'deploy/cloud.json').write_text(json.dumps({'vercel': config}))
    for key, value in {'GITHUB_REPOSITORY': 'codera647/MarketPulse',
                       'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': 'a'*40,
                       'VERCEL_PROJECT_ID': 'approved', 'VERCEL_ORG_ID': 'approved',
                       'VERCEL_TOKEN': 'private-test-token'}.items():
        monkeypatch.setenv(key, value)
    return tmp_path


def private_project():
    return json.dumps({'id': 'approved', 'accountId': 'approved', 'rootDirectory': 'web',
                       'ssoProtection': {'deploymentType': 'all'}})


def test_prepare_verifies_project_without_user_scope_and_writes_only_ids(reviewed, monkeypatch):
    from marketpulse import cloud_deploy
    calls = []

    def run(args):
        calls.append(args)
        return private_project()

    monkeypatch.setattr(cloud_deploy, 'run', run)
    prepare(reviewed)
    assert calls == [['api', '/v9/projects/approved?teamId=approved']]
    link = (reviewed / '.vercel/project.json').read_text()
    assert json.loads(link) == {'projectId': 'approved', 'orgId': 'approved'}
    assert 'private-test-token' not in link
    prepare(reviewed)
    assert (reviewed / '.vercel/project.json').read_text() == link


@pytest.mark.parametrize('key,value', [
    ('VERCEL_PROJECT_ID', 'other'), ('VERCEL_ORG_ID', 'other'), ('VERCEL_TOKEN', ''),
    ('GITHUB_REPOSITORY', 'other/repo'), ('GITHUB_REF', 'refs/heads/other'),
    ('GITHUB_SHA', 'not-a-commit'),
])
def test_prepare_refuses_wrong_context_before_cli_or_link(reviewed, monkeypatch, key, value):
    from marketpulse import cloud_deploy
    monkeypatch.setenv(key, value)
    monkeypatch.setattr(cloud_deploy, 'run', lambda _: pytest.fail('unexpected CLI call'))
    with pytest.raises(ValueError):
        prepare(reviewed)
    assert not (reviewed / '.vercel').exists()


@pytest.mark.parametrize('field,value', [
    ('id', 'other'), ('accountId', 'other'), ('rootDirectory', None),
    ('ssoProtection', {'deploymentType': 'preview'}),
])
def test_prepare_does_not_create_link_if_remote_target_or_privacy_differs(
    reviewed, monkeypatch, field, value
):
    from marketpulse import cloud_deploy
    project = json.loads(private_project())
    project[field] = value
    monkeypatch.setattr(cloud_deploy, 'run', lambda _: json.dumps(project))
    with pytest.raises(ValueError, match='protection'):
        prepare(reviewed)
    assert not (reviewed / '.vercel').exists()


def test_prepare_preserves_wrong_existing_link_without_authentication(reviewed, monkeypatch):
    from marketpulse import cloud_deploy
    (reviewed / '.vercel').mkdir()
    link = reviewed / '.vercel/project.json'
    link.write_text(json.dumps({'projectId': 'other', 'orgId': 'other'}))
    original = link.read_bytes()
    monkeypatch.setattr(cloud_deploy, 'run', lambda _: pytest.fail('unexpected CLI call'))
    with pytest.raises(ValueError, match='target differs'):
        prepare(reviewed)
    assert link.read_bytes() == original


def test_stage_preserves_guards_without_global_scope(reviewed, monkeypatch):
    from marketpulse import cloud_deploy
    (reviewed / '.vercel').mkdir()
    (reviewed / '.vercel/project.json').write_text(
        json.dumps({'projectId': 'approved', 'orgId': 'approved'}))
    calls = []

    def run(args, timeout=180):
        calls.append(args)
        assert '--scope' not in args and '--token' not in args
        if args[0] == 'deploy':
            assert timeout == 900
            return URL
        if '/v9/projects/' in args[1]:
            return private_project()
        assert args[1].endswith('?teamId=approved')
        return json.dumps({'projectId': 'approved', 'target': 'production',
                           'readyState': 'READY', 'meta': {'githubCommitSha': 'a'*40}})

    monkeypatch.setattr(cloud_deploy, 'run', run)
    monkeypatch.setattr(cloud_deploy, 'inspect_output', lambda root: {'status': 'PASS'})
    assert stage(reviewed) == URL
    assert len(calls) == 3


def test_ci_commands_never_request_global_user_scope():
    workflow = (Path(__file__).parents[1] / '.github/workflows/deploy-dashboard.yml').read_text()
    commands = [line.strip() for line in workflow.splitlines() if 'run:' in line]
    assert not any('--scope' in line or '--token' in line for line in commands)
    assert 'run: python -m marketpulse.cloud_deploy --prepare' in commands
    assert workflow.index('--prepare') < workflow.index('run: vercel pull')
    assert 'environment: production' in workflow


def test_python_builder_tool_is_pinned_hash_checked_and_verified_before_private_steps():
    root = Path(__file__).parents[1]
    workflow = (root / '.github/workflows/deploy-dashboard.yml').read_text()
    lock = (root / 'deploy/requirements-build.txt').read_text()
    assert 'uv==0.10.11' in lock
    assert lock.count('--hash=sha256:') == 2
    assert 'deploy/requirements-build.txt' in workflow.split('permissions:')[0]
    installation = '--only-binary=:all: --no-deps --require-hashes -r deploy/requirements-build.txt'
    assert installation in workflow
    assert workflow.index('uv --version') < workflow.index('run: vercel build --prod --standalone')
    assert workflow.index('uv --version') < workflow.index('run: vercel pull')
    tool_step = workflow.split('Install and verify pinned Python build tool')[1].split(
        '- name: Verify private target')[0]
    assert "version[:2] == ['uv', '0.10.11']" in tool_step
    assert "shutil.which('uv')" in tool_step
    assert 'secrets.' not in tool_step and 'VERCEL_TOKEN' not in tool_step


def test_hosted_cli_verification_does_not_request_user_scope(monkeypatch):
    import importlib.util
    path = Path(__file__).parents[1] / 'scripts/verify_hosted_dashboard.py'
    spec = importlib.util.spec_from_file_location('hosted_verification', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'command', lambda: ['vercel'])

    def run(args, **kwargs):
        assert '--scope' not in args and '--token' not in args
        assert args[:3] == ['vercel', 'curl', URL + '/api/health']
        return SimpleNamespace(returncode=0, stdout='{"status":"OK"}__HTTP__:200', stderr='')

    monkeypatch.setattr(module.subprocess, 'run', run)
    assert json.loads(module.curl(URL, '/api/health')) == {'status': 'OK'}
