"""Stage only the reviewed prebuilt production artifact on the verified private project."""
from __future__ import annotations

import argparse
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


def context(root: Path):
    config = json.loads((root / 'deploy/cloud.json').read_text())['vercel']
    if os.environ.get('GITHUB_REPOSITORY') != 'codera647/MarketPulse' or (
        os.environ.get('GITHUB_REF') != 'refs/heads/main'
    ):
        raise ValueError('this stage command accepts the reviewed main Actions job only')
    sha = os.environ['GITHUB_SHA']
    if len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('invalid reviewed commit')
    if (os.environ.get('VERCEL_PROJECT_ID'), os.environ.get('VERCEL_ORG_ID')) != (
        config['project_id'], config['org_id']
    ):
        raise ValueError('deployment environment target differs from reviewed project')
    return config, sha


def check_link(root: Path, config):
    link = json.loads((root / '.vercel/project.json').read_text())
    if (link['projectId'], link['orgId']) != (config['project_id'], config['org_id']):
        raise ValueError('deployment target differs from linked project')


def check_project(config):
    # Global --scope resolves /v2/user first, which project-scoped tokens cannot
    # access. Address this project directly with its reviewed team ID instead.
    project = json.loads(run(['api',
        f"/v9/projects/{config['project_id']}?teamId={config['org_id']}"]))
    protection = project.get('ssoProtection') or {}
    if (project.get('id'), project.get('accountId'), project.get('rootDirectory'),
        protection.get('deploymentType')) != (
        config['project_id'], config['org_id'], 'web', 'all'
    ):
        raise ValueError('private project/root/protection verification failed')


def prepare(root: Path):
    config, _ = context(root)
    if not os.environ.get('VERCEL_TOKEN', '').strip():
        raise ValueError('VERCEL_TOKEN is unavailable in the production environment')
    link = root / '.vercel/project.json'
    if link.exists():
        check_link(root, config)
    check_project(config)
    # A fresh Actions checkout has no ignored CLI link. Seed public IDs only
    # after exact remote target/protection verification; never auto-link.
    link.parent.mkdir(exist_ok=True)
    if not link.exists():
        link.write_text(json.dumps({'projectId': config['project_id'],
                                    'orgId': config['org_id']}), encoding='utf-8')


def stage(root: Path):
    config = json.loads((root / 'deploy/cloud.json').read_text())['vercel']
    check_link(root, config)
    config, sha = context(root)
    check_project(config)
    url = deployment_url(run(['deploy', '--prebuilt', '--prod', '--skip-domain', '--yes',
                              '--meta', f'githubCommitSha={sha}'], timeout=900))
    deployment = json.loads(run(['api', '/v13/deployments/' + urlsplit(url).hostname
                                + f"?teamId={config['org_id']}"]))
    if (deployment.get('projectId'), deployment.get('target'),
        deployment.get('readyState'), deployment.get('meta', {}).get('githubCommitSha')) != (
        config['project_id'], 'production', 'READY', sha
    ):
        raise ValueError('staged production identity/commit differs')
    return url


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            prepare(Path.cwd())
            print(json.dumps({'status': 'VERIFIED_PRIVATE_PROJECT', 'writes': 'public_link_ids'}))
            return 0
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
