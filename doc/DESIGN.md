# Prediction and decision design

Status: proposed contract. This document defines one consistent experiment; settings marked **provisional** must be frozen before final-test access.

## 1. The company-session example

One row means one ticker in `{AAPL,NVDA,AMZN,JPM,XOM,WMT}` on one exchange session. At `09:00 America/New_York`, construct the row using only observable eligible information. SPY is context and a benchmark. The same ticker may have no eligible article; no-news rows remain in the population. No market session means no row.

The proposed article window is `(previous regular close, cutoff]`. Include all eligible after-hours and pre-open records in that interval, deduplicated into event groups. A broader lookback can be tested on training/validation data, but cannot be changed after looking at the final test.

At the cutoff, only earlier completed price sessions may contribute price features. The same day's open, close, high, volume, or SPY movement must never enter the input. Price-bar timestamps, source feed, and adjustment method are recorded. Use a real exchange calendar and timezone-aware UTC storage.

## 2. Label and target

For regular session `d`, `r(ticker,d) = close_regular(d) / open_regular(d) - 1`. A configured symmetric threshold `theta > 0` gives `UP` when `r > theta`, `DOWN` when `r < -theta`, and `NO_MATERIAL_MOVE` otherwise. Boundary equality is in the no-material class. Choose `theta` from a predeclared training/validation procedure; do not choose it on the final test. The threshold is not a fee/slippage estimate.

Open and close must come from the same documented provider/feed and same regular-session convention. Use adjusted historical data consistently for features and labels, reconcile split/dividend conventions, and use raw or appropriately adjusted opening/closing levels for paper P&L without mixing incompatible series. Reject missing or anomalous sessions. A ticker's session return is not the return from the previous close; an overnight gap is outside this target.

At 09:00 the opening price is unknown. The paper fill at the regular open is idealized; show cost and slippage sensitivity. The target may be difficult because much pre-open news can be reflected in the opening price. Measure that limitation explicitly rather than shifting the target after the final test.

## 3. News preparation

Minimum article fields: provider ID, source URL/source, headline, available text, provider ticker list, `created_at`/published time, `updated_at`, locally observed `received_at` for forward captures, content hash, event group, and quality flags. Preserve original payloads; normalized records are derived and versioned.

Filter by source availability at the cutoff, then normalize text, attach ticker only when mapping is credible, group duplicates, and assign transparent event tags (`EARNINGS`, `GUIDANCE`, `ACQUISITION`, `REGULATORY`, `OTHER`). Start with rules and manually inspect a sample. Do not call these trained event classifiers. Allow a record to relate to several tickers, but prevent duplicate story versions crossing evaluation partitions.

Historical API retrieval today proves neither original receipt time nor original text. If a post-cutoff edit may have changed content, exclude it from `RECORDED_STRICT`; label any publication-time-only replay `HISTORICAL_APPROXIMATE`. Capture new versions and local receipt times going forward. Synthetic fixtures use `FIXTURE` mode and are excluded from market-performance metrics.

## 4. Feature set and candidates

Common earlier-price features: previous-session return, 5/20-session trailing returns, trailing realized volatility and volume summaries, plus lagged SPY return/volatility. All rolling features end before the cutoff. A fixed-universe identifier may help the model but may overfit; compare with and without it on validation.

News features: unique article/event counts, event-tag counts, article age, headline TF-IDF, and optional FinBERT positive/negative/neutral scores aggregated across eligible events. FinBERT sentiment is a text feature, not a price-rise probability. If article text is absent, use available headline and record the missing-content flag. Never fill missing news-feed data with a zero-news value.

Train candidates in this order: majority class; price-only logistic regression; news-only TF-IDF logistic regression; combined price/news model using a small regularized or gradient-boosting estimator. Keep a no-news ablation and a combined-minus-price comparison. The exact estimator library is a replaceable implementation choice; the experiment contract is the important part.

## 5. Splitting, calibration, and policy

Use chronological date partitions shared across every ticker. A candidate schedule is 2022-2024 training, 2025 validation/calibration/policy selection, and 2026 through the latest complete month as final test, **only if data availability and sample sizes support it**. Reserve non-overlapping chronological validation segments for calibration and threshold selection, or use a justified time-series calibration scheme. Purge examples whose outcome window crosses a partition boundary; group duplicate article versions. Fit every transformer, imputer, vocabulary, and model within training folds only.

Produce three calibrated class probabilities summing to one. Check classwise calibration and log loss on held-out dates. Select a confidence threshold and any ticker/event eligibility rules using validation alone. `PAPER_LONG` is considered only for valid inputs and a sufficiently strong calibrated `UP` probability, subject to a paper exposure limit. Otherwise return `ABSTAIN` with a reason. `BLOCKED` is for operational/data-contract failures, not weak forecasts. If no defensible expected-return model exists, do not claim cost-aware expected profit from `P(UP)` alone.

Historical performance views must show sample count, coverage, macro-F1, confusion matrix, per-class metrics, calibration, and uncertainty by date/ticker where meaningful. Paper returns must use explicit opening/closing fill assumptions, costs, max exposure, missing-data rules, and matched cash/SPY comparisons. If confidence is uncalibrated or sample size too small, suppress automatic `PAPER_LONG` and show research-only predictions.

## 6. Worked hypothetical

On a valid session, the 09:00 snapshot for NVDA contains a guidance headline received before the cutoff, one deduplicated event, the prior completed NVDA and SPY price bars, and data-quality status `VALID`. The model outputs `UP 0.61`, `DOWN 0.16`, `NO_MATERIAL_MOVE 0.23`. These numbers are **illustrative only**. If the validation-frozen policy threshold is 0.65, action is `ABSTAIN/LOW_CONFIDENCE`. After the close, the separate outcome record stores the actual regular open, close, return, class, source, and outcome-availability time. The original decision is unchanged.
