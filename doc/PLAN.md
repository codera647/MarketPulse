# Project plan and framework coverage

Status: planning baseline. The framework's S0-S6 stages are used as gates; they are not a claim that all production concerns have been implemented. The initial calendar is a seven-day interview sprint with a typical 4-5 engineering hours and 1-2 study hours per day, adjustable to actual access and results.

## Product contract in one line

Given one of six US stock tickers and a valid session at 09:00 New York time, use only eligible news and completed earlier price data to return a versioned open-to-close class forecast and a validated paper action or reasoned abstention/block; record the outcome later without altering the original decision.

## Stages and gates

| Stage | Work and output | Gate to proceed |
| --- | --- | --- |
| S0 discovery | Confirm user journey, target, baseline, six-stock universe, autonomy and costs of error | PRD, typed example, action matrix, representative success/failure cases reviewed by project author |
| S1 feasibility | Verify Alpaca account access/rights, article coverage/versioning, price-feed convention; build a tiny real sample and leakage-free price baseline | Data audit with counts/gaps, as-of limitations, valid calendar/label examples, decision on strict vs approximate research |
| S2 blueprint | Freeze initial contract, data lineage, storage/harness bridge, model/evaluation plan, threat/failure register | ADRs and gates coherent; no critical dependency disguised as solved |
| S3 vertical slice | One ticker/session end to end: saved input snapshot, features, forecast, check, policy, decision, later outcome, replay | Deterministic replay, duplicate protection, cutoff exclusion, interrupted-run recovery, explicit provenance tier |
| S4 supervised demo | Six-stock backfill, baselines/ablation, calibration, evaluation, UI, operations/failure controls | Held-out metrics with sample counts, honest negative results, blocked/abstain paths, measured latency/cost, usable interview walkthrough |
| S5 release | Freeze code/model/policy/data manifest, run checks, document setup and rollback | Only claim a production-oriented demo; credentials/config safe; reproducible from documented commands |
| S6 operation | If kept running: collect new article versions and frozen forecasts, monitor drift, inspect incidents, propose retraining | New model/policy promotion requires fresh chronological evaluation and human review |

The minimal slice uses one real eligible snapshot if access succeeds. A clearly marked fixture can establish software behavior while data access remains unresolved; it cannot pass the empirical S4 gate.

## Framework's five design moves and eleven questions

The five moves are represented by concrete artifacts: observe the work (PRD current-work hypothesis and interview cases); define trigger/output (PRD and DESIGN); assign steps to rules, models, providers and human (ARCHITECTURE); set autonomy per action (PRD, DESIGN, SECURITY); and walk failures before build (GUARDRAILS, TASKS). The current-work observation is still a hypothesis, so S0 asks the project author to validate it.

| Question | MarketPulse answer or open evidence |
| --- | --- |
| Q1 Costly limitation | Hard to make and inspect a time-valid forecast; measure reproducibility, model quality and time to review alongside false-action countermetrics |
| Q2 Expert analogue | Analyst checks company/event identity, past market context, timing and contrary evidence; validate this workflow during demo preparation |
| Q3 Exact contract | One ticker/session/cutoff request, three probabilities, paper action/status, reason, provenance and version IDs; invalid request is typed error |
| Q4 Mature version | More sources, permissions, monitoring, portfolio context and independent forward evaluation are future hypotheses, not MVP promises |
| Q5 Missing context | Earlier company/SPY bars and eligible after-hours/pre-open articles resolved by exact cutoff/version |
| Q6 State | Raw versions, derived snapshots, model artifacts, product truth, Trailforge authority, events and cache separated in MEMORY |
| Q7 Reconstruction/cost | Decision links source/snapshot/feature/model/policy/run IDs; count API calls, elapsed compute and operator time per useful decision |
| Q8 Autonomy | Automatic bounded forecast and paper ledger; human promotes model/policy, resolves ambiguous run, authorizes any future real effect |
| Q9 Failure | Provider, data, model, duplicate, expiry and cross-store interruption cases in GUARDRAILS and TASKS |
| Q10 Storage | Local SQLite product truth plus files and separate Trailforge SQLite; backup/restore test and explicit scale triggers |
| Q11 Interfaces | Small provider, feature, model, record and harness-host boundaries; no fake interchangeability of providers or Trailforge profiles |

