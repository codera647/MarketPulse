from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pandas_market_calendars as mcal

from marketpulse.alpaca import AlpacaClient
from marketpulse.audit import AuditCase, run_audit
from marketpulse.config import load_alpaca_settings
from marketpulse.extraction import ExtractionConfig, ExtractionPipeline
from marketpulse.features import features_for_snapshot
from marketpulse.labels import preview_label


def sessions_between(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end date is before start date")
    sessions = [
        item.date() for item in mcal.get_calendar("NYSE").valid_days(
            start_date=start, end_date=end
        )
    ]
    if not 1 <= len(sessions) <= 31:
        raise ValueError("backfill requires 1 to 31 market sessions per invocation")
    return sessions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded, auditable market data extraction")
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="extract one NYSE session")
    extract.add_argument("--session", required=True, type=date.fromisoformat)
    extract.add_argument("--mode", choices=("historical", "forward"), default="historical")
    extract.add_argument("--feed", choices=("iex", "sip"), default="iex")
    extract.add_argument("--adjustment", choices=("raw", "split", "all"), default="split")
    extract.add_argument("--web-url", action="append", default=[],
                         help="optional Agent-Reach/Jina supplementary page; not a model input")
    extract.add_argument("--data-dir", type=Path, default=Path("data"))
    extract.add_argument("--env-file", type=Path, help="explicit dotenv path; default cwd/.env")
    backfill = commands.add_parser("backfill", help="historical extraction, at most 31 sessions")
    backfill.add_argument("--start", required=True, type=date.fromisoformat)
    backfill.add_argument("--end", required=True, type=date.fromisoformat)
    backfill.add_argument("--feed", choices=("iex", "sip"), default="iex")
    backfill.add_argument("--adjustment", choices=("raw", "split", "all"), default="split")
    backfill.add_argument("--data-dir", type=Path, default=Path("data"))
    backfill.add_argument("--env-file", type=Path)
    audit = commands.add_parser("audit", help="write a dated source-quality audit")
    audit.add_argument(
        "--case", action="append", required=True, type=AuditCase.parse,
        help="repeat category:YYYY-MM-DD; categories: ordinary, earnings, early_close, "
        "correction, holiday",
    )
    audit.add_argument(
        "--plan", action="store_true", help="write report without network/credentials"
    )
    audit.add_argument("--feed", choices=("iex", "sip"), default="iex")
    audit.add_argument("--adjustment", choices=("raw", "split", "all"), default="split")
    audit.add_argument("--include-content", action="store_true",
                       help="ask Alpaca for article bodies; check license/retention first")
    audit.add_argument("--data-dir", type=Path, default=Path("data"))
    audit.add_argument("--output-dir", type=Path)
    audit.add_argument("--env-file", type=Path)
    audit.add_argument("--page-size", type=int,
                       help="10 to 50 items/page to exercise real provider pagination")
    labels = commands.add_parser(
        "label-preview", help="read-only provisional open-to-close label from an audited outcome"
    )
    labels.add_argument("--snapshot-hash", required=True)
    labels.add_argument("--outcome-job-key", required=True)
    labels.add_argument("--threshold", required=True,
                        help="explicit material-move fraction, e.g. 0.01 for 1 percent")
    labels.add_argument("--data-dir", type=Path, default=Path("data"))
    feature = commands.add_parser(
        "feature-preview", help="read-only pre-open features from one saved snapshot"
    )
    feature.add_argument("--snapshot-hash", required=True)
    feature.add_argument("--data-dir", type=Path, default=Path("data"))
    arguments = parser.parse_args(argv)

    if arguments.command == "feature-preview":
        try:
            result = features_for_snapshot(arguments.data_dir, arguments.snapshot_hash)
        except (ValueError, OSError, sqlite3.DatabaseError) as error:
            print(f"feature preview failed: {error}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if arguments.command == "label-preview":
        try:
            result = preview_label(
                arguments.data_dir, arguments.snapshot_hash,
                arguments.outcome_job_key, arguments.threshold,
            )
        except (ValueError, OSError, sqlite3.DatabaseError) as error:
            print(f"label preview failed: {error}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if arguments.command == "audit":
        try:
            pipeline = None
            if not arguments.plan:
                settings = load_alpaca_settings(arguments.env_file)
                pipeline = ExtractionPipeline(arguments.data_dir, AlpacaClient(
                    settings.key, settings.secret, base_url=settings.data_url
                ))
            report, paths = run_audit(
                tuple(arguments.case), pipeline=pipeline,
                feed=arguments.feed, adjustment=arguments.adjustment,
                include_content=arguments.include_content,
                output_dir=arguments.output_dir or arguments.data_dir / "audits",
                page_size=arguments.page_size,
            )
        except ValueError as error:
            print(f"audit failed: {error}", file=sys.stderr)
            return 2
        print(json.dumps({
            "status": report["status"], "json_report": str(paths[0]),
            "markdown_report": str(paths[1]),
            "case_statuses": [
                {"case": f"{item['kind']}:{item['session']}", "status": item["status"]}
                for item in report["cases"]
            ],
        }, indent=2))
        return 1 if report["status"] == "BLOCKED" else 0

    if arguments.command in {"extract", "backfill"}:
        try:
            settings = load_alpaca_settings(arguments.env_file)
            pipeline = ExtractionPipeline(arguments.data_dir, AlpacaClient(
                settings.key, settings.secret, base_url=settings.data_url
            ))
            if arguments.command == "extract":
                manifest = pipeline.run(
                    ExtractionConfig(
                        arguments.session, feed=arguments.feed,
                        adjustment=arguments.adjustment, mode=arguments.mode,
                        web_urls=tuple(arguments.web_url),
                    )
                )
                print(json.dumps(manifest, sort_keys=True, indent=2))
                return 0 if manifest["state"] == "COMPLETE" else 1
            sessions = sessions_between(arguments.start, arguments.end)
            manifests = [
                pipeline.run(
                    ExtractionConfig(
                        session, feed=arguments.feed, adjustment=arguments.adjustment
                    )
                )
                for session in sessions
            ]
            summary = {
                "sessions": len(sessions),
                "complete": sum(item["state"] == "COMPLETE" for item in manifests),
                "results": [
                    {"session": session.isoformat(), "state": item["state"],
                     "job_key": item["job_key"]}
                    for session, item in zip(sessions, manifests)
                ],
            }
            print(json.dumps(summary, sort_keys=True, indent=2))
            return 0 if summary["complete"] == summary["sessions"] else 1
        except Exception as error:
            # Never print credentials, raw provider payloads, or article bodies.
            print(f"extraction failed: {type(error).__name__}; no secrets or payloads logged",
                  file=sys.stderr)
            return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
