# MarketPulse checkpoint for the next agent

## Cloud state and hosted dashboard implementation - 2026-10-14

User made `codera647/MarketPulse` public; connector independently confirms it.
Source is public, not provider data or results. All six CI secrets (including
VERCEL_TOKEN) and the storage endpoint were reported saved by the user. The
user additionally reports production environment reviewer `codera647`, main-only
deployment restriction and self-review allowed. A credential-bearing run still
requires approval of its exact commit; do not bypass that review.

Migrations 0001/0002 were installed and checksum replayed on the existing review
branch, then applied to production after review checks. Thirteen rollback-only
review checks pass: reader views/table boundaries, worker DDL/delete/overwrite
boundaries and completion checkpoint constraints. No fixture rows retained.
Use direct owner endpoints for migrations only; application connections remain
pooled restricted roles. Worker cannot DELETE history or overwrite projections.

New CloudState stores checksum-verified immutable private objects, explicit
single-writer ownership/lease fences and native checkpoint references. Expired
attempts become UNKNOWN, never stolen/reset/repeated. SQLite backup includes
committed WAL pages and explicitly closes connections (a Windows file-lock
regression was caught and fixed). The research publisher independently replays
the existing pinned native research projections before private publication.
It does not train, fetch articles, promote models or pretend replay is live.

Hosted `web/` is an isolated small FastAPI runtime with no ML/provider dependencies.
Graphite/teal UI, company/model/period filters, monthly accuracy comparison,
class counts, equal-class recall, saved replay with separate outcome reveal,
provenance and actual cloud-job views. API uses restricted reader views,
parameterized queries, bounded results, private/no-store responses and redacted
errors. No credentials, model files, raw articles or owner connection in browser.
Vercel All Deployments Authentication must be independently checked before any
result-serving deployment. Never deploy the repository root's default output.

New focused cloud/dashboard suite: **48 passed in 14.12s**; repository lint passes.
Full suite not rerun for this stage. The previous committed 9458d8b full GitHub
CI run independently passed (run 38440359967). New cloud-preflight workflow uses
reviewed SHA-pinned actions, lightweight locked dependencies, production review
gate, exact-main/repo restriction, step-scoped credentials, bounded authenticated
reads only and no private artifacts/logs. Its live run is not yet verified.

Still pending: actual hosted privacy/data verification, worker credentials in
Actions, forward collection/features/inference/outcomes, weekly rolling refits,
durable restore/reconciliation integration and safe retention. Schedules remain
disabled; no research quality/paper/milestone gate is closed by this stage.
The dated sections below are earlier snapshots, not current cloud completion.

## Private cloud bootstrap - 2026-10-13

User selected Neon Free, Vercel CLI, weekly batch retraining, daily forecasts
using information available by 09:00 New York, and automatic safe storage
retention. Private cloud storage/training and private display permissions are
explicitly confirmed. No orders or automatic model promotion are authorized.

Created dedicated Vercel `codera647s-projects/marketpulse`, ID
`prj_Gto0aVFyeStSCSyOezczGk8myTWx`, linked and independently inspected through
authenticated CLI 63.1.2. Created dedicated Neon MarketPulse project
`weathered-art-74189441`, production branch `br-cool-fire-b7c9ge4z`, database
`marketpulse`, PG17, aws-us-east-1; separate review branch
`br-restless-dawn-b7k4b3y1`; production private `research-artifacts` bucket.
Unrelated Vercel/Neon resources were untouched. Provider reports 512 MiB for
this new branch, NOT an assumed 1 GB. Explicit suspend configuration was
rejected; default Free configuration succeeded, no paid upgrade.

No deployment, application-table migration, data upload, worker schedule, weekly
refit, model promotion or retention deletion occurred. `.env` is unchanged; Vercel's link
created ignored `.env.local`. CI credential handoff is required: the Vercel
deployment skill forbids copying interactive login credentials into GitHub
and requires the owner to configure protected CI credentials directly. Start
with `VERCEL_TOKEN` in the repository's production environment; the user now
reports it saved. Five worker secrets and the storage endpoint still require
direct CI configuration. Never ask for token values in chat. See
[CLOUD_OPERATIONS](CLOUD_OPERATIONS.md) for IDs,
remaining credentials, exact implementation order and quota precautions.

`deploy/cloud.json` stores public target metadata with schedules/orders/model
promotion disabled. `python -m marketpulse.cloud_bootstrap` is a read-only,
fail-closed key-presence/target check; it does not validate credentials or
pretend the pipelines are implemented. Live preflight and tests are recorded
below after execution. A fresh dashboard/fixture run now passes 47 tests in
211.21s; the interrupted earlier run is not used as passing evidence. Actual
browser screenshot/keyboard QA remains unverified.

Restricted-role migration 0000 was tested on the separate review branch before
production. SQL-created `marketpulse_reader` and `marketpulse_worker` have no
administrator/bypassrls privileges or role memberships; reader is read-only by
default. Real connections for both roles and private storage HEAD/ACL checks
passed. No application tables are created/granted yet. Private credentials are
saved in ignored `.env.cloud.local`; ignored `.env.cloud-migration.local` is
owner-only migration authority and MUST NOT be uploaded to either platform.
Two unused API-created administrator-default roles were removed without data
deletion. A temporary connection exposed by a patch formatting error was
rotated immediately, then its unused role removed; current restricted values
were not displayed/committed/deployed. See CLOUD_OPERATIONS for the incident.

New optional cloud dependencies are psycopg/binary 3.3.6 and boto3 1.43.97,
with transitive lock pins. No dependencies enter the Vercel browser bundle.
Credential scanner now covers every private dotenv variant and credentialed
database URL/password fragments, as well as Neon token patterns. Six scanner
regression checks are added; no secret values appear in scanner output.

Final focused cloud/setup/scanner suite: 31 passed in 5.33s. Dashboard/fixture
suite: 47 passed in 211.21s. Full suite was not rerun for this bootstrap.
Repository lint and dependency checks pass. Private cloud connection checks
passed without uploads; Vercel env list is empty, so no hosted-app credentials
are configured yet. No cloud worker/deployment is claimed ready by these checks.
Final staged inspection covers 26 paths, zero credential findings; staged
whitespace validation passes. Private dotenv files and `.vercel` remain ignored,
and user-owned `.agents` remains untracked/untouched. No existing GitHub
milestone is closed by this dashboard/cloud-bootstrap evidence.

## Research dashboard implementation - 2026-10-13

The user requested a complete polished local dashboard using `.agents/skills`.
The build-quality and human-copy skills informed layout, precise research-state
copy, accessibility and regression checks. User-owned `.agents` files are left
untouched and untracked. See [DASHBOARD](DASHBOARD.md) for scope and launch.

The real stacking run completed at 12:18:24 Pakistan: 101 fits / 107 verified
native tasks, 4,500 nested past-only OOF rows. Release
`7fa2667f7268de276953112d6fa81e06c6315ba958e771786f4842b4cbe21951`
selects the price CatBoost expert by later-2025 macro-F1, not the actual LR stack.
The frozen 2026 retrospective run completed at 16:04:15 Pakistan: 1,104 rows,
184 dates Jan 5–Sept 30; 100 native tasks verified COMPLETED/PASS. Report
`617a7f51186f0cfd192af5b5862c6fa5254d9fc0bdf4732b350defdb6ef2deea`.
These previously exposed dates are not a new blind test. Full-population stack
accuracy 50.36%, selected CatBoost 36.78%, earlier XGBoost 40.13%, neutral-only
51.72%. No learned model wins overall accuracy; no test-driven reselection.

New read-only data projection verifies the pinned reports and native receipts,
content hashes, complete six-company groups, class conventions, all saved model
metrics and confusion matrices. Native storage validation is reused through
read-only SQLite connections; no initializing Harness or training runs occur.
No model binary deserialization, provider access, credentials or broker actions.

Five Streamlit views: overview with monthly accuracy, class distribution,
company/month heatmap and observed return series; comparisons/confusion/recall/
calibration; saved prediction probabilities with explicit outcome reveal/reset;
dataset and source provenance; all-task receipt checks and open release gates.
Ticker/date/model/period filters, private local CSV exports, errors/empty states,
responsive CSS, visible focus and reduced-motion support are implemented.
Default `marketpulse dashboard` now opens research; `--mode fixture` preserves
the isolated synthetic app. The FastAPI fixture contract is unchanged.

