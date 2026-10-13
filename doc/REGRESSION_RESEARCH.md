# Continuous-return regression research — 2026-10-13

Status: COMPLETED/PASS at 08:34:41 Pakistan on 2026-10-13.
All 56 fold/final fits and saved input-only inference are verified. Source
recovery passed independently; the original expired attempt stays UNKNOWN.
Specification D27 in [DECISION](DECISION.md) was recorded before fitting.
No regression accuracy improvement is claimed. This is a new named retrospective
development experiment, not a fresh blind test or trading approval.

## Measured results

Release: `5cf4aa68f67448cd38db28c76b1e8a890fc15bd0244af63f4a5c6b1c9ce6d0ab`.
Report: `63fef64ae75b1059c4cb2059bbd1a2fcaf732ba2d5bdc9a34b5a3f3b1be868ef`.
Native release run: `1a306532-8429-4cf9-bcac-2fc35e70ee33`.
Receipt: `sha256:1bd1f3c8e30d8545f6423b3ee4a99e31783f370aa55906c92afbb2b9333c728f`.

744 selection examples: DOWN 128, neutral 487, UP 129.
Errors are return percentage points; lower is better.

| Candidate | MAE | RMSE | R-squared | Derived accuracy | Balanced accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| Linear | .964906 | 1.300021 | -.052124 | 65.0538% | 33.5099% |
| Ridge | .960103 | 1.295505 | -.044827 | 65.0538% | 33.5099% |
| Random Forest | .930577 | 1.268477 | -.001684 | 65.4570% | 33.3333% |
| Histogram boosting | .942145 | 1.284608 | -.027324 | 65.3226% | 33.2649% |
| CatBoost | .932099 | 1.273611 | -.009810 | 65.4570% | 33.3333% |
| Zero return | .929370 | 1.267410 | -.000000349 | 65.4570% | 33.3333% |
| Training-mean return | .928704 | 1.268080 | -.001059 | 65.4570% | 33.3333% |

Selected candidate is **zero_return**, NOT a trained estimator. No trained
model beats its selection RMSE. Random Forest and CatBoost classify every
prediction as neutral. Linear/Ridge each predict 4 DOWN/736 neutral/4 UP, with
DOWN recall .78125% and UP recall .77519%; histogram predicts 2 DOWN/742 neutral/
0 UP and detects no actual UP/DOWN examples. The roughly 65% accuracy is driven
by the neutral majority, not effective move prediction. All five models remain saved.

Within-family fold choices: Ridge alpha 100; Random Forest 150 trees/depth 6/
minimum leaf 20; histogram 200 iterations/15 leaves/L2 10; CatBoost 200 iterations/
depth 4/L2 10. Plain Linear Regression has no searched regularizer.
Previous guarded full suite passed 240 tests in 649.56s (two SQLite resource
warnings); focused source-recovery/model checks passed 34 tests in 66.80s.
New boosting comparison is separate: [BOOSTING_RESEARCH](BOOSTING_RESEARCH.md).

## Reused data and target

Use the verified six-company 2018–2025 v2 roster, 11,952 rows. Source release:
`51bce00fd0ce0ea0146877884c36eaa09055d23eff6bc337d453f065579542d7`.
Source dataset: `a9af101ab249424e0f92cdf6629a5cd4cea5c16d89fc395e6fe1a399b98a2805`.
V2 completed at 00:35:55 Pakistan on October 13 with 59 verified fit tasks;
its selected classifier is CatBoost, validation accuracy 53.63%, macro-F1 .3843.
Its neutral baseline accuracy is 65.46%; this is not a positive overall-accuracy result.

Regressors reuse the same 48 enriched numeric features, available by 09:00 New
York: price history, company indicators, sector proxies, pre-market coverage,
news sentiment/events/relevance/missingness. No new data capture, FinBERT
inference or TF-IDF addition occurs in this stage. Source availability remains
HISTORICAL_APPROXIMATE, with incomplete PIT/news revision, corporate-action and
FinBERT corpus-date audits. Private non-commercial restrictions remain.

Continuous target is `(last regular-minute close / first regular-minute open) - 1`.
It is taken from immutable audited base rows after checking content identity,
v2/base native authority, feature chunk receipts, company/date/role/cutoff and
agreement with the original strict +/-1% label. It is not reconstructed from
the three classification names. No clipping, fabricated targets or resampling.
Targets live in separate training rosters; inference opens label-free inputs only.

## Frozen experiment

