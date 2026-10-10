# Architecture and contracts

Status: proposed modular-monolith design. One repository may run a scheduled worker, FastAPI process, and Streamlit UI; code boundaries do not require separate services.

Current implemented slice: extraction, source audit, and read-only provisional
label/feature previews. Alpaca is the canonical structured news/bar provider.
Agent-Reach `WebChannel` is an opt-in supplementary internet capture path
whose output is excluded from market snapshots. Extraction and outcome-source
audit Goals use Trailforge now; model, policy, API, and UI remain proposed.

## 1. End-to-end flow

```text
Alpaca news/bars -> raw versioned cache -> normalization + quality checks
  -> as-of snapshot -> shared feature builder -> pinned model + calibrator
  -> independent validation -> paper policy -> idempotent decision ledger
  -> API / replay UI

After session close: price outcome -> separate outcome ledger -> evaluation/reveal UI
```

The scheduled worker creates a request per company-session at the cutoff. Replay can use a saved, versioned snapshot or a clearly approximate historical reconstruction. Both call the same feature builder, predictor, and policy. Evaluation reuses that code with chronological splits; it does not use a separate notebook-only path.

## 2. Responsibilities and boundaries

| Boundary | Owns | Must not own |
| --- | --- | --- |
| `domain` | session, horizon, class/action enums, cutoff and decision invariants | Alpaca SDK, UI, SQL clients |
| `providers` | Alpaca news/bars adapters, pagination, rate limits, payload provenance | market labels or policy |
| `data` | raw records, normalization, article versions, ticker mapping, dedup, quality | authorization of paper action |
| `features` | as-of feature computation and schema version | same-day outcomes at inference |
| `models` | fit/infer/calibrate, artifact manifest | paper-trade authority |
| `policy` | `PAPER_LONG`/`ABSTAIN`/`BLOCKED`, reason codes, exposure rules | model fitting |
| `records` | decision identity, transactions, outcomes, evidence references | changing old decisions |
| `evaluation` | splits, baselines, diagnostics, backtest accounting | threshold changes after test |
| `api`/`ui` | typed access, reveal control, operator views | hidden recomputation with newest model |
| `trailforge_host` | bounded run construction, adapters, verifier, recovery bridge | market semantics and model-quality claims |

Core contracts depend inward on stable domain types. Provider, storage, framework, and Trailforge adapters depend on those contracts. No component accepts instructions embedded in a news article as authority.

## 3. Main records

`article_version`: provider/source ID, ticker links, article ID/version/hash, source URL, created/published/updated/received timestamps, raw payload reference, availability tier, quality flags, event group.

`price_bar`: symbol, session, timeframe, feed, open/high/low/close/volume, adjustment convention, provider timestamp, retrieval time, raw hash and quality flags. SPY has the same contract.

`snapshot`: ticker, session, cutoff UTC and zone, article-version IDs, prior bar IDs, source feed/availability tier, snapshot hash, feature-schema version, creation time.

`decision`: stable unique decision key, snapshot hash, ticker/session/horizon, model/calibrator/policy versions, feature-value or immutable feature-artifact hash, class probabilities, action/reasons, quality flags, Trailforge run ID and verified receipt references, creation/latency. Unique key includes ticker, session, cutoff/horizon, snapshot hash, model and policy versions. Identical retry returns the stored record.

`outcome`: decision ID, regular open/close, actual return/class, price source/feed/adjustment, observation time, quality flags. An outcome is appended separately and never edits `decision`.

`model_manifest`: code/data split IDs, feature schema, training parameters, calibrator, threshold/policy compatibility, artifact digest, evaluation artifact links, release date, human promotion decision. A model file without its manifest is not ready for serving.

## 4. Storage and transaction design

Use Parquet or equivalent immutable files for bulk raw/derived datasets and model/evaluation artifacts; use application SQLite for unique decision/outcome and metadata records in the local demo. Trailforge maintains its **own** SQLite authority for bounded run/checkpoint state. The two stores do not share an atomic transaction. The host bridges them using a stable product request key, persisted mapping, idempotent writes, and a reconciliation scan for completed harness runs lacking product decisions. A harness `COMPLETED` state is insufficient by itself to assert that the product decision was persisted.

Large model files and datasets stay in application artifact storage with content hashes; Trailforge task JSON carries bounded IDs, hashes, and concise results. Trailforge's local artifact store has small per-object bounds and is not the model registry. Back up the application database, harness authority, and referenced artifacts as a consistent recovery set; verify restore on a copy. Access-controlled storage and backups, not simple hashes, provide audit integrity against privileged changes.

## 5. Request and operational surfaces

Candidate API: `GET /health/live`, `GET /health/ready`, `POST /predict`, `GET /decisions/{id}`, `POST /replay`, `GET /outcomes/{decision_id}` after horizon, `GET /evaluation`, `GET /metrics`. These are illustrative contracts; implementation can refine names without changing semantics. Readiness requires compatible model, calibrator, feature schema, policy, and usable stores. Liveness only means process responds.

UI: replay with outcome reveal; decision detail with source and version links; evaluation with baselines/calibration/coverage/costs; operations with freshness, latency, holds, and failure controls. Display `RECORDED_STRICT`, `HISTORICAL_APPROXIMATE`, or `FIXTURE` prominently. Do not preload the outcome in hidden frontend state.

## 6. Failure and recovery

Provider outage, missing or stale data, ambiguous company match, and invalid session yield explicit `BLOCKED` or typed errors. Model uncertainty yields `ABSTAIN`. Timeouts and uncertain harness tasks retain `WAITING_HUMAN`/`UNKNOWN` state for operator inspection; no blind retry of ambiguous provider effects. Duplicate requests converge on one decision. An outcome job can be safely retried by decision ID without changing the original forecast.

The initial deployment is a single trusted local demo. Public multi-user access, distributed scheduling, and live execution each require a new architecture and security review.
