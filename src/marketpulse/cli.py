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
from marketpulse.dataset import load_contract, run_dataset_batch, split_sessions, validate_contract
from marketpulse.extraction import ExtractionConfig, ExtractionPipeline
from marketpulse.features import features_for_snapshot
from marketpulse.labels import preview_label
from marketpulse.outcomes import capture_regular_outcome


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
    plan = commands.add_parser("dataset-plan", help="validate a draft contract without network")
    plan.add_argument("--contract", required=True, type=Path)
    dataset = commands.add_parser("dataset-batch", help="approved historical batch, <=31 sessions")
    dataset.add_argument("--contract", required=True, type=Path)
    dataset.add_argument("--start", required=True, type=date.fromisoformat)
    dataset.add_argument("--end", required=True, type=date.fromisoformat)
    dataset.add_argument("--data-dir", type=Path, default=Path("data/m03"))
    dataset.add_argument("--env-file", type=Path)
    outcome = commands.add_parser("regular-outcome", help="one after-close minute-proxy probe")
    outcome.add_argument("--session", required=True, type=date.fromisoformat)
    outcome.add_argument("--feed", choices=("iex", "sip"), required=True)
    outcome.add_argument("--adjustment", choices=("raw", "split", "all"), default="split")
    outcome.add_argument("--data-dir", type=Path, default=Path("data/m03"))
    outcome.add_argument("--env-file", type=Path)
    arguments = parser.parse_args(argv)

    if arguments.command in {"dataset-plan", "dataset-batch", "regular-outcome"}:
        try:
            contract = None
            if arguments.command.startswith("dataset-"):
                contract = load_contract(arguments.contract)
                if arguments.command == "dataset-plan":
                    from collections import Counter

                    counts = dict(Counter(split_sessions(contract).values()))
                    print(json.dumps({
                        "sessions_by_split": counts,
                        "expected_rows": sum(counts.values()) * len(contract["symbols"]),
                        "plan_approved": contract["plan_approved"],
                        "rights_confirmed": contract["rights_confirmed"],
                        "network_used": False, "ready_for_training": False,
                    }, indent=2))
                    return 0
                # Refuse an unapproved draft before reading secrets or opening databases.
                validate_contract(contract, require_approval=True)
            settings = load_alpaca_settings(arguments.env_file)
            pipeline = ExtractionPipeline(arguments.data_dir, AlpacaClient(
                settings.key, settings.secret, base_url=settings.data_url))
            if arguments.command == "dataset-batch":
                result = run_dataset_batch(pipeline, contract, arguments.start, arguments.end)
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1 if result["batch_failures"] else 0
            result = capture_regular_outcome(pipeline, arguments.session,
                                             feed=arguments.feed, adjustment=arguments.adjustment)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["state"] == "COMPLETE" else 1
        except Exception as error:
            print(f"dataset/outcome operation failed: {type(error).__name__}; "
                  "inspect approvals and local evidence; no secrets or payloads logged",
                  file=sys.stderr)
            return 2

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
