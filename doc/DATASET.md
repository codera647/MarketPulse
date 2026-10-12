# M03 historical dataset pipeline

2026-10-12 update: the user has confirmed data permissions and requested real
training and a larger historical dataset. Authorized collection now uses a
private 2018–September 2026 contract and a user-approved whole-date boundary-gap
quarantine policy. See [REAL_DATA_RUN](REAL_DATA_RUN.md) for current scope and
evidence. The older plan/hold below is retained as historical context; it is not
the active rights state. A complete real dataset has not yet been achieved.

Status on 2026-10-10: software implemented; live bulk collection and model
training remain gated. The user approved the research dates and fixed 1%
threshold, and explicitly asked to keep bulk collection gated because data
rights have not been confirmed. M03 is not complete and must not be closed.

[PIPELINE](PIPELINE.md) now connects bounded multi-batch collection/resume,
offline report regeneration, exact report-bound human promotion and real-data
baseline software. The default contract remains held; complete collection
never automatically promotes or trains.

## Agreed research plan

Six targets: AAPL, NVDA, AMZN, JPM, XOM and WMT. SPY is context only. Predict
at 09:00 America/New_York. Preserve the previous-close-to-cutoff news window,
21 consecutive earlier price sessions, and `HISTORICAL_APPROXIMATE` provenance.

| Split | Inclusive dates | Usable sessions | Company rows |
| --- | --- | ---: | ---: |
| Training | 2025-07-01 to 2025-12-31 | 128 | 768 |
| Validation | 2026-01-01 to 2026-03-31 | 60 | 360 |
| Final test | 2026-04-01 to 2026-09-30 | 125 | 750 |
| Total | | 313 | 1,878 |

The first exchange session of validation and test is embargoed; all six
companies on a date stay together. The one-session embargo is a conservative
technical default, not proof that related events cannot cross a boundary.
The approved threshold is fixed before labels are collected: return greater
than +0.01 is `UP`, less than -0.01 is `DOWN`, and both exact boundaries belong
to `NO_MATERIAL_MOVE`. Do not optimize this threshold on the final test.

Historical SIP and split-adjusted price inputs remain the technical research
choice. Full article bodies and Agent-Reach captures are excluded. Account
rights, corporate-action history, and monthly coverage still need review.

## Precise outcome convention

`regular-minute-proxy/1` requests only NYSE-calendar regular-session `1Min`
bars: timestamps from opening time through closing time minus one minute,
inclusive. Opening price is the first minute's `o`; closing price is the last
regular minute's `c`. Early closes and UTC/DST follow the calendar. The query
pins the symbol-mapping `asof` to the session date. Return is `close/open - 1`
using Decimal arithmetic.

