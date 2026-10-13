# Verified v2 classification results — 2026-10-13

Completed October 13 at 00:35:55 Pakistan / October 12 at 19:35:55 UTC.
Status COMPLETE, release native COMPLETED/PASS. All 54 fold and 5 final fit
receipts were checked, saved label-free inference passed, and v1 remained intact.

Data: six companies, 11,952 audited 2018–2025 development examples; 10,458
training rows, 744 early-2025 calibration rows, a six-row whole-date embargo,
744 later-2025 selection rows. The source/news pass processed 26,833 unique
cleaned headlines. Fixed cutoff 09:00 New York, strict +/-1% return labels.
This is HISTORICAL_APPROXIMATE development research, not a new blind final test.

## Same-cohort results

| Candidate | Accuracy | Macro-F1 | UP recall | DOWN recall |
| --- | ---: | ---: | ---: | ---: |
| Unweighted logistic, existing price + TF-IDF | 63.17% | .3070 | 4.65% | 3.91% |
| Weighted logistic, existing price + TF-IDF | 54.84% | .3803 | 20.93% | 19.53% |
| Weighted logistic, enriched market + TF-IDF | 48.66% | .3725 | 27.91% | 25.00% |
| Weighted logistic, market/news meaning + TF-IDF | 48.92% | .3726 | 25.58% | 26.56% |
| Weighted CatBoost, market/news meaning | 53.63% | .3843 | 21.71% | 23.44% |
| Neutral-only training-prior baseline | 65.46% | .2637 | 0.00% | 0.00% |

CatBoost was selected by macro-F1, not accuracy. Its fixed configuration is
depth 6, 200 trees, training-balanced class weights and move multiplier 1.
No trained model beats the neutral-only baseline on overall selection accuracy.
Class weighting increases UP/DOWN recall at the cost of false alarms; neither
profitable performance nor a statistically established improvement is claimed.

The user later requested an increased movement ratio. A read-only equal-class
reweighting diagnostic retained all 744 rows (DOWN 128, neutral 487, UP 129),
with no refit, resampling or reselection. Balanced accuracy is mean class recall:
CatBoost 38.39%, unweighted logistic 34.27%, weighted existing 37.85%, weighted
market 37.76%, weighted meaning 37.71%, neutral-only 33.33%. This is a separate
diagnostic, not replacement validation data or new final-test performance.

## Immutable private evidence

- Release: `51bce00fd0ce0ea0146877884c36eaa09055d23eff6bc337d453f065579542d7`
- Selected model: `80fc55b5346c42fe2221ce80e1e612a982d43051bb8b2541598879b7e9b70557`
- Report: `ddc1dc0f6e6edd28b3193c2c37f438e44ac6b94e29e04c80112e3eeaa78aa44c`
- Dataset: `a9af101ab249424e0f92cdf6629a5cd4cea5c16d89fc395e6fe1a399b98a2805`
- Native release run: `14e2acd4-f920-481d-a4c0-55236193a41c`
- Receipt: `sha256:450a1d449b146811660f4e66d1ca59694eb00e9369db9c9efd751e93c87950ea`

Private artifacts remain under `data/research-v2-20261012`, excluded from Git.
Previous expired UNKNOWN attempts remain held with explicit positive child
reconciliation receipts, not erased or reset. The original v1 model hash is
`86fd36518754d6beded20b1a49d2abad84d0917fea47ffd61cfeaa5e2711daad`.

## Remaining gates

No new 2026 test was used: that period was already exposed in v1. New forward
testing is needed after freezing future research choices. Corporate-action/PIT
quality, model corpus-date audit, verified earnings data, human dataset review,
live serving/dashboard integration and deployment/paper approval remain open.
FinBERT is private non-commercial only. See [RESEARCH_V2](RESEARCH_V2.md) and
[FINAL_TEST](FINAL_TEST.md); do not hide v1's negative held-out results.
