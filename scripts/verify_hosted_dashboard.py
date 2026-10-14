"""Verify protected HTTP/API/data boundaries without logging private responses."""
from __future__ import annotations

import argparse
import json
import subprocess
from urllib.parse import urlsplit

import requests

from marketpulse.vercel_cli import command


def curl(url, path):
    result = subprocess.run(
        command() + ['curl', url + path,
         '--', '--max-time', '40', '--silent',
         '--show-error', '--write-out', '__HTTP__:%{http_code}'],
        capture_output=True, text=True, timeout=90,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        print(json.dumps({'check': 'authenticated_cli_request', 'exit_code': result.returncode,
                          'trusted_source_mismatch':
                          'TRUSTED_SOURCES_ENVIRONMENT_MISMATCH' in output}))
        raise ValueError('authenticated CLI request failed')
    body, marker, code = result.stdout.rpartition('__HTTP__:')
    if not marker or code.strip() != '200':
        print(json.dumps({'check': 'authenticated_cli_response',
                          'http_status': code.strip() if code.strip().isdigit() else None,
                          'trusted_source_mismatch':
                          'TRUSTED_SOURCES_ENVIRONMENT_MISMATCH' in output}))
        raise ValueError('authenticated response is not HTTP 200')
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    args = parser.parse_args()
    target = urlsplit(args.url)
    if (target.scheme != 'https' or target.username or target.password or target.query
            or target.fragment or target.path not in {'', '/'} or not target.hostname
            or target.port not in {None, 443} or not target.hostname.startswith('marketpulse-')
            or not target.hostname.endswith('-codera647s-projects.vercel.app')):
        print('FAIL: unexpected deployment origin')
        return 1
    try:
        anonymous = requests.get(args.url + '/api/dashboard', timeout=(10, 20),
                                 allow_redirects=False)
        if anonymous.status_code not in {302, 303, 307, 308, 401, 403}:
            raise ValueError('unauthenticated result request was not denied')
        print(json.dumps({'check': 'unauthenticated_results_denied',
                          'http_status': anonymous.status_code}))
        health = json.loads(curl(args.url, '/api/health'))
        if health.get('status') != 'OK':
            raise ValueError('health response mismatch')
        for period, count in [('2026 retrospective', 1104), ('2025 development', 744)]:
            path = '/api/dashboard?period=' + period.replace(' ', '%20')
            payload = json.loads(curl(args.url, path))
            research = payload['research']
            if (len(research['rows']) != count or research['period'] != period
                    or research['availability_tier'] != 'HISTORICAL_APPROXIMATE'
                    or research['live'] is not False or payload['forward'] is not None
                    or payload['paper_action_authorized'] is not False):
                raise ValueError('hosted projection identity differs')
            print(json.dumps({'check': 'authenticated_database_projection',
                              'period': period, 'rows': count, 'live': False}))
        html = curl(args.url, '/')
        if 'Read the evidence.' not in html or '/assets/app.js' not in html:
            raise ValueError('HTML/asset route mismatch')
    except Exception as error:
        print(json.dumps({'status': 'FAIL', 'error_type': type(error).__name__,
                          'detail': 'Hosted verification held; private details suppressed.'}))
        return 1
    print(json.dumps({'status': 'PASS', 'boundary': 'HTTP/API/database/response',
                      'browser_visual_keyboard_QA': 'NOT_RUN'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
