# Research dashboard

## Design and scope

The dashboard is a local, read-only research terminal, not a trading screen.
Graphite surfaces, teal emphasis, restrained borders and tabular numbers keep
attention on evidence. Red/teal encode down/up; slate encodes no material move.
Charts use labelled axes, hover details and visible sample sizes. No decorative
stock-price curves, simulated profits or invented live feeds are included.

Five research views: overview, model diagnostics, saved prediction replay,
data/provenance and operations. Controls filter the verified 2025 development and retrospective
2026 evaluation populations without changing training, calibration or selection.
The synthetic fault/replay app remains available in a separate fixture mode.

The data layer admits two pinned reports, verifies content hashes, validates
their positive Trailforge receipts through read-only SQLite connections, checks
complete six-company groups and replays every candidate's saved metrics before
display. Missing or inconsistent artifacts fail closed, with no fixture fallback.
The dashboard does not fetch data, train, deserialize estimator binaries, read
credentials, submit orders or promote a model. Private datasets remain local.
Operations separately verifies every completed native task receipt and displays
retained states; it never infers worker liveness from a reused PID or build lock.

## Launch

From the project root:

```powershell
.\.venv\Scripts\marketpulse.exe dashboard
```

Open http://127.0.0.1:8501. An alternate data parent can be specified with
`--research-data-dir`; this is an operator CLI setting, never a browser input.
Synthetic replay: `marketpulse dashboard --mode fixture --data-dir data/demo`.

## Interpretation

The 09:00 New York cutoff predicts the regular-minute open-to-close return proxy.
UP is strictly above +1%, DOWN strictly below -1%; boundary values are neutral.
SPY is context, not a seventh prediction target. Class probabilities are saved
stock-movement estimates, not FinBERT sentiment. Replay is historical, not live.
Outcomes appear only after an explicit reveal in replay.

2026 dates were exposed in earlier research: this is a retrospective check,
not a fresh blind test. The price CatBoost expert was selected on 2025 macro-F1;
the actual Logistic Regression stack is a different candidate. No learned model
beats neutral-only overall accuracy in these full populations. Filtered results
are exploratory diagnostics, not a new selection procedure.

Historical availability remains approximate. The FinBERT corpus-date audit is
incomplete; event tags are heuristic; earnings consensus/surprise features are
not present. Human quality, strict point-in-time capture, forward evaluation,
paper policy and deployment gates remain open. No financial return or readiness
claim follows from a completed software run.

## Verification

Fresh focused dashboard/fixture regression run: 47 tests passed in 211.21s on
13 October 2026. Repository lint and dependency checks pass. Earlier interrupted
test output was not counted as a successful run. Actual browser screenshot,
narrow-screen, keyboard and hover inspection remain unverified. See
[CLOUD_OPERATIONS](CLOUD_OPERATIONS.md) for the separate pending hosted rollout.
