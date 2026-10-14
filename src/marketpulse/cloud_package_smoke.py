"""Real Linux standalone build of allowlisted public source, without cloud credentials."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from marketpulse.cloud_package import failure_code, inspect_output
from marketpulse.vercel_cli import command

PUBLIC_WEB_FILES = (
    'index.py', 'pyproject.toml', 'requirements.txt', '.python-version', 'vercel.json',
    'static/index.html', 'static/app.css', 'static/app.js',
)


def seed_public_context(source: Path, target: Path):
    config = json.loads((source / 'deploy/cloud.json').read_text())['vercel']
    settings = json.loads((source / 'deploy/vercel-project-settings.json').read_text())
    settings = {key: settings[key] for key in (
        'rootDirectory', 'framework', 'buildCommand', 'installCommand', 'outputDirectory')}
    settings['nodeVersion'] = '24.x'
    for name in PUBLIC_WEB_FILES:
        origin = source / 'web' / name
        if origin.is_symlink() or not origin.resolve().is_relative_to((source / 'web').resolve()):
            raise ValueError('public smoke source is redirected')
        destination = target / 'web' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, destination)
    cache = target / '.vercel'
    cache.mkdir()
    (cache / 'project.json').write_text(json.dumps({
        'projectId': config['project_id'], 'orgId': config['org_id'],
        'projectName': config['project_name'], 'settings': settings,
    }))
    # Offline public fixture cache only. Never pull production envs in this test.
    (cache / '.env.production.local').write_text('')
    return config


def smoke(source: Path) -> dict:
    if sys.platform != 'linux':
        raise ValueError('standalone smoke requires Linux for runner parity')
    with tempfile.TemporaryDirectory(prefix='marketpulse-public-build-smoke-') as directory:
        target = Path(directory)
        config = seed_public_context(source, target)
        environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL')
                       if key in os.environ}
        environment.update({
            'CI': '1', 'VERCEL_TELEMETRY_DISABLED': '1',
            'VERCEL_ORG_ID': config['org_id'], 'VERCEL_PROJECT_ID': config['project_id'],
        })
        result = subprocess.run(command() + ['build', '--prod', '--standalone'], cwd=target,
                                env=environment, capture_output=True, text=True, timeout=300)
        if result.returncode:
            # Even this public-only build never dumps raw logs or authentication state.
            raise ValueError('credential-free standalone build failed')
        report = inspect_output(target)
        return {**report, 'check': 'credential_free_linux_standalone_build',
                'public_source_files': len(PUBLIC_WEB_FILES), 'credentials_used': False,
                'deployments_created': False}


def main():
    try:
        report = smoke(Path.cwd())
    except Exception as error:
        print(json.dumps({'status': 'FAIL', 'check': 'credential_free_linux_standalone_build',
                          'error_type': type(error).__name__, 'failure_code': failure_code(error)}))
        return 1
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
