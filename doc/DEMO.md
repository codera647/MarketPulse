# MarketPulse local demonstration

Availability: **FIXTURE only**. This is a software demonstration, not a fitted
market model, investment advice, a profitable backtest or a broker paper account.
The synthetic news/returns contain deliberately manufactured relationships.
The agreed real-data rights hold remains in force.

## Start

```powershell
cd F:\MarketPulse
.\.venv\Scripts\marketpulse demo-init --data-dir data/demo
.\.venv\Scripts\marketpulse serve --data-dir data/demo
```

In another terminal:

```powershell
cd F:\MarketPulse
.\.venv\Scripts\marketpulse dashboard --mode fixture --data-dir data/demo
```

Dashboard: http://127.0.0.1:8501. API: http://127.0.0.1:8000/docs.
Both bind only loopback. Ctrl+C stops the foreground command. Initial setup
and cold calendar/imports take longer than warm replay. `demo-init` needs no
credentials, paid calls, source downloads or account changes.

The current environment project is `F:\MarketPulse`, not the nonexistent
`F:\US_Stock_Prediction`. Do not create a competing project in the latter path.

## What happens

1. Shared feature code constructs manufactured prior-company/SPY bars and news.
2. On training dates only: fit majority, price logistic regression, TF-IDF text
   logistic regression and combined price/text logistic regression. Median,
   scale and vocabulary are fitted on training only. Save JSON, not pickle.
3. Fit independent temperature calibrators on the first two validation dates.
4. Select a fixture-only UP confidence threshold on two different validation
   dates. Disable simulated longs if no candidate passes the fixture condition.
5. Trailforge verifies fit/calibration/policy by deterministic replay. Only
   after these choices freeze are synthetic test rows opened for comparison.
6. Save separate input-only and outcome-only artifacts and an immutable release.
7. A forecast uses its saved input, frozen model/calibrator/policy and typed
   Trailforge score/VERIFY tasks. It does not read its future outcome.
8. Persist one immutable decision with request identity, class probabilities,
   action/reasons, feature/model/policy hashes and harness receipt. The same
   request returns the saved decision. At most two distinct simulated positions
   per date, with no repeated company position across release variants.
9. Reveal outcome is a separate operation after close. It links the outcome to
   the original release/decision and never changes the prediction.

Synthetic dates are July/August **2024**, intentionally different from the
agreed 2025–2026 real experiment. There are 84 train, 12 calibration, 12 policy
and 24 test rows. The 1% labels retain strict greater/less comparisons and
neutral exact boundaries. The synthetic test contains a manufactured shock.

## Walkthrough

| Selection | Visible behavior |
| --- | --- |
| AMZN / 2024-07-30 / NONE | UP and fixture PAPER_LONG; reveal manufactured UP |
| NVDA / 2024-07-30 / NONE | Neutral forecast, ABSTAIN |
| AAPL / 2024-08-02 / NONE | DOWN forecast; reveal manufactured UP, a deliberate miss |
| Any ticker / STALE | BLOCKED, STALE_DATA |
| Any ticker / MISSING_NEWS | BLOCKED, NEWS_FEED_UNAVAILABLE; not healthy empty news |
| Any ticker / EXPIRED | BLOCKED, SIGNAL_EXPIRED, explicitly simulated expiry |
| Any ticker / LOW_CONFIDENCE | Equal probabilities, ABSTAIN |
| Any ticker / TIMEOUT | Trailforge hold; no accepted decision or position; repeats reuse known run |

These failure modes are injected fixtures, not claims of observed provider
failures. Historic replay runs at its simulated cutoff. It is not a production
clock scheduler, and injected EXPIRED does not prove live wall-clock expiry.

The audit expander shows literal headline text, shared feature values, hashes,
availability and typed verification receipt. No headline HTML/scripts are
executed. Changing selectors clears the previous outcome in the UI. Evaluation
shows matched accuracy, macro-F1, log loss, multiclass Brier, confusion counts,
ECE bins and 100 date-bootstrap accuracy intervals for manufactured rows only.
Intervals from two/four synthetic dates have no financial evidentiary value.

## HTTP and CLI

POST `/predict` takes exactly `symbol`, ISO `session` and optional `fault`.
Example body: `{"symbol":"AMZN","session":"2024-07-30","fault":"NONE"}`.
Successful decisions return HTTP 200; held tasks return 202. Invalid typed
fields return 422, out-of-catalog requests 409, absent decisions 404, unready
artifacts 503. Requests larger than 16 KiB and non-loopback peers are rejected.
Do not put this local demo behind a public reverse proxy; it has no user auth.

Endpoints: `/health/live`, `/health/ready`, `/catalog`, `/predict`,
`/decisions/{id}`, POST `/decisions/{id}/reveal`, `/evaluation`, `/operations`,
POST `/reconcile`. There is no order endpoint or provider credentials endpoint.

```powershell
.\.venv\Scripts\marketpulse demo-forecast --symbol AMZN --session 2024-07-30
.\.venv\Scripts\marketpulse demo-forecast --symbol JPM --session 2024-07-31 --fault TIMEOUT
.\.venv\Scripts\marketpulse demo-reconcile
.\.venv\Scripts\marketpulse demo-ops
.\.venv\Scripts\marketpulse demo-evaluation
```

Operation metrics report saved action/run counts and measured product-write
latencies (p50/p95). Cached requests return the original latency; these are not
load-tested SLOs. No cost/accuracy guarantees are implied. Model training and
replay are local CPU; installation downloads dependencies once.

## Backup, recovery, rollback

Stop API/UI and all other demo writers before backup: locks cover one process,
not a distributed cross-database transaction. Use a **new** destination outside
the source tree. Existing destinations are refused, never deleted/overwritten.

```powershell
.\.venv\Scripts\marketpulse demo-backup --data-dir data/demo --destination data/demo-backup-01
# Copy the printed manifest_hash to the following command:
.\.venv\Scripts\marketpulse demo-restore --backup-dir data/demo-backup-01 --destination data/demo-restored-01 --manifest-hash <hash>
```

Only allowlisted fixture JSON stores and SQLite backup snapshots are copied;
`.env`, credentials, provider captures and logs are excluded. Restore verifies
file hashes before copying, validates readiness/DB integrity and existing
decision/outcome artifacts. Point serve/dashboard at the restored directory to
roll back. Keep the original directory intact. No deletion is performed.

`demo-reconcile` repairs known verified runs that lack product decisions.
Held/UNKNOWN work is not automatically converted to success or blindly retried.
A crash between harness start and saving run ID can still leave an orphan and
needs manual evidence inspection. A product-write rollback can leave an unused
immutable JSON candidate; it is not an accepted position. Do not erase harness
databases to bypass budgets, holds or uncertainty.

## Real research is separate

Use [PIPELINE](PIPELINE.md) for the gated provider path. It implements resumable
collection, separate minute outcomes, quality reports, explicit human promotion
and majority/price validation. The committed contract remains rights-unconfirmed.
The fixture comparison service rejects real-model tiers. Real news-model
training/promotion and a real sealed-test release need a separately reviewed
extension after M03/M04 evidence; the fixture artifacts are not substitutes.
