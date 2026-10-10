# Decision register and architecture decisions

Status terms: **agreed** by the user; **provisional** design default; **open** needs a bounded experiment or user/domain choice; **deferred** excluded from this MVP. Owner for current entries: project author. A passing test can promote a provisional technical choice; changing the product target or expanding external authority needs a recorded decision.

| ID | Decision | Status | Basis / next evidence | Revisit trigger |
| --- | --- | --- | --- | --- |
| D01 | Six target companies: AAPL, NVDA, AMZN, JPM, XOM, WMT; SPY benchmark | Agreed | Conversation; fixed-universe bias documented | Access or coverage gap in a named stock |
| D02 | Research/paper demo, no real-money action | Agreed | Original project brief and planning discussion | Explicit new scope and independent risk review |
| D03 | One 09:00 New York decision, regular open-to-close target | Provisional | Coherent with paper open-entry; no signal study yet | Feasibility shows unavailable data or uninformative target |
| D04 | News window from prior regular close through cutoff | Provisional | Captures after-hours/pre-open events; train/validation ablation needed | Insufficient eligible events or leakage issue |
| D05 | Benzinga news through Alpaca; Alpaca price bars | Provisional | APIs documented, account access untested | Coverage, rights, versioning, or feed quality fail |
| D06 | `UP/DOWN/NO_MATERIAL_MOVE` symmetric threshold | Open | Choose and freeze through training/validation plan | Label imbalance or cost interpretation |
| D07 | Confidence-based `PAPER_LONG`, otherwise abstain/block | Provisional | Requires calibration and validation threshold | Calibration/coverage evidence insufficient |
| D08 | Use Trailforge neutral Harness v0.1.0a1 for bounded prediction/replay runs | Provisional | PDF and pinned release support Goal/Task checks; integration spike pending | Latency or host-bridge cost outweighs recovery value |
| D09 | Modular monolith, local SQLite plus immutable dataset artifacts | Provisional | One-user demo, small universe, simple recovery | Concurrent/load or restore tests reveal limitation |
| D10 | Rules/event tags, conventional ML baselines, optional FinBERT feature | Provisional | Matches one-week scope and controlled ablation | Text benefit absent or runtime too costly |
| D11 | Broad global news, LLM explanations, broker execution | Deferred | Adds entity/rights/evaluation and risk work | Post-MVP measured need and new authorization |
| D12 | Product name MarketPulse | Open | Working label only; Catalyst was suggested, not accepted | User selects a final name |
| D13 | Agent-Reach as supplementary internet-access layer, not a historical price source | Agreed for extraction; usage boundary implemented | User requested Agent-Reach; its documented WebChannel is integrated behind explicit URL opt-in | A suitable licensed point-in-time web source is approved for model input |
| D14 | Trailforge neutral Harness supervises extraction jobs | Implemented in local fixture tests; live gate open | Typed VERIFY, bounded artifacts, and separate SQLite authority tested | Real provider latency, account access, or recovery audit changes scope |

## ADR-01: one provider pair first

Question: which input sources minimize ambiguity for the first evaluation? Options: Alpaca news and bars; SEC filings plus another price source; several global news feeds; licensed institutional feed. Select Alpaca news and bars **provisionally** because ticker/date filtering, timestamps, and stock bars are documented. Price feed can be IEX or SIP with different coverage; do not mix them without recording the feed. The available plan, historical article versions, regular-session open/close quality, and data rights remain unverified. One-day spike samples each ticker/SPY across ordinary, earnings, holiday, and corrected-story dates. If it fails, consider SEC/company releases for event analysis or a provider with documented point-in-time versioning. Source: [Alpaca news](https://docs.alpaca.markets/us/reference/news-3), [bars](https://docs.alpaca.markets/us/reference/stockbars), [data plans](https://docs.alpaca.markets/us/docs/about-market-data-api).

## ADR-02: one horizon and time cutoff

Question: what exactly is predicted? Options: previous close-to-close, premarket gap, regular open-to-close, multi-horizon. Provisional selection: same-session regular open-to-close from a 09:00 New York cutoff. It matches the proposed paper-open entry, but news may already be priced into the open. This is a research risk, not something to hide. Hold the final test untouched; if feasibility cannot support the target, amend this ADR before training/test lock. Record calendar, early-close treatment, threshold, source/feed and idealized fill convention in the experiment manifest.

## ADR-03: Trailforge is execution authority, not domain authority

Question: how is the user's harness used? Options: use only in the development workflow; wrap every market step; wrap one bounded decision/replay workflow while ordinary application code owns business state. Provisional selection: one neutral Goal per ticker/session for snapshot reference, feature build, inference, and independent VERIFY, with stable adapters and declared units. The app independently decides policy and writes the product decision idempotently after verified completion. Trailforge's separate SQLite store is a recovery authority for its run, not a market decision database. The host must reconcile cross-store partial completion. A latency/recovery spike determines if live 09:00 runs can use this path; if not, preserve it for offline replay/training evidence and document the narrower runtime use. Do not route data through the Review CLI or claim the Develop profile is model-serving infrastructure. Source: [Trailforge pinned release](https://github.com/codera647/Trailforge/tree/v0.1.0a1) and supplied guide, chapters 6-9, 18, 20.

## ADR-04: model and policy separation

Question: where does predictive uncertainty become an action? Options: model returns action; model returns class distribution and deterministic policy decides; LLM explanation authorizes action. Select the second. It allows calibration, validation-tuned threshold, input-quality override, and explicit abstention. A positive FinBERT score is a sentiment feature only. `P(UP)` is not an expected-profit estimate; cost-aware optimization waits for a defensible payoff model. If probability quality is inadequate, run in research-only mode with no `PAPER_LONG` decisions.

## ADR-05: storage and deployment

Question: which storage/topology is justified? Options: local SQLite/Parquet modular monolith; PostgreSQL and separate services; cloud data lake. Provisional selection: local SQLite records and immutable file artifacts, with Trailforge's separate SQLite. This fits a one-user demo but needs a bridge and restore test. Move to PostgreSQL only for measured multi-user/concurrent needs; Trailforge v0.1.0a1's optional PostgreSQL adapter is for its legacy Review path, not the neutral Harness.

## Pending decision protocol

For each open item, log owner, date, evidence link, considered options, effect on scope, and whether it blocks S1 feasibility, final-test lock, or release. Never convert an untested assumption into an achieved metric. The first explicit stop/go gate is data access and point-in-time quality; the second is model/coverage evidence before paper action; the third is recovery and demo readiness.
