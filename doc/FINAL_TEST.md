# Frozen real-data final evaluation — 2026-10-12

Status: **COMPLETE — verified real retrospective research evaluation**.
Completed 2026-10-12 at 12:15:59 UTC / 17:15:59 Pakistan. Trailforge recorded
COMPLETED and typed VERIFY PASS. No retraining or model reselection occurred.
The pre-reveal specification below was recorded before this evaluator opened
labels; measured results follow it. Research-only, not deployment/trading approval.

The user requested the next step after real training completed: evaluate the
held-out 2026 research period. No refitting, calibration, vocabulary/IDF learning,
threshold tuning, test-driven model reselection, paper actions or orders are
authorized by this stage.

## Pre-reveal specification

Frozen training release:
`4c706aa1821093bba26231405ee1e119fcbb7787c38aff8c75c333897520f95f`.
Frozen four-model artifact:
`86fd36518754d6beded20b1a49d2abad84d0917fea47ffd61cfeaa5e2711daad`.
Selected candidate is **text_only**, chosen on 744 later-2025 validation rows
by macro-F1, then log loss, then name; NOT by test performance. Training used
10,458 rows and calibration used 744 separate earlier-2025 rows, with one full
date embargoed between calibration and selection. Training verification PASS
is required to load this release.

Configured held-out period: January–September 2026. The existing boundary
embargo and authorized quality exclusions leave **1,104 stock-day examples**,
184 complete six-company date groups, January 5–September 30. All four frozen
comparison models use the same rows. Labels remain >+1% UP, <-1% DOWN, otherwise
NO_MATERIAL_MOVE, derived from exact first/last regular-minute proxy boundaries.

Metrics: accuracy, macro-F1, log loss, multiclass Brier, ten-bin ECE, calibration
bins, confusion matrices, class counts, per-class precision/recall, selected-model
ticker breakdowns and selected prediction counts. Accuracy uncertainty uses
100 whole-date bootstrap samples with seed 123 and 2.5%/97.5% quantiles.
These intervals do not establish independent market observations, exclude
cross-date dependence, or prove profitability. A majority baseline may win.

## Execution boundary

`research-evaluate --data-dir ... --release-hash ... --authorization-evidence ...`
verifies the frozen release, complete audited row index and excluded dates.
It persists an immutable test plan and binds a one-release-per-contract test
lock before reading final labels. Replaying the identical freeze is idempotent;
a different release/plan cannot silently reuse this test experiment.

The initial loader opens saved input snapshots only, never labeled dataset row
artifacts or regular-minute outcome pages. Story masking replays complete dates
chronologically using earlier input metadata only and a private copy of the
frozen seen-story registry; model parameters and the saved registry do not change.
Trailforge's predict task commits the complete four-model probability artifact
BEFORE the evaluate task opens outcomes. The label loader then reconstructs each
row and label from independently verified source boundaries. A separate VERIFY
task checks release authority, input replay, saved predictions and metric replay.
No failed or UNKNOWN authority is erased or implicitly retried.

All full rosters, inputs and outputs remain private content-addressed artifacts
under `data/real-2018-2026/research-evaluations`, with separate evaluation SQLite
ledgers. Harness messages contain small hash references, not complete row lists.
Runtime progress is `real-evaluation-status.json`; an exclusive
`research-final-test.lock` prevents duplicate local evaluators. Do not remove an
active owner's lock. Training status/release are preserved unchanged.

## Interpretation and remaining gates

This is HISTORICAL_APPROXIMATE retrospective research. Earlier bounded source
QA may overlap 2026; the held-out fitting/selection seal does not imply a globally
never-inspected blind test. News versions are not certified historical receipt
records. Interior-minute gaps, lexical rather than semantic story grouping,
corporate-action review and data permissions attestation remain limitations.

High neutral-class accuracy can hide poor UP/DOWN recall; compare macro-F1,
per-class results and majority/price baselines before describing model value.
No numerical target, accuracy improvement, news benefit or profitability claim
is pre-approved. Report a negative result honestly; do not tune and replace it.
Future changes after seeing this test require a named new experiment and a new
forward or genuinely held-out evaluation period.

Human dataset quality approval, live point-in-time evidence, real dashboard
integration and paper-policy/deployment promotion are separate remaining gates.
The existing demo dashboard remains FIXTURE-only. This step does not promote
an investment action or close unverified milestone requirements.

## Verified measured results

All models were scored on 1,104 stock-day examples / 184 complete date groups.
Actual class counts: DOWN 260, NO_MATERIAL_MOVE 571, UP 273. Every ticker has
184 examples. A prediction row is not an independent market observation.

