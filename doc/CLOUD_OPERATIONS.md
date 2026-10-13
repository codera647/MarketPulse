# Private cloud rollout

## Current state: provisioned, not deployed

The user confirmed permission for private cloud data storage/training and private
result display, selected Neon Free, requested weekly batch retraining and daily
09:00 New York forecasts, and authorized Vercel CLI setup. No broker orders.

Created and independently checked on 13 October 2026:

| Resource | Dedicated MarketPulse target |
| --- | --- |
| Vercel team / project | `codera647s-projects/marketpulse` |
| Vercel org ID | `team_75Ikyytg6OGvW0iRj2fKq0Gg` |
| Vercel project ID | `prj_Gto0aVFyeStSCSyOezczGk8myTWx` |
| CLI | `63.1.2`, user-authenticated |
| Neon project | `weathered-art-74189441`, MarketPulse |
| Neon region / PostgreSQL | `aws-us-east-1` / 17 |
| Database / primary branch | `marketpulse` / `production`, `br-cool-fire-b7c9ge4z` |
| Schema review branch | `cloud-schema-review`, `br-restless-dawn-b7k4b3y1` |
| Private object bucket | `research-artifacts`, production branch |

Neon reports a **536,870,912-byte (512 MiB) branch limit** for this new
project. Its existing unrelated project reports a different quota. Do not
assume 1 GB from plan marketing or silently increase spending. Custom suspend
settings were rejected with HTTP 412; creation succeeded with account defaults.
No paid provisioning, existing-project changes or cloud dataset uploads
occurred. The bucket is private; no public access was enabled. Two temporary
API-created administrator-default roles were removed during setup; they owned
no application data and are not needed. No history or datasets were deleted.

The Neon role API initially created administrator-default roles. Removing
their `neon_superuser` membership was denied. Migration
`deploy/migrations/0000_application_roles.sql` instead creates restricted roles
through SQL: `marketpulse_reader` and `marketpulse_worker`. It was tested on
the review branch before production. Both production logins were independently
connected and checked: no superuser/createdb/createrole/bypassrls privileges or
role memberships; reader defaults to read-only. No application schema exists
and neither role has application-table grants yet.

One newly generated temporary writer connection was exposed in a failed
credential-file patch error. Its password was immediately rotated, and the
unused role was subsequently removed. It was never committed or deployed.
Current restricted credentials are fresh values, saved only in ignored
`.env.cloud.local`. An ignored `.env.cloud-migration.local` contains the owner
connection for migrations only; never upload it to GitHub Actions or Vercel.

The repo is explicitly linked to the Vercel project; `.vercel` and `.env.local`
are ignored. Existing provider `.env` was not overwritten or displayed. No
Vercel deployment exists. Do not deploy the current repository root using the
`Other` preset's default output directory: a reviewed web output and exclusions
must be defined first. The current Streamlit dashboard remains local.

## Credential handoff

Vercel CLI login on this laptop does **not** configure GitHub Actions. The
deployment skill requires the account owner to configure CI credentials
directly, not paste them into chat or let the agent copy CLI authentication.

The user reports `VERCEL_TOKEN` is now saved in the repository's `production`
environment. Its value was not requested, fetched or printed; Actions has not
yet authenticated with it. For future rotation use:

