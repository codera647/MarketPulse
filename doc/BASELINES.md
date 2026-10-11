# M04 baseline software and reviewed-data training

Status on 2026-10-10: implemented and exercised on generated synthetic data.
Real-data collection/training is still held by the user's explicit rights
instruction. M03 and the empirical M04 milestone remain incomplete. A fitted
fixture artifact is not a market model, calibrated forecast or paper policy.

The default demo remains fixture-only. A separate reviewed-data entry point
now uses the same fitting/scoring code without relabeling real feature tiers.
It requires an approved private rights contract and exact dataset promotion;
its only execution evidence is synthetic wire tests. See [PIPELINE](PIPELINE.md).

## What this step establishes

The majority baseline always chooses the most frequent training label; ties
prefer `NO_MATERIAL_MOVE`, then `DOWN`, then `UP`. Its probability vector is
the training class frequency. The price baseline is pooled three-class
logistic regression on the shared feature builder's eleven prior company/SPY
price/volume features. It does not use ticker identity, news, same-day prices,
outcomes or labels as input features.

The fitted pipeline is median imputation, standard scaling and logistic
regression. All fitting uses training rows only. Hyperparameters are fixed:
`C=1`, `lbfgs`, `max_iter=2000`, `tol=1e-6`, random seed 17, no class weighting.
There is no validation tuning, calibration or final-test evaluation here.
Every class needs at least two training examples; an all-missing training
feature or convergence warning blocks completion. This follows
[scikit-learn's leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html)
and its [logistic regression contract](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html).

The fitted state is stored as content-addressed JSON, not pickle/joblib:
training row references/counts, schema/class/feature ordering, settings and
library version, imputation medians, scaler means/scales, coefficients and
intercepts. One shared `predict_baselines` function scores saved JSON for
validation and later fixture replay. Fitting checks its probabilities against
the original sklearn pipeline to `1e-12` tolerance. Scoring rejects mismatched
schemas, future/missing prior-session coverage, nonfinite values/parameters,
wrong class order or dimensions, and attempts to authorize paper action.

Probabilities are explicitly **uncalibrated**. `paper_action_authorized` is
always false. Fixture models reject historical/recorded feature tiers. The
reviewed-data path produces `HISTORICAL_APPROXIMATE` models and scores only
matching historical features. `RECORDED_STRICT` serving remains a later stage.

## Fixture and chronological split

`baseline_fixtures.py` generates synthetic prior prices/volumes, calling the
same pure `build_features` used by saved provider snapshots. Its relationship
between prior price trends and labels is deliberately manufactured to exercise
the learner. It says nothing about whether real news or prices predict returns.
It does not read `.env`, existing provider databases or make network requests.

| Partition | Synthetic dates | Rows |
| --- | --- | ---: |
| Train | 2024-07-01 through 2024-07-19 | 84 |
| Validation | 2024-07-23 through 2024-07-26 | 24 |
| Locked test | 2024-07-30 through 2024-08-02 | 24 |

The first exchange session of validation and test is omitted. All six stocks
on each date remain together. The reader checks complete company/date groups,
disjoint chronological dates and at least one embargoed exchange session.
It reads train and validation row artifacts only. Test roster references may
be bound into the dataset identity, but test row bodies/labels are never opened
by fitting, evaluation or verification. Test-read refusal is regression-tested.
The real July-2025–September-2026 experiment contract is unchanged.

## Trailforge and artifacts

```text
Generated fixture catalog
  -> fit [MODEL, CANDIDATE_WRITE]: immutable model hash
  -> evaluate [TOOL, CANDIDATE_WRITE]: immutable validation report hash
  -> verify [VERIFY, PURE]: refit from training references + recompute report
  -> application result only after verified COMPLETED
```

Validation compares both baselines on exactly the same rows. The report
contains class/sample counts, accuracy, macro-F1, log loss, multiclass Brier
score (`mean(sum((p-y)^2))`, not divided by the class count), confusion matrices
in `DOWN/NO_MATERIAL_MOVE/UP` order, and per-ticker rows/correct counts.
It is prominently `FIXTURE_SOFTWARE_CHECK_ONLY`. No final-test metrics exist.

Under the chosen private data directory:

- `baseline-artifacts/`: immutable catalogs, rows, JSON models and reports.
- `baseline-trailforge.sqlite3`: the separate harness authority.
- `baseline-jobs.sqlite3`: application mapping from job key to known run ID.
- `baseline-results/`: accepted immutable result references and VERIFY receipt.

The job binds dataset hash, feature/schema settings and sklearn/numpy versions.
Identical known-run retries reuse the completed run and revalidate stored
model/report data. Failed candidates cannot publish an accepted result;
uncertain tasks remain held with no blind retry. Candidate artifacts can remain
after a failed check. The existing harness-start/application-run-ID crash gap
still exists; this is not an exactly-once/recovery certification.

## Run safely now

```powershell
.\.venv\Scripts\marketpulse baseline-demo --data-dir data/baseline-fixture
```

`--seed` selects a bounded fixture-generation seed (default 42), not a model
selection experiment. The command returns artifact hashes, row counts and
the harness receipt. It does not print headline text, provider data or claim
market accuracy. Separate `baseline-train` now accepts explicitly promoted
historical datasets; no real-data fitting has been run. See [PIPELINE](PIPELINE.md).

Local seed-42 smoke evidence:

- Catalog: `84126e6af63839da3e76e76947b1bd6c1b35ae978b9c7ab05c59daefffaa9982`.
- Model: `9976d16d50919a5b1dede05b5082217914c2f155e27461ec2603350d658535df`.
- Validation report: `53550f6639ca52b417fc604077150bb4516b718a0c54103d15e8cd30b80c48d8`.
- Trailforge run: `97dd61a8-9a2c-4abd-9c4d-84831d5a494b`, verified completion.

Artifacts stay under ignored `data/`, not Git. Exact fitted numeric hashes are
local evidence; numerical library/platform changes can produce different
artifacts and must create new version-bound experiment evidence.

Verification on 2026-10-10: full regression suite passed all 118 tests in
103.17 seconds; lint and dependency checks passed. The 30 baseline tests
include training-only imputation/scaling, JSON/sklearn probability parity,
fixed class order and hand-checked majority metrics, validation-only changes
leaving fitted state unchanged, final-test read refusal, nonfinite/schema
failures, chronological date grouping, altered-candidate VERIFY failure,
UNKNOWN/no silent retry, idempotence, and credential-free CLI execution.

## Next empirical gate

First complete rights confirmation and the M03 dataset/coverage/corporate-
action/event review. Promotion records and the reviewed-data loader are now
implemented in `research.py`. The loader, learner, evaluation, verifier and
cached-run revalidation exclude final-test row bodies and outcome pages.
Real results preserve `HISTORICAL_APPROXIMATE`; fixture catalogs/models remain
separate and reject real inputs. Matched real
chronological validation, code push and acceptance review precede closing M04.
News models, calibration, final-test release, paper policy and UI remain later
stages. Do not substitute synthetic scores for any of that evidence.
