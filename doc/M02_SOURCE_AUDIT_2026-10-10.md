# M02: live source-access evidence

Audit date: 2026-10-10. Scope: private local research samples for AAPL, NVDA,
AMZN, JPM, XOM, WMT, and benchmark SPY. This completes the **technical M02
audit**, not the broader data-rights, regular-session target, or model gates.
Reports remain `TECHNICAL_REVIEW_REQUIRED`; no model was trained.

## Implemented controls

The CLI reads cwd `.env` or an explicit `--env-file`; process values win.
Parsing is literal, with no shell execution, interpolation, parent-directory
discovery, or environment mutation. UTF-8 BOM and the user's mixed-case
`APCA_API_EndPOINT` name work. Secret fields are excluded from representations.

The configured endpoint was recognized as a trading endpoint. Extraction uses
only `https://data.alpaca.markets`; no trading/account/order endpoint was called.
`APCA_API_DATA_URL` must equal that approved origin. Arbitrary hosts, embedded
credentials, URL query parameters, and redirects are rejected before credentials
can be forwarded. HTTP/transport failures expose sanitized status/reason data.

Reports include observed schema/types, publisher, pagination, last-21-session
gaps, and provider failures. Page-size settings participate in `extraction/3`
identity. Incomplete extraction cannot materialize snapshots.

## Live results

Both `iex` and historical `sip` passed these four distinct completed-session
cases, with `split` adjustment and article bodies disabled:

| Session | Case | Raw / eligible news per feed | Prior bar dates per symbol | Prior / outcome symbol coverage |
| --- | --- | ---: | ---: | --- |
| 2026-10-09 | Recent ordinary | 26 / 26 | 32 | 7/7 and 7/7 |
| 2025-08-04 | Older ordinary | 27 / 27 | 30 | 7/7 and 7/7 |
| 2025-08-01 | Post-Apple-earnings | 43 / 43 | 31 | 7/7 and 7/7 |
| 2025-11-28 | Early close: 18:00 UTC / 13:00 ET | 34 / 34 | 32 | 7/7 and 7/7 |

No required 21-session price gaps appeared in these samples. The 2025-11-27
holiday produced `CALENDAR_CLOSED` without market extraction. Each accepted
session produced six snapshots, a `COMPLETED` Trailforge extraction, and a
separate verified outcome-source run: 24 company snapshots per feed across
the four distinct sessions, not a training table. Local reports preserve
raw page hashes, request IDs, run IDs, and verification receipts.

