from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from agent_reach.channels.web import WebChannel
from trailforge.ports import AdapterCapabilities, FunctionAdapter, VerifiedResult
from trailforge.runtime import Goal, Harness, Task

from marketpulse.alpaca import AlpacaClient, CapturedPage
from marketpulse.clock import SessionWindow, parse_time, session_window, utc_iso
from marketpulse.constants import BARS_MAX_PAGES, NEWS_MAX_PAGES, STOCKS, SYMBOLS, WEB_MAX_URLS
from marketpulse.normalize import (
    DataQualityError,
    build_snapshots,
    normalize_bars,
    normalize_news,
    validate_bar_coverage,
)
from marketpulse.storage import ExtractionStore, RawStore, digest

CONTRACT_VERSION = "extraction/3"


@dataclass(frozen=True)
class ExtractionConfig:
    session: date
    feed: str = "iex"
    adjustment: str = "split"
    mode: str = "historical"
    web_urls: tuple[str, ...] = ()
    min_prior_bars: int = 21
    include_content: bool = False
    news_page_size: int = 50
    bar_page_size: int = 10000

    def validate(self) -> None:
        if self.feed not in {"iex", "sip"}:
            raise ValueError("feed must be iex or sip")
        if self.adjustment not in {"raw", "split", "all"}:
            raise ValueError("unsupported bar adjustment")
        if self.mode not in {"historical", "forward"}:
            raise ValueError("mode must be historical or forward")
        if not 1 <= self.min_prior_bars <= 30:
            raise ValueError("min_prior_bars must be between 1 and 30")
        if type(self.include_content) is not bool:
            raise ValueError("include_content must be a boolean")
        if not 1 <= self.news_page_size <= 50 or not 1 <= self.bar_page_size <= 10000:
            raise ValueError("invalid provider page size")
        if len(self.web_urls) > WEB_MAX_URLS:
            raise ValueError(f"at most {WEB_MAX_URLS} supplementary web URLs are allowed")
        if len(set(self.web_urls)) != len(self.web_urls):
            raise ValueError("duplicate web URL")


