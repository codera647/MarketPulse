# Implementation backlog and acceptance evidence

Status: proposed work; no task below is marked done. Owner: project author unless assigned otherwise. `F` marks a feasibility blocker; `R` marks a release blocker. Day numbers are target sequencing, not a promise that data-dependent work will finish on that date.

## Discovery and data (days 1-2)

| ID | Task | Depends on | Done when |
| --- | --- | --- | --- |
| T01 F | Inspect repository, local instructions and user-approved scope | None | Existing changes preserved; package/setup decisions recorded |
| T02 F | Validate Alpaca account permissions, news/bar entitlement, terms and credentials path | T01 | Authenticated queries for six stocks and SPY, plan/feed/rights audit without logging secrets |
| T03 F | Audit coverage by ticker/month/event type, article contents/versions, open/close bars, pagination and rate limits | T02 | Counts, missingness and sampled raw IDs in a source-audit report; strict replay feasibility stated |
| T04 F | Define NYSE/Nasdaq sessions, early closes, cutoff, prior close and DST behavior | T01 | Handchecked weekend/holiday/DST/early-close examples pass |
| T05 F | Freeze return label convention, candidate `theta` selection rule, split boundaries and data tier | T03,T04 | Versioned experiment manifest; final period untouched |
| T06 | Create raw article/bar stores and retrieval cache with content hashes | T02 | Same provider page fetched twice does not silently replace original bytes |
| T07 | Normalize article timestamps, ticker links, versions, duplicate groups, event-rule tags and quality flags | T06 | Human-reviewed sample and duplicate/correction fixtures demonstrate expected grouping |
| T08 | Normalize provider price bars, adjustment/feed metadata and missing-session flags | T04,T06 | Hand-calculated open-to-close returns match; feed and convention never silently mix |

## Features and models (days 3-4)

| ID | Task | Depends on | Done when |
| --- | --- | --- | --- |
| T09 R | Build eligible as-of company-session snapshots from raw versions and completed prior bars | T05,T07,T08 | Future article, later correction and incomplete bar cannot enter strict snapshot; tier visible |
| T10 R | Build one versioned feature function shared by training, replay and serving | T09 | Same snapshot yields identical ordered feature schema and values in offline/served paths |
| T11 | Train majority and price-only baselines | T10 | Reproducible artifact/manifest and chronological validation output |
| T12 | Train text TF-IDF baseline with training-only vocabulary | T10 | No document or duplicate group from validation/test influences fit |
| T13 | Train combined model and optional FinBERT feature ablation | T11,T12 | Headline/text availability measured; effect on quality and latency reported, including negative result |
| T14 R | Calibrate probabilities on data separate from base fit; choose policy threshold on validation only | T11-T13 | Class probabilities/checks and untouched-test lock documented |
| T15 R | Run final chronological evaluation and paper-cost sensitivity | T14 | Baselines matched by dates; sample counts, uncertainty, macro-F1, calibration, coverage, costs, drawdown and exposure shown |

## Harness, decisions and service (days 5-6)

| ID | Task | Depends on | Done when |
| --- | --- | --- | --- |
| T16 F | Pin Trailforge v0.1.0a1 in isolated environment and run neutral Goal/Task smoke example | T01 | Exact package/version and typed verifier behavior observed; no Review CLI substitution |
| T17 R | Implement bounded snapshot/score/VERIFY adapters with explicit status and version bindings | T09,T10,T14,T16 | Goal completes only when independent contract check passes; invalid/missing inputs become an explicit blocked result |
| T18 R | Implement run-to-product bridge, deterministic decision key, unique constraint and retry/recovery behavior | T17 | Concurrent identical requests produce one decision; known completed run can be materialized after a crash; orphan window documented |
| T19 R | Implement action policy, expiry, exposure cap and reason codes | T14,T18 | Low confidence abstains; stale/missing blocks; expired signal cannot become a paper-long action |
| T20 R | Append separate outcomes after session close with source and quality metadata | T08,T18 | Original decision hash/fields remain unchanged after outcome and model upgrade |
| T21 | Implement API liveness/readiness and decision/replay/evaluation routes | T18-T20 | Typed invalid requests rejected, incompatible artifacts fail readiness, duplicate retry returns original |
| T22 | Implement UI replay, decision audit, baseline/evaluation and operations panels | T21 | Future outcome fetched only on reveal; provenance/limitations obvious |
| T23 R | Fault-injection exercises: feed loss, stale price, duplicate article/request, model timeout, restart after harness completion | T18-T22 | Every case yields correct block/hold/recovery; no duplicate product decision |

## Release and communication (day 7)

| ID | Task | Depends on | Done when |
| --- | --- | --- | --- |
| T24 R | Freeze code/model/data/policy manifest and run regression checks | T15,T23 | Same snapshot replays with original artifacts; bad changed candidate is rejected |
| T25 R | Write project README, `.env.example`, commands, provider limitations, cost/latency setup | T24 | Fresh engineer can run fixture without secrets and real path with valid credentials |
| T26 R | Exercise backup/restore and document recovery/rollback | T18,T24 | Restored copy yields matching stored decisions and linked artifacts; harness authority preserved |
| T27 | Prepare interview script: success, failure, abstention, stale/duplicate, honest negative result if applicable | T22,T24 | Every shown example has a source/provenance label and exact decision ID |

## Decision gates and fallback

- **G1 after T03:** if Alpaca access, coverage or rights do not support this question, stop empirical-performance claims. Continue software fixtures and choose a smaller event-analysis experiment only through a documented scope decision.
- **G2 after T15:** if calibrated probabilities or sample size do not justify a confidence threshold, disable `PAPER_LONG` and demonstrate forecast/abstention only. Do not change the final period to rescue metrics.
- **G3 after T23:** if duplicate/recovery/expiry behavior fails, do not present the system as an operationally reliable paper-decision service.

## Meaningful acceptance examples

1. Article created at 09:01 is excluded from a 09:00 snapshot; an 08:30 article edited at 09:05 does not overwrite an earlier captured version.
2. Monday at 09:00 uses Friday's completed regular bar when Monday is the next exchange session; a holiday and DST boundary are correct.
3. A provider request succeeds with zero articles: valid no-news. A provider outage: `BLOCKED/NEWS_FEED_UNAVAILABLE`.
4. A delayed score finishes after its paper-action expiry: no `PAPER_LONG`, even if `P(UP)` is high.
5. Two simultaneous identical requests and a retry after a crash return one immutable decision; a new snapshot/model/policy version gets a distinct identity.
6. A classifier with excellent macro-F1 but poor class calibration cannot pass the paper-long gate without revising the policy on validation data.
