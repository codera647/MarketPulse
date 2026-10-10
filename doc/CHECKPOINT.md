# MarketPulse checkpoint for the next agent

Last checked: 2026-10-10 (Asia/Karachi). This is a handoff record, not a claim
that the whole product is built or that live market data has been validated.

## Project in one minute

MarketPulse is a six-company US-stock prediction **research and paper-demo**
project. The agreed target companies are AAPL, NVDA, AMZN, JPM, XOM, and WMT;
SPY is market context and a benchmark, not a seventh company prediction.
The proposed daily decision time is **09:00 America/New_York** on NYSE trading
days. Using only information available by then, a future model will estimate
`UP`, `DOWN`, or `NO_MATERIAL_MOVE` for that day's regular-session
**open-to-close** return. A separate deterministic policy may eventually say
`PAPER_LONG`, `ABSTAIN`, or `BLOCKED`. No real trading, broker orders, model,
prediction API, or dashboard exists yet. The forecasting target and policy
threshold are still provisional and require data/evaluation evidence.

The supplied production-AI thinking framework guides the planning and evidence
gates; it is not a substitute for the user's instructions. The user explicitly
requires their [Trailforge](https://github.com/codera647/Trailforge.git) harness
for the agent and requested [Agent-Reach](https://github.com/Panniantong/Agent-Reach.git)
for internet access. The implemented extraction slice uses both within their
actual capabilities.

## Workspace and starting points

- Project root is **`F:\MarketPulse`**. The environment supplied
  `F:\US_Stock_Prediction` as a cwd, but that path was checked and does not
  exist. Do not silently start a second project there or move existing files.
- This directory is now a local Git repository on `main`. The initial remote
  repository, milestones, and push are pending callable GitHub connector tools.
  The local `.env`, `.evn`, `.venv/`, generated `*.egg-info/`, and `data/` are
  ignored by `.gitignore`. See [MILESTONES](MILESTONES.md) for the delivery plan.
- Read [PRD](PRD.md), [DESIGN](DESIGN.md), [ARCHITECTURE](ARCHITECTURE.md),
  [DECISION](DECISION.md), [EXTRACTION](EXTRACTION.md), and
  [TRAILFORGE_INTEGRATION](TRAILFORGE_INTEGRATION.md) before changing the
  contract. [BUILD_ORDER](BUILD_ORDER.md) and [TASKS](TASKS.md) list the
  remaining stages. [Project README](../README.md) has setup/run commands.

## What is implemented now

| Area | Current implementation |
| --- | --- |
| Python package/CLI | `pyproject.toml` and `src/marketpulse/cli.py`; `marketpulse extract --session ...` and bounded `backfill --start ... --end ...` (up to 31 exchange sessions per invocation). |
| Market sources | `src/marketpulse/alpaca.py` calls Alpaca historical news and multi-symbol daily stock-bar endpoints with credentials from environment variables, bounded pagination, response-size limit, retries/timeouts, and request-ID capture. |
| Calendar and eligibility | `clock.py` uses the NYSE calendar and timezone-aware UTC; `normalize.py` rejects same-day/future bars and post-cutoff article versions, checks OHLC and at least 21 distinct prior bar dates per symbol by default with the latest bar on the previous session, and builds six hash-identified snapshots. The feature gate additionally requires 21 consecutive exchange sessions. |
| Raw and product storage | `storage.py` saves content-addressed raw JSON plus normalized article/bar metadata, web captures, extraction jobs, and snapshots in application SQLite. Extraction materialization is one application-DB transaction. No Parquet training export exists yet. |
| Trailforge | `extraction.py` uses pinned neutral `Goal`/`Task`/`Harness` with explicit `CANDIDATE_WRITE` fetch tasks and a typed `VerifiedResult` check. Trailforge has its own SQLite authority. Only a `COMPLETED` verified run can materialize accepted product snapshots. UNKNOWN provider outcomes are held, not silently retried. |
| Agent-Reach | Pinned `WebChannel` is wired to opt-in `--web-url` capture through Jina Reader. It is supplementary evidence, **not** the canonical historical price/news source or an automatic prediction feature. No social-cookie/login channels or system-wide installation were used. |
| Provenance | Manifest records source/feed/adjustment, cutoff and news query end, article/bar counts, six snapshot hashes, availability tier, freshness flag, and Trailforge receipt IDs. Historical retrieval is `HISTORICAL_APPROXIMATE`; a genuinely recorded pre-cutoff capture can be `RECORDED_STRICT`. `fresh_for_0900` is a separate provisional five-minute freshness check. |
| Source audit | `marketpulse audit` writes dated JSON/Markdown reports for explicit ordinary, earnings, early-close, correction, and holiday cases. Plan mode needs no credentials. Live mode runs pre-open extraction plus a separate Trailforge-supervised same-day outcome-bar probe. It records per-symbol coverage, raw page hashes, source request IDs, and unresolved gates; outcome bars do not enter prediction snapshots. See [SOURCE_AUDIT](SOURCE_AUDIT.md). |
| Provisional label preview | `marketpulse label-preview` reads one saved pre-open snapshot and one separate verified outcome job. It validates matching session/feed/adjustment, immutable raw outcome pages and post-close receipt, then computes the symmetric `UP`/`DOWN`/`NO_MATERIAL_MOVE` class under an explicit threshold. It writes nothing and always marks the result not ready for training. See [LABELS](LABELS.md). |
| Pre-open feature preview | `marketpulse feature-preview` uses one shared `build_features` function on a saved snapshot. It validates raw-version agreement and 21 consecutive prior NYSE sessions, then outputs versioned lagged company/SPY price features and simple headline-count features. No outcome or Agent-Reach capture is an input. It writes nothing and is not a fitted model. See [FEATURES](FEATURES.md). |

External packages are pinned by Git commits in `pyproject.toml`:
Trailforge `v0.1.0a1` at
`fbefaf40fb39a1429dcc328184372214f9fd849d`, and Agent-Reach at
`94f06c1969dfc1834001269d79d3ad0972d9dee6`. Transitive packages have
version ranges, not a fully locked deployment file.
The interrupted baseline setup added and installed `scikit-learn==1.9.1`;
there is still no training implementation or fitted model.

## Verification performed

An isolated project `.venv` exists. On this checkpoint, these commands passed:

```powershell
cd F:\MarketPulse
.\.venv\Scripts\python -m pytest -q
# 25 passed
.\.venv\Scripts\ruff check src tests
# All checks passed!
```

Tests in `tests/test_extraction.py`, `tests/test_audit.py`, and
`tests/test_labels.py`, and `tests/test_features.py` use synthetic provider responses. They
exercise successful extraction, empty-but-healthy news, missing/future bars,
strict versus early forward capture, optional Agent-Reach isolation, provider
UNKNOWN and no silent retry, pagination, post-cutoff revisions, idempotence,
NYSE session/early-close behavior, source-audit coverage, separate outcome
probing, missing-outcome blocking, and a read-only provisional label with
hand-checked symmetric class boundaries, raw-source feature consistency,
21-session rolling-window coverage, and no-news feature handling. This
validates code paths, not real
feed quality, real network access, or financial predictive value.

A credential-free audit plan was generated with an ordinary session,
early-close session, and holiday. It is marked `NOT_RUN` and lists missing
earnings and correction examples; it is not a live-data verdict.

## Unverified gates and honest limitations

1. **No live Alpaca run has occurred.** The user has now supplied credentials
   in a local `.env`; loading and testing that file is the next pipeline step.
   The current CLI reads process environment variables. Never request that
   the user paste secrets in chat; have them set credentials locally. Account
   access, IEX/SIP entitlement, request/response shape on real dates, historical
   coverage, article text/metadata, rate limits, and data-use/retention rights
   must be audited before calling extraction empirically complete.
2. **Historical news is not proven point-in-time.** A current API response may
   not reproduce what an article said at 09:00 on an old date. Keep such replay
   labeled approximate. Do not train/evaluate as if revisions or original
   receipt times were known.
3. **Agent-Reach's actual web network path is not live-tested.** Tests inject a
   stub reader. Its Jina Reader path sends an opted-in public URL to a third
   party; verify source rights and response quality before use. It cannot
   replace Alpaca bars or certify historical article availability.
4. **Cross-store recovery has a known orphan window.** A crash after
   `Harness.start` but before the product DB records the run ID may create a
   second harness run on retry. Idempotent product records do not imply
   exactly-once external calls. Audit/reconciliation and backup/restore still
   need a real fault-injection exercise.
5. This slice has **no persisted/frozen labels, fitted model, Parquet training table, paper policy,
   outcome ledger, FastAPI, Streamlit UI, scheduler, or real-order capability**.
   Do not describe fixture tests or Trailforge completion as model accuracy or
   production certification.

## Recommended next agent action

First finish M00: use the user's GitHub connector to create a private
`MarketPulse` repository and the milestones in `github_milestones.json`, push
the local source commit, and verify the remote. User authorization to push
at each completed milestone is recorded in root `AGENTS.md`.

First run the commands above and inspect the current code/docs without
changing the agreed six-stock scope. Then, after the user configures Alpaca
credentials locally, use [SOURCE_AUDIT](SOURCE_AUDIT.md) to run the Stage 1
live source audit. Select independently verified earnings and corrected-story
dates; sample ordinary, holiday/early-close, and those event sessions for all
six stocks and SPY. Confirm response schemas, page traversal, missingness,
account entitlements, and retention terms. Save and inspect the dated audit
result with concrete counts and gaps. Fix any
extraction defects exposed by that evidence and add regression tests. Only
then freeze the target/threshold/split contract and proceed to persisted labels,
features/training and later prediction-specific
Trailforge integration. Keep Agent-Reach web captures out of the model until a
separate source-eligibility and point-in-time decision is documented.
