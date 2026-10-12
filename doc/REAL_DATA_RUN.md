# Real-data research run — 2026-10-12

Status: real collection running; model fitting has not yet started.

The user confirmed data permissions and requested the complete real dataset and
model training after requesting a larger historical dataset. Use the proposed
2018–September 2026 scope, keeping the six stocks and separate SPY context.
The private contract is `data/real-2018-2026/approved-contract.json`, ignored by Git.
Rights evidence is the user's attestation, not an independently verified grant.

Training: 2018–2024. Validation: 2025. Final test: January–September 2026.
One NYSE session is embargoed at each held-out boundary. The initial calendar
plan is 13,176 company-day rows (2,196 usable sessions), before quality exclusions.
The target remains a fixed symmetric 1% first/last regular-minute proxy return;
exact threshold equality is neutral. No official auction or execution claim.

Alpaca/Benzinga historical headlines and summaries and SIP/split price bars are
canonical. Article bodies, supplementary Agent-Reach web captures and social
platforms do not silently become model features. Their licenses and historical
availability require separate source-specific review.

Historical article versions remain HISTORICAL_APPROXIMATE. Inputs contain only
pre-cutoff news versions and earlier complete price sessions. Outcome prices are
stored separately. Final-test labels must not influence model selection.

Preserve raw captures, source request IDs, Trailforge receipts, immutable rows,
quality reports, training-only preprocessing and safe JSON model artifacts.
Do not invent missing prices/news or call fixture scores real performance.
Collection failures and dataset promotion remain explicit, inspectable states.

## Authorized quality policy

On 2026-10-12 the user approved quarantining unusable whole six-company date
groups and continuing. The optional frozen contract field `quality_policy` is
`quarantine-missing-boundaries/1`; contracts without it retain strict stop behavior.
A date is excluded only after Trailforge records terminal typed verification
FAIL and an independent replay of intact, complete raw pages identifies a
missing exact opening or last regular minute. Other integrity errors, UNKNOWN,
expired work, inaccessible artifacts and incomplete pagination still stop.
Failed runs are not reset or retried. Immutable exclusion artifacts bind the
contract, date, all six symbols, failed run, raw hashes and verification receipt.
Full audits reconstruct these records. Planned, excluded and accepted counts
are separate. Calendar dates, label definition and split boundaries do not change.

The 2 May 2018 response has only an opening bar for AAPL, AMZN and NVDA;
the other four symbols have 390 bars. The entire date is excluded, not filled
with daily bars. Additional confirmed coverage failures follow the same policy.
The current frozen identity is
`9dc1139a0866271ad6d6b525d37bff3245ac6bc2944a7dd8450a0bdcf8abff97`.
Earlier strict-contract captures and rows remain preserved. Verified source
jobs are reused; rows are materialized under the new immutable policy identity.

## Completion runner and training boundary

`research-build` performs up to three collection cycles, each at most 50 batches
of 31 dates, with up to three isolated provider connections. Only one bounded
wave of dates is in flight; a failure/hold stops new waves. Each capture and row
is checked immediately; full-roster audits run at cycle boundaries. No broker
endpoints, social cookies or paid upgrades are involved.

The user's explicit training request authorizes **offline diagnostic research
fitting**, not a fabricated human quality review or deployment promotion.
Only a complete, integrity-checked roster can proceed. The runner records that
request as an authorization artifact bound to the exact final contract/report
hashes. The existing human-reviewed baseline promotion route remains unchanged.
The new research release explicitly marks human_dataset_reviewed=false,
deployment_promoted=false and paper_action_authorized=false. M03/M04/M05's
human-review and empirical acceptance criteria are not silently waived.

Four comparison models: majority-prior baseline, scaled price logistic
regression, TF-IDF text logistic regression, and price+TF-IDF logistic regression.
The financial-text/1 cleaner removes HTML/scripts, links, control characters,
spacing noise and exact within-example duplicates, retaining negation,
numbers, signs and percentages. Raw payloads stay intact. Median imputation,
scaling, vocabulary/IDF and classifier fitting use training data only. Text
vocabulary is bounded to 1,024 terms. Calibration uses the first half of usable
2025 validation dates; one whole date is embargoed before the separate model
selection segment. Selection is highest validation macro-F1, then lowest log
loss, then name. No final-test examples/outcome pages are opened during fitting.

