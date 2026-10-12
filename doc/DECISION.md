# Decision register and architecture decisions

Status terms: **agreed** by the user; **provisional** design default; **open** needs a bounded experiment or user/domain choice; **deferred** excluded from this MVP. Owner for current entries: project author. A passing test can promote a provisional technical choice; changing the product target or expanding external authority needs a recorded decision.

| ID | Decision | Status | Basis / next evidence | Revisit trigger |
| --- | --- | --- | --- | --- |
| D01 | Six target companies: AAPL, NVDA, AMZN, JPM, XOM, WMT; SPY benchmark | Agreed | Conversation; fixed-universe bias documented | Access or coverage gap in a named stock |
| D02 | Research/paper demo, no real-money action | Agreed | Original project brief and planning discussion | Explicit new scope and independent risk review |
| D03 | One 09:00 New York decision, regular open-to-close target | Provisional | Coherent with paper open-entry; no signal study yet | Feasibility shows unavailable data or uninformative target |
| D04 | News window from prior regular close through cutoff | Provisional | Captures after-hours/pre-open events; train/validation ablation needed | Insufficient eligible events or leakage issue |
| D05 | Benzinga news through Alpaca; Alpaca price bars | Provisional; live samples audited | M02 verifies IEX and historical SIP on four sessions; rights, monthly coverage and regular-session convention remain open | Coverage, rights, versioning, or feed quality fail |
| D06 | Fixed symmetric 1% research threshold; exact boundaries neutral | Agreed on 2026-10-10 | User accepted the first research plan before bulk labels; see DATASET | New experiment only, never tune against final test |
| D07 | Confidence-based `PAPER_LONG`, otherwise abstain/block | Provisional | Requires calibration and validation threshold | Calibration/coverage evidence insufficient |
| D08 | Use Trailforge neutral Harness v0.1.0a1 for bounded prediction/replay runs | Provisional | PDF and pinned release support Goal/Task checks; integration spike pending | Latency or host-bridge cost outweighs recovery value |
| D09 | Modular monolith, local SQLite plus immutable dataset artifacts | Provisional | One-user demo, small universe, simple recovery | Concurrent/load or restore tests reveal limitation |
| D10 | Rules/event tags, conventional ML baselines, optional FinBERT feature | Provisional | Matches one-week scope and controlled ablation | Text benefit absent or runtime too costly |
| D11 | Broad global news, LLM explanations, broker execution | Deferred | Adds entity/rights/evaluation and risk work | Post-MVP measured need and new authorization |
| D12 | Product name MarketPulse | Open | Working label only; Catalyst was suggested, not accepted | User selects a final name |
| D13 | Agent-Reach as supplementary internet-access layer, not a historical price source | Agreed for extraction; usage boundary implemented | User requested Agent-Reach; its documented WebChannel is integrated behind explicit URL opt-in | A suitable licensed point-in-time web source is approved for model input |
| D14 | Trailforge neutral Harness supervises extraction jobs | Implemented and exercised on live M02 samples | Typed VERIFY, bounded artifacts, separate SQLite authority and separate outcome probes; recovery guarantees still unverified | Real provider latency, account access, or recovery audit changes scope |
| D15 | Prefer historical SIP for M03 price research; never merge it with IEX | Provisional technical recommendation | Both sampled feeds work, but 27/28 matched outcome pairs differ in open or close; not evidence of live SIP access or official auction fills | Monthly coverage, rights, or regular-session convention fail |
| D16 | July–December 2025 train, January–March 2026 validation, April–September 2026 final test | Agreed on 2026-10-10 | User accepted the dates; one-session boundary embargo is the implementation default | New experiment required for changed boundaries |
| D17 | Keep bulk collection and training gated until account rights confirmation | Explicit user instruction on 2026-10-10 | User said rights are not confirmed; build fixtures and bounded verification only | Recorded rights review and confirmation |
| D18 | First regular minute open / last regular minute close as explicit price proxy | Implemented research convention; not auction certification | Two bounded SIP probes pass; source semantics and limitations in DATASET | Missing boundary bars or target feasibility failure |
| D19 | Basic is the active Alpaca plan; documented private ML use cases are positive evidence, not complete retention clearance | Screenshot-confirmed plan / remaining terms unresolved | PERMISSIONS records the user's screenshots and official ML/news documentation; no paid upgrade performed | Account-applicable rights clarification |
| D20 | Build connected collection/review/training software without fabricating gate approval | Implemented at user request | PIPELINE adds bounded resume, report-bound human promotion and train/validation-only loader; synthetic tests only | Rights and real dataset review allow empirical M03/M04 work |

## ADR-01: one provider pair first

