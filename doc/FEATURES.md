# Pre-open feature preview

Status on 2026-10-10: the shared numerical feature function and read-only CLI
are fixture-tested. This is **not** a fitted model, training export, or
empirical signal. Live source access and the label/test contract remain gated.

## Input and boundary

`marketpulse feature-preview --snapshot-hash <hash>` reads one saved,
Trailforge-verified extraction snapshot for one of the six companies. It
checks the snapshot's content hash and source manifest, job-linked article
and price versions, and their immutable raw pages. It never opens a same-day
outcome job. SPY is context, not a prediction target.

All price inputs must be from the **21 immediately preceding NYSE sessions**,
with no gap, duplicate date, future date, feed mismatch, or adjustment
mismatch. Twenty-one closes are required to calculate a 20-session return.
The extraction default is now 21 bars. An explicit lower extraction override
can still produce a snapshot that this feature gate blocks; it never shortens
the return window silently. Contiguous-session coverage is checked here even
when the upstream count gate passed.

## Version 1 feature schema

- Company: prior 1-, 5-, and 20-session close-to-close returns; population
  standard deviation of 20 daily returns; mean volume over 5 and 20 prior
  sessions; and their ratio.
- SPY: lagged 1-, 5-, and 20-session returns and 20-return volatility.
- News: count of eligible article versions, available summaries, and
  headline keyword matches for earnings, guidance, acquisition, and
  regulatory topics; minutes since the latest eligible article version.

The keyword matches are deterministic **heuristics**, not verified events or
sentiment predictions. Multiple tags can match one article. A healthy no-news
snapshot has zero counts and `null` for latest-article age; `null` must be
imputed inside a future training fold, never by looking at validation/test
data. Article bodies and Agent-Reach captures do not enter this schema.

The result contains ordered feature names, values, a schema version and
content hash, cutoff, source feed/adjustment, provenance tier, and prior bar
dates. `build_features` is the single pure function intended for offline
training, replay, and later scoring; the CLI calls it after read-only
hydration. No feature rows are persisted yet.

## Next gate

Run the live [source audit](SOURCE_AUDIT.md), validate the regular-session
target and rights, choose a threshold/split protocol, and only then export
training examples. The next software slice can build training/validation
splits and majority/price-only baselines against explicitly labeled fixtures,
without claiming real predictive performance.
