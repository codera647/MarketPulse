# Provisional label preview

Status on 2026-10-10: implemented and fixture-tested, **not a frozen training
label contract**. The Stage 1 live source audit remains `NOT_RUN`. This is a
software slice of Stage 2, not evidence that Alpaca's daily-bar open/close is
the intended regular-session or executable-price convention.

## Contract

For one of the six target companies on a valid NYSE session, the preview
reads a verified pre-open snapshot and a separately captured, Trailforge-
verified same-session outcome-bar job. It checks matching session, source
feed and adjustment, the 09:00 ET cutoff, snapshot identity, immutable raw
outcome pages, page receipts, after-close capture time, and all seven outcome
bars. SPY is checked as source context but receives no company label.

Given an **explicit** positive decimal threshold `theta < 1`, the proposed
return is `close / open - 1`. It is `UP` only above `theta`, `DOWN` only below
`-theta`, and `NO_MATERIAL_MOVE` at both boundaries and between them.
The preview uses decimal arithmetic, reports the exact threshold and source
identities, and has a stable hash. There is deliberately no default threshold.
Choosing and freezing one is still D06 in [DECISION](DECISION.md).

The command does not call a provider, change either database, append an
outcome, create a training row, or authorize a paper action. Its JSON says
`ready_for_training: false` and `PROVISIONAL_DAILY_BAR_CONVENTION`.
Prediction inputs still contain only pre-open articles and prior bars; the
same-day outcome is read by this separate preview path.

## Try it after a live audit

Use exact IDs from the live source-audit JSON for a **completed** trading
session, then run:

```powershell
.\.venv\Scripts\marketpulse label-preview `
  --snapshot-hash <64-character-snapshot-hash> `
  --outcome-job-key <64-character-outcome-job-key> `
  --threshold 0.01
```

`0.01` is an illustration, not a selected project threshold. Do not report
any preview as a research label until the provider/feed's regular-session
open/close convention and data rights are checked, historical article
point-in-time limitations are handled, a split/threshold procedure is frozen,
and an outcome ledger is added. See [SOURCE_AUDIT](SOURCE_AUDIT.md).
