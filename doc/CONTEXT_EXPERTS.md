# News and market experts: background experiments

## Frozen scope - 2026-10-13, before real fitting

User requested starting the news and market experts after verified price-expert
completion. Train only these two specialists; do not start stacking, change the
target, collect new data, fine-tune FinBERT, promote models or submit orders.
Use separate roots `data/news-expert-20261013` and `data/market-expert-20261013`.
Both are Trailforge-managed and reuse the same positively verified v2 source
and bounded six-company roster as [PRICE_EXPERT](PRICE_EXPERT.md).

Keep 10,458 training rows (2018-2024), 744 early-2025 calibration rows, a six-row
whole-date gap and 744 later-2025 comparison rows. Target: regular-minute-proxy
open-to-close return >+1% UP, <-1% DOWN, otherwise NO_MATERIAL_MOVE. Every feature
is from the existing 09:00 America/New_York-cutoff payload. All six companies
share chronological fold boundaries. Missing values are train-imputed, not
fabricated raw observations; preprocessing/scaling is fitted within each fold.

## News expert: FinBERT features plus Logistic Regression

Schema `news-expert-classification/1`, 24 numeric inputs: eighteen existing
meaning/event/relevance/age/count/missing features plus six company indicators.
No company/market prices, volume, sector, pre-market or raw text/TF-IDF input.
The missing earnings schedule/consensus/surprise values remain missing; this
experiment does not claim to have those unavailable historical sources.

Reuse cached recency/relevance-weighted headline sentiment from
ProsusAI/finbert revision `0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031`.
News source release must match the exact pinned FinBERT specification. No new
transformer inference, checkpoint download or fine-tuning. Event features are
existing explicit heuristics, not FinBERT event labels or verified surprises.
Earlier seen headlines remain masked under the existing authorized policy.

Four settings: Logistic Regression C .1/1 crossed with unweighted/balanced
classes, lbfgs, max_iter 2000, tolerance 1e-6. Three expanding folds (2022,
2023, 2024; one whole-date embargo) plus one family final = 13 fits.
Actual stock-movement labels train the classifier; sentiment probabilities
are not themselves stock-movement probabilities. Model/report/release retain
the FinBERT spec and noncommercial/incomplete historical corpus-audit caveats.

## Market expert: LightGBM plus Logistic Regression control

Schema `market-expert-classification/1`, 22 numeric inputs:

- Four lagged SPY returns/volatility features.
- Six sector return/volatility/coverage/missing features.
- Six company indicators using the fixed research sector-proxy mapping.
- Three sector-minus-SPY returns and three company-minus-sector returns
  over 1/5/20 prior sessions; missing inputs propagate to missing differences.

No sentiment, news, raw text, company volume/volatility or company pre-market
features. Company returns are used only inside the explicit relative-context
features. Reliable same-day SPY/sector pre-market features are not available
in the current frozen input schema; do not invent them or silently recollect.
Sector ETFs are fixed research proxies, not perfect sector membership labels.

Eight settings: the four Logistic Regression controls above, plus LightGBM
Classifier leaves 15/31 crossed with unweighted/balanced classes. LightGBM:
200 rounds, learning rate .05, multiclass, minimum child samples 20, L2 10,
full row/column sampling, deterministic/force_col_wise true, no bagging.
All primary/subordinate seeds 17. Three folds plus two final fits = 26 fits.

## Shared execution and evaluation

Use one CPU thread per specialist so both can run on the two-core laptop.
Pin installed versions without changing dependencies or prior environment
bindings. Separate locks/status/logs and positive source/fit/release receipts.
UNKNOWN tasks are never reset or implicitly retried. Immutable portable JSON
for Logistic Regression and content-hashed native LightGBM text; no pickle.
Each fit must reproduce fitted probabilities from saved artifacts. Independently
replay saved probabilities and metrics before native positive verification.

Choose settings within family by mean fold macro-F1, log loss, digest.
Calibrate each final on the early-2025 block using temperatures
.5/.75/1/1.5/2 and log loss, then compare on the same later-2025 rows. Include
training-frequency majority probabilities and select macro-F1/log loss/name,
even if the baseline wins. Retain all finals and honest per-class/ticker results.

These are exposed-date DEVELOPMENT_NOT_FINAL_TEST experiments on
HISTORICAL_APPROXIMATE data, not new blind evaluations or proof of predictive
value/profitability. FinBERT's checkpoint corpus-date audit remains incomplete;
private noncommercial scope only. New untouched forward evaluation is required
for a final claim. Do not open 2026 outcome data for this experiment.

Search-fold predictions are not approved meta-training data: later stacking
requires pre-frozen or earlier-only/nested expert selection and calibration
before each out-of-sample forecast. This step does not train a stack.

## Status and handoff

PowerShell:

```powershell
foreach ($expert in 'news', 'market') {
    Get-Content -Raw "F:\MarketPulse\data\$expert-expert-20261013\v2-status.json" |
        ConvertFrom-Json |
        Select-Object schema, stage, family, fits_complete, fits_total, pid, updated_at_utc
}
```

COMPLETE means finished; STOPPED means inspect error/native receipts, not
background progress. Confirm lock/PID/status before any restart. Keep AC/lid
open; temporary Windows idle-sleep protection does not override explicit sleep.
No internet is needed. Logs stay private: `news-r1.*.log`, `market-r1.*.log`.
After launch confirmation stop active monitoring and await the user's return.
Then verify native receipts, saved label-free inference and matched evaluation
rosters before recording completion or reporting performance.
