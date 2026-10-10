# Product requirements document

Status: pre-build plan, 10 October 2026. Owner: project author. Working name: MarketPulse; a final name has not been selected.

## 1. Product and user

The first user is the applicant demonstrating end-to-end ML engineering to an interviewer. The user wants to inspect a prediction that was made from information available before a US equity session, see its paper decision, and reveal the subsequent outcome. A future investment-team buyer is a hypothesis, not a validated customer.

Present workflow: manually collect articles, decide which company and event they concern, inspect previous prices, form a view, then later try to remember what was known at the time. The bottleneck is reproducible, timed evidence and honest comparison with simple forecasts. No observation of a real investment team's workflow has yet occurred; this is a hypothesis to validate during interviews.

The product's owed outcome is a reviewable forecast for one company-session plus an explicit paper policy result. It should be possible to explain exactly which input versions, feature values, model, and policy produced that result. The demo must display misses and abstentions alongside successes.

## 2. Fixed MVP boundary

- Universe: AAPL, NVDA, AMZN, JPM, XOM, WMT. SPY is market context and benchmark, not a seventh company decision target.
- One US regular-session decision per company, with a proposed 09:00 `America/New_York` cutoff on exchange trading days.
- Proposed news window: previous regular-session close through the cutoff. The exchange calendar defines the previous session, including weekends, holidays, and early closes.
- One target: the same session's regular open-to-close percentage return. This target is still a feasibility decision; see [DECISION](DECISION.md).
- Forecast classes: `UP`, `DOWN`, `NO_MATERIAL_MOVE`. The material-move threshold is configured and frozen before final testing.
- Paper results: `PAPER_LONG`, `ABSTAIN`, or `BLOCKED`. No short position, live order, or broker connection.
- One candidate news source: Benzinga via Alpaca; one candidate price source: Alpaca bars, including SPY. Both are pending account-level verification.
- Historical replay, audit detail, baseline comparison, calibration/coverage views, failure demonstrations, and API/UI access.

## 3. Main user journeys

1. Select ticker and historical session. See the cutoff, what information is eligible, its provenance tier, and the prediction without the outcome.
2. Inspect class probabilities, event summary, paper action, abstention/block reason, model and policy versions, and the exact input snapshot.
3. Reveal the separately stored actual return and compare the prediction with truth.
4. Open an evaluation view with majority, price-only, text-only, and combined results, including negative results and sample counts.
5. Trigger controlled stale-price, missing-feed, duplicate-article, and timeout cases and inspect the operational response.

The outcome must be fetched only when revealed. A hidden UI panel containing the future close is not an acceptable replay implementation.

## 4. Input and output contract

Input: a ticker in the fixed universe, valid exchange session, cutoff, data-mode (`RECORDED_STRICT`, `HISTORICAL_APPROXIMATE`, or `FIXTURE`), source snapshot identity, and permitted model/policy version. A scheduled request may omit an explicit snapshot so the service builds one from presently observed data.

Output: decision ID; ticker, session, cutoff, and horizon; class probabilities and top class; paper action and reason codes; data-quality/provenance status; eligible source IDs; model/feature/calibrator/policy versions; immutable feature snapshot hash; creation time and measured latency. The actual outcome is a different record and response, available only after the session ends.

Invalid ticker/session/schema: reject with a typed error. Missing/stale required data: `BLOCKED`. Valid data with weak evidence or low confidence: `ABSTAIN`. A functioning feed with zero relevant articles is a valid no-news observation. Retry of the same exact request returns the existing decision.

Illustrative response shape (numbers are fictional, not a model result):

```json
{
  "decision_id": "example-only",
  "ticker": "NVDA",
  "session": "2026-09-14",
  "cutoff": "2026-09-14T09:00:00-04:00",
  "horizon": "REGULAR_OPEN_TO_CLOSE",
  "data_mode": "HISTORICAL_APPROXIMATE",
  "probabilities": {"UP": 0.61, "DOWN": 0.16, "NO_MATERIAL_MOVE": 0.23},
  "action": "ABSTAIN",
  "reason_codes": ["LOW_CONFIDENCE"],
  "snapshot_hash": "example-sha256",
  "model_version": "example-model",
  "policy_version": "example-policy"
}
```

An invalid example is a request for `TSLA` (outside the fixed universe), a Saturday session, or a prediction input that carries that session's close. Each is rejected before inference. A valid but stale price input produces a recorded `BLOCKED` result rather than invented probabilities.

## 5. Success and countermetrics

The demo succeeds if a reviewer can reproduce a saved decision, see one success, one failure, one abstention, and one blocked/duplicate case; all are backed by real records or explicitly labeled fixtures. A working data adapter and a chronological evaluation are required for any claim about model performance.

Measure macro-F1, per-class precision/recall, confusion matrix, log loss, multiclass Brier score, probability calibration, accepted-opportunity coverage, and inference p50/p95. Compare market-reaction model results with majority and price-only baselines on the same held-out dates. Simulated return, drawdown, turnover, exposure, and cost sensitivity are secondary, with assumptions shown.

Countermetrics: leakage violations, invalid decisions accepted, undocumented blocked requests, duplicate persisted decisions, unexplained data coverage gaps, and paper-trade exposure breaches. A high accuracy number does not compensate for any of these.

No numerical model target or profitability claim is pre-approved. The final test may show news adds no value. A negative result with sound evaluation still demonstrates engineering skill.

## 6. User authority and exclusions

The system may automatically fetch permitted data, compute forecasts, and save paper decisions. A human reviews model/policy promotion and any move toward external publication or trading. No live investment action is authorized by this plan. The UI must describe probabilities as empirical estimates, not certainty or financial advice.

Excluded from the one-week MVP: shorts, derivatives, broad-universe scanning, multi-horizon forecasting, live trading, portfolio optimization, general global-news ingestion, LLM-generated trade explanations, autonomous agents, and microservices. These can be reconsidered only after measured need and a new scope decision.

## 7. Open product questions

- Can the intended Alpaca account retrieve sufficient news and compatible regular-session open/close bars for all six stocks and SPY? What are actual terms, retention, delay, and redistribution rights?
- Are historical article contents versioned enough for strict as-of replay? If not, which dates can only support approximate research?
- Does pre-open news carry useful information for open-to-close movement after the opening gap? If not, do we retain the negative finding or formally revise the target?
- What material-move threshold yields an interpretable class balance on training/validation dates, and what minimum evidence justifies `PAPER_LONG`?
- What hardware and feasible article count make FinBERT a measured improvement rather than a demo burden?

Each is assigned a bounded feasibility task in [TASKS](TASKS.md). The project can start software fixtures before these answers; empirical claims wait for real data.
