# Guardrails and failure policy

Status: proposed enforceable rules. The owner is the project author. A guardrail is effective only when implemented in code/tests and reflected in the user-visible result.

## Data and temporal integrity

- Use timezone-aware UTC storage and an exchange calendar for `America/New_York` cutoff/session interpretation. Reject invalid sessions.
- Admit an article version only if its known availability is no later than the cutoff. Historical publication time alone cannot certify receipt or the contents of later revisions. Put such cases in `HISTORICAL_APPROXIMATE`, never `RECORDED_STRICT`.
- Use only completed earlier bars for price features. Same-day open/close and outcome records are unavailable to the prediction path.
- Keep raw records and content hashes. Duplicate stories/event versions are grouped; ambiguous ticker mapping is blocked or omitted with a flag, not silently assigned.
- Treat successful empty news response as no-news. Treat unavailable, partial or stale provider response as data failure. Record feed, adjustment and corporate-action convention for prices.
- Fixtures test software and failure handling, never market-model performance. Never mix fixture and real rows in evaluation totals.

## Prediction and paper action

- Compare majority, price-only, news-only and combined models on identical chronological dates. No random stock-day split, test-set tuning, or fitting text vocabulary/calibration on final-test data.
- Output finite calibrated probabilities with named classes and model/calibrator version. Report uncertainty and sample counts; do not equate sentiment with return probability.
- `PAPER_LONG` requires complete valid inputs, matching artifact/schema, validated policy threshold, non-expired signal, and exposure room. Any failing required condition returns `ABSTAIN` or `BLOCKED` with a reason. A no-news day can be valid but may abstain by policy.
- The expected return is not derivable from `P(UP)` alone. Show costs as sensitivity until a validated payoff model exists.
- The paper ledger is simulation only; regular-open fills are idealized. Report actual assumptions, fees/slippage, exposure, turnover and missing outcomes.
- Preserve decisions after outcomes or model upgrades. New snapshots/models/policies create new identities, not edits to old records.

## Bounded operation and user experience

- Set adapter/provider timeouts, request deadlines, bounded retries, pagination limits and payload caps. After the action window expires, an otherwise valid forecast cannot become a new paper-long decision.
- Duplicate requests use a durable unique key. Incomplete/unknown Trailforge work is inspectable and cannot be reported as complete.
- API readiness requires usable compatible model, calibrator, feature schema and stores. Liveness has narrower meaning.
- The replay UI fetches outcomes only after reveal. Every view shows data mode, source/time cutoff and whether a value is prediction, action, or observed outcome.
- Failure injection is available only in local demo mode, cannot modify production source records, and labels the resulting example as a fixture or induced failure.

## Failure table

| Fault | Detect | Result/recovery |
| --- | --- | --- |
| Feed unavailable / partial page | Adapter error, missing pagination completion | `BLOCKED/NEWS_FEED_UNAVAILABLE`; bounded retry, operator-visible gap |
| No relevant article, feed healthy | Complete successful query | Valid no-news features; model/policy may abstain |
| Stale/missing prior bar | Timestamp/session/quality check | `BLOCKED/STALE_DATA` or `MISSING_DATA` |
| Ambiguous ticker | Mapping evidence below rule | `BLOCKED/AMBIGUOUS_ENTITY` for affected event; manual correction later creates new version |
| Post-cutoff correction | Article version/time check | Exclude strict snapshot; approximate tier or block |
| Low calibrated confidence | Validation-frozen threshold | `ABSTAIN/LOW_CONFIDENCE` |
| Exposure cap | Paper ledger transaction | `ABSTAIN/EXPOSURE_LIMIT` |
| Model timeout / unknown task | Adapter deadline, harness hold | Pending/`WAITING_HUMAN`; inspect before any retry; signal may expire |
| Duplicate request | Unique product key | Return existing decision; never duplicate paper ledger effect |
| Outcome missing | Outcome job status/source check | Decision remains; mark outcome pending/unknown, do not invent return |

Reason codes are stable API values with a documented version. The UI should show a plain-language explanation alongside each code.