Both real populations load and replay their metrics successfully; all five real
views are being verified with Streamlit application tests. Local health returned
HTTP 200. Browser automation was blocked; desktop/narrow screenshot and actual
browser keyboard/hover QA are NOT verified. Verification results are recorded
below when complete. No deployment, paper or human/PIT gate is closed.

Older launch/preparation entries below are historical, not current status.

## Real stacking background launch - 2026-10-13

Verified software was pushed as `99c9ddd` after 57 focused checks, lint,
dependency checks and an eight-path credential scan passed. CI for this new
commit is not verified. No human-quality or deployment milestone was closed.
Hidden independent launcher PID 10440 started 11:53:31 Pakistan / 06:53:31 UTC;
native owner PID 20112. Separate private root data/stacking-20261013 and
stack-r1.stdout.log / stack-r1.stderr.log. D31 settings and chronology were
frozen before this launch. AC reports charging, 100%; temporary idle-sleep
guard enabled, no power-plan edits. No network or credentials are required.

Source native authority independently checked COMPLETED/PASS: run
`aad1c6c6-54ae-40f2-9ba7-c10c2af315f6`, receipt
`sha256:90e47ea17ff316054bed0bade64f785daeddea4837db943401d3ee71ee677f96`.
Build binding `a3e8c89ee520eb0e927c6e17a33be029128ef12e78a9d17e732aa2f24ca5d815`.
At 11:58:10 Pakistan the owner was alive with increasing CPU, stage
LOADING_STACK_INPUTS, 2,700 / 11,952 inputs loaded. Actual fitting has NOT
begun at this observation; 101 fits follow automatically after preparation.
No stacking result or completed empirical release is claimed. Observed loading
throughput suggests roughly 20-40 minutes remaining, approximately 12:20-12:40
Pakistan; provisional estimate, not a deadline or completion promise.

Status command is in STACKING_RESEARCH. Stop active monitoring after launch
handoff and await the user. On return inspect status, lock and owner/launcher
before any restart; never reset held native authority. COMPLETE requires
checking all 101 fit receipts, assembly proofs and release receipt, saved
input-only composed inference, exact evaluation roster and reported metrics.
Retain actual stack even if another candidate wins. All models/data/logs remain
private/local. All human/PIT/forward-evaluation/paper/deployment gates stay open.
Older preparation entries below are dated evidence, not current run status.

## Chronological stacking preparation - 2026-10-13

Latest user authorized stacking after specialist completion. D31 and
[STACKING_RESEARCH](STACKING_RESEARCH.md) freeze a new 101-fit experiment
before any real stack fit. New modules provide nested past-only expert
selection, calibrated 2022-2024 out-of-sample probability inputs, a nine-input
Logistic Regression combiner, seven matched later-2025 comparisons, and saved
input-only composed inference. New CLI commands are research-stack-build and
research-stack-predict. Separate private root data/stacking-20261013.
No new extraction, FinBERT training, target/threshold/distribution changes,
2026 outcome access, trading or deployment. Source/PIT/FinBERT corpus-date
caveats and all human gates remain open. Earlier releases remain intact.

Initial synthetic test caught resumed OOF selection metadata not being checked
before cache reuse; fixed explicit request identity validation. Final comparison
replay reconstructs averaged/baseline/stack metrics from verified fit artifacts
and the exact evaluation roster. All 57 focused stacking/context/price/v2/
regression/boosting tests passed in 633.87s with no warnings; lint, dependency
checks and an eight-path staged credential scan pass (zero findings). Full
suite was NOT rerun for D31. Synthetic stack completed 27 reduced-grid fits,
saved inference, chronology rejection and completed resume without refitting.
Source-roster dry inspection confirms 4,500 OOF examples (1,488/1,500/1,512
in 2022/2023/2024). No real stacking results are claimed by this preparation
entry. A launch/status entry must be recorded separately.

## Verified news and market completion - 2026-10-13

Verified on return: news finished 11:12:24 Pakistan / 06:12:24 UTC, 13/13 fits;
market finished 11:14:45 Pakistan / 06:14:45 UTC, 26/26 fits. All native fit and
release receipts COMPLETED/PASS. Every final saved model passed input-only
probability replay; exact 744 input/row hashes match the price expert. No live
owner/launcher PID or lock. Both selected balanced C=1 Logistic Regression;
news temperature 2, market 1.5. No new final-test or promotion claim.

News accuracy 42.87634%, equal-class recall 35.95942%, macro-F1 .34655859,
UP/DOWN recall 31.00775%/26.5625%, log loss 1.10750807.
Market Logistic accuracy 50.13441%, equal-class recall 36.42836%, macro-F1
.36181380, UP/DOWN recall 17.05426%/27.34375%, log loss 1.22343782.
Market LightGBM accuracy 50.53763%, macro-F1 .34762589, log loss 1.05304483.
The majority baseline has 65.45699% accuracy, macro-F1 .26374222, log loss
.89971312. No overall accuracy/probability-quality win. Price XGBoost remains
the strongest specialist by macro-F1. These are exposed-date development results.

News release `87f98591e878925de99e619d48528dc61b9f7fcd1fca8a1aed77fb162ec9539e`;
report `03cd766c9b6b7b501fbe7807f96ff79d7b7e04a0684faf71aaa949a3feb7b823`;
model `b92ce351407c1f9e0bcc5632cb93e7ebb942967a2875bda301e1a3b80151b005`.
Market release `d0c151efe0472e6902332c54170d9a0c71642741970b141a769321edb2152ee6`;
report `02dc814b9e82019cd72dde058d6318b5193721cf6a50c795c915fa89a2e11262`;
selected model `cbe40525f51a871a38a65ee82937de8d296abfca67ac0fbda9460a37a6004e36`.
Older running entries below are historical snapshots.

## News/market expert preparation - 2026-10-13

User requested starting both remaining experts after price completion. D30 and
[CONTEXT_EXPERTS](CONTEXT_EXPERTS.md) freeze the experiments before fitting:
news = cached FinBERT/event features plus Logistic Regression, 24 numeric
features, four settings / 13 fits; market = SPY/sector/relative-context inputs,
22 features, Logistic Regression / LightGBM, eight settings / 26 fits.
Same immutable real source, target and 10,458/744/744 rosters. One CPU thread
per job; separate private directories. No new collection, FinBERT pass, market
pre-market invention, stacking, forward-test claim, paper/trading or promotion.
54 focused context/price/v2/regression/boosting checks passed in 126.10s, no
warnings; lint and dependencies pass. Earlier price release still loads under
the generalized runner. Isolation, missingness, roles, fixed-seed saved replay,
checkpoint identity, native completion and resume-without-refitting are covered.
Full suite was NOT rerun in this turn. Both hidden jobs launched 11:02:40
Pakistan / 06:02:40 UTC. News launcher/owner PIDs 13720/13776; market
13960/19564. At 11:03:21 both positively verified their reused source and began
loading inputs. News binding
`5927493d204e723ab380969762f7ec62453b2441b6f76a53a25a9955a64bf603`;
market binding `482cbb169b2680334b4dcfceb6409a00d115aae3c224cd4bcc9ed01dd3323434`.
Private roots/status/log commands are in CONTEXT_EXPERTS. Temporary sleep guards
are enabled; AC independently reports charging, 100%. No current results are
claimed. Initial estimate was 5-15 minutes, but first observed input-loading
throughput is slower with both jobs: at 11:04:30 each loaded 900/11,952 rows.
Both owners are alive, CPU counters increasing, no error, idle-sleep guards on.
Revised provisional estimate is 20-30 minutes remaining from 11:05 Pakistan,
including preparation and fitting; not a completion promise. Actual fitting
has not begun at this last observation and follows automatically. No active
monitoring continues after handoff. Source/software/price evidence was pushed
as `c100099`; datasets, logs and models remain private/local. Check
status/lock/PID and native authority before restarting or reporting results.
Stop after launch confirmation; wait for the user before stacking or further
experiments. Commit/push covers verified software and price completion only;
news/market empirical completion and all human promotion gates remain open.

## Verified price expert completion - 2026-10-13

