# GitHub delivery milestones

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
| M03 Complete labeled historical dataset | Resumable batch/immutable-row software and separate minute-proxy ledger implemented; threshold/dates agreed; two live boundary probes pass; see [DATASET](DATASET.md) | In progress; bulk dataset explicitly gated on rights, not complete or closed |
| M04 Majority and price baselines | Training-only preprocessing, reproducible artifacts and matched chronological validation report | Pending |
| M05 News models and calibrated evaluation | Text/combined ablations, calibration and policy validation, final-test report and limitations | Pending |
| M06 Trailforge decision and paper records | Verified forecast runs, immutable decisions/outcomes, duplicate/restart recovery, paper policy and expiry | Pending |
| M07 API and demonstration | Typed API, replay/details/evaluation views, failure demonstrations and measured readiness/latency | Pending |
| M08 Release and handoff | Dependency/artifact freeze, regression and recovery evidence, backup/restore and reproducible setup guide | Pending |

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
