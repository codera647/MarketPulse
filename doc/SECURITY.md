# Security, authority and permitted use

Status: threat model for a local, single-operator research demo. It does not establish legal compliance or readiness for customer/live-trading use.

## Assets and trust boundaries

Assets: provider API credentials; licensed article content and raw payloads; historical price records; model artifacts; Trailforge authority database; application decision/outcome database; logs and exports; the protected evaluation/test specification. The local operator owns model/policy promotion. The interviewer may view demo results, not provider secrets or unrestricted raw exports.

External news, HTML, model outputs, provider responses, and task dependency JSON are untrusted observations. The host application decides source eligibility, scope, policy and action. Trailforge `tenant_id`/`resource_id` strings bind a run but do not authenticate a human. Its checksums and receipts detect accidental mismatch; they do not prevent a privileged database rewrite. The application must restrict filesystem/database access and back up evidence.

## Threats and controls

| Threat | Required control | Verification |
| --- | --- | --- |
| API key or licensed text leaks into code/logs/export | Environment/secret storage, `.env.example` only, redaction, artifact ACLs, no raw source in routine telemetry | Secret-scan fixture and inspect normal error logs/exports |
| Article text contains instructions or malicious HTML | Treat as data, sanitize UI rendering, never execute or follow source instructions | Script/HTML fixture and adversarial article text |
| Future data enters a replay | Exact cutoff/version/received-time checks; strict vs approximate tier | Post-cutoff article/edit and same-day bar fixtures |
| Ticker or session spoofing | Fixed universe, typed schema, exchange calendar, permission checks | Invalid ticker/session requests rejected |
| Model artifact or policy swapped mid-run | Digest/version binding in snapshot, Goal, manifest and decision | Changed artifact/adapter identity denied or new run required |
| Duplicate paper position | Unique request key and ledger transaction with exposure cap | Concurrent requests and restart exercise |
| Unsafe public API exposure | Local loopback by default; if exposed, add authentication, authorization, rate limiting and TLS before use | Port binding/config review; unauthorized access test if public mode exists |
| Trailforge callback overreach | Trusted callbacks only, least-privilege host process, no untrusted code execution | Adapter permissions review and fixture |
| Tampering with evidence | Restricted DB/artifact writes, hash references, backups and restore check | Corruption detection plus restore exercise; no tamper-proof claim |
| Provider terms misuse | Record permitted use, caching, display, training and redistribution limits | Source-rights review before data pull/public sharing |

## Identity and human authority

The first release has one local operator. An interview demo can be shown through a local screen or protected local URL. Public multi-user deployment requires authenticated identity, per-user access control, scoped source-data rights, audit retention, and a new security review. Neither model confidence nor Trailforge VERIFY authorizes a real order. The project contains no broker order adapter.

Human review is required for changing the target definition after feasibility, promoting a model/policy to paper-action mode, publishing performance claims, and any future external effect. Approval must be tied to the exact artifact/configuration being promoted. Unresolved `UNKNOWN` work is inspected by the operator; timeout is not approval.

## Data governance

Before downloading or displaying provider material, verify terms for local research, storage duration, derived-feature/model training and interview sharing. Keep a source-rights record with date and provider account/plan, without credentials. Minimize saved article text when terms require it; retain allowed IDs, URL, timestamp and hash for audit. Do not redistribute full articles by default.

Set a local retention period after rights review; until then, avoid public export and keep raw caches private. Deletion must remove both source-bearing artifacts and their indexes while preserving a non-sensitive tombstone/lineage note where permitted. Financial/legal requirements for a commercial pilot need qualified review; this demo plan does not decide them.

## Fixture service boundary and delivery checks

The implemented API/dashboard commands bind loopback only. The HTTP API rejects
non-loopback peers, unexpected hosts and request bodies larger than 16 KiB;
input symbols/faults are typed literals, no caller-supplied URLs or file paths.
This does not establish public-service authentication: do not proxy it publicly.
The UI displays headlines as literal text and does not execute provider content.
Fixture models, policies and outcomes cannot promote real research artifacts or
authorize broker orders. Keep private data stores and backup destinations outside
Git; quiesce writers for backup and preserve originals during restore.

Before each delivery, stage only intended source/docs and run
`python scripts/check_staged_secrets.py`. The scanner checks forbidden data/
credential paths, exact locally configured credential values and common secret
signatures without printing them. It is a safeguard, not a proof that every
possible secret or sensitive dataset can be recognized. `.env.example` remains
an empty template; `.env`/`.evn` and real artifact stores must never be staged.

## Incident and rollback

If a credential leaks, revoke/rotate it, stop ingestion, inspect access, and document affected exports. If a source version, feature cutoff or label bug is found, mark affected evaluations invalid, disable paper-action mode, preserve the original evidence, and retrain/re-evaluate with a new manifest. If a Trailforge authority store is corrupted, stop admission, restore a known consistent copy and reconcile product decisions; never reset the store to regain declared-unit allowance.
