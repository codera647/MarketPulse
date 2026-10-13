# MarketPulse

This repository implements **data extraction, source audit, gated collection,
explicit dataset review and baseline training software**, plus a runnable
**synthetic local replay demo** with four models, calibration, Trailforge-backed
decisions, FastAPI, Streamlit and recovery tools. The scope remains
AAPL, NVDA, AMZN, JPM, XOM, WMT, and benchmark SPY.
The private v1 research run now has 13,056 accepted real company-day rows,
four trained comparison models and a verified 1,104-row retrospective 2026 test.
The selected model underperformed the majority accuracy baseline and remains
research-only; see [measured results](doc/FINAL_TEST.md). There is no broker-order
capability or real-model deployment approval. Live IEX and historical SIP access
have been sampled under Trailforge;
see the [M02 audit](doc/M02_SOURCE_AUDIT_2026-10-10.md) for coverage and open
source limitations. The product plan is in [`doc/`](doc/README.md).
The [delivery milestones](doc/MILESTONES.md) track completed stages and
the user's requested GitHub commit/push checkpoints.

It also provides a read-only, explicitly provisional
[`label-preview`](doc/LABELS.md) command for an already audited outcome job.
That preview is not a training dataset or an empirical result.
The shared [`feature-preview`](doc/FEATURES.md) computes only pre-open
features from a saved snapshot; it does not read same-day outcomes.

## Run the local demo

The [research dashboard](doc/DASHBOARD.md) reads the verified specialist/stacking
reports and frozen 2026 retrospective evaluation. It includes model comparisons,
monthly/company charts, confusion matrices, probability calibration, historical
prediction reveal, dataset provenance and read-only Trailforge operation receipts.
Private artifacts must already be present; none are included in the repository.

```powershell
.\.venv\Scripts\marketpulse dashboard
```

Open http://127.0.0.1:8501. No collection, training or broker actions run from
the dashboard. Human quality/forward evaluation/deployment gates remain open.

For the separate **synthetic** demo:

```powershell
cd F:\MarketPulse
.\.venv\Scripts\marketpulse demo-init --data-dir data/demo
.\.venv\Scripts\marketpulse serve --data-dir data/demo
# In a second terminal:
.\.venv\Scripts\marketpulse dashboard --mode fixture --data-dir data/demo
```

