"""Check standalone build completeness without printing artifacts or credentials."""
from __future__ import annotations

import json
import os
import stat
import tomllib
from pathlib import Path


def inspect_output(root: Path) -> dict:
    output = root / '.vercel/output'
    if not output.is_dir() or output.is_symlink():
        raise ValueError('prebuilt output is missing or redirected')
    boundary = output.resolve(strict=True)
    count = links = 0
    for directory, dirs, files in os.walk(output, followlinks=False):
        for name in dirs + files:
            count += 1
            if count > 50000:
                raise ValueError('prebuilt output exceeds inspection bound')
            path = Path(directory) / name
            if (name in {'.env', '.evn'} or name.startswith(('.env.', '.evn.'))
                    or '.sqlite3' in name):
                raise ValueError('prebuilt output contains a forbidden private file')
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                links += 1
                try:
                    target = path.resolve(strict=True)
                except (OSError, RuntimeError):
                    raise ValueError('prebuilt output has a broken link') from None
                if not target.is_relative_to(boundary):
                    raise ValueError('prebuilt output has a link outside its boundary')
            elif not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ValueError('prebuilt output contains a special filesystem entry')
    config = json.loads((output / 'config.json').read_text(encoding='utf-8'))
    if config.get('version') != 3:
        raise ValueError('prebuilt output is not Build Output API version 3')
    functions = list((output / 'functions').rglob('.vc-config.json'))
    if not functions:
        raise ValueError('prebuilt output has no configured function')
    app_manifests = 0
    python_functions = 0
    for file in functions:
        function = json.loads(file.read_text(encoding='utf-8'))
        if not str(function.get('runtime', '')).startswith('python'):
            continue
        python_functions += 1
        handler = file.parent / function.get('handler', '')
        if (not function.get('handler') or not handler.is_file()
                or not handler.resolve().is_relative_to(file.parent.resolve())):
            raise ValueError('prebuilt Python function handler is missing or redirected')
        found_manifest = False
        for manifest_path in file.parent.rglob('pyproject.toml'):
            manifest = tomllib.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest.get('project', {}).get('name') == 'marketpulse-dashboard':
                found_manifest = True
                app_manifests += 1
                required_files = [
                    'index.py', 'static/index.html', 'static/app.js', 'static/app.css',
                ]
                for required in required_files:
                    if not (manifest_path.parent / required).is_file():
                        raise ValueError('prebuilt dashboard is missing an application file')
        if not found_manifest:
            raise ValueError('prebuilt Python function lacks the dashboard manifest')
    if not python_functions:
        raise ValueError('prebuilt output has no Python dashboard function')
    return {'status': 'PASS', 'check': 'standalone_prebuilt_package',
            'entries': count, 'internal_links': links, 'python_functions': python_functions,
            'dashboard_manifests': app_manifests, 'uploads_performed': False}


def main():
    try:
        report = inspect_output(Path.cwd())
    except Exception as error:
        # OS/TOML/JSON errors can embed absolute paths or private content.
        print(json.dumps({'status': 'FAIL', 'check': 'standalone_prebuilt_package',
                          'error_type': type(error).__name__,
                          'detail': 'Package verification failed; private details suppressed.'}))
        return 1
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