Question: which input sources minimize ambiguity for the first evaluation? Options: Alpaca news and bars; SEC filings plus another price source; several global news feeds; licensed institutional feed. Select Alpaca news and bars **provisionally** because ticker/date filtering, timestamps, and stock bars are documented. Price feed can be IEX or SIP with different coverage; do not mix them without recording the feed. The available plan, historical article versions, regular-session open/close quality, and data rights remain unverified. One-day spike samples each ticker/SPY across ordinary, earnings, holiday, and corrected-story dates. If it fails, consider SEC/company releases for event analysis or a provider with documented point-in-time versioning. Source: [Alpaca news](https://docs.alpaca.markets/us/reference/news-3), [bars](https://docs.alpaca.markets/us/reference/stockbars), [data plans](https://docs.alpaca.markets/us/docs/about-market-data-api).

M02 update (2026-10-10): bounded live access is now verified for both historical
feeds. Use [the audit](M02_SOURCE_AUDIT_2026-10-10.md) rather than interpreting
the original account-untested paragraph as current status. Headline/metadata
research stays approximate; full bodies, data rights and the regular-session
label convention are still open. M02 completion does not clear the entire
Stage 1 empirical gate.

## ADR-02: one horizon and time cutoff

Question: what exactly is predicted? Options: previous close-to-close, premarket gap, regular open-to-close, multi-horizon. Provisional selection: same-session regular open-to-close from a 09:00 New York cutoff. It matches the proposed paper-open entry, but news may already be priced into the open. This is a research risk, not something to hide. Hold the final test untouched; if feasibility cannot support the target, amend this ADR before training/test lock. Record calendar, early-close treatment, threshold, source/feed and idealized fill convention in the experiment manifest.

## ADR-03: Trailforge is execution authority, not domain authority

Question: how is the user's harness used? Options: use only in the development workflow; wrap every market step; wrap one bounded decision/replay workflow while ordinary application code owns business state. Provisional selection: one neutral Goal per ticker/session for snapshot reference, feature build, inference, and independent VERIFY, with stable adapters and declared units. The app independently decides policy and writes the product decision idempotently after verified completion. Trailforge's separate SQLite store is a recovery authority for its run, not a market decision database. The host must reconcile cross-store partial completion. A latency/recovery spike determines if live 09:00 runs can use this path; if not, preserve it for offline replay/training evidence and document the narrower runtime use. Do not route data through the Review CLI or claim the Develop profile is model-serving infrastructure. Source: [Trailforge pinned release](https://github.com/codera647/Trailforge/tree/v0.1.0a1) and supplied guide, chapters 6-9, 18, 20.

## ADR-04: model and policy separation

Question: where does predictive uncertainty become an action? Options: model returns action; model returns class distribution and deterministic policy decides; LLM explanation authorizes action. Select the second. It allows calibration, validation-tuned threshold, input-quality override, and explicit abstention. A positive FinBERT score is a sentiment feature only. `P(UP)` is not an expected-profit estimate; cost-aware optimization waits for a defensible payoff model. If probability quality is inadequate, run in research-only mode with no `PAPER_LONG` decisions.

## ADR-05: storage and deployment

Question: which storage/topology is justified? Options: local SQLite/Parquet modular monolith; PostgreSQL and separate services; cloud data lake. Provisional selection: local SQLite records and immutable file artifacts, with Trailforge's separate SQLite. This fits a one-user demo but needs a bridge and restore test. Move to PostgreSQL only for measured multi-user/concurrent needs; Trailforge v0.1.0a1's optional PostgreSQL adapter is for its legacy Review path, not the neutral Harness.

## D21 — Synthetic application delivery, not rights clearance (2026-10-11)

The user requested autonomous completion while away. Continue normal local
implementation but preserve their explicit earlier rights hold. Build a
credential-free fixture application rather than assert unobserved market
accuracy. Its synthetic news comparator, calibration, policy and replay service
accept FIXTURE only, never real/recorded tiers. The real dataset promotion's
purpose remains majority/price validation; no implicit news/test/action approval
is added. Model/cost/outcome evidence must retain its synthetic provenance.
See [DEMO](DEMO.md) and [RELEASE](RELEASE.md) for implementation and limitations.

## Pending decision protocol

## D22 — Authorized larger private research run (2026-10-12)

User confirmation supersedes D17's earlier rights hold for this private
Alpaca/Benzinga experiment; it is recorded as attestation, not independent legal
verification. After the user requested a larger history, the active private
experiment uses 2018–2024 training, 2025 validation, Jan–Sep 2026 held-out test,
preserving the six companies, SPY context, 09:00 cutoff and fixed 1% minute proxy.
The user approved whole-date quarantine for confirmed coverage failures.
Only typed FAIL plus independent missing-boundary replay qualifies; UNKNOWN
work and other integrity failures still stop. See [REAL_DATA_RUN](REAL_DATA_RUN.md).

## D23 — Offline diagnostic fitting is not human promotion (2026-10-12)

The explicit user request to train authorizes research fitting after a complete
technical audit. That authorization binds exact contract/report hashes; no
human review is fabricated. Four matched models, training-only preprocessing,
separated calibration/selection and sealed final-test fitting boundaries are
implemented. Research releases prohibit paper actions/deployment and report
human_dataset_reviewed=false. Existing reviewed-promotion workflows and remaining
milestone review criteria remain intact. No real metrics are claimed yet.

## D24 — Earlier-date story masking (2026-10-12)

The user explicitly approved masking previously seen stories in later model
inputs instead of dropping valid company/date rows or stopping on exact repeats.
Raw news and strict duplicate reports remain unchanged. Registry keys use only
provider IDs, normalized headlines and first input dates; no labels/outcomes.
First-date news is retained across all companies on that date, and later news
is masked chronologically. Training vocabulary/IDF/weights remain train-only;
calibration and selection replay earlier input history, and no final-test input
enters the fitted release. Complete duplicate-only raw rosters can enter this
explicit research authorization route, never unmasked/human promotion. This
conservative lexical rule can also mask distinct events with identical titles.
See REAL_DATA_RUN and the masking/held-out tests; no market skill is implied.

## D25 — Separate enriched and weighted v2 experiment (2026-10-12)

The user authorized implementing the three proposed improvements together:
class weighting, richer market/company inputs, and financial-news meaning.
Preserve v1 contracts, raw data, models, selection, and exposed test report.
V2 is a separate private research experiment under Trailforge. Keep six targets,
SPY context, the 09:00 America/New_York cutoff and the fixed +/-1% minute-proxy
open-to-close labels. Sector ETFs are context, not additional prediction targets.

Use only 2018–2024 training and 2025 development/calibration/selection for this
first v2 run. Time-grouped expanding folds ending in 2022, 2023 and 2024 select
bounded model settings. Keep whole dates together and embargo one exchange date.
The January–September 2026 test has already been inspected: it is NOT a new
blind test, and this run does not use its outcomes for fitting or selection.
A future forward test requires a separately frozen collection/evaluation plan.

Collect historical SIP raw daily context and 30-minute pre-market bars into a
separate v2 directory, preserving pages/queries/feed/receipt hashes. Only bars
fully ended by 09:00 may contribute to pre-market features. Missing observations
are explicit nulls and coverage flags, not invented zero activity. Sector
assignment is a fixed research proxy mapping, not a historical GICS claim.
News earnings/event flags are NOT a verified earnings calendar or numerical
earnings surprise; unavailable schedule/consensus features remain explicitly
unavailable. Do not purchase new data subscriptions or claim unavailable inputs.

FinBERT is a pinned frozen text feature extractor, not a price predictor. Its
published non-commercial weight terms and incomplete corpus/date audit restrict
this candidate to the existing private non-commercial research demo. Do not
commercially deploy it or certify it as a historical point-in-time model.
Keep heuristic event/entity flags distinct from its sentiment probabilities.
No sentiment fine-tuning or invented article annotations are authorized.
Fit imputation/scaling/vocabulary/class weights only on each training segment;
calibrate on a separate 2025 segment. Compare majority, unweighted/weighted
logistic ablations and enriched CatBoost on identical dates. No promised
accuracy uplift, paper actions, deployment promotion or automatic test reuse.
See [RESEARCH_V2](RESEARCH_V2.md) for the frozen implementation specification.

## D26 — Version the CPU-bounded headline sentiment variant before fitting

2026-10-12, host implementation choice within D25; no v2 stock model has been
fitted or evaluated. The two-core CPU / absent CUDA device makes full-text
FinBERT inference slower than the reported battery window. On the same frozen
16-document diagnostic, headline FP32 inference took 5.97s versus 13.06s for
headline-plus-summary under concurrent processing. Dynamic int8 was rejected
because its sample sentiment probabilities changed substantially.

Use a separately identified `financial-news-meaning/4` / `preopen-enriched/4`
variant: frozen FP32 FinBERT sees the cleaned headline only; complete eligible
headlines AND summaries remain in TF-IDF, heuristic event features and immutable
source/input artifacts. This deliberately gives sentiment less context; it is
not presented as equivalent to full-text sentiment. Keep the 96-token ceiling,
two CPU threads, all company-day examples, labels, cutoff and chronological
evaluation. Deterministically bucket headline inputs by clipped word count then
digest to reduce padding. The final runtime bound is 64 documents: a synthetic
96-token maximum-length diagnostic took 47.73s, comfortably below the native
300s lease. Its probabilities matched 16-document FP32 scoring within 3e-8.
This reduces task overhead without changing weights or truncation. The earlier
16-document headline pilot is retained separately, not mixed with this cache.
Blank cleaned headlines do not receive sentiment, but valid full-text event
flags remain available after the same cutoff/entity checks.

Archive the interrupted full-text owner/status/lock/log evidence and retain all
its native task history; do not reset UNKNOWN work or mix cached feature
versions. Source captures and base rows can be reused only through their
existing positive receipts. New sentiment identities bind the new specification.
Blank cleaned headlines have no fabricated sentiment; missingness is explicit.
No corpus/label reduction, external upload, subscription, new test or quality
promotion is authorized by this change. See RESEARCH_V2 for execution evidence.

For each open item, log owner, date, evidence link, considered options, effect on scope, and whether it blocks S1 feasibility, final-test lock, or release. Never convert an untested assumption into an achieved metric. The first explicit stop/go gate is data access and point-in-time quality; the second is model/coverage evidence before paper action; the third is recovery and demo readiness.