- [Vercel token settings](https://vercel.com/account/settings/tokens)
- [MarketPulse GitHub environments](https://github.com/codera647/MarketPulse/settings/environments)

Use the public org/project IDs above as environment variables
`VERCEL_ORG_ID` and `VERCEL_PROJECT_ID`, and set `VERCEL_CLI_VERSION=63.1.2`.
Verify that the account supports the required reviewed-code/environment
protection before enabling production automation; do not purchase a plan
without separate cost approval. Never expose secrets to pull-request code.

The complete workers will additionally need CI secrets `APCA_API_KEY_ID`,
`APCA_API_SECRET_KEY`, `MARKETPULSE_DATABASE_URL`, `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY`, plus variable `AWS_ENDPOINT_URL_S3`. Restricted database
and production-branch storage credentials are issued in `.env.cloud.local`.
The storage access key maps to Neon's `token_id`, not its API bearer token.
Add the worker URL and storage keys directly to GitHub; Alpaca keys remain in
the original `.env`. These CI values have not been independently confirmed.
Keep the dashboard reader URL separate for Vercel server-side use; never use
the owner database connection in the dashboard or browser. Provider credentials
must never be embedded in the Vercel browser bundle.

Read-only key-presence inspection (does not load dotenv/login credentials):

```powershell
.\.venv\Scripts\python.exe -m marketpulse.cloud_bootstrap
```

Exit 1 / `BLOCKED` is expected until the relevant environment is configured.
`KEYS_PRESENT` only means keys and target IDs match; it does not prove credentials,
database migrations, dashboard privacy, inference, or worker readiness.

Verified bounded read-only local cloud access:

```powershell
.\.venv\Scripts\python.exe -m marketpulse.cloud_connections
```

Both restricted database roles connected successfully; authenticated private
bucket HEAD and ACL checks passed. No payloads were uploaded. CLI key-presence
inspection remains blocked outside the configured CI environment. Cloud/setup
checks and credential-scanner regression checks pass; see CHECKPOINT for counts.

## Remaining implementation and acceptance order

1. Verify credentials and exact linked targets. Write a code-managed compact
   Postgres schema, test it on the review branch, inspect the diff, and then
   migrate production. The initial restricted-role migration is already verified;
   the application-table schema and grants are not. Keep raw payloads and binary
   models in private storage.
2. Implement durable cloud Trailforge checkpoints and single-writer ownership.
   GitHub runners are ephemeral; a fresh local SQLite database is not durable
   audit authority. Retain UNKNOWN attempts and reconcile; never reset them.
3. Import a bounded, verified research release with provenance and native
   receipts. Keep the existing historical data/reports unchanged. No invented
   live results or implicit promotion of a weak research model.
4. Build the daily forward pipeline: NYSE calendar, timezone-aware capture and
   receipt timestamps, news preprocessing and FinBERT features, saved expert
   inference, complete six-company projection, immutable publication and
   post-close labels. All inputs must be available by 09:00 New York. Clearly
   identify an earlier capture's actual as-of time. A late/missing job must
   abstain or show a missed cutoff, never generate a backdated live prediction.
5. Build weekly batch retraining on completed labelled sessions with
   chronological training/calibration/validation, train-only preprocessing,
   duplicate masking and saved replay. Publish candidates only; replacement
   requires validation and the remaining forward/quality gates. Previously
   exposed 2026 data is not a new blind holdout.
6. Build compact private hosted dashboard access, read-only backend and API
   tests. Keep the existing local Streamlit research and fixture contracts.
   Authenticate before revealing results; test unauthenticated denial and
   authenticated data access before publication.
7. Test private archive restore, idempotent retries, crash/UNKNOWN recovery,
   stale-data and deadline failures; then enable GitHub schedules. Treat
   scheduled runs as best-effort, not an exact-time guarantee.

## Storage cleanup design: not enabled yet

The user requested automatic removal of old data as the database fills.
Implement a proactive policy using the **actual provider quota**, with a
reviewed age policy and a verified archive before removing source material.
Proposed thresholds: begin at 75%, target 60%, stop ingestion at 90% if safe
cleanup cannot free room. Do not treat these proposed thresholds as implemented.

Protect active training rosters, pending outcomes, retained/UNKNOWN tasks,
model lineage, active/candidate releases, publication receipts and audit
holds. Never delete needed training data merely because it is old. Database
row deletion does not necessarily shrink allocated storage immediately;
design retention/partitioning and vacuum handling against measured usage.
Do not promise perpetual free capacity: compute, object storage, transfer and
GitHub runner limits also need checks. No history has been deleted.

Cloud provisioning alone closes no research-quality, paper-policy or release
milestone. See [CHECKPOINT](CHECKPOINT.md) for the existing model evidence.
