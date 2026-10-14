# GitHub delivery milestones

2026-10-14: user made repository public while retaining private data/results.
Cloud schema 0001/0002 passes 13 rollback-only review-branch checks and is migrated
to production. Forty-eight focused cloud/dashboard tests and lint pass. Compact
read-only web UI, private-object/native checkpoints and reviewed-main preflight
workflow implemented; live worker/deployment verification remains pending.
Schedules, model promotion and broker orders remain disabled. No GitHub research
milestone closure is claimed by this implementation stage.

2026-10-13: local real research dashboard extends the M07 presentation surface
with five evidence-led views, saved prediction reveal, charts and read-only
native operation checks. Default research mode is separate from `--mode fixture`.
See DASHBOARD / CHECKPOINT for verification and browser-QA limitations. This
does not close human data quality, strict point-in-time, forward evaluation,
paper-policy or deployment gates. No new GitHub milestone closure is claimed.

2026-10-13: news/market specialists now have verified empirical completion,
13/26 fits and saved input-only inference. D31 freezes the requested nested
stacking experiment in STACKING_RESEARCH; 57 focused checks, lint, dependencies
and staged credential scan pass. Full suite was not rerun for D31. This does
not close human quality, forward-test, paper or deployment
requirements. No new GitHub milestone is claimed complete.

2026-10-13: D29 price expert completed 10:15 Pakistan, 27 fits and all three
saved classifiers positively verified; XGBoost selected by macro-F1 .400588,
not overall accuracy (52.96% versus neutral-only 65.46%). D30 implements isolated
news/market experts, with 54 focused context/price/v2/regression/boosting checks,
lint and dependency checks passing. Full suite was not rerun for D30.
See PRICE_EXPERT / CONTEXT_EXPERTS / CHECKPOINT for exact launch/status evidence.
No fresh blind-test, human quality, paper or deployment gate is closed.

2026-10-13: D27 regression completed with 56 verified fits and saved input-only
inference. Full suite passed 240 tests; no model beats zero-return RMSE.
No quality/paper/deployment gate closed. User's D28 boosting request is now
implemented; 41 focused checks and the full 247-test suite passed.
The full run reported 179 warnings including SQLite connection resource warnings.
Real boosting completed 09:05:07 Pakistan with all 39 fits verified and saved
input-only inference passed. None beats zero-return RMSE, all have zero UP/DOWN
recall. Quality, human data approval, paper and deployment gates remain open. See
[REGRESSION_RESEARCH](REGRESSION_RESEARCH.md) and [BOOSTING_RESEARCH](BOOSTING_RESEARCH.md).
Earlier launch snapshots below are historical, not current completion state.

2026-10-13 regression stage: five continuous-return model families, bounded
chronological search, native verification and saved inference are implemented;
nine focused checks pass and the full 239-test software suite is running.
Real source preflight/training has started in `data/regression-20261013`.
See [REGRESSION_RESEARCH](REGRESSION_RESEARCH.md). No regression quality claim
or promotion gate is closed.

V2 classification completed at 00:35:55 Pakistan on October 13. All 59 fits and
the saved release have native COMPLETED/PASS verification; saved label-free
inference passed. Results/limitations are in [V2_RESULTS](V2_RESULTS.md).
The selected CatBoost classifier does not beat neutral-only overall accuracy.
No new final-test claim or human/deployment approval. Historical snapshots below
are retained, not current status.

Latest v2 recovery evidence, 2026-10-12: guarded full suite passes 230 tests in
578.29s; 24 focused v2 checks pass. Lint and
dependencies pass; all 194 real context captures are verified. The expired
source attempt remains UNKNOWN with a separate complete-capture reconciliation
receipt. Complete expired sentiment captures have separately verified child
receipts; original UNKNOWN attempts stay held. AC is independently verified
online after user confirmation. R8 resumes news enrichment; real v2 training/results are not yet
complete. See [RESEARCH_V2](RESEARCH_V2.md). No promotion gate is closed.

Earlier v2 software evidence, 2026-10-12: enriched/weighted research CLI, source
captures, financial sentiment, feature chunks, chronological model search and
saved inference are implemented; 222 regression tests, lint and dependency
checks pass. The authorized first real v2 run is still in source preflight.
No v2 accuracy improvement or new blind test is claimed. See [RESEARCH_V2](RESEARCH_V2.md).
V1 evidence below remains unchanged; human quality/deployment gates stay open.

Latest completed 2026-10-12 research step: training and the frozen held-out test
are verified COMPLETED/PASS. Test covers 1,104 examples / 184 complete dates;
selected text model accuracy is 49.82% versus majority 51.72%, with poor UP/DOWN
recall. All four models and results are saved; no test-driven reselection/refit.
206 tests, lint and dependency checks pass. See [FINAL_TEST](FINAL_TEST.md).
Human quality/policy/deployment promotion remains unverified; paper eligibility
is explicitly false. Earlier running statuses below are dated snapshots.

Latest 2026-10-12 evidence: real collection/audit now has 13,056 accepted rows
and 20 excluded whole-date groups. The training-size integration fix and an
offline resume are implemented; saved-input verification is running. Human
quality review, actual model results and release criteria remain unverified.
See [REAL_DATA_RUN](REAL_DATA_RUN.md); no additional milestone is closed yet.