Price boundary gaps are excluded; interior minute gaps are recorded, not filled.
Corporate-action and semantic-event review still matter. Cross-split exact
provider-ID/headline duplication blocks the original unmasked fitting route.
Historical approximate data
does not become certified point-in-time data by passing these software checks.

Models, validation report, release and Trailforge fitting/verification records
are private under `data/real-2018-2026/research-models` and separate model SQLite
ledgers. `research-predict` loads only saved inputs and the frozen model and
returns class probabilities, not a trading action. Final-test evaluation and
real dashboard promotion are not implied by completing this research runner.

Runtime status: `data/real-2018-2026/real-build-status.json`.
Private logs: `real-build.stdout.log` and `real-build.stderr.log` in that directory.
These show actual progress, audit failures or the completed model release;
do not call the dataset complete or publish performance before those exist.

## Software and live evidence

The complete regression suite passed 185 tests before the annual-calendar
optimization; its added parity checks plus dataset/training/quarantine tests
passed 37 tests. The earlier 498 real strict-contract rows were independently
re-audited after the optimization with identical rebuilt row contents.
Profiling that audit dropped from 186 to 102 seconds under concurrent local
load; this is diagnostic evidence, not a controlled latency guarantee.
Workers reuse isolated connections within each bounded batch and close them
afterward. Training bounds BLAS to two threads; library versions and this bound
are pinned into the immutable fitting identity.
Lint and dependency checks passed. The staged 23-path credential scan had zero
findings; updated staging must be rescanned before committing. None of this
constitutes empirical model accuracy, full dataset completion, or human review.

## Approved chronological story masking

The user explicitly approved masking previously seen stories in later model
inputs on 2026-10-12. The policy is `earlier-date-story-mask/1` and is separately
bound into the build intent, training authorization, model and release identities.
It does not change raw captures, fixed labels, outcome prices or date splits.

Provider-ID and normalized exact-headline keys record their first observed model
input date. First-date stories remain available to all companies on that date;
later repetitions are hidden from model text. Training vocabulary/IDF/weights
use training rows and their training-only registry. Calibration and evaluation
replay complete dates chronologically, extending an input-only registry with
earlier dates, without reading labels for preprocessing or mutating the frozen
candidate. After fitting and calibration, selection-input metadata is registered
in the research release; no final-test row or outcome page enters its registry.
A one-off `research-predict` uses this frozen train/validation history only and
reports that scope. An eventual chronological final-test replay can update its
own input-only history without changing model parameters.

The strict raw duplicate audit is preserved, including INTEGRITY_BLOCKED and
its duplicate hashes. Explicitly authorized masked research fitting may proceed
only when every nonquarantined company/date row is present and the only raw
integrity warning is exact-story duplication. Missing rows, lineage errors,
batch failures and unknown authority states still block. Unmasked training and
the original human-reviewed promotion path keep their existing strict gates.
Research releases record masked-story counts for training/calibration/selection.

This is conservative lexical filtering, not verified semantic-event grouping:
identical headlines can describe distinct events, which may also be masked.
Corporate-action, approximate-news and human deployment-review limitations remain.
Four synthetic wire/masking tests passed, including a sealed-final-test-artifact
guard. These are software checks, not market performance claims.
Current masked build intent:
`95b5594f032ca052614341207c827314f61ab36d123e28cb3b4b8979a1bd957a`.

Final software verification: **198 tests passed**, with one upstream Starlette
httpx deprecation warning; lint and `pip check` passed. The staged 25-path
credential scan had zero findings. At 06:34:36 UTC on 2026-10-12, collection had
3,300 canonical rows through 2020-03-27 and 13 excluded date groups. This is a
dated progress snapshot, not the completed dataset count. No real model has
been fitted yet. The managed launcher was PID 10388 when checked; verify command
identity and current status rather than treating a PID as permanent.

"Final test not opened" means the fitting/calibration/selection path does not
read its row artifacts or outcome pages. Earlier bounded source QA may have
sampled dates within 2026, so do not call this a pristine never-inspected blind
test. It remains a held-out retrospective research period, not forward evidence.
