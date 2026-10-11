# Fixture release candidate — 2026-10-11

This candidate completes the **runnable synthetic demonstration**, not the
empirical financial project or a production trading deployment. Real bulk
collection, market-model training and market-policy approval remain gated.
M03/M04/M05 cannot be declared complete from synthetic evidence.

## Reproduce

Supported/tested environment: Windows, CPython 3.13, local CPU. Python package
metadata permits 3.11+; those other interpreters/platforms are not release-tested.
`requirements.lock.txt` snapshots installed runtime/dev dependencies, including
exact Trailforge/Agent-Reach Git commits. It is not a wheel-hash lock or a
guarantee that a future package index/Git checkout remains available.

```powershell
cd F:\MarketPulse
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock.txt
.\.venv\Scripts\python -m pip install -e ".[dev]" --no-deps
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python -m ruff check src tests
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\marketpulse demo-init --data-dir data/demo
```

Use a clean/new virtual environment for fresh setup; never replace the user's
existing environment blindly. CI uses the snapshot on Windows/Python 3.13.
Runtime model, feature, policy, input, outcome and report identities are full
SHA-256 hashes in the private local release manifest. JSON scoring is checked
against sklearn; no pickle is loaded. The code version is the Git delivery commit.

## Verification and operational limits

Local final full suite: **170 passed in 203.79 seconds**, with one upstream
Starlette/httpx deprecation warning left visible. Ruff (src/tests/scripts) and
pip dependency checks pass. Staged scan: 31 intended paths, zero findings.
Actual loopback readiness and Streamlit health checks return success. Remote
CI evidence is separate and recorded after delivery in CHECKPOINT.

`tests/test_demo.py` exercises four-model portable scoring, artifact tampering,
cutoff/split/calibration separation, policy segment isolation, invalid
probabilities, outcome-read exclusion at forecast, immutable repeat/reveal,
injected stale/missing/expired/low-confidence/timeout paths, concurrent duplicate
requests, verified-run crash recovery, cross-release exposure checks, strict HTTP
API, readiness, body/host guards, restore integrity, and Streamlit interaction.
The older suite covers shared features, source pagination, provider security,
point-in-time limitations, dataset completeness/promotion and real-path baseline
wire tests using fixtures. Passing these tests is not a live-feed certification.

No paid upgrade, support submission, broker order, account setting change or
permission bypass occurred. Agent-Reach remains supplementary, not a model
input. All generated data, databases, models, backups and logs stay Git-ignored.
Local API/UI lack public-service auth and must stay loopback. Recovery is not a
distributed exactly-once guarantee; see [DEMO](DEMO.md) for crash windows and
quiesced backup requirements. UI behavior is tested headlessly with AppTest;
no browser visual/pixel QA is claimed.

## Remaining work before a real-data release

1. Resolve and record applicable account/news data-use and retention permissions;
   current user instruction explicitly keeps bulk collection gated.
2. Collect the agreed 313 usable sessions/1,878 rows in bounded batches. Audit
   all tickers, corporate actions, event/revision leakage, minute-proxy semantics,
   gaps and approximate historical availability. Promote only an exact human-
   reviewed complete report. Never reuse a changed report's prior approval.
3. Run majority/price chronological validation through the implemented reviewed
   loader. Keep real final-test rows sealed during fitting and model selection.
4. Extend the news comparator to reviewed provider datasets under an explicit
   promotion contract; separate full-date calibration/policy segments, reject
   unavailable/version-ineligible text, and independently verify candidates.
   Current comparator and service intentionally accept FIXTURE only.
5. Freeze a real candidate and policy before releasing the real test once.
   Report coverage, per-ticker/period metrics, uncertainty and failures honestly;
   news may not beat the baselines. A failed experiment is a valid result.
6. Add strict recorded-forward capture/scheduling, real expiry-clock enforcement,
   session-level accounting/cost assumptions, approved research-serving artifact
   admission, prolonged fault/load checks and operational approval. No order
   placement is part of this authorized scope.

Do not close empirical milestone gates, fabricate a real-data performance
number or relabel a fixture as a market model to make the project look complete.
The next agent should read [CHECKPOINT](CHECKPOINT.md) first, then
[PERMISSIONS](PERMISSIONS.md), [PIPELINE](PIPELINE.md) and this release record.
