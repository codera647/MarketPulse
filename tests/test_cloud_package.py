from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest

from marketpulse.cloud_package import failure_code, inspect_output, main


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


def test_real_vercel_module_symbol_handler_resolves_to_bundled_python_file(packaged):
    root, _, function = packaged
    (function / 'vc__handler__python.py').write_text('def vc_handler(): pass')
    (function / '.vc-config.json').write_text(
        '{"runtime":"python3.13","handler":"vc__handler__python.vc_handler"}')
    assert inspect_output(root)['status'] == 'PASS'


def test_module_symbol_handler_with_missing_module_is_still_blocked(packaged):
    root, _, function = packaged
    (function / '.vc-config.json').write_text(
        '{"runtime":"python3.13","handler":"vc__handler__python.vc_handler"}')
    with pytest.raises(ValueError, match='handler'):
        inspect_output(root)


def test_safe_failure_code_reveals_condition_not_exception_content():
    assert failure_code(ValueError('prebuilt output has a broken link')) == 'BROKEN_LINK'
    assert failure_code(ValueError('private-test-password')) == 'UNEXPECTED_READ_OR_PARSE_ERROR'
    code = failure_code(FileNotFoundError('/private/secret/path'))
    assert code == 'UNEXPECTED_READ_OR_PARSE_ERROR'


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
    assert json.loads(output)['failure_code'] == 'PRIVATE_FILE_PRESENT'


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
        'run: python -m marketpulse.cloud_package\n') < workflow.index(
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


def test_smoke_context_copies_only_allowlisted_public_source(tmp_path):
    import shutil

    from marketpulse.cloud_package_smoke import PUBLIC_WEB_FILES, seed_public_context

    root = Path(__file__).parents[1]
    source, target = tmp_path / 'source', tmp_path / 'target'
    target.mkdir()
    for name in PUBLIC_WEB_FILES:
        destination = source / 'web' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / 'web' / name, destination)
    (source / 'deploy').mkdir()
    for name in ['cloud.json', 'vercel-project-settings.json']:
        shutil.copyfile(root / 'deploy' / name, source / 'deploy' / name)
    (source / 'web/.env.production.local').write_text('private-test-password')
    (source / '.env').write_text('private-test-password')
    seed_public_context(source, target)
    assert not (target / 'web/.env.production.local').exists()
    assert not (target / '.env').exists()
    assert (target / '.vercel/.env.production.local').read_text() == ''
    copied = {file.relative_to(target / 'web').as_posix()
              for file in (target / 'web').rglob('*') if file.is_file()}
    assert copied == set(PUBLIC_WEB_FILES)


def test_real_build_smoke_does_not_inherit_cloud_credentials(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from marketpulse import cloud_package_smoke

    monkeypatch.setattr(cloud_package_smoke.sys, 'platform', 'linux')
    monkeypatch.setattr(cloud_package_smoke, 'command', lambda: ['vercel'])
    monkeypatch.setattr(cloud_package_smoke, 'seed_public_context',
                        lambda source, target: {'project_id': 'approved', 'org_id': 'approved'})
    monkeypatch.setattr(cloud_package_smoke, 'inspect_output', lambda _: {'status': 'PASS'})
    for key in ['VERCEL_TOKEN', 'MARKETPULSE_DATABASE_URL', 'AWS_SECRET_ACCESS_KEY',
                'APCA_API_SECRET_KEY', 'GITHUB_TOKEN']:
        monkeypatch.setenv(key, 'private-test-password')

    def run(args, **kwargs):
        assert args == ['vercel', 'build', '--prod', '--standalone']
        assert 'private-test-password' not in json.dumps(kwargs['env'])
        assert kwargs['timeout'] == 300
        return SimpleNamespace(returncode=0, stdout='private-test-password', stderr='')

    monkeypatch.setattr(cloud_package_smoke.subprocess, 'run', run)
    assert cloud_package_smoke.smoke(tmp_path)['credentials_used'] is False


def test_workflow_gates_production_on_real_credential_free_smoke():
    root = Path(__file__).parents[1]
    workflow = (root / '.github/workflows/deploy-dashboard.yml').read_text()
    verify_job = workflow.split('  verify:')[1].split('  release:')[0]
    assert 'python -m marketpulse.cloud_package_smoke' in verify_job
    assert 'secrets.' not in verify_job
    assert 'needs: verify' in workflow
    assert 'upload-artifact' not in workflow
