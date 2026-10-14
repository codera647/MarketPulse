"""Stage only the reviewed prebuilt production artifact on the verified private project."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

from marketpulse.cloud_package import inspect_output
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


def check_project(config, timeout=None):
    # Global --scope resolves /v2/user first, which project-scoped tokens cannot
    # access. Address this project directly with its reviewed team ID instead.
    args = ['api', f"/v9/projects/{config['project_id']}?teamId={config['org_id']}"]
    project = json.loads(run(args) if timeout is None else run(args, timeout=timeout))
    protection = project.get('ssoProtection') or {}
    if (project.get('id'), project.get('accountId'), project.get('rootDirectory'),
        protection.get('deploymentType')) != (
        config['project_id'], config['org_id'], 'web', 'all'
    ):
        raise ValueError('private project/root/protection verification failed')
    return project


def checked_deployment(config, sha, url):
    url = deployment_url(url)
    deployment = json.loads(run(['api', '/v13/deployments/' + urlsplit(url).hostname
                                + f"?teamId={config['org_id']}"]))
    if (deployment.get('projectId'), deployment.get('target'),
        deployment.get('readyState'), deployment.get('meta', {}).get('githubCommitSha')) != (
        config['project_id'], 'production', 'READY', sha
    ):
        raise ValueError('staged production identity/commit differs')
    return deployment


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
    inspect_output(root)
    url = deployment_url(run(['deploy', '--prebuilt', '--prod', '--skip-domain', '--yes',
                              '--meta', f'githubCommitSha={sha}'], timeout=900))
    checked_deployment(config, sha, url)
    return url


def promote(root: Path, url: str, *, wait=time.sleep):
    config, sha = context(root)
    check_link(root, config)
    check_project(config)
    inspect_output(root)
    deployment = checked_deployment(config, sha, url)
    identifier = deployment.get('id', '')
    if not isinstance(identifier, str) or not re.fullmatch(r'dpl_[A-Za-z0-9]+', identifier):
        raise ValueError('verified deployment ID is invalid')
    # The high-level promote command performs another user lookup. Use its same
    # project-scoped endpoint via CLI api; no broader token or rebuild is needed.
    run(['api', f"/v10/projects/{config['project_id']}/promote/{identifier}"
         + f"?teamId={config['org_id']}", '--method', 'POST'])
    # POST acceptance alone is not completion. Read the exact project's alias job.
    # Never repeat an uncertain POST; failure/timeout remains held.
    for attempt in range(15):
        project = check_project(config, timeout=30)
        request = project.get('lastAliasRequest') or {}
        if request.get('toDeploymentId') == identifier and request.get('type') == 'promote':
            if request.get('jobStatus') == 'succeeded':
                return identifier
            if request.get('jobStatus') in {'failed', 'skipped'}:
                raise ValueError('production alias promotion did not succeed')
        if attempt < 14:
            wait(2)
    raise ValueError('production alias promotion completion is unverified')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--promote', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            prepare(Path.cwd())
            print(json.dumps({'status': 'VERIFIED_PRIVATE_PROJECT', 'writes': 'public_link_ids'}))
            return 0
        if args.promote:
            identifier = promote(Path.cwd(), os.environ['DEPLOYMENT_URL'])
            print(json.dumps({'status': 'PROMOTED', 'deployment_id': identifier,
                              'rebuilt': False, 'alias_completion_verified': True}))
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
