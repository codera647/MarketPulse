# MarketPulse v2 — enriched, weighted research experiment

Specification recorded 2026-10-12 before v2 training, with D26's explicitly
versioned headline-sentiment amendment before any v2 stock-model fitting.
Status: implementation
verified; first real run in progress, no v2 accuracy improvement claimed. The user authorized the combined
improvements. V1 is immutable and its measured negative result stays visible.

## Data and feature boundary

Implementation entry points are `research-v2-build` and `research-v2-predict`.
Install the pinned full environment with `requirements.lock.txt`, then install
this project editable with `--no-deps`, or use the `[research-v2]` optional extra
in a fresh environment. Keep all generated artifacts under ignored `data/`.

- Same six stocks, SPY benchmark, 09:00 New York cutoff and existing +/-1%
  regular-minute open/close proxy labels. Source rights are user attestation.
- Private new work directory: `data/research-v2-20261012`; source dataset:
  `data/real-2018-2026`. No overwrite of v1 datasets/models/ledgers.
- Use the technically audited 2018–2024 train and 2025 validation roster only.
  Previously exposed 2026 outcomes remain outside this experiment's fitting,
  tuning, calibration and model selection. No fresh final-test result is claimed.
- Add ticker one-hot indicators and fixed sector-proxy ETF inputs: AAPL/NVDA
  XLK; AMZN XLY; JPM XLF; XOM XLE; WMT XLP. These are chosen research proxies,
  not a reconstructed historical sector classification.
- Capture SIP raw daily ETF and stock bars, plus stock 30-minute bars in bounded
  monthly jobs. Retain full immutable provider pages and native Trailforge
  verification receipts. Derive sector 1/5/20-session returns/volatility only
  from exactly the expected prior NYSE dates.
- Pre-market observations are between 04:00 and 09:00 New York; intervals must
  finish by cutoff. Return uses the last eligible close versus prior raw daily
  close; volume is observed SIP bar volume, not invented complete-market volume.
  Bar count, interval coverage and missing/staleness flags accompany values.
- Never treat empty/partial observations as known zero volume. Successful empty
  source results and failed captures are distinct; failed/UNKNOWN jobs stop.
  Raw adjustments and corporate actions remain an explicit research caveat.

## News meaning

Use saved eligible headlines/summaries, preserving financial numbers/negation.
The active `financial-news-meaning/4` / `preopen-enriched/4` experiment sends
only cleaned headlines to frozen FP32 FinBERT. Full headlines AND summaries
remain in TF-IDF, event flags and immutable source/input artifacts. This gives
sentiment less context than the interrupted full-text variant; do not claim
they are equivalent. Headline batches are deterministically ordered by clipped
word count then digest to reduce padding; the final limit is 64 / 96 tokens.
Same frozen weights, all company-day examples, labels and chronological
evaluation are retained. A blank cleaned headline has no fabricated sentiment,
while valid full-text summary event flags are still retained.

In a paired 16-document runtime diagnostic under concurrent processing,
headline-only scoring took 5.97s versus 13.06s for full text. This measures
runtime, not predictive accuracy or a guaranteed end-to-end completion time.
R3's interrupted full-text logs/status/lock and native attempts are preserved;
their sentiment cache is not mixed with the new specification. The active
builder uses `v2-build-r8.stderr.log` / `.stdout.log`. The 16-document headline
pilot (r4) also has archived status/lock/logs and retained native attempts.
Its feature cache is not reused across the new specification binding.

The final 64-document bound was checked using synthetic maximum-length
96-token inputs (never training data): 47.73s versus 11.42s for 16 inputs under
concurrent processing. FP32 probabilities differed by at most 3e-8, and the
larger batch remains comfortably below the 300s native lease. A regression
check covers 129 unique documents in three bounded tasks, without omissions.

Windows progress-file readers briefly blocked R5's atomic status rename before
news extraction. The original committed status and STOPPED temporary status are
archived, and a bounded status-only PermissionError retry is implemented. Both
transient recovery and permanent denial are tested; it cannot retry native
tasks. R6 uses exactly the same modeling binding. Read progress with
`Get-Content -Raw` to release the file handle promptly.

Apply the approved earlier-date repeated-story masking. Pin a frozen FinBERT
revision and cache per-text probabilities privately, independent of market
labels. Aggregate positive/negative/neutral scores by ticker/day, alongside
heuristic event flags, source-tag/entity relevance, recency and news coverage.
Missing news signal differs from neutral sentiment. Do not silently fall back
to fabricated sentiment if model download/inference fails.

