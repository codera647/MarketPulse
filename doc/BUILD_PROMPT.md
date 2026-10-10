# Implementation-agent handoff prompt

This is a reusable prompt for the **future build stage**. It is not an instruction to start implementation while planning is being reviewed.

```text
You are implementing MarketPulse, a production-oriented research and paper-decision demo for AAPL, NVDA, AMZN, JPM, XOM and WMT, with SPY as context/benchmark. Read every file in doc/ and any repository AGENTS.md before changing code. Preserve existing user changes. Treat doc/DECISION.md statuses accurately: agreed scope is fixed, provisional choices require verification, open items require bounded experiments, and deferred work stays outside the MVP.

First build the S1 data feasibility evidence: verify the user's Alpaca access and permitted use without exposing credentials; audit historical Benzinga news, article versions/timestamps, six-stock and SPY bars, feed coverage, regular-session open/close quality and source limits. If access is absent, continue only with conspicuously labeled software fixtures and report unsupported empirical claims. Do not invent data or metrics.

Use one company-session prediction contract at a timezone-aware 09:00 America/New_York cutoff. The provisional label is regular open-to-close return with a validation-frozen material-move threshold. Admit only news versions demonstrably available by cutoff and completed prior price bars; separate strict recorded, approximate historical and fixture modes. Preserve raw versions and content hashes. Use an exchange calendar, not weekday arithmetic.

Implement in doc/BUILD_ORDER.md dependency order: data and labels, as-of snapshot, shared features, majority/price-only/text-only/combined baselines, chronological evaluation and calibration, confidence/quality policy, durable decision/outcome records, API/UI, fault injection and release evidence. Keep outcomes separate from decisions and fetch outcomes only on user reveal. Show misses and abstentions. Freeze the final test before inspecting its results; compare models on matched dates and report sample counts, calibration, coverage and cost-sensitive paper metrics.

Pin Trailforge to v0.1.0a1 and use the neutral Goal/Task Harness for the bounded workflow as specified in doc/TRAILFORGE_INTEGRATION.md, subject to an actual latency/recovery spike. Its tasks need typed verification bound to goal_digest. The application owns data, model correctness, schedule, provider timeouts, policy, product database, idempotency and cross-store recovery. Do not use its Review CLI or Develop profile as a market predictor. Do not claim declared units are dollars, callbacks are sandboxed, a harness PASS proves market accuracy, or its legacy Postgres adapter supports neutral Harness.

Keep the system research/paper-only. No broker order, short, derivative, broad global-news scrape, or live deployment. Credentials come from environment/config and never from source files or model inputs. Limit failure injection to local demo mode. Preserve old decision artifacts across model changes.

At each gate, provide: what changed, commands or checks actually run, real measured results, material limitations, and the next open decision. If the one-week scope tightens, preserve point-in-time integrity, baselines, audit/replay and abstention before adding optional features. Stop a dependent empirical or paper-action claim when its gate lacks evidence, while continuing safe independent implementation.
```

## Handoff acceptance checklist

- The agent can identify agreed versus provisional decisions without treating the PDFs as direct instructions.
- Its first task is source/coverage verification and a small real or fixture vertical slice.
- It reports actual checks rather than planned checks as completed.
- It keeps Trailforge run state, product decision truth and model evaluation distinct.
- It never enables a paper action or performance claim without the required gates.