Unit of useful work: one valid, auditable company-session forecast. At most six scheduled opportunities exist per exchange session in this fixed universe; backfills and retries add work. During S1, measure article count, API calls/limits, disk use and inference CPU/time for a sampled period. During S4, report per-decision costs/latency and operator hold volume. Do not treat Trailforge declared units as monetary spend. Human review capacity is one local operator for exceptional holds and model promotion, not six manual approvals each day; if holds exceed available review time, restrict the demo scope rather than silently approving them.

## Seven-day build allocation

| Day | Engineering focus | Study/rehearsal focus |
| --- | --- | --- |
| 1 | Access/rights/coverage spike, calendar, cutoff, label and split lock | Open/close, gaps, returns, market sessions |
| 2 | Raw cache, versions, dedup, price adapters and quality flags | Timestamps, SQL/pandas, idempotency |
| 3 | Shared feature builder, price/text baselines, sample event audit | Leakage and train/validation boundaries |
| 4 | Combined model, calibration, held-out evaluation and ablations | F1, calibration, confidence and negative results |
| 5 | Paper policy, immutable decision/outcome records, Trailforge run/recovery bridge | Costs, coverage, exposure and failure explanations |
| 6 | API/UI, operations, fault injection and measured latency | Deployment, monitoring, recovery |
| 7 | Freeze artifacts, README/demo script, verify a win/miss/abstention/block, rehearse | Design tradeoffs, limitations and next experiment |

If time compresses, preserve data integrity, baseline comparison, audit/replay, and abstention. Defer FinBERT, elaborate dashboard work, or nonessential event categories before weakening cutoff or evaluation rules.

## P00-P20 disposition worksheet

Every area has an owner now (project author). Evidence below is planned, not yet achieved. The detailed test/task IDs are in [TASKS](TASKS.md).

| Concern | MVP disposition and planned evidence |
| --- | --- |
| P00 Product | Applicable: PRD, current-work hypothesis, outcome/countermetrics, final user review |
| P01 Architecture | Applicable: component/data graph and ADRs; one request walkthrough |
| P02 Frontend | Applicable: replay/detail/evaluation/ops views; hidden outcome fetched after reveal |
| P03 Backend/API | Applicable: typed request/result/error; idempotent duplicate and readiness checks |
| P04 Orchestration | Applicable: simple scheduled host plus bounded Trailforge Goal; pause/UNKNOWN recovery |
| P05 Modeling | Applicable: baselines, combined model, artifacts, calibration and ablations |
| P06 Context/memory | Applicable as time-valid news/prices/features; conversational/vector memory not applicable |
| P07 Tooling/sandbox | Applicable as bounded provider/model adapters and credentials; executing untrusted code not in runtime scope |
| P08 Multi-agent | Not applicable: single predictor and deterministic pipeline; add only if ablation justifies it |
| P09 Evaluation | Applicable: date splits, sample counts, errors, uncertainty, costs and leakage cases |
| P10 Observability | Applicable: run/decision IDs, latency, freshness, holds, failures and sanitized traces |
| P11 Security | Applicable: secrets, input validation, role separation, artifact permissions and threat tests |
| P12 Reliability | Applicable: retries/holds, stable keys, recovery bridge, restore/fault exercises |
| P13 Infrastructure | Applicable at local-demo scale: pinned environment, disk/CPU budget, startup/backup/restore; no cloud scale claim |
| P14 Data engineering | Applicable: provenance, article versions, calendar, dedup, splits, schema and feature parity |
| P15 Governance | Applicable: research-only use, provider rights, retention, promotion owner, limitations |
| P16 Economics | Applicable: article/API counts, inference CPU/time, storage and human effort; Trailforge units not dollar caps |
| P17 Developer experience | Applicable: fixture, setup, commands, seeded failure and reproducible replay |
| P18 CI/CD for AI | Applicable: code/data/model/calibrator/policy manifest and regression gate; no live rollout planned |
| P19 Human operations | Applicable to model/policy promotion and unresolved runs; no per-prediction reviewer queue in the demo |
| P20 Improvement | Applicable as documented monitoring and versioned retraining proposal; automatic online learning deferred |

## Pre-build exit check

We may begin S1 experiments with open data assumptions. We do **not** freeze the final test, advertise market accuracy, or enable paper-long actions until source rights/coverage, point-in-time limitations, label definition, split plan, and calibration policy are documented. We do **not** call the result production-certified based on a framework checklist or Trailforge conformance.
