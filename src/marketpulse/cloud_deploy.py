"""Stage only the reviewed prebuilt production artifact on the verified private project."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from marketpulse.vercel_cli import command


def deployment_url(output: str) -> str:
    try:
        document = json.loads(output)
        value = document['deployment']['url']
    except (ValueError, KeyError, TypeError):
        value = output.strip()
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query
            or parsed.fragment or parsed.path not in {'', '/'} or parsed.port not in {None, 443}
            or not parsed.hostname
            or not parsed.hostname.startswith('marketpulse-')
            or not parsed.hostname.endswith('-codera647s-projects.vercel.app')):
        raise ValueError('deployment URL is not the approved project origin')
    return value.rstrip('/')


def run(args, timeout=180):
    result = subprocess.run(command() + args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('reviewed deployment command failed; private output suppressed')
    return result.stdout


def stage(root: Path):
    config = json.loads((root / 'deploy/cloud.json').read_text())['vercel']
    link = json.loads((root / '.vercel/project.json').read_text())
    if (link['projectId'], link['orgId']) != (config['project_id'], config['org_id']):
        raise ValueError('deployment target differs from linked project')
    if os.environ.get('GITHUB_REPOSITORY') != 'codera647/MarketPulse' or (
        os.environ.get('GITHUB_REF') != 'refs/heads/main'
    ):
        raise ValueError('this stage command accepts the reviewed main Actions job only')
    sha = os.environ['GITHUB_SHA']
    if len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('invalid reviewed commit')
    scope = ['--scope', config['team_slug']]
    project = json.loads(run(['api', f"/v9/projects/{config['project_id']}"] + scope))
    protection = project.get('ssoProtection') or {}
    if (project.get('id'), project.get('accountId'), project.get('rootDirectory'),
        protection.get('deploymentType')) != (
        config['project_id'], config['org_id'], 'web', 'all'
    ):
        raise ValueError('private project/root/protection verification failed')
    url = deployment_url(run(['deploy', '--prebuilt', '--prod', '--skip-domain', '--yes',
                              '--meta', f'githubCommitSha={sha}'] + scope, timeout=900))
    deployment = json.loads(run(['api', '/v13/deployments/' + urlsplit(url).hostname] + scope))
    if (deployment.get('projectId'), deployment.get('target'),
        deployment.get('readyState'), deployment.get('meta', {}).get('githubCommitSha')) != (
        config['project_id'], 'production', 'READY', sha
    ):
        raise ValueError('staged production identity/commit differs')
    return url


def main():
    try:
        url = stage(Path.cwd())
        # CI metadata only, never credentials or private response bodies.
        with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as output:
            output.write(f'url={url}\n')
    except Exception as error:
        print(json.dumps({'status': 'FAIL', 'error_type': type(error).__name__}))
        return 1
    print(json.dumps({'status': 'READY', 'url': url, 'promotion_requested': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