Checked at the user's return: finished 10:15:00 Pakistan / 05:15:00 UTC,
27/27 fits and release independently verified COMPLETED/PASS. All three final
models separately passed saved input-only probability replay; selected release
inference passed. No live PID/lock. Exact 744 input/row roster matches v2.
Trained 10,458 rows, calibrated 744, compared 744. Selected XGBoostClassifier
depth 3, 200 trees, balanced sample weights, temperature 1.5 by macro-F1.
Accuracy 52.95699%, equal-class recall 40.34116%, macro-F1 .40058834;
UP/DOWN recall 24.8062%/29.6875%. Majority accuracy 65.4570%, macro-F1 .26374222
and equal-class recall 33.3333%; no overall-accuracy/probability-quality win.
CatBoost accuracy 51.2097%, macro-F1 .37214306; Logistic 50.1344%/.37557627.
Development-only results, not a fresh final test or proof of trading skill.

Release `b129f626fc828541443ee8c9e1e93bd5b5e18b19e795c41ce6f047b9179392fa`;
report `cd9a1fc43a7dc71fcfc44836136cb4185b47163f6b49e1978d8bac3e29ecdb2f`;
selected model `42daae3e73209d42c08580a033749ec7eaf591c037ab3258e90594f4ece3d2b3`;
native release run `74566eae-4c2c-4ba9-af44-8facff869741`, receipt
`sha256:0a94c7a304142f6858d25c35064d5646fde641fd9c80ca2a49d109c8e46f1635`.
Earlier launch entry below is historical. No human/paper/deployment gate closed.

## Price expert background launch - 2026-10-13

User requested ONLY starting the price expert, an ETA, then stopping active
work until they return. Do not proceed to news/market experts or stacking yet.
D29 and [PRICE_EXPERT](PRICE_EXPERT.md) freeze eight settings / 27 fits, twenty
company-only lagged price, identity and pre-market inputs, no news/SPY/sector.
CatBoostClassifier, XGBClassifier and Logistic Regression are new classifiers,
not earlier regressors. Existing positive source receipts and 11,952 real
development rows are reused; no new collection/FinBERT inference or `.env` read.
Preserve 10,458 train / 744 calibration / six-row embargo / 744 selection.
Earlier evaluation outcomes are exposed; no new final-test or deployment claim.

47 focused price/v2/regression/boosting tests passed in 106.92s, no warnings;
lint and dependency checks pass. Tests include fixed-seed saved probability
replay, feature isolation, cutoff/role/calibration rejection, native receipts,
source reuse and completed resume without refitting. A status-binding bug caught
by the initial synthetic test was fixed before real launch. Full suite was NOT
rerun this turn; previous 247-test result belongs to the earlier commit.

Hidden independent launcher PID 16428 began 10:11:26 Pakistan / 05:11:26 UTC.
Private root `data/price-expert-20261013`; status `v2-status.json`; logs
`price-r1.stderr.log` / `price-r1.stdout.log`. Native owner may be a child PID;
check status PID and lock/process before any restart. AC independently reports
charging, 100%. Temporary Windows idle-sleep guard is retained, no power-plan
change. All 11,952 inputs loaded; real training confirmed at 10:12:07 Pakistan,
owner PID 16480, Logistic Regression first fold on 5,952 rows, 0/27 fits complete.
Build binding `bf72e193117a50da56326479636ecb9a6f3678013f52aacb30553d0e83f21abc`.
No accuracy/result is claimed yet. Estimated remaining 15-30 minutes on this
two-core host (estimate, not a completion promise). Active monitoring stopped
at the user's request after launch confirmation; source/code/docs remain local
uncommitted changes until a verified completion handoff or explicit push request.
The owner automatically saves/verifies models and completes the development
report/release. When user returns, check status and native receipts, verify saved
label-free inference, record honest results and commit/push completion evidence.
Never reset UNKNOWN authority, rerun to hide poor results, or close human gates.

## Verified boosting completion — 2026-10-13

User requested fixed-seed XGBoost, AdaBoost and LightGBM training after viewing
regression results. D28 freezes 12 settings and 39 chronological fits before
real fitting. Same six stocks, 48 numeric features, continuous targets and
selection dates; separate root `data/boosting-20261013`. New model dependencies
are pinned without changing old v2 environment identities. No new final test,
trading, paper action or promotion. See [BOOSTING_RESEARCH](BOOSTING_RESEARCH.md).
41 focused boosting/regression/v2 checks passed in 56.42s, lint/dependencies pass;
Guarded full suite passed 247 tests in 516.36s, with 179 warnings including
SQLite connection resource warnings (cleanup remains).
Managed real job began 08:53:22 Pakistan, owner PID 10564.
Completed 09:05:07 Pakistan: all 39 fold/final receipts COMPLETED/PASS;
saved input-only inference verified separately for all three models and release.
Build binding `3a67964ad2d018e78e8433fee05c5e0e11cfb7c6de059a89879b6822db6a5252`.
Status `data/boosting-20261013/v2-status.json`; log `boosting-r1.stderr.log`.
Release `7764534d2afe86583f17f324224ac55988dfbe98c3a799ec3a39f7f627988376`;
report `1b1deb739ba76de4757c8d6b75b4ff5b6ede56e9be83feacaf7a20de0dc27dc1`;
native run `b57b6b6e-0779-4512-91f6-036afb353716`, receipt
`sha256:341ffb80945c9567376ad791ed3b9166917a848a5b57a9239bb94abf7809bc48`.
Selection row/input hashes exactly match prior regression report.
Selected **zero_return**, RMSE 1.267410pp. XGBoost RMSE 1.278242pp, accuracy
65.4570%; LightGBM 1.281219pp/65.3226%; AdaBoost 1.269392pp/65.4570%.
All three have zero UP/DOWN recall; XGBoost/AdaBoost outputs are all neutral,
LightGBM has one false DOWN. No trained-model improvement; no new final test.
Preserve all models/results and v1/v2. Do not rerun/reselect to conceal the result.

## Verified regression completion — 2026-10-13

D27's original five-model experiment completed 08:34:41 Pakistan, all 56 fits
COMPLETED/PASS, saved label-free inference verified. Release:
`5cf4aa68f67448cd38db28c76b1e8a890fc15bd0244af63f4a5c6b1c9ce6d0ab`.
Report `63fef64ae75b1059c4cb2059bbd1a2fcaf732ba2d5bdc9a34b5a3f3b1be868ef`;
native run `1a306532-8429-4cf9-bcac-2fc35e70ee33`, receipt
`sha256:1bd1f3c8e30d8545f6423b3ee4a99e31783f370aa55906c92afbb2b9333c728f`.
Selected **zero_return baseline** on RMSE: 1.267410 percentage points, versus
best trained Random Forest 1.268477. No improvement in return RMSE; RF/CatBoost
derived labels are all neutral. 10,458 train/744 selection/744 reserved examples.
This is retrospective development, not a fresh blind final test.

Source reconciliation child `f07a4b71-dd3b-42b3-b0cc-a9b1ab531b2c` passed,
receipt `sha256:5b619fef5f4cba2337ef2d8be909aadd65ccfffac2c8a80f74754a8bcf051449`.
Original `ac4b9d4a-9adf-4d7d-94ef-98fb0b61a69f` retains UNKNOWN/EXPIRED,
one attempt/unit; no authority reset or original adapter retry.
Prior full software suite passed **240 tests in 649.56s**, two SQLite resource
warnings. Focused model/source-recovery checks passed 34 tests in 66.80s.
V1/v2 releases remain unchanged. Details: [REGRESSION_RESEARCH](REGRESSION_RESEARCH.md).

## Historical regression launch/recovery — 2026-10-13

User requested starting regression training. D27 was recorded before fitting.
New modules `regression_models.py` / `regression_pipeline.py` and CLI build/predict
commands implement five families and a bounded 17-setting, 3-fold chronological
comparison, with five final fits. All reuse the existing numeric inputs and
continuous audited return targets; no extraction or FinBERT rerun occurs.
Nine focused synthetic tests passed in 46.38s; lint/dependencies pass. Full
239-test software suite passed in 633.41s. Source v1/v2 artifacts remain unchanged.
An additional expired-source negative/positive recovery check is being run.

