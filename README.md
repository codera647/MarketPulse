# MarketPulse

This repository currently implements **data extraction, source audit, and
read-only label/feature previews** for AAPL, NVDA, AMZN, JPM, XOM, WMT, and
benchmark SPY. It does not train a model, produce predictions, or place
trades. Live IEX and historical SIP access have been sampled under Trailforge;
see the [M02 audit](doc/M02_SOURCE_AUDIT_2026-10-10.md) for coverage and open
data-rights and label-convention gates. The product plan is in [`doc/`](doc/README.md).
The [delivery milestones](doc/MILESTONES.md) track completed stages and
the user's requested GitHub commit/push checkpoints.

It also provides a read-only, explicitly provisional
[`label-preview`](doc/LABELS.md) command for an already audited outcome job.
That preview is not a training dataset or an empirical result.
The shared [`feature-preview`](doc/FEATURES.md) computes only pre-open
features from a saved snapshot; it does not read same-day outcomes.

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