Open [dashboard](http://127.0.0.1:8501) or [API docs](http://127.0.0.1:8000/docs).
Choose a synthetic date/ticker, Forecast, then Reveal outcome. The
[walkthrough](doc/DEMO.md) covers successes, a deliberate miss, holds,
duplicate requests, recovery and backup/restore. All demo data are manufactured;
no `.env` or provider API is used. Fixture mode remains isolated from the real
research dashboard and its empirical results.
See [release notes](doc/RELEASE.md) for setup, verification and remaining work.

## Extraction contract

For one NYSE session, the pipeline obtains Benzinga-supplied Alpaca news from
the previous regular close to the 09:00 New York cutoff, plus earlier completed
daily bars for the six stocks and SPY. It follows all provider page tokens within
fixed page limits, records receipt times and raw hashes, checks 21 prior bars per
symbol, creates six immutable snapshot identities, and saves a Trailforge
verification receipt. A healthy empty news response is valid; missing prices or
an incomplete page sequence are not.

The **Trailforge neutral Harness** runs bounded news, bars, optional web, and
typed verification tasks. `CANDIDATE_WRITE` is used explicitly because fetch
tasks save raw candidate artifacts. A completed harness run alone is not a
product record; the application then commits normalized records and snapshots
idempotently to its separate SQLite database. An interrupted run can be resumed
when its run ID reached the product database. A crash between harness start and
that write may leave an orphan run, which requires operator inspection.

**Agent-Reach** is integrated for opt-in web-page capture via its `WebChannel`
(Jina Reader). Those captures are stored separately and **never silently become
stock-news or historical as-of features**. Agent-Reach is a capability layer,
not a structured historical stock-bar provider. An opt-in page is sent through
Jina Reader, so use only URLs whose content you are permitted to share with that
service. No cookie/login channels or system-wide Agent-Reach installation are
used.

## Setup and one-session run

Python 3.11 or newer is required. Install into an isolated environment:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
# Copy .env.example to .env locally and set your credentials there.
.\.venv\Scripts\marketpulse extract --session 2026-10-09 --mode historical --feed iex
.\.venv\Scripts\marketpulse backfill --start 2026-09-01 --end 2026-09-30 --feed iex
.\.venv\Scripts\marketpulse audit --plan --case ordinary:2026-10-09 --case early_close:2025-11-28 --case holiday:2025-11-27
```

Extraction and live audit read cwd `.env`; `--env-file PATH` selects another
file. Process values win. The existing `APCA_API_EndPOINT` spelling works.
Trading endpoints are recognized but never called. Requests go only to the
official data host, with redirects disabled. Never commit credential files.

Use `--mode forward` only for an actual pre-09:00 capture. A strict snapshot
requires every canonical page to have been received by the cutoff. The separate
`fresh_for_0900` flag requires the news query to reach at least 08:55 ET; an
earlier capture must not drive a 09:00 action. A later
historical reconstruction is labeled `HISTORICAL_APPROXIMATE` even if the
article's published timestamp is earlier; a revised article may not represent
the text visible then. `--web-url https://example.com/article` adds one optional
Agent-Reach page capture, not a canonical news item. The application will not
retrieve article URLs automatically.

Backfill is bounded to 31 exchange sessions per invocation; use monthly chunks
for longer history. It reuses the same verified one-session contract and is
deliberately conservative about provider pagination and missing bars.

The data directory contains `marketpulse.sqlite3`, `trailforge.sqlite3`, and
content-addressed JSON under `raw/`. It is excluded from Git. Raw provider
payload retention and downstream use must comply with the user's data license.
No Alpaca keys are stored in the database or raw artifacts. The `iex` and `sip`
feeds differ; select one deliberately and verify account entitlements.

Run local verification with `python -m pytest` and `ruff check src tests`.
The [source-audit runbook](doc/SOURCE_AUDIT.md) explains plan and live modes,
case labels, report contents, and why a successful extraction still requires
human review before training claims.

## M03 dataset work

The [dataset runbook](doc/DATASET.md) describes the resumable historical batch
pipeline, separate verified regular-minute outcome ledger, immutable rows and
lineage/gap/leakage reports. A fixed 1% threshold and chronological dates are
agreed in the original small draft. The user subsequently attested source
permissions and authorized the larger private 2018–2026 research run; see
[REAL_DATA_RUN](doc/REAL_DATA_RUN.md). The committed small draft remains
unapproved, while the executed larger approved contract and data stay private.
Human quality/point-in-time/deployment promotion remains separate and open.

```powershell
.\.venv\Scripts\marketpulse dataset-plan --contract doc/dataset_contract.proposed.json
```

This prints the original proposed 1,878-row plan without network or credentials.
`dataset-batch` refuses the committed contract until a human records rights
confirmation in a private approved copy. Do not bypass that hold with backfill.

## Enriched and weighted v2 research

[RESEARCH_V2](doc/RESEARCH_V2.md) describes the separately authorized experiment:
company identity, sector-proxy context, before-09:00 pre-market features,
frozen financial-news sentiment/events, class-weighted logistic ablations and
CatBoost. It preserves v1 and uses only 2018–2025 development data; the exposed
2026 period is not presented as a new untouched final test. The v2 implementation
passes 230 regression tests, including 24 focused v2 checks;
its real research run completed with verified saved models. See
[V2_RESULTS](doc/V2_RESULTS.md): the selected CatBoost classifier has 53.63%
selection accuracy, below the neutral-only baseline's 65.46%. Its FinBERT candidate is non-commercial research
only and has an incomplete historical corpus audit.

Commands are `research-v2-build` and `research-v2-predict`; setup, private status
and saved label-free inference examples are in the runbook. All data/model
artifacts remain ignored under `data/`, and paper actions stay prohibited.

[REGRESSION_RESEARCH](doc/REGRESSION_RESEARCH.md) records the separately authorized
continuous-return experiment: five regressor families, the same enriched numeric
inputs and chronological splits, no new collection or FinBERT inference.
Commands are `research-regression-build` and `research-regression-predict`.
Real training completed with 56 verified fits; no trained model beat zero-return
selection RMSE. Saved models/results remain research-only.
[BOOSTING_RESEARCH](doc/BOOSTING_RESEARCH.md) records the separate fixed-seed
XGBoost/LightGBM/AdaBoost comparison requested next, with the same data/splits.
It completed with 39 verified fits and saved-model inference; none beat the
zero-return baseline and all had zero UP/DOWN recall on development selection.

## Safe baseline software demo

```powershell
.\.venv\Scripts\marketpulse baseline-demo --data-dir data/baseline-fixture
```

This generates synthetic rows, fits majority and price-only baselines, and
verifies saved-model scoring/validation under Trailforge. It uses no `.env`
or provider data. Final-test artifacts stay unopened by the learner, results
are `FIXTURE_SOFTWARE_CHECK_ONLY`, and no paper action is authorized. See
[BASELINES](doc/BASELINES.md) for contracts, artifacts and open real-data gates.

## Connected research pipeline

```powershell
.\.venv\Scripts\marketpulse pipeline-plan --contract doc/dataset_contract.proposed.json
```

The [runbook](doc/PIPELINE.md) connects resumable `pipeline-collect`, offline
`dataset-inspect`, human `dataset-promote`, and gated `baseline-train`.
Collection stops on failed/uncertain work and never trains automatically.
Training/validation reuse the shared scorer; their loader and verifier do not
open final-test rows. The [permissions record](doc/PERMISSIONS.md) distinguishes
confirmed Basic-plan/documented ML evidence from unresolved applicable terms.
The rights hold is unchanged; no real bulk collection or fitting was performed.
