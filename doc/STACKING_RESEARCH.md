# Chronological expert stacking research

Frozen on 2026-10-13 before real stacking fits; user authorized this experiment.
This is private noncommercial development research, not a trading release.

## Inputs and scope

Reuse `data/research-v2-20261012`, release
`51bce00fd0ce0ea0146877884c36eaa09055d23eff6bc337d453f065579542d7`,
and the positively verified source assembly in `data/boosting-20261013`, rows
`87d407b1c3f0fdfd797fca13876b8aeeeb6d1f4a5b993b9e60e84dbbd2dbcdc8`.
There are 11,952 immutable real company-day development examples: 10,458 in
2018-2024 and 1,494 in 2025. Same six stocks AAPL/AMZN/JPM/NVDA/WMT/XOM;
SPY and sector ETFs are context only. No extraction or new transformer pass.

Keep the 09:00 America/New_York feature cutoff, regular-minute open/close
return proxy, strict +/-1% three-class labels, whole-six-company-date coverage
quarantine, and authorized masking of previously seen headlines. No target,
threshold, class resampling, or validation distribution changes.
Early 2025: 744 calibration rows; one six-row date embargo; later 2025:
744 selection rows. Never read 2026 outcomes in this experiment.

## Experts and combiner

Reuse software/feature whitelists from PRICE_EXPERT and CONTEXT_EXPERTS,
but fit new local experts; do not overwrite their earlier saved releases.
Price has 20 features and eight settings (Logistic Regression, CatBoost,
XGBoost); news has 24 features and four Logistic Regression settings; market
has 22 features and eight settings (Logistic Regression and LightGBM).
The original parameter grids, seeds and portable artifact formats are fixed.

Each expert produces DOWN/NO_MATERIAL_MOVE/UP probabilities. The combiner
uses exactly these nine probabilities, not labels or raw prices/news. It is
multinomial Logistic Regression with C .1/1 crossed with unweighted/balanced
classes, train-only medians/scaler, and saved JSON coefficients. No transformer
fine-tuning, neural combiner, or outcome-dependent feature engineering.

## Past-only selection and meta training

Do not reuse the earlier expert search-fold predictions for meta training:
their configuration selection looked at subsequent development outcomes.
Generate fresh outer forecasts for 2022, 2023 and 2024 using only prior years.
Each outer training roster removes the last exchange session before the
forecast year, with embargo by exchange date even if a source date is missing.

Inside each available historical roster, use its latest prior year for an
early-half calibration / one-date embargo / late-half inner selection. Train
candidate experts on earlier years, also purging the preceding exchange date.
Choose one configuration per expert across its families by macro-F1, then
log loss, then configuration digest. All selection labels precede the outer
forecast. Refit each chosen expert on the past, excluding a trailing
calibration block and its preceding exchange session. The trailing block is
10% of available date groups (floor), capped at 60 and at least four groups.
Calibrate on that block; predict the entire subsequent outer year.

Assemble outer predictions by exact source input/row identity. Verify native
positive receipts, selection identity, and that every expert fit, calibrator,
and tuning roster is a subset of its past history. Store chronological
probability inputs separately from their supervised labels. Recheck request
identity before accepting a resumed assembly task.

Source-roster dry inspection confirms 4,500 OOF examples: 1,488 for 2022,
1,500 for 2023 and 1,512 for 2024. Their forecast refits use 5,586 / 7,074 /
8,574 training examples, respectively, plus 360 separate past-calibration
examples each. These are roster counts, not a claim of completed real fits.

Tune the four combiner settings on expanding OOF histories: predict 2023 from
2022, and 2024 from 2022-2023. Reserve the same adaptive trailing calibration
block and whole-exchange-date embargo in each history. Select by mean macro-F1,
mean log loss, then configuration digest.

Select deployment experts using only 2018-2024 history with the same nested
process. Refit with trailing historical calibration, then predict both 2025
blocks. Fit the final combiner on all OOF 2022-2024 examples, calibrate its
output on early 2025, and evaluate only later 2025. The new experts need not
match the previously selected specialists: past-only selection is intentional.

Total: 101 bounded fit tasks. Four outer/deployment scopes each require
20 inner candidates plus three forecast refits (92); four combiner settings
times two chronological folds plus one final fit (9). Report exact OOF and
final expert training/calibration sizes from saved rosters, not article counts.

## Comparison, verification and gates

Compare seven candidates on the exact same 744 later-2025 examples: actual
stack, three locally fitted experts, equal-probability average, that average
temperature-calibrated on early 2025, and training-frequency majority baseline.
Temperature grid .5/.75/1/1.5/2, selected by calibration log loss. Baseline
hard predictions are neutral for this data; its probabilities are train priors.
Select research candidate by macro-F1, log loss, name, even if a control wins.
Save the actual stack regardless of winner. Report overall accuracy, macro-F1,
equal-class recall, UP/DOWN recall, log loss, Brier and per-class/ticker metrics.

Every source, fit/saved inference replay, OOF assembly and release is a bounded
Trailforge task with positive verification. Independently reconstruct the final
comparison from verified prediction artifacts and fixed rosters before release.
Do not reset UNKNOWN/failed native authority. New private root:
`data/stacking-20261013`; locks, SQLite, model binaries, logs and data stay local.
Saved composed inference accepts input only and rejects dates at/before final
calibration history; it returns both the actual stack and selected-candidate
probabilities, with no broker or paper action capability.

Chronological model selection does not repair underlying point-in-time issues.
Source availability remains HISTORICAL_APPROXIMATE. FinBERT revision
`0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031` has incomplete historical corpus-date
audit and CC BY-NC-SA 4.0/private noncommercial scope. Earlier 2025 and 2026
evaluations were exposed; this is DEVELOPMENT_NOT_FINAL_TEST, not a new blind
test or proof of profitable forecasting. No accuracy improvement is promised.
Human quality/policy, untouched forward evaluation, paper and deployment gates
remain open. Existing milestones are not closed by this experiment.

## Status

```powershell
Get-Content -Raw F:\MarketPulse\data\stacking-20261013\v2-status.json |
    ConvertFrom-Json |
    Select-Object stage, phase, expert, family, fits_complete, fits_total, rows_complete, rows_total, pid, updated_at_utc
```

COMPLETE means finished; STOPPED requires inspecting error/native receipts.
Input loading precedes fitting. Check lock/PID/native authority before restarting.
Run offline from cached data. Keep AC connected and lid open; the temporary
idle-sleep guard cannot override explicit sleep. Background logs are private
`stack-r1.stdout.log` and `stack-r1.stderr.log`. A real launch/completion must
be recorded in CHECKPOINT separately from synthetic test evidence.