Real managed run started at 08:03 Pakistan / 03:03 UTC, owner PID 13704.
Directory `data/regression-20261013`, status `v2-status.json`, logs
`regression-r1.stderr.log` / `.stdout.log`. Modeling binding:
`b7a5f0e878986cc56f39f1b61b09357a47b459b82eeb4fca7b47cf7b30ee42de`.
First run STOPPED before fitting: full source projection took about 402 seconds
and exceeded its 300-second lease; no new Standby events were recorded.
Complete 11,952-row candidate hash:
`87d407b1c3f0fdfd797fca13876b8aeeeb6d1f4a5b993b9e60e84dbbd2dbcdc8`.
Original native run `ac4b9d4a-9adf-4d7d-94ef-98fb0b61a69f`, job
`8ac25ccb942b06d87a812732d43b1e93aa396987feb11a8f5bb1bf183470cde7`.
Keep its UNKNOWN/EXPIRED_ATTEMPT; never reset/re-execute it. Source validation
now uses 300-row native tasks and assembly. Explicit complete-candidate child
reconciliation is required before resuming the same run. No model/data/target/
split/search change. Check live lock/PID/status before any duplicate. AC was
independently online, battery 100%. No regression result is claimed yet.
See [REGRESSION_RESEARCH](REGRESSION_RESEARCH.md). No broker/paper authority.

## Verified v2 classification completion — 2026-10-13

V2 completed at 00:35:55 Pakistan (2026-10-12 19:35:55 UTC).
Release `51bce00fd0ce0ea0146877884c36eaa09055d23eff6bc337d453f065579542d7`,
report `ddc1dc0f6e6edd28b3193c2c37f438e44ac6b94e29e04c80112e3eeaa78aa44c`,
dataset `a9af101ab249424e0f92cdf6629a5cd4cea5c16d89fc395e6fe1a399b98a2805`.
Selected model `80fc55b5346c42fe2221ce80e1e612a982d43051bb8b2541598879b7e9b70557`.
Release and all 59 fold/final fits passed native verification; label-free saved
inference replay passed. V1 model hash stayed unchanged. CatBoost depth 6,
200 trees, class weighting (move multiplier 1) was selected by macro-F1 on the
same 744 later-2025 inputs: accuracy 53.63%, macro-F1 .3843. Majority accuracy
65.46%; no overall-accuracy advantage. Detailed evidence: [V2_RESULTS](V2_RESULTS.md).
No new final test, paper approval or deployment promotion. Earlier running
snapshots below are historical and superseded by this completion record.

## Historical v2 recovery — 2026-10-12

Latest operational state, 18:13 UTC / 23:13 Pakistan: user confirmed AC/lid
open and Win32 independently reports AC online. R7 had been suspended from
22:44:02 to 23:04:52 Pakistan and stopped with an expired task. Its complete
64-output batch passed independent FP32 sampled replay under child run
`adc9bf22-5518-47e7-b921-1c238c43ee5c`. Original run
`8ecd0046-d468-479a-9467-3d1becaabad6` remains held UNKNOWN/EXPIRED_ATTEMPT;
no original adapter retry or authority reset occurred. Archived R7 status is
`v2-status.r7-standby-error.json`. R8 launcher PID 18812 resumes the identical
binding, with `v2-build-r8.*.log`; check live status/lock before any new launch.
The guarded full suite passed 229 tests in 493.40s. An additional unstarted
context-task reconciliation rejection test brings focused coverage to 24 tests,
all passing in 26.09s. The final guarded full suite passed all 230 tests in
578.29s; lint and dependency checks pass. At 18:22 UTC the R8 owner PID 7324
had processed 8,768 / 26,833 headlines. This is a dated snapshot, not completion.

On Modern Standby/DC, Windows may end system-required requests five minutes
after the sleep timeout. AC is required for this long run; the request does not
override explicit Sleep or lid actions. No power plan/security changes were made.

Earlier operational recovery: R6 stopped at 3,520 / 26,833 headlines because
Windows Modern Standby events 506/507 suspended the host from 22:22:16 to
22:27:11 Pakistan. All 64 scores in the interrupted batch were present, with
matching immutable text/spec bindings. Independent sampled FP32 replay passed
under child run `dc64ded8-76ef-4e3c-882b-74ca856092c6`; its registered positive
receipt permits resume. The original run `a8434172-379e-4f07-8688-b5e1c78c0f96`
remains UNKNOWN / EXPIRED_ATTEMPT, without original adapter retry/reset.

Owned builds/reconciliation now hold a temporary Windows system-only idle-sleep
request and restore the previous thread state on exit/error. No display,
away-mode or permanent power-plan change; explicit user sleep/lid action is
respected. The regression run is also wrapped in the temporary guard. All 23
focused v2 tests pass in 25.12s; lint passes. The preceding full run had 222
passes / 5 shared-fixture setup errors during Standby; it is NOT a passed full
suite. Its subsequent guarded 229-test rerun passed; the latest state above
supersedes this historical R6/R7 snapshot.

Current experiment is D26's `financial-news-meaning/4` / `preopen-enriched/4`
headline-sentiment variant, recorded before any v2 stock-model fitting. The
full-text FP32 r3 pass was interrupted at about 2,896/26,835 texts because its
CPU cost exceeded the observed battery window. Its artifacts, status/lock
archives and logs are preserved; its interrupted native run
`05adcbb2-0f17-4f0c-be66-bf7f1e536134` was retained as WAITING_HUMAN / UNKNOWN /
EXPIRED_ATTEMPT, one attempt / one reserved unit, not reset or repeated.
Frozen FP32 weights are unchanged. Only headline text enters FinBERT; summaries
remain in TF-IDF, heuristic events and source/input artifacts. Blank cleaned
headlines have no sentiment, with explicit missingness.
Input-only word-count bucketing reduces padding. The final batch bound is 64;
a synthetic worst-length benchmark finished in 47.73s, well below the 300s
lease, with FP32 probability delta <=3e-8 versus batches of 16. Blank cleaned
headlines have no sentiment but valid full-summary event flags are retained.
New specification-bound cache
identities prevent mixing variants. See D26 and RESEARCH_V2 for the context
tradeoff and measured runtime diagnostic; it is not a model-quality result.

R4's 16-document headline pilot was interrupted at 2,896 / 26,833 texts before
any stock-model fit. Its logs and `v2-status.r4-headline-pilot-interrupted.json`
/ `v2-build.r4-headline-pilot-interrupted.lock` are preserved. No attempt is
reset. R5 stopped on a transient Windows status-file sharing violation before
news extraction: the last committed JSON and STOPPED temporary JSON are archived
as `v2-status.r5-reader-error.json` / `.tmp`. A bounded atomic-rename retry
(40 attempts, 50ms delays, status only) is checked for transient/permanent
failures. It never retries or resets native work. R6 resumed the identical
modeling binding `d677b38454b46ad6b0e26ee8fb0f30349225c15e920b1336fab7b140baf81610`;
owner was PID 16436 / launcher 16312 at 17:12 UTC. Recheck live identity.
Active status is `v2-status.json`; historical R6 logs are `v2-build-r6.*.log`; the r3 snapshot
and lock are `v2-status.r3-fulltext-interrupted.json` and
`v2-build.r3-fulltext-interrupted.lock`. Existing 194 verified source captures
were reused without refetching. The new corpus has 26,833 unique usable cleaned
headlines, with all 11,952 company-day rows retained. The earlier amendment
passed all 224 regression tests in 584.21s. The final bounded-batch/event checks
passed all 19 focused v2 tests in 30.93s and all 225 regression checks in 414.01s.
With the Windows status retry, all 21 focused checks pass in 40.09s; the final
full 227-test run had Standby setup failures; later guarded results are above.
No v2 predictive-model result is yet claimed. Do not duplicate the active owner.

Latest recovery evidence: the r2 builder stopped at 85/194 context queries when
the June 2021 source attempt outlasted its five-minute lease. Its eight saved
pages / 3,665 records were independently validated and reconciled under a
separate COMPLETED/PASS native task. The original expired UNKNOWN remains held;
no retry/reset or source refetch occurred. The r3 builder resumed and passed
139/194 queries at 16:20 UTC (21:20 Pakistan). Recheck live status rather than
treating this dated snapshot as current. Logs now use `v2-build-r3.*.log`.
The explicit recovery CLI and negative/positive reconciliation regression test
are implemented: all 17 v2 tests passed in 28.26 seconds; lint and dependencies
pass. The full suite passed 223 tests in 610.30 seconds. All 194 context captures
have matching positive receipts: 22,572 daily / 340,570 thirty-minute records,
98 / 744 immutable pages. At 16:31 UTC the news stage had processed 560 of
26,835 unique eligible texts. Real v2 training/results are not yet complete.