These are **provider eligible-trade minute-bar proxies, not official auction
prices, consolidated official closing prices, or guaranteed executable fills**.
Trades at exactly 16:00 (or an early close) fall outside the final regular
minute. Daily bars use a different aggregation interval and trade-condition
rules, so this path never substitutes the earlier daily outcome audit.
[Alpaca aggregation rules](https://docs.alpaca.markets/us/docs/market-data-faq),
[historical bars contract](https://docs.alpaca.markets/us/reference/stockbars).

A bounded Trailforge Goal fetches at most four pages, then a separate typed
verifier rereads immutable raw pages. Checks include request/source identity,
pagination tokens, finite valid OHLCV, post-close receipt, unique minute grid,
all seven symbols and exact first/last-minute presence. Missing boundary bars
block the entire outcome job; there is no fallback to a nearby minute.
Missing interior bars are reported for review, not silently fabricated.
Capture requires the session to have closed more than 15 minutes earlier.

`session_outcomes` stores accepted manifests in an application transaction;
outcomes never enter `price_bars`, snapshots, or the shared feature builder.
Cached outcomes are rechecked against raw artifacts, ledger hashes, the
actual passing harness run and receipt before use.

## Immutable artifacts and resumable batches

The JSON contract in [dataset_contract.proposed.json](dataset_contract.proposed.json)
records the approved dates/threshold but intentionally has
`rights_confirmed: false`. An approved private copy must also record a short,
non-secret rights-review reference. These declarations record human review;
the code cannot independently certify the account's legal permissions.

Before any provider call, the batch checks approvals, valid date ranges,
completed sessions and a maximum of 31 eligible sessions per invocation
(also a 60-calendar-day bound). It saves the frozen contract, feature/source
versions, calendar package version, exact date-to-split map, cutoff and data
origin under `data/<run>/contracts/<prefix>/<hash>.json`.

Each session reuses verified extraction and outcome jobs. Every company row
contains its feature hash, snapshot ID, source job, eligible headline/summary
versions, raw references, separate outcome identity and label. Rows are
content-addressed JSON under `datasets/` (the architecture's immutable-file
equivalent to Parquet), indexed by `(contract_hash, session, symbol)` in SQLite.
Identical retries converge; conflicting rows are rejected, never overwritten.
Changing the contract or installed calendar/feature/source version creates a
different identity. Files may be orphaned by a crash before index insertion;
the same known sources can rematerialize them. This is not exactly-once network
execution, and the existing harness-start/run-ID orphan window remains open.

Reports rehydrate rows from verified lineage, list hashes, counts by date and
split/ticker, healthy no-news counts, feature nulls, interior outcome gaps,
missing rows, and cross-split provider-ID or normalized-headline duplicates.
Exact duplicates block promotion; semantic event grouping remains unverified.
No test-label statistics are emitted. Test rows contain outcomes for later
evaluation, but must not be inspected or used for tuning; this local store is
not an access-control mechanism.

Even complete rows produce `COMPLETE_RESEARCH_REVIEW_REQUIRED` with
`ready_for_training: false`. Corporate-action and event/point-in-time review,
rights confirmation, and explicit human dataset promotion precede M04.
Uncertain source work stops the batch for review; it does not sweep onward or
blindly retry held work. Re-running a batch reuses known completed source jobs.

## Commands

This is safe now and needs no credentials/network:

```powershell
.\.venv\Scripts\marketpulse dataset-plan --contract doc/dataset_contract.proposed.json
```

After rights confirmation and a private approved contract (not yet authorized):

```powershell
.\.venv\Scripts\marketpulse dataset-batch `
  --contract data/approved-contract.json `
  --start 2025-07-01 --end 2025-07-31 --data-dir data/m03
```

The result identifies immutable contract/report hashes. Later batches use the
same contract and data directory. Do not copy provider-bearing artifacts into
Git or public exports. The ordinary `backfill` command remains a lower-level
input extractor, not approval to bypass the user's bulk-collection hold.

## Live technical evidence only

Two isolated outcome probes used SIP/split under Trailforge on 2026-10-10;
neither created a training row or fetched new news. Local evidence is in
`data/m03-probe/marketpulse.sqlite3`, `trailforge.sqlite3` and `raw/`.

- 2025-11-28 early close: 7/7 symbols, 210/210 minutes each, zero gaps;
  job `72f9c52fbb434ba9d1fe3b1acb8c9f67d04728b20cde35dfe047de218a91eec8`.
- 2026-10-09 ordinary session (outside the frozen final-test period): 7/7
  symbols, 390/390 minutes each, zero gaps;
  job `5321d36f138dade3b5ad530dd4e930a8bd30bd433fe984ca7b9c78a2bcc18392`.
  These samples do not establish month-scale coverage.

Synthetic tests cover early closes, exact thresholds, invalid OHLCV, missing
boundaries, timestamps, incomplete pagination, held work, idempotence,
separate ledgers, no-news rows, embargo/date grouping, contract gates,
cross-split duplicates, and corrupt/missing lineage. These verify software,
not forecasting accuracy.

Verification: `ruff check src tests` passed; `pytest -q` passed all 88 tests
in 60.35 seconds; `pip check` found no broken requirements. Both cached live
outcome jobs passed the updated raw-ledger/harness-receipt revalidation.
