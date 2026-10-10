# Source-audit runbook

Status on 2026-10-10: command implemented and fixture-tested. **No live Alpaca
source audit has run**, because market-data credentials are not available in
this environment. A plan-mode report is evidence of the intended audit cases,
not evidence of provider access or data quality.

## Purpose and boundaries

This is the Stage 1 source-feasibility gate from [BUILD_ORDER](BUILD_ORDER.md).
It asks whether our account can provide usable Benzinga-supplied Alpaca news
and prior daily bars for AAPL, NVDA, AMZN, JPM, XOM, WMT, and SPY. It uses the
same Trailforge-supervised extraction code as the application. It does not
train a model, prove historical article versions, verify source licensing, or
authorize a paper action.

For each trading-session case, the audit also runs a **separate Trailforge
outcome-source probe** for the seven same-day daily bars. It checks that each
symbol has one structurally valid daily bar after the session. This does **not**
prove that the IEX or SIP bar's open/close equals an executable or official
regular-session opening/closing price; that target convention needs separate
validation. Those bars are saved as
audit-only raw evidence and are never added to the pre-open prediction
snapshots. A missing outcome bar blocks the source gate rather than inventing
a training label.

`marketpulse audit` takes up to 12 explicit `--case type:YYYY-MM-DD` values.
Types are `ordinary`, `earnings`, `early_close`, `correction`, and `holiday`.
The `holiday` case is calendar-only. An `earnings` label is a human hypothesis;
a keyword count is only a lead. An article whose `updated_at` is later than
`created_at` is only a correction candidate: it does not reconstruct the
original 09:00 text. Choose and independently verify representative earnings
and corrected-story dates before treating those case labels as evidence.

## Run it

In PowerShell from `F:\MarketPulse`, plan without network or credentials:

```powershell
.\.venv\Scripts\marketpulse audit --plan `
  --case ordinary:2026-10-09 `
  --case early_close:2025-11-28 `
  --case holiday:2025-11-27
```

The report will explicitly mark missing earnings and correction cases. Add
those only after selecting verified dates. For a live audit, set the Alpaca
market-data keys locally and omit `--plan`:

```powershell
$env:APCA_API_KEY_ID = "your_market_data_key"
$env:APCA_API_SECRET_KEY = "your_market_data_secret"
.\.venv\Scripts\marketpulse audit `
  --case ordinary:2026-10-09 `
  --case early_close:2025-11-28 `
  --case holiday:2025-11-27 `
  --feed iex
```

Do not paste credentials into chat or put them in the command line or source
files. The optional `--include-content` asks Alpaca for article bodies and
stores the raw response; check the applicable license/retention rights first.
Default is headline/metadata only. `--feed sip` is a separate entitlement and
must be audited independently; do not merge SIP and IEX results silently.

Each invocation writes uniquely named dated JSON and Markdown reports under
`data/audits/` by default. The JSON includes per-symbol prior-bar counts,
first/latest bar dates, previous-session coverage, article counts, raw page
hashes, source request IDs, same-day outcome-bar coverage, Trailforge task
state and verifier evidence. It
does not copy article bodies or credentials into the report. The raw captures,
application SQLite, and Trailforge authority remain under `data/` and are
excluded from Git.

## How to read the status

- `NOT_RUN`: no provider request was made (plan mode).
- `BLOCKED`: a provider, integrity, calendar-label, or Trailforge job failed;
  accepted snapshots are not assumed for that case.
- `TECHNICAL_REVIEW_REQUIRED`: all requested extraction/calendar cases
  completed, but licensing, historical point-in-time limitations, event-label
  verification, and any missing case categories remain open. This is **not** a
  green light to make model-quality or trading claims.

Before closing this gate, document real response schemas, account/feed rights,
date-by-date coverage, content availability if permitted, source request IDs,
ordinary and early-close behavior, candidate revisions, and any coverage gaps.
Fix defects with regression tests. Then decide whether historical data is
adequate for the proposed 09:00 open-to-close prediction target.