2026-10-12 update: user-confirmed data rights now permit the larger private real
collection, and the user approved verified whole-date coverage exclusions.
Four-model research-only training and a completion runner are implemented;
collection is in progress, not a completed empirical milestone. See
[REAL_DATA_RUN](REAL_DATA_RUN.md). M03/M04/M05 remain open; the older held statuses
below describe their prior stage. No human quality review or model performance
is inferred from synthetic tests or source access.

Requested on 2026-10-10: create the project repository on the user's GitHub
and commit/push the code at each completed milestone. The private repository
is [codera647/MarketPulse](https://github.com/codera647/MarketPulse), with
`main` tracking `origin/main`. The initial source commit
[`8009cbd`](https://github.com/codera647/MarketPulse/commit/8009cbd9bdb8196d329b1213051c15addd793d5f)
was pushed successfully on 2026-10-10.

All nine definitions in [github_milestones.json](github_milestones.json) were
created as [GitHub milestones](https://github.com/codera647/MarketPulse/milestones).
No due dates are invented. The connector verified the authenticated account
and repository permissions. Repository/milestone creation used GitHub's API
with existing local Git authentication because those operations are not
exposed by the connector; Git pushed the existing local history normally.

| Milestone | Completion evidence | Current local status |
| --- | --- | --- |
| [M00](https://github.com/codera647/MarketPulse/milestone/1) Repository and delivery workflow | Private GitHub repository and nine milestones exist; initial push succeeds; CI is configured; committed content credential scan passed for 41 files | Complete; closed on GitHub after evidence push |
| [M01](https://github.com/codera647/MarketPulse/milestone/2) Extraction and feature foundation | Trailforge extraction/audit, versioned snapshots, provisional label and pre-open feature previews pass 25 fixture regression tests and lint; code pushed | Complete; closed on GitHub using fixture evidence, not live-data certification |
| [M02](https://github.com/codera647/MarketPulse/milestone/3) Live data access and source audit | Safe dotenv loading, both historical feeds, 7/7 price coverage on four sessions, real pagination, dated source decisions/gaps, 51 tests and lint; see [audit](M02_SOURCE_AUDIT_2026-10-10.md) | Complete; closed after commit `02ac97b` was pushed and GitHub CI passed; rights/target gates remain open |
| M03 Complete labeled historical dataset | 13,056 real research rows, 20 excluded date groups, complete audited roster, raw duplicate evidence and authorized masking; see REAL_DATA_RUN | Real research collection complete; human corporate-action/semantic/point-in-time quality promotion remains open |
| M04 Majority and price baselines | Real train-only fitting, immutable JSON models, 2025 calibration/selection and verified frozen 2026 evaluation; see FINAL_TEST | Real research evidence exists; human quality and deployment promotion remain open |
| M05 News models and calibrated evaluation | Four real matched models, separated calibration/selection, 1,104-row held-out test, uncertainty, per-class/ticker metrics and explicit negative paper-eligibility decision; see FINAL_TEST | Research evaluation complete; human quality/policy/live admission requirements remain open, not closed |
| M06 Trailforge decision and paper records | Fixture verified forecasts, immutable decisions/outcomes, duplicate/concurrency/restart recovery, simulated paper policy and injected expiry | Fixture software implemented; real-forward admission/expiry and market policy remain open |
| [M07](https://github.com/codera647/MarketPulse/milestone/8) API and demonstration | Typed local API, replay/details/evaluation dashboard, explicit reveal and success/miss/abstain/blocked/hold cases; 170 tests and lint pass; loopback services healthy | Complete for the local FIXTURE demonstration; pushed as `9e73e3e` and closed on GitHub on 2026-10-11; not real-model certification |
| M08 Release and handoff | Dependency snapshot, fixture regression/recovery checks, backup/restore and reproducible local guide | Fixture release candidate; real-data release remains open |

At each milestone completion, update this file and `CHECKPOINT.md`, run
relevant verification, inspect the staged files, commit and push, then close
the corresponding remote milestone. If a GitHub issue is attached to a
milestone, close it only when its acceptance criteria are met.

M01 establishes software behavior using fixtures. M02/M03 establish the real
data path; model performance claims require M04/M05 evidence. `.env` and raw
or derived market data are excluded from all milestone commits.

GitHub Actions uses `.github/workflows/ci.yml` on Windows/Python 3.13.
The initial commit's [CI run](https://github.com/codera647/MarketPulse/actions/runs/38035607436)
passed dependency installation, lint, and fixture regression tests. Later
commits need their own checked results; this does not certify live data.

## Cloud bootstrap evidence - 2026-10-13

Dedicated Free Neon project, review branch and private bucket, and a dedicated
Vercel CLI-linked project are created. SQL-created restricted roles passed
review-branch checks before production; both real application connections and
private bucket access passed. Public target metadata and read-only preflight
checks are implemented. User reports the Vercel deploy token saved in GitHub;
worker credentials require direct CI configuration. No hosted dashboard,
scheduled pipeline, weekly training, model promotion or automated deletion is
claimed complete. See [CLOUD_OPERATIONS](CLOUD_OPERATIONS.md). Existing research
quality/paper/release milestones remain open; no GitHub milestone is closed by
provisioning infrastructure.
