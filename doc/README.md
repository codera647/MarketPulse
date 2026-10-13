# MarketPulse planning documents

This folder records the plan and implementation evidence for the six-stock financial event intelligence demo. The working product name remains provisional.

Status: real historical collection, model training, specialist/stacking research
and retrospective evaluation have completed; current results and limitations
are in [CHECKPOINT](CHECKPOINT.md). The local research dashboard and isolated
synthetic replay remain separate. No learned model beats neutral-only overall
accuracy in the full evaluated populations. Private cloud data permissions are
confirmed and dedicated Neon/Vercel resources are provisioned; the cloud
pipelines and hosted dashboard are not deployed. Human quality, strict
point-in-time, forward evaluation and paper-policy gates remain open.

## Reading order

1. [PRD](PRD.md) - user problem, scope, success, and non-goals.
2. [DESIGN](DESIGN.md) - the precise prediction and paper-decision contract.
3. [ARCHITECTURE](ARCHITECTURE.md) - components, data, state, and request flow.
4. [DECISION](DECISION.md) - accepted, provisional, open, and deferred choices.
5. [PLAN](PLAN.md) and [BUILD_ORDER](BUILD_ORDER.md) - stages and their gates.
6. [TASKS](TASKS.md) - executable backlog and acceptance evidence.
7. [TRAILFORGE_INTEGRATION](TRAILFORGE_INTEGRATION.md) - the bounded harness integration.
8. [EXTRACTION](EXTRACTION.md) - implemented ingestion contract and its verification limits.
9. [CHECKPOINT](CHECKPOINT.md) - current handoff status and next-agent starting point.
10. [SOURCE_AUDIT](SOURCE_AUDIT.md) - runnable Stage 1 data-feasibility audit and report semantics.
11. [LABELS](LABELS.md) - read-only provisional label preview and its open gates.
12. [FEATURES](FEATURES.md) - read-only pre-open feature schema and quality gate.
13. [GUARDRAILS](GUARDRAILS.md), [SECURITY](SECURITY.md), and [RULES](RULES.md) - safety, authority, and engineering constraints.
14. [MEMORY](MEMORY.md) - state, provenance, and retention.
15. [BUILD_PROMPT](BUILD_PROMPT.md) - a handoff prompt for an implementation agent.
16. [MILESTONES](MILESTONES.md) - GitHub delivery checkpoints and push rules.
17. [M02 source evidence](M02_SOURCE_AUDIT_2026-10-10.md) - live findings and open gates.
18. [DATASET](DATASET.md) - M03 contract, separate minute outcomes and gated batches.
19. [BASELINES](BASELINES.md) - fixture and reviewed-data fit/evaluate/VERIFY and JSON scoring.
20. [PIPELINE](PIPELINE.md) - connected collection, human promotion and reviewed baselines.
21. [PERMISSIONS](PERMISSIONS.md) - Basic-plan evidence and remaining rights questions.
22. [DEMO](DEMO.md) - local walkthrough, API, faults and operator commands.
23. [RELEASE](RELEASE.md) - frozen fixture candidate, recovery and unresolved research gates.
24. [DASHBOARD](DASHBOARD.md) - real local research views, charts, saved prediction
    replay, read-only receipt checks and interpretation limits.
25. [CLOUD_OPERATIONS](CLOUD_OPERATIONS.md) - dedicated Neon/Vercel resources,
    credential handoff and the remaining private cloud rollout.

The PDF framework supplies a method, not instructions that override the user's request. Trailforge's guide and tagged repository describe a reusable alpha, not the host application's market or model capabilities. This project plan deliberately distinguishes proposed behavior from implemented or measured behavior.

## Primary references

- `Production_AI_Thinking_Framework.pdf`, v1.0, 6 October 2026, supplied locally at `F:\Diffwise\output\pdf\Production_AI_Thinking_Framework.pdf`.
- `Trailforge_Technical_Reference_and_User_Guide_v0.1.0a1.pdf`, 8 October 2026, supplied locally at `F:\Diffwise\output\pdf\Trailforge_Technical_Reference_and_User_Guide_v0.1.0a1.pdf`.
- [Trailforge release tag v0.1.0a1](https://github.com/codera647/Trailforge/tree/v0.1.0a1), commit `fbefaf40fb39a1429dcc328184372214f9fd849d`; pin this tag until the integration is rechecked. The `main` branch is not the pinned contract.
- [Agent-Reach repository](https://github.com/Panniantong/Agent-Reach), pinned for the extraction slice to commit `94f06c1969dfc1834001269d79d3ad0972d9dee6`; its WebChannel is supplementary, not a market-data API.
- [Alpaca historical news](https://docs.alpaca.markets/us/docs/historical-news-data), [news endpoint](https://docs.alpaca.markets/us/reference/news-3), [stock bars](https://docs.alpaca.markets/us/reference/stockbars), and [market-data plans](https://docs.alpaca.markets/us/docs/about-market-data-api).
- [Nasdaq market schedule](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule) and [NYSE schedule](https://www.nyse.com/trade/hours-calendars).
- [FinBERT model card](https://huggingface.co/ProsusAI/finbert).