Five families: LinearRegression, Ridge, RandomForestRegressor,
HistGradientBoostingRegressor and CatBoostRegressor. See D27 for the 17 bounded
settings. Each setting has three expanding folds, evaluated in 2022/2023/2024,
with one whole NYSE date embargoed at each boundary. All six companies share
date groups. Fold imputation/scaling/coefficients/trees use training rows only.
Histogram boosting has `early_stopping=False`; no random internal validation.
Fixed seed 17 and CPU thread limit two; unknown native attempts are never reset.

Choose a configuration within each family by mean fold RMSE, then MAE, then
configuration digest. Fit five final models on 10,458 training rows only.
Reserve early-2025 744 examples without fitting/calibration use; retain the
existing six-row full-date embargo. Compare on the same later-2025 744 inputs
as the classification experiment. Include zero-return and training-mean-return
baselines, and select by RMSE then MAE then name, even if a baseline wins.
This is 51 fold fits + 5 final fits, not an unbounded search.

Report MAE/RMSE (fractions and percentage points), R-squared, and fixed +/-1%
derived-class accuracy, balanced accuracy, macro-F1 and class precision/recall.
Equality at +/-1% remains neutral. Returned numeric forecasts are NOT calibrated
class probabilities. A regressor can predict mostly near zero or have negative
R-squared; neither target magnitude nor profitable performance is guaranteed.
Do not alter the threshold to force more UP/DOWN outputs after viewing results.

## Authority and persistence

Separate data root: `data/regression-20261013`. Source v1/v2 datasets, models and
ledgers remain unchanged. Small digest-bound source, fit/replay and release
tasks use the existing neutral Trailforge runtime, a 300-second maximum lease,
typed verification and explicit owned-run lock. Windows gets a temporary
system-only idle-sleep request; keep AC connected and the lid open. Explicit
Sleep/Modern Standby can interrupt work; no permanent power-plan changes.

The first full-roster task exceeded its lease after about 402 seconds, before
any regressor fit. It saved all 11,952 projected target/input references. The
original run remains held UNKNOWN/EXPIRED_ATTEMPT, never reset/re-executed.
Source authority/catalog reads are now preflight outside bounded attempts;
projection and independent replay use 300-row tasks, then assembly verification.
The explicit `research-regression-reconcile-source` command accepts only a
complete expired candidate, verifies every row against immutable source/base
artifacts and checks every child receipt before registering a positive mapping.
Incomplete/mismatched/live/unstarted recovery is rejected. This is operational
recovery only, with D27's data/features/targets/configurations unchanged.

Linear models, Random Forest and numeric histogram trees are non-executable
JSON, with pinned environment and independent fitted-vs-portable replay checks.
Forest prediction follows sklearn's float32 tree-input convention. Histogram
tree export uses pinned sklearn internals and is covered by replay tests; it
does not support categorical splits. CatBoost native CBM binaries have their
own SHA-256 and are checked before use. No pickle/joblib executable artifact.
All artifacts stay private/ignored; Git gets only code and aggregate documentation.

## Commands

The managed run uses recorded user evidence; do not launch duplicates or change
that evidence while resuming. The build needs no internet or credentials.

```powershell
.venv\Scripts\python.exe -u -m marketpulse.cli research-regression-build `
  --source-v2-dir data/research-v2-20261012 `
  --source-release-hash 51bce00fd0ce0ea0146877884c36eaa09055d23eff6bc337d453f065579542d7 `
  --data-dir data/regression-20261013 `
  --authorization-evidence "Explicit user authorization for separate regression research"
```

Status and managed log:

```powershell
Get-Content -Raw F:\MarketPulse\data\regression-20261013\v2-status.json
Get-Content F:\MarketPulse\data\regression-20261013\regression-r2.stderr.log -Tail 2
```

`TRAINING_REGRESSION` names the family and phase; `COMPLETE` requires a matching
positive release receipt. `STOPPED` is not success and requires inspection.

Explicit complete-candidate recovery (operator evidence required; do not run
concurrently with an active build):

```powershell
.venv\Scripts\python.exe -m marketpulse.cli research-regression-reconcile-source `
  --source-v2-dir data/research-v2-20261012 `
  --data-dir data/regression-20261013 `
  --parent-job-key <expired-source-key> `
  --rows-hash <independently-inspected-complete-roster-hash> `
  --evidence "<bounded dated complete-candidate reconciliation evidence>"
```

```powershell
.venv\Scripts\python.exe -m marketpulse.cli research-regression-predict `
  --source-v2-dir data/research-v2-20261012 `
  --data-dir data/regression-20261013 `
  --release-hash <verified-regression-release> `
  --input-hash <saved-v2-label-free-input>
```

This scores saved replay inputs, not a live feature service. Model comparison
and new forward testing remain research stages. No orders, paper action, live
dashboard integration, human dataset approval or deployment promotion is implied.
