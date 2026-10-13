# Fixed-seed boosting research — 2026-10-13

Status: COMPLETED/PASS at 09:05:07 Pakistan on 2026-10-13.
Managed real job started 08:53:22 Pakistan, launcher 14068/owner 10564.
41 focused synthetic checks passed in 56.42s; lint and dependencies pass.
All 39 fold/final fit receipts and saved input-only inference are verified.
The guarded full software suite passed 247 tests in 516.36s. It reported 179
warnings, including SQLite connection resource warnings; cleanup remains.
Build binding: `3a67964ad2d018e78e8433fee05c5e0e11cfb7c6de059a89879b6822db6a5252`.
D28 records the frozen design
before model fitting. XGBoost, AdaBoost.R2 and LightGBM are regressors here.
Their numeric forecasts also receive the unchanged strict +/-1% movement labels.
No predictive improvement, new final test, paper permission or promotion claimed.

## Measured results and artifacts

Release: `7764534d2afe86583f17f324224ac55988dfbe98c3a799ec3a39f7f627988376`.
Report: `1b1deb739ba76de4757c8d6b75b4ff5b6ede56e9be83feacaf7a20de0dc27dc1`.
Native release run: `b57b6b6e-0779-4512-91f6-036afb353716`.
Receipt: `sha256:341ffb80945c9567376ad791ed3b9166917a848a5b57a9239bb94abf7809bc48`.
The report's selection input and row hashes exactly match D27's prior report;
10,458 training / 744 selection / 744 unused reserved examples.

| Candidate | MAE (pp) | RMSE (pp) | R-squared | Derived accuracy | Balanced accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| XGBoost | .938294 | 1.278242 | -.017167 | 65.4570% | 33.3333% |
| LightGBM | .938670 | 1.281219 | -.021911 | 65.3226% | 33.2649% |
| AdaBoost | .930064 | 1.269392 | -.003130 | 65.4570% | 33.3333% |
| Zero return | .929370 | 1.267410 | -.000000349 | 65.4570% | 33.3333% |
| Training-mean return | .928704 | 1.268080 | -.001059 | 65.4570% | 33.3333% |

Selected **zero_return baseline** on RMSE, not a trained model. No model improves
on its return error. XGBoost/AdaBoost derived predictions are all 744 neutral;
LightGBM predicts 743 neutral and one DOWN (that example was actually neutral).
UP and DOWN recall are **zero for all three**. Overall accuracy comes from the
487/744 neutral majority, not movement detection. These are numeric regressors:
near-zero predictions need not be identical to zero to receive a neutral label.
This is retrospective development, not an untouched final test.

Training-fold choices, all final models saved:
- XGBoost: 200 rounds, depth 3, L2 10, model
  `c93c81bcdd6022390181c526c6b8862df9c8bda5729bb3a57201728b53bce573`.
- LightGBM: 200 maximum rounds, 15 leaves, L2 10, model
  `51c727e8078c8f64b2a9553fcee1d363937a076f309b147a9b9f4066c624ac55`.
- AdaBoost: 200 actual weak learners, depth 2, rate .05, no zero-weight degeneracy,
  model `e03b7e165d5def0fee0214c33646cf9faafc1fb0fe10084d185c7d46f9bb7901`.

All 39 fold/final native receipts checked after completion; release receipt
checked against native and application records. Each final model separately
scored three original label-free inputs; selected-release inference also passed.
Prior v1 model/v2 release/model digests remain unchanged. No promotion gate closes.

## Data and experiment

Reuse the same audited v2 source release
`51bce00fd0ce0ea0146877884c36eaa09055d23eff6bc337d453f065579542d7`:
11,952 real six-company examples, 48 numeric features available at 09:00 NY,
immutable first/last regular-minute return proxies. All preprocessing uses
training data only. No collection, new sentiment pass, target clipping, added
features, row sampling or threshold change. PIT/revision/corporate-action and
FinBERT corpus-date audits remain incomplete; HISTORICAL_APPROXIMATE only.
Private non-commercial license/permission limits remain in effect.

D28 freezes four configurations per family. 12 settings x 3 expanding
2022/2023/2024 date-grouped, embargoed folds = 36 fits, followed by three final
fits on 10,458 training examples. Select within family by mean fold RMSE, MAE,
then config digest. Early-2025 744 rows remain reserved/unused; six-row date
embargo remains. Evaluate on the exact same later-2025 744 selection inputs as
previous research. Select by RMSE, then MAE, then name including zero-return
and training-mean-return baselines. Keep all three final models, even if a
baseline wins. Report RMSE/MAE in percentage points, R-squared, derived-class
accuracy, balanced accuracy, macro-F1, confusion matrices and per-class recall.
This is RETROSPECTIVE_DEVELOPMENT_NOT_FINAL_TEST, not unbiased final performance.

## Reproducibility and persistence

Pin XGBoost 3.4.1, LightGBM 4.7.0 and existing sklearn 1.9.1. CPU, seed 17,
maximum two threads; no random early-stopping validation split.
XGBoost uses histogram trees and full sampling. LightGBM uses deterministic
CPU GBDT, forced column-wise building, full sampling and all seeds fixed.
AdaBoost has fixed bootstrap/tree seeds and linear loss; its output is a
weighted median of tree predictions, NOT their weighted average.
If sklearn retains a first weak learner with zero weight, replay preserves its
defined zero-CDF behavior and records the degeneracy; no substitute weights.
Same-host reproducibility is tested, not promised across hardware/OS/builds.

Each fitting task binds the new library versions without changing v2's existing
environment identities. Separate root: `data/boosting-20261013`.
Source validation uses bounded 300-row Trailforge child tasks plus assembly;
each fit has saved-input replay verification. UNKNOWN attempts are never reset.
Owned-run locking and temporary Windows idle-sleep guard remain; keep AC/lid open.

XGBoost models use hash-checked native UBJSON; LightGBM uses hash-checked native
text; AdaBoost uses portable numeric tree/weight JSON. Every fit compares saved
inference to the actual fitted estimator. No pickle/joblib executable models.
All data, models, databases and logs stay private and Git-ignored. Only code,
dependency pins and aggregate evidence go to GitHub.

## Commands

Do not start a duplicate managed job. The existing runner records exact evidence.

```powershell
.venv\Scripts\python.exe -u -m marketpulse.cli research-boosting-build `
  --source-v2-dir data/research-v2-20261012 `
  --source-release-hash 51bce00fd0ce0ea0146877884c36eaa09055d23eff6bc337d453f065579542d7 `
  --data-dir data/boosting-20261013 `
  --authorization-evidence "Explicit user authorization for separate boosting research"
```

Read current status or watch the managed log:

```powershell
Get-Content -Raw F:\MarketPulse\data\boosting-20261013\v2-status.json
Get-Content F:\MarketPulse\data\boosting-20261013\boosting-r1.stderr.log -Tail 10 -Wait
```

Saved label-free inference uses `research-regression-predict` with the boosting
root/release hash, the original source-v2 directory and a saved input hash.
No target records are opened on that path. Outputs are numeric return forecasts,
not calibrated class probabilities. Prior classifiers/regressors stay unchanged.

References: [XGBoost model IO](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html),
[LightGBM determinism](https://lightgbm.readthedocs.io/en/stable/Parameters.html#deterministic),
[AdaBoostRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.AdaBoostRegressor.html).
