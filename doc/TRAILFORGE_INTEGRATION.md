# Trailforge integration contract

Status: proposed host integration against pinned `v0.1.0a1` (`fbefaf40fb39a1429dcc328184372214f9fd849d`). Verify the installed package and behavior before writing product adapters. Source: supplied Trailforge technical guide and [release source](https://github.com/codera647/Trailforge/tree/v0.1.0a1).

Implementation update: the extraction slice now uses the pinned neutral Harness
for one session-wide Goal containing bounded Alpaca news, bars, optional
Agent-Reach web capture, and a typed independent `VERIFY` task. The host uses
`CANDIDATE_WRITE` for raw capture writes and commits normalized records to its
separate application database only after `COMPLETED`. Local fixture tests pass;
live provider and recovery audits remain open. The ticker-session
prediction Goal described below is still a **future** integration, not an
implemented serving path. See [EXTRACTION](EXTRACTION.md).

## What Trailforge will control

Trailforge's **neutral Harness** will bind a finite company-session run to a tenant/resource, goal digest, allowed adapters/effects, declared-unit budget, bounded input/output and required typed VERIFY task. It persists checkpoints, task results, receipts and `UNKNOWN` holds in its SQLite authority. It is useful for reproducible replay and restart inspection.

The application still owns Alpaca credentials and calls, feature and model implementations, market validation, probability calibration, paper policy, decision/outcome records, UI, user identity, provider timeouts, real cost measurement, scheduling and release approval. Trailforge `COMPLETED` means its named checks passed; it does not mean the forecast was correct or a paper decision exists. Declared units are a reservation ledger, not dollars or provider token spend.

Do not use the fixed PR Review CLI/profile for market data. Do not use `Develop` as a prediction API. The optional PostgreSQL adapter applies to the legacy Review path, not the neutral Goal/Task Harness. The optional LangGraph facade is unnecessary for this finite sequence. No multi-agent topology is planned.

## One candidate Goal per ticker-session

Scope: `tenant_id=local-demo`, `resource_id=marketpulse:<ticker>:<session>`. The goal objective/input binds the exact cutoff, horizon, data tier, snapshot request key, source/feature schema, model/calibrator/policy identities and adapter version. Stable adapter IDs must change when callback behavior changes materially; the capability digest alone does not hash Python function code.

1. `snapshot`: a `TOOL/SCOPED_READ` adapter resolves a specific source snapshot and reports its ID/hash, eligibility and quality. It does not place full article bodies in bounded task JSON. Provider requests have host-side timeouts and a cache policy.
2. `score`: a `MODEL/PURE` adapter uses the shared feature builder and pinned artifacts. It returns structured `VALID` probabilities/feature digest or a structured `BLOCKED` result if required data is unavailable. It never authorizes `PAPER_LONG`.
3. `verify`: a `VERIFY/SCOPED_READ` or `VERIFY/PURE` adapter independently checks ticker/session/cutoff, source-version eligibility, feature/model/calibrator compatibility, finite probabilities summing to one, and honest blocked status. It returns `VerifiedResult(PASS|FAIL|UNKNOWN, request.goal_digest, evidence)`; ordinary JSON containing `PASS` is insufficient.

Only `verify` is a required check. `PASS` on a correctly blocked result means the workflow handled invalid data according to contract. If the check cannot establish whether data or inference was valid, use `UNKNOWN`; do not declare an action. A callback exception or oversized result also becomes an uncertain run requiring inspection. Define a practical processing deadline before the assumed regular open; a result that expires before policy materialization cannot produce `PAPER_LONG`.

The first integration spike should test actual latency and task payload sizes. If a per-session harness run cannot meet the deadline, the product decision path can remain ordinary trusted application code while Trailforge guards replay and offline evaluation runs. Record that narrower use in DECISION rather than claiming it covers live serving.

## Product decision bridge

The product database creates a deterministic `request_key = hash(ticker,session,cutoff,horizon,snapshot_hash,model,calibrator,policy)`. Place a unique constraint on it. The host records a pending request before starting a harness run, then records the returned run ID as soon as it can. After `COMPLETED` and current artifact/expiry checks, the host transactionally writes one product decision or returns the existing one. An outcome is another transaction and record.

Trailforge's SQLite authority and the product SQLite database cannot commit atomically together. A crash after `Harness.start` but before the product records the run ID may leave an orphan run; a repeated request can start another run, consume more declared units, and still must converge on one product decision. Keep this window visible in operations and document an orphan-audit procedure; do not assert exactly-once model execution. For known run IDs, startup reconciliation inspects the harness state and materializes or holds the decision idempotently.

Same Goal and adapter capabilities are required on resume. A changed model, policy, source snapshot, or adapter contract starts a new Goal, never a checkpoint rewrite. A successful stored decision replays from its original snapshot and artifacts, not current news or the newest model.

## Budgets, uncertainty and security

Configure finite tasks, attempts, JSON byte bounds, lease duration and declared units. Harness runs tasks sequentially within one run. An expired lease does not stop a synchronous callback; enforce actual network/model timeouts in adapters or supervised processes. `WAITING_HUMAN` or expired/UNKNOWN attempts require a trusted host decision after inspection; `RETRY` retains prior reservations and attempt count. Never reset the authority DB to recover budget.

`FunctionAdapter` callbacks execute in the trusted Python host; effect labels are not OS sandboxing. News text is untrusted data, and no model receives credentials or authority to broaden scope. Do not execute article content or generated code. Trailforge receipts are integrity records, not signatures or proof that the financial forecast is correct. Restrict SQLite/artifact access and scrub routine telemetry. No external publication boundary is needed for internal paper records; any future broker/external write would require a separate authorization design.

## Integration acceptance

- Pinned tag installs in an isolated environment and a neutral `Goal` with typed `VerifiedResult` passes a smoke check.
- Pause/resume after `snapshot` yields the same versioned result without refetching it; changed Goal or adapter identity is denied.
- A source/model mismatch yields VERIFY `FAIL` or `UNKNOWN`; no paper action is persisted.
- A callback timeout is visible as `UNKNOWN`/hold, with no invisible retry or budget refund.
- Identical concurrent requests persist one product decision; cross-store interruption is recoverable for known run IDs and the orphan window is documented.
- Product evaluation metrics are computed independently of harness completion state.
