# Extraction implementation and evidence

Status: code, fixture tests, and bounded live IEX/historical SIP source audits
are implemented. See [M02 evidence](M02_SOURCE_AUDIT_2026-10-10.md). This is not
a complete training dataset or prediction system. Entry point:
[`README`](../README.md).

## Scope and source authority

`marketpulse extract --session YYYY-MM-DD` runs one bounded exchange-session
job. `marketpulse backfill --start ... --end ...` repeats it for at most 31 NYSE
sessions. The six target stocks are AAPL, NVDA, AMZN, JPM, XOM, WMT; SPY is a
price benchmark. Alpaca historical news (Benzinga) and daily bars are the only
canonical market inputs. The configured price feed (`iex` or `sip`) and
adjustment convention are stored with every bar and in the job manifest.

Agent-Reach commit `94f06c1969dfc1834001269d79d3ad0972d9dee6` is installed
in the project environment. Its `WebChannel` can optionally read up to three
explicit public URLs through Jina Reader. Those captures are retained with
receipt times and hashes but never automatically become eligible historical
market news. Agent-Reach does not supply authoritative historical US stock
bars or point-in-time article versions. No social login, cookie export, or
system-wide `agent-reach install --system` is required.

## Bounded job and provenance

1. Resolve the NYSE session, previous close, 09:00 ET cutoff, and previous-bar
   query window with timezone-aware timestamps.
2. The pinned Trailforge neutral Harness starts `news` and `bars` fetch tasks;
   optional `web` runs only for explicitly provided URLs. Each task saves raw,
   content-addressed JSON and returns bounded hashes/counts, not article text.
3. A separate typed `VERIFY` adapter rereads the raw artifacts, checks schema,
   temporal eligibility, OHLC consistency, complete page traversal and at
   least 21 prior daily bars by default for each stock and SPY. Healthy empty news is
   distinguished from provider failure.
4. Only after harness `COMPLETED` does the application commit source-page,
   normalized article/bar, optional web-capture, and six snapshot records in
   one application-SQLite transaction. Trailforge uses a separate SQLite file.
5. The manifest records snapshot hashes, source/feed/adjustment, query cutoff,
   availability tier and Trailforge receipt IDs. Identical completed requests
   return the existing manifest without refetching.

Callbacks use Trailforge `CANDIDATE_WRITE`, because writing raw candidate
artifacts is a real effect. The callback code is trusted host code, not an OS
sandbox. On a provider exception Trailforge conservatively holds `UNKNOWN`;
it does not silently retry. A known run ID can resume. A crash after harness
start but before the product database gets that ID can leave an orphan run;
the host does not claim exactly-once extraction or cross-database atomicity.

`RECORDED_STRICT` requires all canonical pages to have been received by the
09:00 cutoff. Separately, `fresh_for_0900` requires a forward news query
through at least 08:55 ET. This five-minute threshold is a provisional
operational rule, not evidence that every source published promptly. A
recorded but early capture must not drive a 09:00 action. Historical retrieval after the fact is
`HISTORICAL_APPROXIMATE`, even if article timestamps predate the cutoff.
Post-cutoff article versions and same-day bars are excluded or rejected.

## Verification status and next gate

Local tests cover successful extraction, safe local credential loading,
endpoint/redirect refusal, sanitized errors, empty news, missing/future bars,
pre-cutoff capture, supplementary Agent-Reach isolation, pagination,
post-cutoff revision, idempotency, and provider UNKNOWN. They do not prove
Alpaca account entitlements, real feed coverage, publisher licensing, original
article-version availability, an actual Agent-Reach/Jina response, or model
quality. Live audits now cover ordinary, post-earnings, holiday/early-close,
and revision-candidate cases; both feeds returned prices for all seven symbols.
Reports preserve request IDs and hashes. A true corrected story/original
version, account-specific rights, month-scale coverage, and the regular-session
target convention still need evidence before training begins.

The [source-audit runbook](SOURCE_AUDIT.md) describes the new dated audit
command. Job-to-version link tables preserve which overlapping extraction
jobs observed the same article/bar version and each job's receipt metadata.
The audit's separate Trailforge outcome-bar Goal is for source feasibility
only; same-day bars remain outside pre-open snapshots.
