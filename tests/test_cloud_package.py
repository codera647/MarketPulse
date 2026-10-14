from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest

from marketpulse.cloud_package import inspect_output, main


@pytest.fixture
def packaged(tmp_path):
    output = tmp_path / '.vercel/output'
    function = output / 'functions/index.func'
    function.mkdir(parents=True)
    (output / 'config.json').write_text('{"version":3}')
    (function / '.vc-config.json').write_text(
        '{"runtime":"python3.13","handler":"index.py"}')
    (function / 'index.py').write_text('app = None')
    (function / 'pyproject.toml').write_text('[project]\nname = "marketpulse-dashboard"\n')
    (function / 'static').mkdir()
    for name in ['index.html', 'app.js', 'app.css']:
        (function / 'static' / name).write_text('test fixture')
    return tmp_path, output, function


def test_complete_standalone_package_passes_without_upload(packaged):
    root, _, _ = packaged
    report = inspect_output(root)
    assert report['status'] == 'PASS'
    assert report['python_functions'] == report['dashboard_manifests'] == 1
    assert report['uploads_performed'] is False


@pytest.mark.parametrize('missing', ['index.py', 'pyproject.toml', '.vc-config.json'])
def test_missing_function_or_manifest_blocks(packaged, missing):
    root, _, function = packaged
    (function / missing).unlink()
    with pytest.raises(ValueError):
        inspect_output(root)


@pytest.mark.parametrize('missing', ['index.html', 'app.js', 'app.css'])
def test_missing_dashboard_asset_is_refused(packaged, missing):
    root, _, function = packaged
    (function / 'static' / missing).unlink()
    with pytest.raises(ValueError, match='application file'):
        inspect_output(root)


@pytest.mark.parametrize('name', ['.env', '.env.production.local', '.evn', 'authority.sqlite3'])
def test_private_files_are_refused_without_printing_content(packaged, name, monkeypatch, capsys):
    root, _, function = packaged
    (function / name).write_text('private-test-password')
    monkeypatch.chdir(root)
    assert main() == 1
    output = capsys.readouterr().out
    assert 'private-test-password' not in output and str(root) not in output
    assert json.loads(output)['status'] == 'FAIL'


def link_or_skip(link, target):
    try:
        link.symlink_to(target)
    except OSError:
        if os.name != 'nt':
            raise
        pytest.skip('Windows symlink privilege unavailable; Linux CI runs this case')


def test_broken_symlink_is_detected(packaged):
    root, _, function = packaged
    link_or_skip(function / 'missing.txt', 'absent.txt')
    with pytest.raises(ValueError, match='broken link'):
        inspect_output(root)


def test_reference_to_existing_source_outside_package_is_refused(packaged):
    root, _, function = packaged
    source = root / 'source.txt'
    source.write_text('not inside upload')
    link_or_skip(function / 'external.txt', source)
    with pytest.raises(ValueError, match='outside'):
        inspect_output(root)


def test_internal_file_link_is_supported(packaged):
    root, _, function = packaged
    link_or_skip(function / 'internal.py', 'index.py')
    assert inspect_output(root)['internal_links'] == 1


@pytest.mark.parametrize('handler', ['absent.py', '../../../../outside.py'])
def test_invalid_handler_is_refused(packaged, handler):
    root, _, function = packaged
    (root / 'outside.py').write_text('not inside upload')
    (function / '.vc-config.json').write_text(
        json.dumps({'runtime': 'python3.13', 'handler': handler}))
    with pytest.raises(ValueError, match='handler'):
        inspect_output(root)


def test_non_v3_output_is_refused(packaged):
    root, output, _ = packaged
    (output / 'config.json').write_text('{"version":2}')
    with pytest.raises(ValueError, match='version 3'):
        inspect_output(root)


def test_dashboard_manifest_keeps_exact_existing_runtime_pins_and_entrypoint():
    root = Path(__file__).parents[1]
    manifest = tomllib.loads((root / 'web/pyproject.toml').read_text())
    requirements = {line for line in (root / 'web/requirements.txt').read_text().splitlines()
                    if line and not line.startswith('#')}
    assert set(manifest['project']['dependencies']) == requirements
    assert manifest['project']['requires-python'] == '>=3.13,<3.14'
    assert manifest['tool']['uv']['package'] is False
    assert manifest['tool']['vercel']['entrypoint'] == 'index:app'


def test_manifest_module_object_entrypoint_resolves_to_healthy_fastapi_application():
    import importlib

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    root = Path(__file__).parents[1]
    manifest = tomllib.loads((root / 'web/pyproject.toml').read_text())
    module_name, object_name = manifest['tool']['vercel']['entrypoint'].split(':')
    assert (root / 'web' / (module_name.replace('.', '/') + '.py')).is_file()
    module = importlib.import_module('web.' + module_name)
    application = getattr(module, object_name)
    assert isinstance(application, FastAPI)
    response = TestClient(application).get('/api/health')
    assert response.status_code == 200 and response.json()['status'] == 'OK'
    assert response.headers['cache-control'] == 'private, no-store'


def test_ignore_rule_allows_web_manifest_but_excludes_research_and_secrets():
    root = Path(__file__).parents[1]
    result = subprocess.run(
        ['git', '-c', f'core.excludesFile={root / ".vercelignore"}',
         'check-ignore', '--no-index', 'pyproject.toml', 'web/pyproject.toml',
         '.env.cloud.local', 'web/.env.production.local', 'data/authority.sqlite3'],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    ignored = set(result.stdout.splitlines())
    assert 'web/pyproject.toml' not in ignored
    assert {'pyproject.toml', '.env.cloud.local', 'web/.env.production.local',
            'data/authority.sqlite3'} <= ignored


def test_standalone_and_upload_gate_are_in_release_order():
    root = Path(__file__).parents[1]
    workflow = (root / '.github/workflows/deploy-dashboard.yml').read_text()
    assert workflow.index('run: vercel build --prod --standalone') < workflow.index(
        'run: python -m marketpulse.cloud_package') < workflow.index(
        'run: python -m marketpulse.cloud_deploy\n')
    assert 'tests/test_cloud_package.py' in workflow


def test_staging_cannot_upload_a_missing_package(tmp_path, monkeypatch):
    from marketpulse import cloud_deploy
    config = {'project_id': 'approved', 'org_id': 'approved'}
    (tmp_path / 'deploy').mkdir()
    (tmp_path / 'deploy/cloud.json').write_text(json.dumps({'vercel': config}))
    (tmp_path / '.vercel').mkdir()
    (tmp_path / '.vercel/project.json').write_text(
        json.dumps({'projectId': 'approved', 'orgId': 'approved'}))
    for key, value in {'GITHUB_REPOSITORY': 'codera647/MarketPulse',
                       'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': 'a'*40,
                       'VERCEL_PROJECT_ID': 'approved', 'VERCEL_ORG_ID': 'approved'}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(cloud_deploy, 'check_project', lambda _: None)
    monkeypatch.setattr(cloud_deploy, 'run', lambda _: pytest.fail('unexpected upload'))
    with pytest.raises(ValueError, match='missing'):
        cloud_deploy.stage(tmp_path)
