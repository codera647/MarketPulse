# Price expert: first specialist experiment

## Frozen plan (2026-10-13, before real fitting)

User requested starting only the price expert in the background, reporting an
estimated completion time, then stopping active work until instructed again.
No news expert, market expert, stacking training, collection or promotion is
authorized by this step. Trailforge remains the execution/verification harness.

Reuse the verified v2 release
`51bce00fd0ce0ea0146877884c36eaa09055d23eff6bc337d453f065579542d7`
and the positively verified fresh bounded-source assembly in
`data/boosting-20261013`, roster
`87d407b1c3f0fdfd797fca13876b8aeeeb6d1f4a5b993b9e60e84dbbd2dbcdc8`.
Validate its native source/chunk receipts, immutable roster, source release,
audited targets, roles and complete six-company date groups. This is reuse of
positive source authority, not acceptance of the earlier expired UNKNOWN task.
Read existing inputs; do not read `.env`, download data, run FinBERT or alter
older artifacts. New private root: `data/price-expert-20261013`.

## Inputs and target

Schema `price-expert-classification/1`; same six companies
AAPL, AMZN, JPM, NVDA, WMT, XOM. Twenty explicitly whitelisted numeric inputs:

- Seven company-only lagged return, volatility and volume features.
- Six company-identity indicators, fixed from the agreed roster.
- Seven company pre-market return, volume, count, age, coverage/missing features.

No SPY, sector, news, sentiment, TF-IDF, outcomes, future bars or new indicators.
All selected inputs are from the existing 09:00 America/New_York-cutoff payloads.
Missing values remain missing until training-only median imputation. Logistic
scaling is fitted only on each fit roster. No sampling or threshold change.
Prices retain historical adjustment/corporate-action limitations; this is
HISTORICAL_APPROXIMATE data, not certified point-in-time history.

Target stays first/last regular-minute open-to-close proxy: UP strictly above
+1%, DOWN strictly below -1%, otherwise NO_MATERIAL_MOVE (including boundaries).
These are classifiers with three class probabilities, not earlier regressors.

## Eight settings; 27 bounded fits

- Logistic Regression: C .1/1 crossed with balanced/unweighted classes,
  lbfgs, max_iter 2000, tolerance 1e-6; four settings.
- CatBoostClassifier: depth 4/6, 200 iterations, learning rate .05,
  inverse-frequency class weights; two settings.
- XGBClassifier: depth 3/6, 200 rounds, learning rate .05, multiclass softprob,
  inverse-frequency sample weights, minimum child weight 20, L2 10,
  CPU histogram trees, full row/column sampling; two settings.

Seed 17, two CPU threads. No GPUs or new dependencies. Fixed-seed repeatability
means the pinned host/environment, not a cross-platform bitwise promise.

Three expanding training-only folds evaluate 2022, 2023 and 2024, with a whole
exchange-date embargo. Within each family choose mean macro-F1, then log loss,
then configuration digest. 24 fold fits plus three final fits on 10,458 rows.
Early 2025: 744 calibration rows; one whole-date (six-row) gap; later 2025:
744 selection rows. Calibration uses a frozen five-temperature grid .5/.75/1/1.5/2
on log loss. No evaluation label enters fitting or calibration.

Compare the three finalists with training-frequency majority probabilities.
Select macro-F1, then log loss, then family name; retain the baseline if it wins.
Report overall accuracy, macro-F1, per-class precision/recall, confusion, log
loss, Brier/calibration diagnostics and per-ticker results. This is exposed-date
DEVELOPMENT_NOT_FINAL_TEST; no new final-test claim. Leave 2026 untouched.

Search-fold predictions MUST NOT be used directly as stacking meta-training
data after their settings are selected using all fold outcomes. A later stacking
step requires pre-frozen or nested/earlier-only expert selection and calibration
before generating each chronological meta-training prediction.

## Execution, persistence and handoff

Trailforge verifies source reuse, each fit/saved-model prediction replay and
each reported metric, then the release. Median/scaler/coefficient JSON,
content-hashed CatBoost CBM and XGBoost UBJSON are private; no pickle/joblib.
All probabilities follow DOWN, NO_MATERIAL_MOVE, UP. Saved inference opens only
label-free input payloads. Negative results remain visible. Locks prevent
duplicate owners; completed native tasks resume without refitting. UNKNOWN
tasks are not reset. No broker orders, paper authorization or deployment.

The owned run temporarily requests Windows idle-sleep prevention, without
changing the power plan. Keep AC connected and the lid open; explicit sleep
still interrupts work. Training requires no internet once launched.

Status (PowerShell):

```powershell
Get-Content -Raw F:\MarketPulse\data\price-expert-20261013\v2-status.json |
    ConvertFrom-Json |
    Select-Object stage, family, phase, train_rows, fits_complete, fits_total, pid, updated_at_utc
```

Logs: private `price-r1.stderr.log` / `price-r1.stdout.log` in that directory.
COMPLETE means the pipeline finished; STOPPED means inspect the error type and
private native receipts, not that training continues. Check PID/lock before
any restart. Update CHECKPOINT with launch/test evidence. Do not claim results
until completion, receipts and saved inference are checked on the next turn.