class ExtractionPipeline:
    def __init__(
        self,
        data_dir: Path,
        client: AlpacaClient,
        *,
        clock: Callable[[], datetime] | None = None,
        web_reader: Callable[[str], str] | None = None,
    ):
        self.data_dir = data_dir
        self.raw = RawStore(data_dir / "raw")
        self.store = ExtractionStore(data_dir / "marketpulse.sqlite3")
        self.harness_path = data_dir / "trailforge.sqlite3"
        self.client = client
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.web_reader = web_reader or WebChannel().read

    def _capture_pages(self, pages: list[CapturedPage]) -> dict:
        hashes = []
        count = 0
        for page in pages:
            envelope = asdict(page)
            hashes.append(self.raw.put(envelope))
            items = page.payload["news"] if page.source == "alpaca_news" else page.payload["bars"]
            count += len(items) if isinstance(items, list) else sum(len(v) for v in items.values())
        return {"hashes": hashes, "count": count, "pages": len(hashes)}

    def _load_source(self, result: dict, expected_source: str) -> list[tuple[str, dict]]:
        pages = []
        if not result["hashes"] or result["pages"] != len(result["hashes"]):
            raise DataQualityError(f"{expected_source}: missing or incomplete pages")
        for key in result["hashes"]:
            page = self.raw.get(key)
            if page.get("source") != expected_source:
                raise DataQualityError("source identity mismatch")
            pages.append((key, page))
        return pages

    def _normalized(
        self, news_result: dict, bars_result: dict, window: SessionWindow, config: ExtractionConfig
    ) -> tuple[list[dict], list[dict], list[dict]]:
        news_pages = self._load_source(news_result, "alpaca_news")
        bar_pages = self._load_source(bars_result, "alpaca_bars")
        articles = [
            article for key, page in news_pages for article in normalize_news(page, key, window)
        ]
        bars = [
            bar for key, page in bar_pages
            for bar in normalize_bars(page, key, window, config.feed, config.adjustment)
        ]
        validate_bar_coverage(bars, window, config.min_prior_bars)
        page_records = [
            {
                "digest": key,
                "source": page["source"],
                "received_at": page["received_at"],
                "request_id": page.get("request_id"),
            }
            for key, page in [*news_pages, *bar_pages]
        ]
        return page_records, articles, bars

    def run(self, config: ExtractionConfig) -> dict:
        config.validate()
        window = session_window(config.session)
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("host clock must be timezone-aware")
        # Forward capture may be taken shortly before 09:00; it never requests future news.
        news_end = min(now, window.cutoff) if config.mode == "forward" else window.cutoff
        if news_end <= window.previous_close:
            raise ValueError("news capture time precedes previous market close")
        input_binding = {
            "contract": CONTRACT_VERSION,
            "session": config.session.isoformat(),
            "previous_close": utc_iso(window.previous_close),
            "cutoff": utc_iso(window.cutoff),
            "news_end": utc_iso(news_end),
            "feed": config.feed,
            "adjustment": config.adjustment,
            "mode": config.mode,
            "web_urls": config.web_urls,
            "min_prior_bars": config.min_prior_bars,
            "include_content": config.include_content,
            "news_page_size": config.news_page_size,
            "bar_page_size": config.bar_page_size,
            "data_url": getattr(self.client, "base_url", "https://data.alpaca.markets"),
        }
        job_key = digest(input_binding)
        prior = self.store.get_job(job_key)
        if prior and prior["status"] == "COMPLETE":
            import json

            return json.loads(prior["manifest_json"])

        def fetch_news(request):
            specification = request.input
            pages = self.client.pages(
                "alpaca_news", "/v1beta1/news",
                {
                    "symbols": ",".join(STOCKS), "start": specification["start"],
                    "end": specification["end"], "sort": "asc", "limit": config.news_page_size,
                    "include_content": str(specification["include_content"]).lower(),
                },
                "news", max_pages=NEWS_MAX_PAGES,
            )
            return self._capture_pages(pages)

        def fetch_bars(request):
            specification = request.input
            pages = self.client.pages(
                "alpaca_bars", "/v2/stocks/bars",
                {
                    "symbols": ",".join(SYMBOLS), "start": specification["start"],
                    "end": specification["end"], "timeframe": "1Day",
                    "limit": config.bar_page_size,
                    "feed": specification["feed"], "adjustment": specification["adjustment"],
                    "sort": "asc",
                },
                "bars", max_pages=BARS_MAX_PAGES,
            )
            return self._capture_pages(pages)

        def fetch_web(request):
            captures = []
            for url in request.input["urls"]:
                content = self.web_reader(url)
                if not isinstance(content, str) or len(content.encode("utf-8")) > 5_000_000:
                    raise ValueError("supplementary web response is invalid or too large")
                received_at = utc_iso(self.clock())
                raw_digest = self.raw.put(
                    {"source": "agent_reach_web", "url": url,
                     "received_at": received_at, "content": content}
                )
                captures.append({"url": url, "raw_digest": raw_digest, "received_at": received_at})
            return {"captures": captures, "count": len(captures)}

        def verify(request):
            try:
                news_result = request.dependencies["news"]
                bars_result = request.dependencies["bars"]
                _, articles, bars = self._normalized(news_result, bars_result, window, config)
                if "web" in request.dependencies:
                    for capture in request.dependencies["web"]["captures"]:
                        raw = self.raw.get(capture["raw_digest"])
                        if raw["url"] != capture["url"] or raw["source"] != "agent_reach_web":
                            raise DataQualityError("web capture mismatch")
                evidence = {
                    "job_key": job_key, "news_pages": news_result["pages"],
                    "bar_pages": bars_result["pages"], "eligible_articles": len(articles),
                    "prior_bars": len(bars), "news_empty": news_result["count"] == 0,
                }
                return VerifiedResult("PASS", request.goal_digest, evidence)
            except (DataQualityError, ValueError, KeyError, TypeError) as error:
                return VerifiedResult("FAIL", request.goal_digest, {"reason": str(error)[:300]})
            except OSError:
                return VerifiedResult(
                    "UNKNOWN", request.goal_digest, {"reason": "artifact_unavailable"}
                )

        adapters = [
            FunctionAdapter(
                AdapterCapabilities("marketpulse.alpaca_news/1", "TOOL", "CANDIDATE_WRITE",
                                    reservation_units=2), fetch_news
            ),
            FunctionAdapter(
                AdapterCapabilities("marketpulse.alpaca_bars/1", "TOOL", "CANDIDATE_WRITE",
                                    reservation_units=2), fetch_bars
            ),
            FunctionAdapter(
                AdapterCapabilities("marketpulse.agent_reach_web/1", "TOOL", "CANDIDATE_WRITE",
                                    reservation_units=2), fetch_web
            ),
            FunctionAdapter(
                AdapterCapabilities("marketpulse.verify_extract/1", "VERIFY", "PURE"), verify
            ),
        ]
        tasks = [
            Task("news", "marketpulse.alpaca_news/1",
                 {"start": utc_iso(window.previous_close), "end": utc_iso(news_end),
                  "include_content": config.include_content}),
            Task("bars", "marketpulse.alpaca_bars/1",
                 {"start": utc_iso(window.bars_start), "end": utc_iso(window.bars_end),
                  "feed": config.feed, "adjustment": config.adjustment}),
        ]
        dependencies = ["news", "bars"]
        if config.web_urls:
            tasks.append(Task("web", "marketpulse.agent_reach_web/1", {"urls": config.web_urls}))
            dependencies.append("web")
        tasks.append(Task("verify", "marketpulse.verify_extract/1", input_binding,
                          tuple(dependencies)))
        goal = Goal(
            "local-demo", f"marketpulse:extract:{job_key}",
            f"Extract and independently verify market inputs for {config.session}",
            tuple(tasks), ("verify",),
            allowed_effects=("PURE", "CANDIDATE_WRITE"), budget_units=8,
        )
        harness = Harness(
            self.harness_path, tenant_id=goal.tenant_id, resource_id=goal.resource_id,
            adapters=adapters, lease_seconds=180, tenant_limit=100000, global_limit=1000000,
        )
        self.store.reserve_job(job_key, config.session.isoformat())
        prior = self.store.get_job(job_key)
        run_id = prior["run_id"] or harness.start(goal)
        if prior["run_id"] is None:
            self.store.set_run_id(job_key, run_id)
        record = harness.advance(run_id, goal)
        if record["state"] != "COMPLETED":
            self.store.set_status(job_key, record["state"])
            return {"job_key": job_key, "run_id": run_id, "state": record["state"]}

        news_result = record["tasks"]["news"]["result"]
        bars_result = record["tasks"]["bars"]["result"]
        page_records, articles, bars = self._normalized(news_result, bars_result, window, config)
        news_pages = self._load_source(news_result, "alpaca_news")
        strict = config.mode == "forward" and all(
            parse_time(page["received_at"]) <= window.cutoff
            for _, page in [*news_pages, *self._load_source(bars_result, "alpaca_bars")]
        )
        fresh_for_0900 = news_end >= window.cutoff - timedelta(minutes=5)
        tier = "RECORDED_STRICT" if strict else "HISTORICAL_APPROXIMATE"
        web_captures = []
        if "web" in record["tasks"]:
            for item in record["tasks"]["web"]["result"]["captures"]:
                web_captures.append({"digest": digest(item), "job_key": job_key, **item})
        snapshots = build_snapshots(
            job_key, window, articles, bars, tier=tier,
            fresh_for_0900=fresh_for_0900 if strict else False,
        )
        manifest = {
            "job_key": job_key,
            "run_id": run_id,
            "state": "COMPLETE",
            "session": config.session.isoformat(),
            "cutoff_utc": utc_iso(window.cutoff),
            "news_query_end_utc": utc_iso(news_end),
            "tier": tier,
            "fresh_for_0900": fresh_for_0900 if strict else False,
            "feed": config.feed,
            "adjustment": config.adjustment,
            "include_content": config.include_content,
            "data_url": getattr(self.client, "base_url", "https://data.alpaca.markets"),
            "price_timeframe": "1Day",
            "price_convention": "PROVIDER_DAILY_NOT_CERTIFIED_REGULAR_SESSION",
            "raw_page_count": len(page_records),
            "eligible_article_versions": len(articles),
            "bar_versions": len(bars),
            "supplementary_web_captures": len(web_captures),
            "snapshots": {item["symbol"]: item["snapshot_hash"] for item in snapshots},
            "trailforge_receipts": {
                name: record["tasks"][name]["receipt"]["receipt_id"]
                for name in record["tasks"]
            },
            "note": (
                "Agent-Reach web captures are supplementary and excluded "
                "from market snapshots."
            ),
        }
        self.store.commit_extract(
            job_key, manifest, page_records, articles, bars, web_captures, snapshots
        )
        return manifest
