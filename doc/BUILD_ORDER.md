# Build order and dependency gates

This order follows the data and authority dependencies. A stage is complete only with the listed evidence; a passing script exit code alone is insufficient.

## 0. Freeze planning interfaces

Read PRD, DESIGN, ARCHITECTURE, DECISION, GUARDRAILS, SECURITY and Trailforge integration. Record product name as provisional. Resolve any external provider account constraints and confirm no live orders. Output: signed-off local contract and open-question list. Gate: two independent readers can describe the same input, cutoff, label, action, and failure behavior.

## 1. Prove the data can support the question

Check Alpaca historical news/bar access for each of six symbols plus SPY; verify feed (`iex`/`sip`), article text/metadata, provider timestamps, page traversal, corporate actions, coverage by month, and acceptable use. Inspect sample earnings, ordinary, holiday/early-close, and corrected-story dates. Output: source audit and raw immutable sample. Gate: enough permitted, compatible data for a meaningful time split; otherwise declare an approximate/fixture path and reduce empirical claims.

## 2. Define calendar, label and provenance

Implement exchange sessions and cutoff UTC conversion, regular open/close extraction, configured class threshold, and article-version eligibility. Output: deterministic company-session examples and split manifest. Gate: future articles/bars and post-cutoff corrections fail eligibility checks; open/close labels match hand calculations.

## 3. Build ingestion and as-of snapshots

Add source adapters, raw records, normalized records, dedup/event grouping, ticker mapping and quality flags. Output: stable snapshot hash and a `RECORDED_STRICT`/`HISTORICAL_APPROXIMATE`/`FIXTURE` tier. Gate: duplicate and revision fixtures retain original versions, no-news differs from feed outage, missing prices block.

## 4. Make a vertical feature/forecast slice

Create one shared feature builder; train majority and price-only baselines first, then news TF-IDF and combined model. Output: one artifact/manifest per candidate and a saved forecast. Gate: offline and served feature values agree for the same snapshot; preprocessing fits training only.

## 5. Evaluate before paper action

Perform chronological validation, calibration, threshold selection and untouched final test. Compare news ablations, record counts/uncertainty and cost sensitivity. Output: evaluation report and policy candidate. Gate: no leakage; calibration is credible for the intended action population; otherwise keep research-only forecasts with abstention.

## 6. Integrate Trailforge and product records

Pin v0.1.0a1, build neutral Goal/Task adapters and independent verifier for snapshot/feature/model compatibility, store a stable run-to-decision mapping, and reconcile cross-store partial completion. Output: saved decision with run/receipt references and separate later outcome. Gate: crash/restart, duplicate request, UNKNOWN and mutated model/check inputs have honest results; harness `COMPLETED` does not substitute for saved decision.

## 7. Serve and demonstrate

Add typed FastAPI endpoints, Streamlit replay/detail/evaluation/ops screens, readiness and measured latency. Add failure controls only in local demo mode. Output: scripted interview walkthrough with win, miss, abstention, stale/duplicate case. Gate: outcome not preloaded, original artifact replay works, status and provenance are conspicuous.

## 8. Freeze and hand off

Pin dependencies and model manifest, publish local setup/run commands, capture limitations and rollback plan, back up and restore a test copy, inspect source/secret handling. Output: production-oriented demo release candidate. Gate: another engineer can reproduce the local fixture and explain which empirical conclusions are supported by real data.

See [TASKS](TASKS.md) for granular work IDs. Stages 1 and 5 are stop/go points for empirical and paper-action claims; software implementation can continue with explicitly labeled fixtures.
