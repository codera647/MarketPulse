# State, provenance and retention design

The framework uses “memory” broadly. MarketPulse does not need conversational memory or a vector database. Its useful memory is **time-valid market context and an unaltered record of what was predicted**. This file separates context, business truth, execution state, events and bulky artifacts.

| State class | Content | Authority / update rule | Typical storage |
| --- | --- | --- | --- |
| Raw source versions | News payloads and price responses, source IDs, timestamps, hashes | Append new version; never rewrite a prior captured payload | Private immutable files/Parquet plus metadata |
| Derived context | Event groups, ticker links, feature rows, eligible as-of snapshot | Rebuildable only from named source versions and feature schema; old snapshot hash stable | Parquet/cache plus snapshot manifest |
| Model artifacts | Weights/vectorizer/calibrator, schema, split and training manifest | New version on change; human promotion to action mode | Content-addressed private files |
| Product truth | Request key, decision, paper ledger, outcome, promotion decision | Unique/idempotent decision; append separate outcomes; no silent edit | Application SQLite |
| Harness authority | Trailforge Goal, task attempts/checkpoints, reservations and receipts | Trailforge-owned transitions; same Goal/adapter contract on resume | Separate persistent Trailforge SQLite |
| Events/telemetry | Latency, data age, error/hold, action reason, cost proxy | Append/aggregate; cannot replace business truth | Sanitized logs/metrics |
| Working cache | Provider page cache, temporary tensors/UI state | Disposable; never proves historical availability | Local cache/memory |

## Provenance chain

`source article/bar IDs + exact versions -> snapshot hash -> feature schema and values hash -> model/calibrator manifest -> policy version -> decision ID -> later outcome ID`. Store the time each item was created/observed. In a strict forward record, `received_at` and captured content prove what this host actually observed; publication timestamps alone do not. A historical response obtained now may be revised and belongs to an approximate tier unless version availability is established.

On replay, load the original snapshot, feature schema, model/calibrator and policy referenced by the decision. A new model can create a **new comparison run**, never a replacement for an old decision. Display both if useful and distinguish recorded decision replay from counterfactual rescoring.

## Data access and retention

At 09:00 the feature resolver can read only eligible article versions and completed prior bars. The outcome writer reads the same-session open/close only after the session finishes. The UI's initial replay endpoint withholds outcome fields; a separate reveal endpoint authorizes the outcome request. These are application contracts, not merely hidden display controls.

Retain raw payloads, snapshots, models and both databases together while their provider rights and demo needs allow. A backup is useful only after a restore test confirms linked artifact hashes and original decision records. Use consistent snapshots or SQLite backup APIs for active databases; copying a live SQLite file at arbitrary time is not sufficient. A retention/deletion schedule remains open until provider terms are verified.

## What is deliberately absent

No chat history informs market predictions. No retrieval index or vector memory is required for six ticker-specific news streams. No model-generated chain of thought is stored as evidence. If a future explanation is added, it must point to factual source IDs and feature values; it cannot change the saved probability or paper action.