Apple's [issuer release](https://www.apple.com/newsroom/2025/07/apple-reports-third-quarter-results/)
confirms results on July 31, 2025 and an afternoon Pacific-time call; August 1
samples the following pre-open window. This is an AAPL event case, not evidence
that all six companies reported earnings. Exchange-calendar handling was
checked against [NYSE calendar information](https://www.nyse.com/trade/hours-calendars).

The recent ordinary case is also tagged `correction` **as a revision-candidate
probe only**: three items had `updated_at > created_at`, but none had an explicit
correction headline or a post-cutoff revision. Independent evidence of a true
corrected story and its original version remains unavailable. The four distinct
sessions showed 3, 20, 32, and 26 revision candidates respectively, not verified
editorial corrections. Synthetic tests cover post-cutoff version rejection.

50-item price queries traversed five pages each. A 15-item SIP query traversed
two news pages and 15 price pages, including all seven symbols. A 10-item stress
run exceeded the 20-page price cap, stayed `WAITING_HUMAN`, and materialized no
snapshots. The held run was preserved; changed page size created a different job.

All six recent SIP snapshots passed the real shared feature builder with 21
earlier sessions, raw-version checks, and healthy no-news handling for JPM/WMT.
This exposed a relative-path SQLite URI bug; feature and label readers now
resolve paths before opening SQLite read-only, with regression coverage.

## Schema and source choices

Observed publisher: `benzinga`. News fields included integer `id`, string
`created_at/updated_at/headline/summary/source/url/author/content`, and list
`symbols/images`; `content` was empty. Bars had string `t`, numeric `o/h/l/c/v/vw`,
and integer `n`, consistent with the [news endpoint](https://docs.alpaca.markets/us/reference/news-3)
and [bar endpoint](https://docs.alpaca.markets/us/reference/stockbars). No raw
article or price row is copied into this document.

- Keep canonical news Alpaca/Benzinga, headline/metadata only. Body retrieval
  and Agent-Reach model features remain disabled pending separate review.
- Historical SIP is the preferred candidate for M03 price research. This does
  not prove a paid subscription or real-time SIP entitlement: the [provider FAQ](https://docs.alpaca.markets/us/docs/market-data-faq)
  distinguishes older historical access from recent data, and IEX is one venue.
- Never combine feeds as one series: open or close differed in **27 of 28**
  matched ticker-session outcome pairs. Record feed and adjustment explicitly.
- Historical snapshots remain `HISTORICAL_APPROXIMATE`. Publication/update
  timestamps cannot reconstruct original text or receipt time. The
  [historical-news documentation](https://docs.alpaca.markets/us/docs/historical-news-data)
  describes historical access, not an original-version archive.
- Daily bars are `PROVIDER_DAILY_NOT_CERTIFIED_REGULAR_SESSION`. The provider's
  [aggregation description](https://docs.alpaca.markets/us/docs/market-data-faq)
  is trade-condition-based; a daily response does not certify official auction
  prices, a regular-session-only target, or an executable fill.

## Gates before M03/model claims

1. Verify regular-session opening/closing prices and freeze the label contract,
   or obtain user approval for a distinctly named provider-daily target. Do
   not relabel provisional bars silently.
2. Confirm account-specific storage, training, retention, and sharing rights.
   Public [Alpaca terms](https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf)
   describe personal/noncommercial use and redistribution restrictions;
   additional account/provider agreements may apply. This audit does not
   approve public/interviewer distribution. Keep caches private, avoid body
   pulls, and obtain provider clarification where necessary.
3. Audit coverage by month, corporate actions, and symbol/adjustment history
   before selecting chronological splits. Four samples do not prove complete
   multi-year coverage or a useful predictive signal.
4. Verify an actual corrected-story example or retain the original-version
   limitation. Rate ceilings were not load-tested; bounded retries are not
   a measured account-throughput guarantee.

## Local evidence (excluded from Git)

| Report | SHA-256 |
| --- | --- |
| `data/m02-iex/audits/source-audit-20261010T080805.547948Z-b4d58e6a.json` | `d7dcc60c6466c2ee30c299fc7cf35e337a443057d6f7be97ebc5a2d1e11e1cdb` |
| `data/m02-sip/audits/source-audit-20261010T080704.745290Z-5cc1b8d6.json` | `fa704c9c43e6eb30bd60696e91760e04807c09f7d7906d2b30ac54b00e841c11` |
| `data/m02-sip-pagination/audits/source-audit-20261010T080817.500740Z-7c39ef24.json` | `398a3a136566cd3ae2a7c38bcf3faece40f2b6c0fbb58a455162136ae31f7300` |

Cap-failure report:
`data/m02-sip-pagination/audits/source-audit-20261010T080726.409544Z-6826f00e.json`.
Associated raw captures and SQLite authorities stay in their local data
directories. Code, tests, and this aggregate audit summary are the GitHub
deliverables, not `.env`, raw payloads, datasets, or model artifacts.

Verification: **51 fixture regression tests passed**, including local-file
configuration, credential redaction, endpoint/redirect refusal, sanitized
failures, pagination caps, rolling-window gaps, and relative preview paths.
`ruff check src tests` passed. Real feature validation passed for six SIP
snapshots; none of these checks establishes financial predictive value.

Delivery: [code commit `02ac97b`](https://github.com/codera647/MarketPulse/commit/02ac97bcd3f161ff53a8baa3774a11c09fb31686)
was pushed to `main`. Its [GitHub CI run](https://github.com/codera647/MarketPulse/actions/runs/38037607123)
passed installation, lint, and regression tests. [M02](https://github.com/codera647/MarketPulse/milestone/3)
was closed only after verifying that push and CI success. The credential scan
passed for 22 staged files and 101 local audit/raw/database artifacts; no
credential value was printed. Later commits require their own CI verification.
