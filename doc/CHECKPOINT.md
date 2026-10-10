# MarketPulse checkpoint for the next agent

Last checked: 2026-10-10 (Asia/Karachi). This is a handoff record, not a claim
that the whole product is built or a complete historical dataset is validated.
M02 now has bounded live IEX/historical SIP access evidence.

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
- This directory is a Git repository on `main`, tracking `origin/main` at
  [codera647/MarketPulse](https://github.com/codera647/MarketPulse), a private
  repository. The initial source commit `8009cbd` was pushed on 2026-10-10.
  All nine GitHub milestones exist; M00/M01 cover repository setup and the
  fixture-tested foundation, not live data or trained models. The connector
  verified account/repository access; creation used the GitHub API with
  existing local Git authentication because the connector lacks those tools.
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
| Market sources | `config.py` loads literal local `.env` or process values without exposing keys; approved data host only, trading endpoint recognition without use, and no redirects. `alpaca.py` calls historical news/daily bars with bounded pagination, response-size limit, retries/timeouts, request IDs, and sanitized provider failures. |
| Calendar and eligibility | `clock.py` uses the NYSE calendar and timezone-aware UTC; `normalize.py` rejects same-day/future bars and post-cutoff article versions, checks OHLC and at least 21 distinct prior bar dates per symbol by default with the latest bar on the previous session, and builds six hash-identified snapshots. The feature gate additionally requires 21 consecutive exchange sessions. |
| Raw and product storage | `storage.py` saves content-addressed raw JSON plus normalized article/bar metadata, web captures, extraction jobs, and snapshots in application SQLite. Extraction materialization is one application-DB transaction. No Parquet training export exists yet. |
| Trailforge | `extraction.py` uses pinned neutral `Goal`/`Task`/`Harness` with explicit `CANDIDATE_WRITE` fetch tasks and a typed `VerifiedResult` check. Trailforge has its own SQLite authority. Only a `COMPLETED` verified run can materialize accepted product snapshots. UNKNOWN provider outcomes are held, not silently retried. |
| Agent-Reach | Pinned `WebChannel` is wired to opt-in `--web-url` capture through Jina Reader. It is supplementary evidence, **not** the canonical historical price/news source or an automatic prediction feature. No social-cookie/login channels or system-wide installation were used. |
| Provenance | Manifest records source/feed/adjustment, cutoff and news query end, article/bar counts, six snapshot hashes, availability tier, freshness flag, and Trailforge receipt IDs. Historical retrieval is `HISTORICAL_APPROXIMATE`; a genuinely recorded pre-cutoff capture can be `RECORDED_STRICT`. `fresh_for_0900` is a separate provisional five-minute freshness check. |
| Source audit | Dated ordinary, post-earnings, early-close, holiday and revision-candidate audits passed for IEX and historical SIP. Includes observed schema/types, page traversal, required-21-session gaps, request IDs, and separate verified outcome probes. Reports remain `TECHNICAL_REVIEW_REQUIRED`; see [M02 evidence](M02_SOURCE_AUDIT_2026-10-10.md). |
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
# 51 passed
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
21-session rolling-window coverage, and no-news feature handling. New tests
cover dotenv loading, redaction, endpoint/redirect refusal, sanitized failures,
pagination caps, audit rolling gaps, and relative read-only preview paths.
Fixture tests validate code paths, not financial predictive value.

The initial GitHub commit `8009cbd` also passed the Windows/Python 3.13
[CI run](https://github.com/codera647/MarketPulse/actions/runs/38035607436):
dependency installation, lint, and fixture regression tests all succeeded.
The committed-content scan checked 41 files against locally supplied secret
values and token/private-key patterns without printing any secret. `.env`,
`.evn`, `.venv/`, and `data/` were not tracked.

A credential-free audit plan was generated with an ordinary session,
early-close session, and holiday. It is marked `NOT_RUN` and lists missing
earnings and correction examples; it is not a live-data verdict.

M02 live audits subsequently passed for both feeds on four distinct sessions:
2026-10-09, 2025-08-04, 2025-08-01, and 2025-11-28; 2025-11-27 was calendar-only.
All seven price symbols had prior bars and separate verified outcome bars,
with no required-window gaps. Six recent SIP snapshots passed the actual
feature builder. Source choices, local report paths/hashes, successful news/bar
pagination, and the preserved page-cap failure are in
[M02 evidence](M02_SOURCE_AUDIT_2026-10-10.md). `.env` was not modified or exposed.

M02 code commit [`02ac97b`](https://github.com/codera647/MarketPulse/commit/02ac97bcd3f161ff53a8baa3774a11c09fb31686)
was pushed, and its [GitHub CI](https://github.com/codera647/MarketPulse/actions/runs/38037607123)
passed installation, lint, and tests. Remote M02 is closed. The staged secret
scan checked 22 files, and the local-artifact scan checked 101 files without
finding credential values. Raw captures and SQLite authorities remain local.

## Unverified gates and honest limitations

1. **Source access is sampled, not complete dataset/target certification.**
   Local credentials load safely and both IEX/historical SIP work on the audited
   dates. Paid-plan identity, recent/live SIP rights, monthly coverage, corporate
   actions, rate ceilings, retention/training/sharing rights, and the actual
   regular-session opening/closing convention remain open. The manifests mark
   daily bars `PROVIDER_DAILY_NOT_CERTIFIED_REGULAR_SESSION`. Do not train
   regular-session labels from them without verifying the convention or an
   explicitly approved change in target. Article bodies were not requested.
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

GitHub setup and the M02 technical audit are complete. Next is M03 (a complete
labeled historical dataset), subject to the open gates below. User
authorization to commit/push at each completed
milestone is recorded in root `AGENTS.md`. Update this checkpoint and
`MILESTONES.md`, verify acceptance criteria, scan staged content for secrets,
push normally, and only then close the matching GitHub milestone. The
Windows/Python 3.13 GitHub Actions workflow passed for the initial commit;
verify subsequent commits independently rather than assuming they are green.

Read [M02 evidence](M02_SOURCE_AUDIT_2026-10-10.md) first. Before materializing
training labels, verify the regular-session price convention and account data
rights. Historical SIP is a preferred candidate, not a silently frozen choice.
Define the label/threshold/split contract, then audit month-scale coverage and
build resumable ingestion, separate persisted outcomes, and immutable dataset
rows with lineage and missingness/leakage reports. Keep healthy no-news rows
and approximate provenance. Do not inspect a final test while tuning settings.
Keep Agent-Reach captures out of the model until independently approved.