Runtime diagnostic, 2026-10-12: the host is a two-core Intel i7-7Y75 with
no CUDA device. A separate 16-document dynamic-int8 diagnostic took 8.24s
(6.72s repeat) versus 11.04s FP32 under concurrent collection. The maximum
sample sentiment-probability difference was 0.545, although int8 replay itself
was deterministic. This is NOT an equivalent replacement: quantization was
rejected and never entered the dataset or model search. Continue the pinned
FP32 experiment; this diagnostic is not a stock-prediction quality result.

FinBERT weights: [ProsusAI model card](https://huggingface.co/ProsusAI/finbert),
CC BY-NC-SA 4.0 as inspected on 2026-10-12. Attribution: Dogu Araci / MIH AI B.V.;
[paper](https://arxiv.org/abs/1908.10063). Non-commercial research only; no model
weights or provider text committed to Git. Published corpus descriptions do
not certify every training document's date or eliminate historic contamination.
Model release postdates some 2018 input dates; all results remain approximate
retrospective research, never strict point-in-time evidence.

Event flags are versioned heuristic text indicators, not human-reviewed event
truth. FinBERT does not extract company relevance, earnings consensus or event
types. A verified earnings schedule and numeric surprise are NOT supplied by
our existing feeds; mark them unavailable rather than scrape unreliable data.

## Training and evaluation specification

Compare the majority prior and five staged candidates: unweighted existing
price+TF-IDF logistic control; weighted existing price+TF-IDF; weighted enriched
market+TF-IDF; weighted enriched market+news meaning+TF-IDF; and enriched CatBoost
with market/news meaning features. Keep all candidates on identical dates.

Bounded settings: logistic C in {0.1, 1.0}, movement weight multiplier in
{1.0, 1.5}; balanced weights computed ONLY from training counts. CatBoost depth
in {4, 6}, 200 trees, learning rate .05, fixed seed, two CPU threads. No automatic
unbounded search. Time-grouped expanding development folds: train through 2021
evaluate 2022; train through 2022 evaluate 2023; train through 2023 evaluate 2024.
Exclude one whole exchange date at each boundary. Fit each fold's vocabulary,
imputation, scaler and weights using only its training segment. No stock-day
random split or oversampling before splitting.

Select settings by mean fold macro-F1, then mean log loss, then stable candidate
identity. Final fitting uses 2018–2024. Calibration uses earlier 2025 dates;
selection uses later 2025 with one whole-date embargo between them. Temperature
scaling changes confidence, not the argmax class; it is not an imbalance cure.
Preserve accuracy, macro-F1, probability metrics, confusion matrices, class
precision/recall, ticker and fold breakdowns. Inspect neutral prediction rate
and false alarms. A higher macro-F1 can coexist with lower overall accuracy.

The grid contains 18 parameter configurations, each checked on three folds,
followed by five final fitted/calibrated candidates. News extraction uses a
frozen float32 FinBERT checkpoint, 96-token maximum and 16-document batches on
two CPU threads. Truncation counts remain visible. Each batch gets full
probability/text-binding checks plus independent first/last inference replay;
this is sampled inference verification, not full-corpus double inference.
Dataset construction is chunked into 300 rows. Native leases remain <=300
seconds; long initial v1 lineage preflight uses its existing source receipts
outside a new task lease, rather than increasing the pinned harness limits.

Trailforge tasks supervise bounded source captures, sentiment batches, dataset
construction, candidate fitting, scoring and independent replay verification.
Durable task messages contain hashes/counts only; data/model binaries remain
private. Failure/UNKNOWN states and exclusive owner locks remain inspectable.
Persist model versions, feature schema, training roster, source hashes, chosen
settings, calibration and saved probabilities. Verify saved-model inference
replays and original v1 hashes remain unchanged.

No new untouched future examples yet exist in this run. The v2 selected release
must state final_test_completed=false, paper_action_authorized=false and
deployment_promoted=false. A next forward test freezes its dates, candidates,
features and scoring plan before collecting future outcomes. A later dashboard
can show v2 DEVELOPMENT results clearly, not substitute them for v1 final test.

## Run and inspect locally

Run from `F:\MarketPulse`, using a NEW separate v2 data directory if changing
the experiment specification. Do not remove an active owner's lock or reset
native FAILED/UNKNOWN work. This command reads credentials locally but never
prints them or invokes broker orders:

```powershell
.venv\Scripts\python.exe -u -m marketpulse.cli research-v2-build `
  --base-data-dir data/real-2018-2026 `
  --base-release-hash 4c706aa1821093bba26231405ee1e119fcbb7787c38aff8c75c333897520f95f `
  --data-dir data/research-v2-20261012 `
  --authorization-evidence "Explicit user authorization for private non-commercial v2 research" `
  --env-file .env
```

The current managed launch uses its own recorded user evidence; do not run
the example concurrently or change that evidence while resuming the same run.
On completion, `v2-status.json` gives the release/report/dataset hashes. The
immutable private artifact root is `data/research-v2-20261012/artifacts`;
CatBoost native `.cbm` binaries have independent SHA-256 identities.

```powershell
Get-Content -Raw data/research-v2-20261012/v2-status.json
Get-Content data/research-v2-20261012/v2-build-r8.stderr.log -Tail 5
```

Saved research inference accepts only a label-free input artifact:

### Interrupted source capture recovery

On 2026-10-12 the June 2021 30-minute capture finished writing eight immutable
pages / 3,665 records, but its original Trailforge attempt exceeded the 300-second
lease. That run is retained as `WAITING_HUMAN` / `UNKNOWN` / `EXPIRED_ATTEMPT`;
its attempt and budget history were not reset. Independent inspection verified
the complete pagination chain, query bounds, source provenance, record count,
unique timestamps and finite OHLC/volume before resuming collection.

The explicit `research-v2-reconcile` command verifies an already-complete
capture under a separate native execute/verify task and records its positive
receipt in `v2_capture_reconciliations`. It neither refetches the source nor
turns arbitrary UNKNOWN attempts into successful original runs. An incomplete
or mismatched candidate is rejected; normal unregistered held tasks still stop.
Keep the original held run and the child receipt together for audit. The resumed
builder's historical R3 logs are `v2-build-r3.stderr.log` / `.stdout.log`.

```powershell
.venv\Scripts\python.exe -m marketpulse.cli research-v2-reconcile `
  --data-dir data/research-v2-20261012 `
  --parent-job-key <expired-context-job-key> `
  --capture-hash <independently-inspected-complete-capture-hash> `
  --evidence "<bounded dated reconciliation evidence>"
```

### Modern Standby and expired sentiment recovery

On 2026-10-12 Windows Kernel-Power events 506/507 recorded Modern Standby at
22:22:16–22:27:11 Pakistan time. R6 stopped at 3,520 headlines after the
interrupted batch missed its five-minute native lease. Its 64 complete saved
scores/text bindings were independently inspected before reconciliation; no
missing outputs are inferred from a partial capture.

The host now holds a temporary `ES_CONTINUOUS | ES_SYSTEM_REQUIRED` request
only while an owned build or explicit reconciliation runs. The previous thread
state is restored on exit/error; process termination also ends the request.
No power plan, display request, away mode, security setting or explicit
user sleep/lid behavior is changed. See
[Microsoft's execution-state API](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate).
On Modern Standby/DC, Windows terminates system/execution-required requests
five minutes after the sleep timeout; see
[Microsoft's power-request limits](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-powersetrequest).
Keep the computer plugged in and its lid open for long runs. The user confirmed
this on 2026-10-12 and Win32 independently reported AC online. A subsequent R7
interruption (22:44:02–23:04:52 Pakistan, before that confirmation) had a complete
64-score capture; a separate positive child receipt preserved the expired
original and allowed R8 to resume. See CHECKPOINT for the dated identities.

`research-v2-reconcile-sentiment` requires a complete immutable batch whose
input/spec/text digests match the expired original task. It retains the original
UNKNOWN and independently replays first/last FP32 inference under a separate
typed verification task, with shape/probability checks for every output.
No original adapter retry or full-corpus replay is claimed. Only its positive
child receipt can be registered and reused; incomplete/mismatched/live attempts
are rejected. Unstarted context/sentiment tasks are also rejected without
calling either original adapter or reserving original attempt units. The
original attempt/reservation history remains unchanged.

```powershell
.venv\Scripts\python.exe -m marketpulse.cli research-v2-reconcile-sentiment `
  --data-dir data/research-v2-20261012 `
  --parent-job-key <expired-sentiment-job-key> `
  --sentiment-hash <independently-inspected-complete-batch-hash> `
  --evidence "<bounded dated reconciliation evidence>"
```

### Saved inference

```powershell
.venv\Scripts\python.exe -m marketpulse.cli research-v2-predict `
  --data-dir data/research-v2-20261012 `
  --release-hash <verified-v2-release-hash> `
  --input-hash <saved-input-hash>
```

It does not open a market outcome or authorize paper action. This first command
scores already-enriched replay inputs, not a live 09:00 feature-extraction
service. Raw/news and derived input hashes tie replay to source/version/cutoff
evidence. Live point-in-time collection, a forward test and dashboard integration
remain separate product stages.