The user approved applying class weighting, richer market/company features and
financial-news meaning, then requested completion. See [RESEARCH_V2](RESEARCH_V2.md)
and D25 in [DECISION](DECISION.md). V1 datasets/models/test report stay unchanged.
V2 uses only the 11,952 audited 2018–2025 train/development rows; previously
exposed 2026 outcomes are not a new untouched final test and are not fitted here.

The six new v2 modules and CLI build/predict commands are implemented. The
first full regression run passed 221 tests; all 16 focused v2 checks now pass,
including source-entity projection and feature-chunk replay. The final full suite
passed 222 tests after those corrections. Dependency checks/lint pass.
Pinned optional CatBoost/Transformers/Torch dependencies are installed and
locked. FinBERT's pinned weights are cached; actual local inference succeeded.

The first v2 preflight was deliberately stopped before any v2 native task
started, to recover source company tags omitted by v1's compact news records.
Only owned processes were stopped; original logs and the dead owner's lock
were archived as `v2-build.interrupted-preflight.lock`. No failed/UNKNOWN task
was reset. The corrected run is active under
`data/research-v2-20261012/v2-status.json`; logs are
`v2-build-r2.stderr.log` and `.stdout.log`. The current owner was PID 20192,
launcher 16720, at 15:19 UTC; always recheck live identity, not these stale PIDs.
It was verifying 1,800/11,952 original rows then; no v2 model accuracy is yet
claimed. Native lease limits remain <=300s and features use 300-row chunks.

News sentiment is a frozen non-commercial FinBERT research feature with an
incomplete historic corpus audit. News-event flags are heuristic; verified
earnings calendar/consensus remain unavailable, explicitly null with flags.
The queued workflow collects SIP context, caches sentiment, constructs v2,
checks 18 settings on three folds and fits five calibrated final candidates.
Paper actions/deployment are forbidden; final_test_completed remains false.
Do not duplicate an active builder or remove its owner lock.

## Latest completed held-out test — 2026-10-12

The user asked to complete the next step after verified training. The real
held-out test is COMPLETE at 12:15:59 UTC (17:15:59 Pakistan), with matching
Trailforge COMPLETED/PASS, saved immutable predictions/report/test release,
checkpoint/event checksums, receipt and application manifest. Model parameters,
calibration and the validation-selected text_only candidate are unchanged.
The 1,104 examples span 184 complete six-company dates, 2026-01-05–2026-09-30.
See [FINAL_TEST](FINAL_TEST.md) for frozen identities, all metrics and limitations.

Accuracy / macro-F1: majority 51.72% / .2273; price-only 51.54% / .2294;
selected text-only 49.82% / .2927; combined 51.90% / .2978. Text-only is below
the majority accuracy baseline and detects only 7.31% of DOWN and 5.86% of UP
moves. Do not switch to combined or tune against the exposed test. Paper/trading
eligibility is explicitly FALSE; quality/deployment/policy gates remain open.
This is historical approximate retrospective evidence, not a pristine blind
test or investment performance claim. Earlier source QA may overlap 2026.

206 regression tests, lint and dependency checks pass. Private runtime status
is `data/real-2018-2026/real-evaluation-status.json`; separate evaluation artifacts
and SQLite ledgers preserve prediction-before-outcome evidence. No evaluation
lock/process should be active after completion. Training status/release are not
overwritten by this test. Source/data rights remain user attestation.

Next product step: integrate the verified research results and chronological
saved predictions into the dashboard. The current UI is still FIXTURE-only;
do not claim that this evaluation promoted it or authorized broker orders.
All running/pending statements below are historical dated snapshots.

## Latest training completion and test stage — 2026-10-12

Training completed at 11:10:25 UTC (16:10 Pakistan). All four real comparison
models are saved; Trailforge COMPLETED/PASS and matching artifacts/receipts/job
were checked. Train rows: 10,458; calibration: 744; selection: 744. Frozen
selection is text_only by validation macro-F1, not highest validation accuracy.
See [FINAL_TEST](FINAL_TEST.md) for release/model hashes and the preregistered
held-out evaluation. All earlier running-training snapshots below are historical.

The user asked to complete the next step, authorizing offline held-out testing
of this frozen release. The new research-evaluate path commits input-only
predictions before opening outcomes, verifies label lineage and metrics, and
keeps model parameters/selection unchanged. There are 1,104 usable test rows
across 184 complete dates, 2026-01-05 through 2026-09-30. Real final-test results
are not claimed until the new evaluator completes with typed verification PASS.

## Latest repair and resume — 2026-10-12

Collection is now complete: 13,056 accepted rows through 2026-09-30, with
20 quarantined whole-date groups (120 excluded rows). The full audit has no
missing required rows, lineage errors or batch failures. Its remaining strict
raw warning is 115 cross-split exact-headline groups, eligible only for the
user-approved masking research route. See [REAL_DATA_RUN](REAL_DATA_RUN.md).

Initial training preparation stopped before fitting: 100,367-byte inline row
rosters exceeded the Trailforge adapter's 65,536-byte default. The user asked
to fix and resume. Complete ordered lists now live in an immutable private
roster manifest, with only its digest/counts in task inputs. Default limits,
dataset, labels, splits and model settings are unchanged. Previous failure
evidence and the old pending no-run-ID job remain preserved.

At 10:51 UTC the repaired hidden `research-train` task started, using the same
saved report-bound authorization and no network collection. It reverifies
11,952 train/validation rows before fitting; final-test artifacts stay sealed
from fitting. Current status is `data/real-2018-2026/real-build-status.json`;
NEW live logs are `real-training-resume.stderr.log` / `.stdout.log` in the same
directory. The owned launcher was PID 14688 when started. An exclusive
`research-training-resume.lock` belongs to this running resume: do not remove
it or start a duplicate. Phase/row counts distinguish loading from fitting.

Twenty focused training/masking/resume tests passed. The full regression suite
passed 202 tests, with one upstream Starlette/httpx deprecation warning; lint
and dependency checks passed. Eight staged paths had zero credential findings.
At 10:57:57 UTC the active resume had verified 4,500 of 11,952 saved rows;
owned launcher/child PIDs were 14688/13104. No trained real release is claimed yet.
Check actual saved model/harness results before changing that statement. All
dated collection-running statements below are historical snapshots.

## Latest override — 2026-10-12 real-data run

The user explicitly confirmed data permissions, requested real dataset/model
training, and approved whole-date quarantine for confirmed missing outcome
boundaries. This supersedes the older rights hold below. Rights evidence is
user attestation, not an independently verified grant. The larger private
experiment covers 2018–2024 train, 2025 validation, Jan–Sep 2026 final test:
13,176 planned company-day rows before exclusions. Fixed six stocks, separate
SPY context, pre-open inputs and the fixed 1% minute-proxy target remain intact.

Read [REAL_DATA_RUN](REAL_DATA_RUN.md) for policy, immutable contract identity,
model methods and boundaries. Real Alpaca/Benzinga collection is running under
Trailforge. The strict run stopped at 2018-05-02 after 498 rows; the authorized
quarantine experiment preserves those captures, excludes whole failed dates
with immutable evidence, and resumes collection. No real fitting results exist
at this checkpoint. No failed/UNKNOWN authority record was erased or reset.

The hidden `research-build` process writes private status/logs under
`data/real-2018-2026`. Check `real-build-status.json`, owned process identity,
SQLite counts and Trailforge receipts before restarting. Never run two builders
against the same directory. The completion runner only fits a complete audited
roster; errors/holds still stop it. The user also approved earlier-date story
masking: strict raw duplicate evidence remains recorded, but complete duplicate-
only rosters can enter explicitly authorized masked research fitting. Preprocessing
uses earlier input metadata only, never future labels; training/vocabulary and
final-test seals remain intact. See REAL_DATA_RUN for policy and scope. The new
research-only fit/score path accepts HISTORICAL_APPROXIMATE, whereas the existing
fixture API/dashboard still accept FIXTURE only. Do not mislabel the UI as real.

Explicit user-authorized offline fitting is separate from human dataset quality
promotion: research releases report human_dataset_reviewed=false and prohibit
deployment/paper action. M03/M04/M05/M06/M08 stay open until their actual remaining
criteria are met. The old agreed contract remains an unchanged historical draft.
Later sections below retain their original dated stage evidence.