| Frozen model | Accuracy | Macro-F1 | Log loss | Multiclass Brier | ECE | Date-bootstrap accuracy 95% interval |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Majority prior | 51.72% | 0.2273 | 1.0287 | 0.6172 | 2.91% | 48.54–54.30% |
| Price-only logistic | 51.54% | 0.2294 | 1.0429 | 0.6262 | 8.62% | 48.40–54.90% |
| Text-only logistic — validation-selected | 49.82% | 0.2927 | 1.0372 | 0.6236 | 5.93% | 46.69–52.49% |
| Combined logistic | 51.90% | 0.2978 | 1.0341 | 0.6192 | 4.12% | 49.18–55.21% |

Macro-F1 gives each class equal weight; log loss and Brier assess probability
quality, with lower values better. ECE is a ten-bin descriptive calibration
error, not a guarantee. The intervals are exploratory date-cluster bootstrap
intervals, not paired improvement tests or proof of independent observations.

The frozen **text-only** candidate remains selected even though combined has a
higher observed test macro-F1. Its accuracy is about 1.90 percentage points below
the majority baseline; its log loss and Brier are also worse. Combined's accuracy
is only about 0.18 points above majority, with overlapping exploratory intervals.
This does not establish a useful accuracy improvement or profitable news signal.

The selected model predicts DOWN 66 times, neutral 974 times and UP 64 times.
Neutral predictions comprise 88.22% of examples, versus 51.72% actually neutral.
It detects only 19/260 DOWN moves (7.31% recall) and 16/273 UP moves (5.86% recall).
The higher macro-F1 than majority does not remedy its very low material-move recall.

Selected-model confusion matrix, rows actual and columns predicted:

| Actual / predicted | DOWN | NO_MATERIAL_MOVE | UP |
| --- | ---: | ---: | ---: |
| DOWN | 19 | 222 | 19 |
| NO_MATERIAL_MOVE | 27 | 515 | 29 |
| UP | 20 | 237 | 16 |

Selected-model breakdown (184 examples per company):

| Ticker | Accuracy | Macro-F1 |
| --- | ---: | ---: |
| AAPL | 56.52% | 0.3108 |
| AMZN | 46.20% | 0.2477 |
| JPM | 57.61% | 0.2437 |
| NVDA | 32.07% | 0.2866 |
| WMT | 50.00% | 0.2609 |
| XOM | 56.52% | 0.3028 |

**Eligibility decision: do not promote for paper actions or trading.** Keep
paper_action_authorized=false and deployment_promoted=false. The historical
quality limitations, weak selected-model results and poor UP/DOWN recall remain
visible. No post-test classifier swap, threshold adjustment or retraining was
performed. A future improvement is a named experiment with new forward/held-out
evidence; this result cannot be silently replaced by tuning on these dates.

## Reproducible evidence

Private content-addressed artifacts in `data/real-2018-2026/research-evaluations`:

- Freeze: `7eeab6161979754a667ff061e8f5f6ce0bf5e5f98435a62df0028fcd5368c32f`.
- Input-only predictions: `379b897f2532310b8deeb50aeb30b978fbd0bc7e8cfee02d06184c7b49f4d5a7`.
- Test report: `d577d665c090799434fae04af596883a31de2320f3818ca86d975cce5144f53e`.
- Test release: `3183601daff380c5e41420c84dfa401be306d04253e26fd5dceaf0598ffd6c5e`.
- Evaluation run: `429a909f-ff1b-419f-8d21-eef4842c37a2`.
- VERIFY receipt: `sha256:663b39a6a045ef37e8450007c05cffe947f7a6d013808197df2811158fecf93d`.

The final model hash still equals the original frozen model hash. SQLite
checkpoint checksum/binding/event, typed verification receipt, artifact hashes
and application job manifest were independently checked after completion.
Persisted prediction inputs have no labels/returns/outcome fields. The training
release's final_test_opened=false remains an immutable statement about its
training-time seal; the separate test release now records final_test_opened=true.
The exclusive evaluation lock has been released after verified completion.

Software evidence: 206 regression tests passed, with one upstream Starlette/httpx
deprecation warning; lint and dependency checks passed. Synthetic tests verify
prediction-before-outcome ordering, no fit/calibration, fixed selection, replay,
probability alignment and lock ownership. Software tests are not market accuracy.
An actual saved-release AAPL/2026-09-30 inference smoke check also succeeded,
reporting HISTORICAL_APPROXIMATE, outcome_loaded=false and no paper authorization.

Next product step is a real research-results/replay dashboard integration, not
automatic admission to trading. Chronological saved test predictions use earlier
2026 input history; one-off research-predict uses only frozen train/validation
story history and explicitly reports that scope. Do not confuse those two modes.
