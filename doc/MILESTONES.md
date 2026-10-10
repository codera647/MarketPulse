# GitHub delivery milestones

Requested on 2026-10-10: create the project repository on the user's GitHub
and commit/push the code at each completed milestone. The planned repository
name is `MarketPulse`, with private visibility by default. GitHub creation
and the initial push are pending access to callable connector tools.

The definitions in [github_milestones.json](github_milestones.json) are ready
to create on GitHub. No due dates are invented. Local implementation evidence
does not substitute for an actual remote milestone or successful push.

| Milestone | Completion evidence | Current local status |
| --- | --- | --- |
| M00 Repository and delivery workflow | GitHub repository and milestones exist; initial push succeeds; CI is configured; credentials excluded | Prepared; remote access pending |
| M01 Extraction and feature foundation | Trailforge extraction/audit, versioned snapshots, provisional label and pre-open feature previews pass fixture regression tests | Implemented; 25 fixture tests previously passed; initial push pending |
| M02 Live data access and source audit | Local credentials load; six stocks/SPY return real news/bars; dated coverage and source-convention audit saved | Pending live verification |
| M03 Complete labeled historical dataset | Reproducible backfill, separate outcomes, explicit label threshold and chronological split manifest, complete rows and gap/leakage report | Pending |
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