Latest verification: 198 tests, lint and dependency checks passed. The source/
documentation staged scan covered 25 paths with zero credential findings. At
2026-10-12 06:34:36 UTC, real collection had 3,300 rows through 2020-03-27 and
13 excluded date groups; fitting had not started. The masked build intent is
recorded in REAL_DATA_RUN and the current private runtime status. Keep the
computer awake for the managed run. Earlier source QA may overlap 2026 dates;
the fit/selection test seal is not a claim of a never-inspected blind period.

The implementation is pushed as `7fedc5861b3c6d93c5808f500786ff3f86b9595b`;
[its CI run](https://github.com/codera647/MarketPulse/actions/runs/38214154024)
passed. At 2026-10-12 06:53:36 UTC the active background run had 4,938 rows
through 2021-04-29 and 14 quarantined date groups, cycle 1/batch 12. Real fitting
had not started. Verified owned launcher/child PIDs were 10388/5684; these are
not permanent identifiers. The task continues independently and automatically
audits and fits if eligible. Consult the live private status before acting;
do not duplicate this running build or mistake this progress snapshot for
completed training. No empirical milestone was closed.

Last checked: 2026-10-11 (Asia/Karachi). This is a handoff record, not a claim
that the whole product is built or a complete historical dataset is validated.
M02 now has bounded live IEX/historical SIP access evidence.
M03 software is now implemented and tested, but the user explicitly holds
bulk collection/training until data rights are confirmed. Read [DATASET](DATASET.md)
for the agreed research plan, current code path, and evidence.
M04 baseline software and the connected collection-to-training workflow are
implemented locally; see [BASELINES](BASELINES.md) and [PIPELINE](PIPELINE.md).
This includes human dataset promotion and a reviewed real-data loader, but no
real dataset/model run. It does not clear the M03 rights hold or establish
market-model performance. User screenshots confirm the Basic plan; see
[PERMISSIONS](PERMISSIONS.md) for positive ML documentation and remaining terms.

LATEST: the local **synthetic full demo** now includes four-model comparison,
separate calibration/policy date segments, Trailforge verification, immutable
forecast decisions, explicit outcome reveal, FastAPI, Streamlit and credential-
free fixture backup/restore. See [DEMO](DEMO.md) and [RELEASE](RELEASE.md).
The user requested autonomous project completion on 2026-10-11; this did not
change the earlier explicit rights hold. No real bulk dataset/model was built.
The fixture comparator/service deliberately reject real research tiers. A
complete real-data news training/serving extension is still remaining work.
Historical statements below describe their original implementation stage;
the latest verification/delivery section at the end takes precedence.

## Project in one minute

MarketPulse is a six-company US-stock prediction **research and paper-demo**
project. The agreed target companies are AAPL, NVDA, AMZN, JPM, XOM, and WMT;
SPY is market context and a benchmark, not a seventh company prediction.
The proposed daily decision time is **09:00 America/New_York** on NYSE trading
days. Using only information available by then, a future model will estimate
`UP`, `DOWN`, or `NO_MATERIAL_MOVE` for that day's regular-session
**open-to-close** return. A separate deterministic policy may eventually say
`PAPER_LONG`, `ABSTAIN`, or `BLOCKED`. No real trading, broker orders or fitted
market model exists. A fixture-only prediction API and dashboard now exist.
The forecasting target and market policy
threshold are still provisional and require data/evaluation evidence.

Update: the user has approved a fixed 1% research label threshold and
July–December 2025 training, January–March 2026 validation, April–September
2026 final-test dates. Paper-action thresholds remain unselected. The new
outcome convention is an explicit first/last regular-minute proxy, not an
official-auction or executable-fill claim. See D16–D18 in [DECISION](DECISION.md).

The supplied production-AI thinking framework guides the planning and evidence
gates; it is not a substitute for the user's instructions. The user explicitly
requires their [Trailforge](https://github.com/codera647/Trailforge.git) harness
for the agent and requested [Agent-Reach](https://github.com/Panniantong/Agent-Reach.git)
for internet access. The implemented extraction slice uses both within their
actual capabilities.

## Workspace and starting points

- Project root is **`F:\MarketPulse`**. The environment supplied
  `F:\US_Stock_Prediction` as a cwd, but that path was checked and does not
  exist. Do not silently start a second project there or move existing files.
- This directory is a Git repository on `main`, tracking `origin/main` at
  [codera647/MarketPulse](https://github.com/codera647/MarketPulse), a private
  repository. The initial source commit `8009cbd` was pushed on 2026-10-10.
  All nine GitHub milestones exist; M00/M01 cover repository setup and the
  fixture-tested foundation, not live data or trained models. The connector
  verified account/repository access; creation used the GitHub API with
  existing local Git authentication because the connector lacks those tools.
  The local `.env`, `.evn`, `.venv/`, generated `*.egg-info/`, and `data/` are
  ignored by `.gitignore`. See [MILESTONES](MILESTONES.md) for the delivery plan.
- Read [PRD](PRD.md), [DESIGN](DESIGN.md), [ARCHITECTURE](ARCHITECTURE.md),
  [DECISION](DECISION.md), [EXTRACTION](EXTRACTION.md), and
  [TRAILFORGE_INTEGRATION](TRAILFORGE_INTEGRATION.md) before changing the
  contract. [BUILD_ORDER](BUILD_ORDER.md) and [TASKS](TASKS.md) list the
  remaining stages. [Project README](../README.md) has setup/run commands.

## What is implemented now

| Area | Current implementation |
| --- | --- |
| Python package/CLI | `pyproject.toml` and `src/marketpulse/cli.py`; `marketpulse extract --session ...` and bounded `backfill --start ... --end ...` (up to 31 exchange sessions per invocation). |
| Market sources | `config.py` loads literal local `.env` or process values without exposing keys; approved data host only, trading endpoint recognition without use, and no redirects. `alpaca.py` calls historical news/daily bars with bounded pagination, response-size limit, retries/timeouts, request IDs, and sanitized provider failures. |
| Calendar and eligibility | `clock.py` uses the NYSE calendar and timezone-aware UTC; `normalize.py` rejects same-day/future bars and post-cutoff article versions, checks OHLC and at least 21 distinct prior bar dates per symbol by default with the latest bar on the previous session, and builds six hash-identified snapshots. The feature gate additionally requires 21 consecutive exchange sessions. |
| Raw and product storage | `storage.py` saves content-addressed raw JSON plus normalized article/bar metadata, web captures, extraction jobs, and snapshots in application SQLite. Extraction materialization is one application-DB transaction. No Parquet training export exists yet. |
| Trailforge | `extraction.py` uses pinned neutral `Goal`/`Task`/`Harness` with explicit `CANDIDATE_WRITE` fetch tasks and a typed `VerifiedResult` check. Trailforge has its own SQLite authority. Only a `COMPLETED` verified run can materialize accepted product snapshots. UNKNOWN provider outcomes are held, not silently retried. |
| Agent-Reach | Pinned `WebChannel` is wired to opt-in `--web-url` capture through Jina Reader. It is supplementary evidence, **not** the canonical historical price/news source or an automatic prediction feature. No social-cookie/login channels or system-wide installation were used. |
| Provenance | Manifest records source/feed/adjustment, cutoff and news query end, article/bar counts, six snapshot hashes, availability tier, freshness flag, and Trailforge receipt IDs. Historical retrieval is `HISTORICAL_APPROXIMATE`; a genuinely recorded pre-cutoff capture can be `RECORDED_STRICT`. `fresh_for_0900` is a separate provisional five-minute freshness check. |
| Source audit | Dated ordinary, post-earnings, early-close, holiday and revision-candidate audits passed for IEX and historical SIP. Includes observed schema/types, page traversal, required-21-session gaps, request IDs, and separate verified outcome probes. Reports remain `TECHNICAL_REVIEW_REQUIRED`; see [M02 evidence](M02_SOURCE_AUDIT_2026-10-10.md). |
| Provisional label preview | `marketpulse label-preview` reads one saved pre-open snapshot and one separate verified outcome job. It validates matching session/feed/adjustment, immutable raw outcome pages and post-close receipt, then computes the symmetric `UP`/`DOWN`/`NO_MATERIAL_MOVE` class under an explicit threshold. It writes nothing and always marks the result not ready for training. See [LABELS](LABELS.md). |
| Pre-open feature preview | `marketpulse feature-preview` uses one shared `build_features` function on a saved snapshot. It validates raw-version agreement and 21 consecutive prior NYSE sessions, then outputs versioned lagged company/SPY price features and simple headline-count features. No outcome or Agent-Reach capture is an input. It writes nothing and is not a fitted model. See [FEATURES](FEATURES.md). |
| Separate regular outcomes | `outcomes.py` and `regular-outcome` use a Trailforge fetch/VERIFY Goal for regular-session minute bars. Exact opening/last-minute presence, pagination, OHLCV, source/request, post-close receipt and all seven symbols are required. `session_outcomes` is separate from prediction bars; cached reads verify raw hashes, actual harness receipts and ledger agreement. |
| Dataset software | `dataset.py`, `dataset-plan` and `dataset-batch`: approval gate before credentials/network, <=31 eligible sessions/batch, frozen contract/calendar/source versions, immutable company-date JSON rows and conflict-rejecting SQLite indexes, no-news rows, completeness/date/ticker/null/gap/lineage/duplicate reports. Synthetic fixture datasets only so far; no real bulk training dataset. |
| Baseline software | `baselines.py`, `baseline_fixtures.py`, `baseline-demo`: synthetic majority/price checks; separate `research.py` and `baseline-train` require explicit promoted real data. Shared train-only median/scaling, safe JSON scoring and validation, sealed test artifacts, Trailforge fit/evaluate/VERIFY. No fitted market model, calibration or paper-action authority. |

External packages are pinned by Git commits in `pyproject.toml`:
Trailforge `v0.1.0a1` at
`fbefaf40fb39a1429dcc328184372214f9fd849d`, and Agent-Reach at
`94f06c1969dfc1834001269d79d3ad0972d9dee6`. Transitive packages have
version ranges, not a fully locked deployment file.
The interrupted baseline setup added and installed `scikit-learn==1.9.1`;
M04 uses it for fixture fitting and the new promoted real-data baseline path.
The latter has only synthetic wire-test evidence; no fitted market model exists.
The new `requirements.lock.txt` snapshots the tested Python 3.13 fixture-demo
environment, with exact FastAPI/Streamlit/uvicorn versions and pinned Git inputs.

## Verification performed

An isolated project `.venv` exists. Before the connected pipeline update,
these commands passed (latest result is in the update at the end):

```powershell
cd F:\MarketPulse
.\.venv\Scripts\python -m pytest -q
# 118 passed in 103.17s
.\.venv\Scripts\ruff check src tests
# All checks passed!
```

Tests in `tests/test_extraction.py`, `tests/test_audit.py`, and
`tests/test_labels.py`, and `tests/test_features.py` use synthetic provider responses. They
exercise successful extraction, empty-but-healthy news, missing/future bars,
strict versus early forward capture, optional Agent-Reach isolation, provider
UNKNOWN and no silent retry, pagination, post-cutoff revisions, idempotence,
NYSE session/early-close behavior, source-audit coverage, separate outcome
probing, missing-outcome blocking, and a read-only provisional label with
hand-checked symmetric class boundaries, raw-source feature consistency,
21-session rolling-window coverage, and no-news feature handling. New tests
cover dotenv loading, redaction, endpoint/redirect refusal, sanitized failures,
pagination caps, audit rolling gaps, and relative read-only preview paths.
Fixture tests validate code paths, not financial predictive value.

New M03 tests in `test_outcomes.py` and `test_dataset.py` cover exact regular
boundaries/early closes, malformed minutes and pagination, UNKNOWN/no retry,
separate outcome storage, approval/date/embargo gates, resumable immutable
rows, 1% boundary neutrality, healthy no-news, cross-split duplicate detection,
and missing/corrupt lineage. Bounded calendar computations are cached within
a process; frozen dataset identities bind the calendar version and split map.
`pip check` also passed. No new GitHub CI is claimed for unpushed M03 work.

Latest update: M03 was pushed at user request as commit
[`546f8d3`](https://github.com/codera647/MarketPulse/commit/546f8d3bb726391047f834460bc7247c1800d7eb),
with remote `main` matching and a clean worktree at that point. Its staged
scan checked 17 files with no secrets or forbidden tracked artifacts. M03 was
not closed. No verification of that commit's GitHub CI is claimed here.
Current M04 and connected pipeline work is local and has not been committed/pushed.

The 30 new `test_baselines.py` tests cover training-only preprocessing,
JSON/sklearn scoring parity, named class distributions and hand-calculated
majority metrics, train/validation exclusion, final-test read refusal,
chronological complete date groups, fixture/real separation, malformed
features/models, missing classes, altered-candidate failure, UNKNOWN/no retry,
idempotence and credential-free CLI execution. A local seed-42 demo completed
through Trailforge with 84 training and 24 validation examples; its 24 test
artifacts were not read by fitting/evaluation/verification. Synthetic price/
label relationships are manufactured; never call their scores market accuracy.

The initial GitHub commit `8009cbd` also passed the Windows/Python 3.13
[CI run](https://github.com/codera647/MarketPulse/actions/runs/38035607436):
dependency installation, lint, and fixture regression tests all succeeded.
The committed-content scan checked 41 files against locally supplied secret
values and token/private-key patterns without printing any secret. `.env`,
`.evn`, `.venv/`, and `data/` were not tracked.

A credential-free audit plan was generated with an ordinary session,
early-close session, and holiday. It is marked `NOT_RUN` and lists missing
earnings and correction examples; it is not a live-data verdict.

M02 live audits subsequently passed for both feeds on four distinct sessions:
2026-10-09, 2025-08-04, 2025-08-01, and 2025-11-28; 2025-11-27 was calendar-only.
All seven price symbols had prior bars and separate verified outcome bars,
with no required-window gaps. Six recent SIP snapshots passed the actual
feature builder. Source choices, local report paths/hashes, successful news/bar
pagination, and the preserved page-cap failure are in
[M02 evidence](M02_SOURCE_AUDIT_2026-10-10.md). `.env` was not modified or exposed.

M02 code commit [`02ac97b`](https://github.com/codera647/MarketPulse/commit/02ac97bcd3f161ff53a8baa3774a11c09fb31686)
was pushed, and its [GitHub CI](https://github.com/codera647/MarketPulse/actions/runs/38037607123)
passed installation, lint, and tests. Remote M02 is closed. The staged secret
scan checked 22 files, and the local-artifact scan checked 101 files without
finding credential values. Raw captures and SQLite authorities remain local.

M03 performed only two bounded SIP/split outcome probes, no new news capture:
2025-11-28 has 210/210 regular minutes for all seven symbols, 2026-10-09 has
390/390, both with zero gaps. They were saved to `data/m03-probe/` and both
cached jobs passed updated raw/ledger/harness-receipt checks. The second date
is outside the final-test period. Details/job IDs are in [DATASET](DATASET.md).
No source-bearing artifact or credential belongs in a commit.

## Unverified gates and honest limitations

1. **Source access is sampled, not complete dataset/target certification.**
   Local credentials load safely and both IEX/historical SIP work on the audited
   dates. Basic-plan identity is now confirmed by the user's screenshot;
   subscriber classification, recent/live SIP rights, monthly coverage, corporate
   actions, rate ceilings, retention/training/sharing rights, and the actual
   official opening/closing prices remain uncertified. The earlier manifests mark
   daily bars `PROVIDER_DAILY_NOT_CERTIFIED_REGULAR_SESSION`. Do not train
   regular-session labels from them without verifying the convention or an
   explicitly approved change in target. The new minute proxy is separately
   documented and technically sampled, not certified as official auctions.
   Article bodies were not requested. On 2026-10-10 the user explicitly said
   rights are not confirmed and to keep bulk collection gated.
2. **Historical news is not proven point-in-time.** A current API response may
   not reproduce what an article said at 09:00 on an old date. Keep such replay
   labeled approximate. Do not train/evaluate as if revisions or original
   receipt times were known.
3. **Agent-Reach's actual web network path is not live-tested.** Tests inject a
   stub reader. Its Jina Reader path sends an opted-in public URL to a third
   party; verify source rights and response quality before use. It cannot
   replace Alpaca bars or certify historical article availability.
4. **Cross-store recovery has a known orphan window.** A crash after
   `Harness.start` but before the product DB records the run ID may create a
   second harness run on retry. Idempotent product records do not imply
   exactly-once external calls. Audit/reconciliation and backup/restore still
   need a real fault-injection exercise.
5. This slice has **no complete real labeled dataset, fitted market model, paper policy,
   FastAPI, Streamlit UI, scheduler, or real-order capability**. Separate
   outcome storage and immutable JSON dataset-row software now exist; only
   fixtures materialized research rows. Fitted fixture baselines now exist,
   but cannot score real input tiers or authorize paper action. M03/M04 remain open.
   Do not describe fixture tests or Trailforge completion as model accuracy or
   production certification.

## Recommended next agent action

GitHub setup and the M02 technical audit are complete. Next is M03 (a complete
labeled historical dataset), subject to the open gates below. User
authorization to commit/push at each completed
milestone is recorded in root `AGENTS.md`. Update this checkpoint and
`MILESTONES.md`, verify acceptance criteria, scan staged content for secrets,
push normally, and only then close the matching GitHub milestone. The
Windows/Python 3.13 GitHub Actions workflow passed for the initial commit;
verify subsequent commits independently rather than assuming they are green.

Read [DATASET](DATASET.md) and the committed draft contract first. The dates
and 1% threshold are agreed; `plan_approved` is true, `rights_confirmed` false.
Do not infer rights confirmation or bypass the hold with low-level backfill.
The safe `dataset-plan` command reports 1,878 rows across 313 usable dates,
with a one-session validation/test-boundary embargo. Once the user confirms
rights with a non-secret account-review reference, create a private approved
contract and run monthly `dataset-batch` invocations using one data directory.
Review full coverage, corporate actions, interior gaps, exact duplicate and
semantic-event leakage, and historical point-in-time limitations. Do not
inspect final-test labels while tuning. Dataset reports remain research-review
required until human promotion. M04 fitting/scoring, report-bound human
promotion and the reviewed-data loader are implemented. Use the commands in
[PIPELINE](PIPELINE.md); collection resumes from verified missing dates and
training/validation/verification cannot open final-test row artifacts. Keep
Agent-Reach captures outside model inputs. M03 must not be closed/pushed as
complete without the real dataset and acceptance evidence. Its in-progress
software checkpoint was pushed at the user's explicit request on 2026-10-10;
the rights hold remains in force. The next safe command is `baseline-demo`,
which generates its own synthetic inputs with no `.env` or network access.
Continue only synthetic/software work until the user confirms rights; then
complete M03 before real M04 validation. Current M04 changes are local; neither
M03 nor M04 is complete. Verify each pushed commit's own CI before claiming
GitHub checks passed.

## Connected pipeline implementation update

New `research.py` and CLI commands: `pipeline-plan`, `pipeline-collect`,
`dataset-inspect`, `dataset-promote`, `baseline-train`. Collection uses bounded
20-session/default-one-batch runs (explicit maximum 50 batches), honors the
existing rights gate before credentials, stops held/failed work, and never
automatically trains. Human review records bind exact current contract/report
hashes with corporate-action, semantic-event, outcome-gap and approximate-
history evidence. The committed review template is deliberately unapproved.

Baseline training shares the fixture implementation without changing data
tiers. Real-path loading rechecks train/validation raw features, separate
outcome/input harness receipts and the complete promoted row index. Final-test
row/outcome artifacts remain unopened by training, validation, verification
and cached-run reuse. Safe JSON parameters and uncalibrated research outputs
never authorize paper or real trading.

The credential-free plan ran successfully: 16 bounded chunks covering the
agreed 313 sessions / 1,878 rows. Initial targeted baseline/research tests passed
51 cases in 189.27 seconds. The final full suite passed **139 tests in 299.01
seconds**, including the tightened input-receipt revalidation. Ruff and
dependency checks pass. The changed-file credential scan checked 17 files
and found zero hits; no forbidden provider/credential artifacts are tracked.
No real bulk collection,
real-data fitted model, support submission, account change or gate removal
occurred. M03/M04 remain empirically open, so no completion push/closure is due.

## Full synthetic application update — 2026-10-11

Implemented `modeling.py`, `demo.py`, `service.py`, `api.py`, `ui.py` and
`backup.py`; commands are in [DEMO](DEMO.md). The private demo is in `data/demo`,
isolated from provider data. Default release has 84 training, 12 calibration,
12 policy and 24 test rows from synthetic 2024 dates. Only after fit/calibration/
policy freeze are synthetic final-test rows opened. Text uses train-only
TF-IDF; all four models save safe JSON parameters with calibrated probabilities.
Fixture policies never authorize broker actions or establish market quality.

The default synthetic release is
`e67ff500133855356c86d310484af0d9e6ecac6d9ad81d3dbf356d7dd11e1bb4`.
Its build run is `f5aafc91-5069-4614-b8b7-e4af034b3986`. These are local artifact/
harness identities, not provider or account secrets. Forecast adapters load
input-only stores. Immutable decisions resolve original model/policy/input
hashes and typed verification receipts; reveal uses a separate outcome store.

Requests are idempotent, accepted positions are transactionally bounded and
known verified runs can repair missing product records after a crash. Unknown
tasks stay held. The start/run-ID cross-store window remains possible. Backup
requires other processes quiesced; restore refuses existing destinations and
checks file hashes, database integrity and saved decision/outcome identities.

FastAPI and Streamlit launch on loopback only, no credentials required. The
dashboard exposes replay, audit, explicit reveal, matched fixture evaluation,
operations and failure fixtures. Initial test run passed 27 new cases and caught
a decimal-string outcome formatting error in the UI; this was fixed before
final regression. Final full suite: **170 passed in 203.79s**, one upstream
Starlette/httpx deprecation warning (not suppressed). Ruff and pip check pass.
The dashboard interaction was verified headlessly with Streamlit AppTest;
no browser visual inspection is claimed. Live local `/health/ready` returns
FIXTURE-ready and Streamlit `/_stcore/health` returns HTTP 200 `ok`.

Background services were started hidden on the user's machine: API launcher
PID 16300 and dashboard launcher PID 14716; listening child PIDs were 6104
(API) and 12552 (UI) when checked. These PIDs are not permanent identities. URLs:
http://127.0.0.1:8000/docs and http://127.0.0.1:8501. Logs are ignored under
`data/demo-*.log`. Do not kill unrelated processes if ports later change owner.
No provider collection, real training, account changes or order submission ran.
Git delivery evidence is recorded after final source/credential inspection.
The staged source/docs scan checked **31 paths with zero findings**; `.env`,
`.evn`, data, databases, model artifacts and logs were not staged. Additional
tests prove full-demo repeated runs reuse their release/run and healthy empty
news/unknown tokens do not expand training vocabulary. M07's local synthetic
API/demo acceptance is satisfied; other empirical/forward-release criteria
remain explicitly open. Do not infer real model completion from this delivery.

Software delivery commit:
[`9e73e3e`](https://github.com/codera647/MarketPulse/commit/9e73e3ecea443452e567594dbf761deb2f2fc56d).
The 31-file source/docs update was pushed normally to private `main`;
the worktree was clean after the push. GitHub CI for that exact commit is
[run 38143063435](https://github.com/codera647/MarketPulse/actions/runs/38143063435).
The GitHub connector verified **success** for this exact source commit: clean
Windows/Python 3.13 dependency-snapshot installation, pip check, lint and full
fixture regression all passed in job `114480697849`. This is independent
fresh-runner evidence, not a live-data certification. Follow-up documentation
records these results; no source changes followed the verified software commit.
No market-data milestone was closed merely from fixtures.
[M07](https://github.com/codera647/MarketPulse/milestone/8) was closed after the
source push and local API/demo acceptance evidence, explicitly scoped to a
FIXTURE-only demonstration. M03/M04/M05/M06/M08 remain open for their respective
real-data/forward/release evidence, despite substantial implemented software.

Real HTTP smoke checks (not TestClient) also returned the expected fixture
AMZN PAPER_LONG, AAPL deliberate DOWN→UP miss, JPM TIMEOUT→WAITING_HUMAN
with null action, XOM STALE→BLOCKED, and NVDA neutral→ABSTAIN. Repeat requests
reuse their decision/run. No synthetic performance number was interpreted as
market accuracy. The unchanged `pipeline-plan` still reports rights_confirmed
false, ready_for_training false, network_used false and the agreed 1,878 rows.
