# Collection-to-baseline research pipeline

Implemented on 2026-10-10. This connects existing extraction, feature,
minute-outcome and baseline components. It is not a fitted market model,
calibrated forecast, paper policy, API or dashboard.

## Input to output

```text
Frozen six-stock contract + separate recorded rights evidence
  -> credential-free bounded collection plan
  -> resumable news/prior prices [Trailforge fetch + VERIFY]
  -> separate after-close minute outcomes [Trailforge fetch + VERIFY]
  -> immutable company/date features and fixed 1% labels
  -> completeness, lineage, no-news, gap and duplicate report
  -> explicit human review bound to exact contract/report hashes
  -> immutable baseline-only dataset promotion
  -> train-only imputation/scaling and majority/price logistic baselines
  -> matched validation [Trailforge fit + evaluate + VERIFY]
  -> safe JSON model, validation report and verified result references
```

Targets: AAPL, NVDA, AMZN, JPM, XOM, WMT. SPY is context only. Dates remain
July-December 2025 train, January-March 2026 validation, April-September 2026
final test, with one exchange session embargoed at each boundary: 313 dates /
1,878 company rows. Price labels use the first/last regular-minute proxy,
not official auctions or guaranteed fills.

Dataset construction and quality inspection may hydrate test lineage, but
do not emit test label statistics. The baseline loader, learner, evaluator,
verifier and cached-run revalidation **do not open final-test row artifacts
or their outcome pages**. They check the full roster using date/ticker/split/
hash metadata only. This is a code boundary, not filesystem access control.

## Safe commands now

```powershell
.\.venv\Scripts\marketpulse pipeline-plan --contract doc/dataset_contract.proposed.json
.\.venv\Scripts\marketpulse baseline-demo --data-dir data/baseline-fixture
```

The plan uses no credentials/network; the demo uses synthetic data only.
The committed contract retains `rights_confirmed: false`. See [PERMISSIONS](PERMISSIONS.md).

## Future authorized real-data workflow

These are instructions for later use, not a completed provider run. Store
approved contracts/reviews under ignored `data/`. Declarations record human
review; code cannot independently establish legal rights. Do not manufacture
confirmation just because an API call or tutorial works.

1. Record applicable rights evidence in a private approved contract. Do not
   change the agreed universe, target or splits to bypass a failure.
2. Run bounded collection:

```powershell
.\.venv\Scripts\marketpulse pipeline-collect `
  --contract data/approved-contract.json --data-dir data/m03 `
  --batch-sessions 20 --max-batches 1
```

Default: 20 sessions per batch / one batch per invocation. `--max-batches`
is an explicit 1-50 batch budget. Each sub-batch is at most 31 sessions and
60 calendar days. All planned sessions must have closed more than 15 minutes
ago. The entire frozen historical experiment can be scheduled within this
budget, but no full-size provider sweep was performed here.

Repeat with the same contract/directory to resume verified missing dates.
Completed dates do not make new provider requests. Unknown/failed work stops
the sweep; rerunning does not silently retry held tasks. Progress prints
counts/status to stderr; stdout contains artifact hashes and summaries,
not credentials or news text. Budget exhaustion returns `INCOMPLETE`.
Complete collection remains review-required and never starts training.

3. Produce an offline quality report and retain its returned hashes:

```powershell
.\.venv\Scripts\marketpulse dataset-inspect `
  --contract data/approved-contract.json --data-dir data/m03
```

4. A human reviews corporate-action compatibility, semantic-event leakage,
   interior outcome gaps and historical-approximation limitations. Use
   [dataset_review.proposed.json](dataset_review.proposed.json) as the shape
   of a private review. Its null fields/false approval intentionally fail.
   Bind exact contract/report hashes, reviewer identifier and timezone-aware
   timestamp; every `checks` field needs a short non-secret evidence reference.
   Do not invent audit evidence or approval.

```powershell
.\.venv\Scripts\marketpulse dataset-promote `
  --contract data/approved-contract.json --review data/dataset-review.json `
  --data-dir data/m03
```

Promotion rehydrates lineage and refuses incomplete, corrupt, cross-split-
exact-duplicate, stale or mismatched reports. Human check references record
the decision, not proof of audit sufficiency. Promotion permits majority/
price validation only, never final-test release or model serving.

5. Use the returned promotion hash for training:

```powershell
.\.venv\Scripts\marketpulse baseline-train `
  --contract data/approved-contract.json --promotion-hash PROMOTION_HASH `
  --data-dir data/m03
```

Review/training do not load `.env` or request provider data. They check local
application/raw/harness artifacts; missing artifacts block instead of being
refetched. The loader rechecks train/validation lineage, input/outcome passing
Trailforge receipts, and the complete immutable row index. No fixture-to-real
relabeling occurs. Real models remain `HISTORICAL_APPROXIMATE`, uncalibrated
and without paper-action authority.

Train-only median imputation/scaling and fixed logistic settings are shared
with fixtures. Each class needs two training rows. Convergence warnings,
all-missing price features, schema errors and nonfinite values block fitting.
The independent verifier refits from training rows and recomputes validation;
completed-run reuse also rechecks the model/report. See [BASELINES](BASELINES.md)
for metrics. There is no final-test evaluation or automatic paper-action command.

## Artifacts and limits

SQLite, raw captures, contracts, rows/reports, `promotions/` and
`pipeline-results/` remain under ignored data storage. `research-baselines/`
contains safe JSON models/reports/results and separate harness/job databases.
Source-bearing records, datasets, models and credentials never belong in Git.

Hashes provide consistency, not protection against a privileged operator.
Human declarations are not signed provider grants. The harness-start/run-ID
crash gap remains; exactly-once effects, concurrent collection, recovery/restore
and performance are not certified. Collection rehydrates growing reports;
full-size runtime benchmarking remains outstanding.

Synthetic wire tests cover extraction through labels, review and fitting,
resume without refetch, uncertainty holds, approval-before-secrets, invalid/
stale review rejection, full company/date groups, changed row indexes and
final-test read refusal. Synthetic labels are manufactured and are not
market-performance evidence. No real bulk dataset or real model was created.

Final verification on 2026-10-10: `pytest -q` passed all 139 tests in 299.01
seconds; Ruff and `pip check` passed. The credential-free CLI plan emitted
16 bounded batches covering 313 dates / 1,878 rows. A changed-file secret scan
found no hits in 17 files. All implementation work remains local; empirical
M03/M04 completion and GitHub milestone closure have not been claimed.
