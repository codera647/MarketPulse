"""Add only the server-side reader URL through CLI stdin, never process arguments."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from dotenv import dotenv_values

from marketpulse.cloud_connections import database_uri


def main():
    root = Path.cwd()
    config = json.loads((root / "deploy/cloud.json").read_text())['vercel']
    link = json.loads((root / '.vercel/project.json').read_text())
    if (link['projectId'], link['orgId']) != (config['project_id'], config['org_id']):
        print('FAIL: linked project differs')
        return 1
    values = dotenv_values(root / '.env.cloud.local', interpolate=False)
    uri = database_uri(values['MARKETPULSE_DASHBOARD_DATABASE_URL'], 'marketpulse_reader')
    result = subprocess.run(
        ['npx.cmd', '--offline', '--yes', f"vercel@{config['cli_version']}", 'env', 'add',
         'MARKETPULSE_DASHBOARD_DATABASE_URL', 'production', '--type', 'secret',
         '--scope', config['team_slug']],
        input=uri + '\n', text=True, capture_output=True, timeout=180, cwd=root,
    )
    print(json.dumps({'status': 'PASS' if result.returncode == 0 else 'FAIL',
                      'operation': 'add_production_reader_secret',
                      'secret_displayed': False, 'exit_code': result.returncode}))
    return 0 if result.returncode == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
