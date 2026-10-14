"""Check standalone build completeness without printing artifacts or credentials."""
from __future__ import annotations

import json
import os
import re
import stat
import tomllib
from pathlib import Path

FAILURE_CODES = {
    'prebuilt output is missing or redirected': 'OUTPUT_MISSING_OR_REDIRECTED',
    'prebuilt output exceeds inspection bound': 'ENTRY_LIMIT_EXCEEDED',
    'prebuilt output contains a forbidden private file': 'PRIVATE_FILE_PRESENT',
    'prebuilt output has a broken link': 'BROKEN_LINK',
    'prebuilt output has a link outside its boundary': 'EXTERNAL_LINK',
    'prebuilt output contains a special filesystem entry': 'SPECIAL_FILE',
    'prebuilt output is not Build Output API version 3': 'UNSUPPORTED_OUTPUT_VERSION',
    'prebuilt output has no configured function': 'FUNCTION_CONFIG_MISSING',
    'prebuilt Python function handler is missing or redirected': 'PYTHON_HANDLER_INVALID',
    'prebuilt dashboard is missing an application file': 'APPLICATION_FILE_MISSING',
    'prebuilt Python function lacks the dashboard manifest': 'DASHBOARD_MANIFEST_MISSING',
    'prebuilt output has no Python dashboard function': 'PYTHON_FUNCTION_MISSING',
    'credential-free standalone build failed': 'PUBLIC_STANDALONE_BUILD_FAILED',
    'public smoke source is redirected': 'PUBLIC_SOURCE_REDIRECTED',
    'standalone smoke requires Linux for runner parity': 'LINUX_SMOKE_REQUIRED',
}


def failure_code(error: Exception) -> str:
    # Never return arbitrary OS/JSON/TOML messages, paths, filenames or file contents.
    return FAILURE_CODES.get(str(error), 'UNEXPECTED_READ_OR_PARSE_ERROR')


def python_handler_file(function_root: Path, handler: str) -> Path:
    if not isinstance(handler, str) or not handler:
        raise ValueError('prebuilt Python function handler is missing or redirected')
    if handler.endswith('.py'):
        return function_root / handler
    # @vercel/python emits module.symbol, e.g. vc__handler__python.vc_handler;
    # the actual bundled file is vc__handler__python.py, not module.symbol.
    module, separator, symbol = handler.rpartition('.')
    if (not separator or not symbol.isidentifier()
            or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', module)):
        raise ValueError('prebuilt Python function handler is missing or redirected')
    return function_root / (module.replace('.', '/') + '.py')


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
        handler = python_handler_file(file.parent, function.get('handler', ''))
        if (not handler.is_file()
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
                          'failure_code': failure_code(error),
                          'detail': 'Package verification failed; private details suppressed.'}))
        return 1
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
