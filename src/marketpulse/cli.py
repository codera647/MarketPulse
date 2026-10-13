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
    baseline = commands.add_parser(
        "baseline-demo", help="synthetic majority/price software check; no provider access"
    )
    baseline.add_argument("--data-dir", type=Path, default=Path("data/baseline-fixture"))
    baseline.add_argument("--seed", type=int, default=42)
    workflow_plan = commands.add_parser(
        "pipeline-plan", help="credential-free collection batches and research gates"
    )
    workflow_plan.add_argument("--contract", required=True, type=Path)
    workflow_plan.add_argument("--batch-sessions", type=int, default=20)
    collect = commands.add_parser(
        "pipeline-collect", help="resumable, rights-gated collection; no automatic training"
    )
    collect.add_argument("--contract", required=True, type=Path)
    collect.add_argument("--batch-sessions", type=int, default=20)
    collect.add_argument("--max-batches", type=int, default=1)
    collect.add_argument("--workers", type=int, choices=(1, 2, 3), default=1,
                         help="bounded workers with separate provider sessions")
    collect.add_argument("--audit-at-end", action="store_true",
                         help="verify each source/row now; defer the full roster audit to run end")
    collect.add_argument("--data-dir", type=Path, default=Path("data/m03"))
    collect.add_argument("--env-file", type=Path)
    inspect = commands.add_parser("dataset-inspect", help="offline lineage and completeness report")
    inspect.add_argument("--contract", required=True, type=Path)
    inspect.add_argument("--data-dir", type=Path, default=Path("data/m03"))
    promote = commands.add_parser("dataset-promote", help="record an explicit human quality review")
    promote.add_argument("--contract", required=True, type=Path)
    promote.add_argument("--review", required=True, type=Path)
    promote.add_argument("--news-models", action="store_true",
                         help="explicitly promote for price AND news model validation")
    promote.add_argument("--data-dir", type=Path, default=Path("data/m03"))
    train = commands.add_parser(
        "baseline-train", help="reviewed real-data baselines; validation only, final test locked"
    )
    train.add_argument("--contract", required=True, type=Path)
    train.add_argument("--promotion-hash", required=True)
    train.add_argument("--data-dir", type=Path, default=Path("data/m03"))
    real_train = commands.add_parser(
        "research-train", help="authorized offline four-model fitting; no deployment promotion")
    real_train.add_argument("--contract", required=True, type=Path)
    real_train.add_argument("--authorization", required=True, type=Path)
    real_train.add_argument("--data-dir", required=True, type=Path)
    real_build = commands.add_parser(
        "research-build", help="bounded real collection, audit and authorized offline fitting")
    real_build.add_argument("--contract", required=True, type=Path)
    real_build.add_argument("--authorization-evidence", required=True)
    real_build.add_argument("--data-dir", required=True, type=Path)
    real_build.add_argument("--env-file", type=Path)
    real_build.add_argument("--workers", type=int, choices=(1, 2, 3), default=1)
    real_build.add_argument("--cycles", type=int, choices=(1, 2, 3), default=3)
    real_build.add_argument("--mask-seen-stories", action="store_true",
                           help="authorized earlier-date story masking; raw audit remains strict")
    real_predict = commands.add_parser(
        "research-predict", help="input-only saved research inference")
    real_predict.add_argument("--data-dir", required=True, type=Path)
    real_predict.add_argument("--release-hash", required=True)
    real_predict.add_argument("--symbol", required=True)
    real_predict.add_argument("--session", required=True, type=date.fromisoformat)
    real_evaluate = commands.add_parser(
        "research-evaluate", help="open the frozen held-out research test; never refit/reselect")
    real_evaluate.add_argument("--data-dir", required=True, type=Path)
    real_evaluate.add_argument("--release-hash", required=True)
    real_evaluate.add_argument("--authorization-evidence", required=True)
    v2_build = commands.add_parser(
        "research-v2-build", help="separate enriched/weighted research; no new final-test claim")
    v2_build.add_argument("--base-data-dir", required=True, type=Path)
    v2_build.add_argument("--base-release-hash", required=True)
    v2_build.add_argument("--data-dir", required=True, type=Path)
    v2_build.add_argument("--authorization-evidence", required=True)
    v2_build.add_argument("--env-file", type=Path)
    v2_predict = commands.add_parser("research-v2-predict", help="saved input-only v2 inference")
    v2_predict.add_argument("--data-dir", required=True, type=Path)
    v2_predict.add_argument("--release-hash", required=True)
    v2_predict.add_argument("--input-hash", required=True)
    v2_reconcile = commands.add_parser(
        "research-v2-reconcile", help="verify complete saved capture; retain expired UNKNOWN")
    v2_reconcile.add_argument("--data-dir", required=True, type=Path)
    v2_reconcile.add_argument("--parent-job-key", required=True)
    v2_reconcile.add_argument("--capture-hash", required=True)
    v2_reconcile.add_argument("--evidence", required=True)
    v2_sentiment_reconcile = commands.add_parser(
        "research-v2-reconcile-sentiment", help="verify saved batch; retain expired UNKNOWN")
    v2_sentiment_reconcile.add_argument("--data-dir", required=True, type=Path)
    v2_sentiment_reconcile.add_argument("--parent-job-key", required=True)
    v2_sentiment_reconcile.add_argument("--sentiment-hash", required=True)
    v2_sentiment_reconcile.add_argument("--evidence", required=True)
    regression_build = commands.add_parser(
        "research-regression-build", help="separate continuous-return research; no trading")
    regression_build.add_argument("--source-v2-dir", required=True, type=Path)
    regression_build.add_argument("--source-release-hash", required=True)
    regression_build.add_argument("--data-dir", required=True, type=Path)
    regression_build.add_argument("--authorization-evidence", required=True)
    boosting_build = commands.add_parser(
        "research-boosting-build", help="fixed-seed XGBoost/LightGBM/AdaBoost return research")
    boosting_build.add_argument("--source-v2-dir", required=True, type=Path)
    boosting_build.add_argument("--source-release-hash", required=True)
    boosting_build.add_argument("--data-dir", required=True, type=Path)
    boosting_build.add_argument("--authorization-evidence", required=True)
    price_build = commands.add_parser(
        "research-price-build", help="price-only classifier research; no trading")
    price_build.add_argument("--source-v2-dir", required=True, type=Path)
    price_build.add_argument("--roster-dir", required=True, type=Path)
    price_build.add_argument("--rows-hash", required=True)
    price_build.add_argument("--source-release-hash", required=True)
    price_build.add_argument("--data-dir", required=True, type=Path)
    price_build.add_argument("--authorization-evidence", required=True)
    price_predict = commands.add_parser("research-price-predict", help="saved price-only inference")
    price_predict.add_argument("--source-v2-dir", required=True, type=Path)
    price_predict.add_argument("--data-dir", required=True, type=Path)
    price_predict.add_argument("--release-hash", required=True)
    price_predict.add_argument("--input-hash", required=True)
    context_build = commands.add_parser(
        "research-context-build", help="separate news/market expert classifiers; no stacking")
    context_build.add_argument("--expert", required=True, choices=("news", "market"))
    context_build.add_argument("--source-v2-dir", required=True, type=Path)
    context_build.add_argument("--roster-dir", required=True, type=Path)
    context_build.add_argument("--rows-hash", required=True)
    context_build.add_argument("--source-release-hash", required=True)
    context_build.add_argument("--data-dir", required=True, type=Path)
    context_build.add_argument("--authorization-evidence", required=True)
    context_predict = commands.add_parser(
        "research-context-predict", help="saved specialist inference")
    context_predict.add_argument("--expert", required=True, choices=("news", "market"))
    context_predict.add_argument("--source-v2-dir", required=True, type=Path)
    context_predict.add_argument("--data-dir", required=True, type=Path)
    context_predict.add_argument("--release-hash", required=True)
    context_predict.add_argument("--input-hash", required=True)
    regression_predict = commands.add_parser(
        "research-regression-predict", help="saved input-only regression inference")
    regression_predict.add_argument("--source-v2-dir", required=True, type=Path)
    regression_predict.add_argument("--data-dir", required=True, type=Path)
    regression_predict.add_argument("--release-hash", required=True)
    regression_predict.add_argument("--input-hash", required=True)
    regression_reconcile = commands.add_parser(
        "research-regression-reconcile-source", help="verify complete expired roster in batches")
    regression_reconcile.add_argument("--source-v2-dir", required=True, type=Path)
    regression_reconcile.add_argument("--data-dir", required=True, type=Path)
    regression_reconcile.add_argument("--parent-job-key", required=True)
    regression_reconcile.add_argument("--rows-hash", required=True)
    regression_reconcile.add_argument("--evidence", required=True)
    full_demo = commands.add_parser("demo-init", help="build the full credential-free fixture demo")
    full_demo.add_argument("--data-dir", type=Path, default=Path("data/demo"))
    full_demo.add_argument("--seed", type=int, default=42)
    forecast = commands.add_parser(
        "demo-forecast", help="verified synthetic replay; no broker orders")
    forecast.add_argument("--symbol", required=True)
    forecast.add_argument("--session", required=True, type=date.fromisoformat)
    forecast.add_argument("--fault", default="NONE", choices=(
        "NONE", "STALE", "MISSING_NEWS", "TIMEOUT", "EXPIRED", "LOW_CONFIDENCE"))
    forecast.add_argument("--data-dir", type=Path, default=Path("data/demo"))
    for name in ("demo-reconcile", "demo-evaluation", "demo-ops", "serve", "dashboard"):
        command = commands.add_parser(name, help="local-only synthetic demo operation")
        command.add_argument("--data-dir", type=Path, default=Path("data/demo"))
        if name in {"serve", "dashboard"}:
            command.add_argument("--port", type=int, default=8000 if name == "serve" else 8501)
    backup = commands.add_parser("demo-backup", help="stop other writers before fixture backup")
    backup.add_argument("--data-dir", type=Path, default=Path("data/demo"))
    backup.add_argument("--destination", type=Path, required=True)
    restore = commands.add_parser("demo-restore", help="restore to a NEW directory and verify")
    restore.add_argument("--backup-dir", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    restore.add_argument("--manifest-hash", required=True)
    arguments = parser.parse_args(argv)

    if arguments.command in {"research-context-build", "research-context-predict"}:
        from marketpulse.context_expert_models import ExpertAPI
        from marketpulse.price_expert_pipeline import build, saved_predict

        try:
            api = ExpertAPI(arguments.expert)
            if arguments.command == "research-context-build":
                result = build(
                    arguments.source_v2_dir, arguments.roster_dir, arguments.data_dir,
                    arguments.source_release_hash, arguments.rows_hash, model_api=api,
                    evidence=arguments.authorization_evidence,
                    progress=lambda event: print(json.dumps(event), file=sys.stderr, flush=True))
            else:
                result = saved_predict(arguments.data_dir, arguments.source_v2_dir,
                                       arguments.release_hash, arguments.input_hash, model_api=api)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        except Exception as error:
            print(f"context research failed: {type(error).__name__}; inspect private receipts; "
                  "no secrets or provider text logged", file=sys.stderr)
            return 2

    if arguments.command in {"research-price-build", "research-price-predict"}:
        from marketpulse.price_expert_pipeline import build, saved_predict

        try:
            if arguments.command == "research-price-build":
                result = build(
                    arguments.source_v2_dir, arguments.roster_dir, arguments.data_dir,
                    arguments.source_release_hash, arguments.rows_hash,
                    evidence=arguments.authorization_evidence,
                    progress=lambda event: print(json.dumps(event), file=sys.stderr, flush=True))
            else:
                result = saved_predict(arguments.data_dir, arguments.source_v2_dir,
                                       arguments.release_hash, arguments.input_hash)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        except Exception as error:
            print(f"price research failed: {type(error).__name__}; inspect private receipts; "
                  "no secrets or provider text logged", file=sys.stderr)
            return 2

    if arguments.command == "research-boosting-build":
        from marketpulse.boosting_pipeline import build

        try:
            result = build(
                arguments.source_v2_dir, arguments.data_dir, arguments.source_release_hash,
                evidence=arguments.authorization_evidence,
                progress=lambda event: print(json.dumps(event), file=sys.stderr, flush=True))
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        except Exception as error:
            print(f"boosting research failed: {type(error).__name__}; inspect private receipts; "
                  "no secrets or provider text logged", file=sys.stderr)
            return 2

    if arguments.command in {"research-regression-build", "research-regression-predict",
                              "research-regression-reconcile-source"}:
        from marketpulse.regression_pipeline import build, reconcile_source, saved_predict

        try:
            if arguments.command == "research-regression-build":
                result = build(
                    arguments.source_v2_dir, arguments.data_dir, arguments.source_release_hash,
                    evidence=arguments.authorization_evidence,
                    progress=lambda event: print(json.dumps(event), file=sys.stderr, flush=True))
            elif arguments.command == "research-regression-predict":
                result = saved_predict(arguments.data_dir, arguments.source_v2_dir,
                                       arguments.release_hash, arguments.input_hash)
            else:
                from marketpulse.v2_runtime import system_awake

                with system_awake():
                    result = reconcile_source(
                        arguments.source_v2_dir, arguments.data_dir, arguments.parent_job_key,
                        arguments.rows_hash, evidence=arguments.evidence,
                        progress=lambda event: print(
                            json.dumps(event), file=sys.stderr, flush=True))
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        except Exception as error:
            print(f"regression research failed: {type(error).__name__}; inspect private receipts; "
                  "no secrets or provider text logged", file=sys.stderr)
            return 2

    if arguments.command in {"research-v2-build", "research-v2-predict", "research-v2-reconcile",
                              "research-v2-reconcile-sentiment"}:
        from marketpulse.v2_pipeline import build_v2, predict_v2

        try:
            if arguments.command == "research-v2-build":
                settings = load_alpaca_settings(arguments.env_file)
                result = build_v2(
                    arguments.base_data_dir, arguments.data_dir, arguments.base_release_hash,
                    AlpacaClient(settings.key, settings.secret, base_url=settings.data_url),
                    evidence=arguments.authorization_evidence,
                    progress=lambda event: print(json.dumps(event), file=sys.stderr, flush=True))
            elif arguments.command == "research-v2-predict":
                result = predict_v2(
                    arguments.data_dir, arguments.release_hash, arguments.input_hash)
            elif arguments.command == "research-v2-reconcile":
                from marketpulse.v2_sources import reconcile_capture

                result = reconcile_capture(arguments.data_dir, arguments.parent_job_key,
                                           arguments.capture_hash, evidence=arguments.evidence)
            else:
                from marketpulse.v2_news import reconcile_sentiment
                from marketpulse.v2_runtime import system_awake

                with system_awake():
                    result = reconcile_sentiment(arguments.data_dir, arguments.parent_job_key,
                                                 arguments.sentiment_hash,
                                                 evidence=arguments.evidence)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        except Exception as error:
            print(f"v2 research failed: {type(error).__name__}; inspect private status/receipts; "
                  "no secrets or provider text logged", file=sys.stderr)
            return 2

    if arguments.command == "research-evaluate":
        from marketpulse.real_evaluation import evaluate_real_research

        try:
            result = evaluate_real_research(
                arguments.data_dir, arguments.release_hash,
                evidence=arguments.authorization_evidence,
                progress=lambda event: print(json.dumps(event, sort_keys=True),
                                            file=sys.stderr, flush=True))
        except Exception as error:
            print(f"research test refused or failed: {type(error).__name__}; "
                  "inspect private test status; no source payloads or credentials logged",
                  file=sys.stderr)
            return 2
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result["state"] == "COMPLETE" else 1

    if arguments.command == "research-build":
        from marketpulse.real_build import build_real_research

        try:
            contract = load_contract(arguments.contract)
            validate_contract(contract, require_approval=True)
            settings = load_alpaca_settings(arguments.env_file)

            def real_pipeline_factory():
                return ExtractionPipeline(arguments.data_dir, AlpacaClient(
                    settings.key, settings.secret, base_url=settings.data_url))

            result = build_real_research(
                real_pipeline_factory(), contract, evidence=arguments.authorization_evidence,
                workers=arguments.workers, cycles=arguments.cycles,
                mask_previous_stories=arguments.mask_seen_stories,
                pipeline_factory=real_pipeline_factory,
                progress=lambda item: print(json.dumps(item, sort_keys=True),
                                            file=sys.stderr, flush=True))
        except Exception as error:
            print(f"real build stopped: {type(error).__name__}; "
                  "inspect private status and harness evidence; no secrets logged", file=sys.stderr)
            return 2
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result["state"] == "COMPLETE" else 1

    if arguments.command in {"research-train", "research-predict"}:
        from marketpulse.real_training import (
            load_training_authorization,
            predict_real_research,
        )

        try:
            if arguments.command == "research-train":
                from marketpulse.real_build import resume_real_training

                result = resume_real_training(
                    arguments.data_dir, load_contract(arguments.contract),
                    load_training_authorization(arguments.authorization),
                    progress=lambda event: print(json.dumps(event, sort_keys=True),
                                                file=sys.stderr, flush=True))
            else:
                result = predict_real_research(arguments.data_dir, arguments.release_hash,
                                               arguments.symbol, arguments.session.isoformat())
        except Exception as error:
            print(f"offline research operation refused or failed: {type(error).__name__}; "
                  "inspect private quality evidence; no credentials or provider payloads logged",
                  file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("state", "COMPLETE") == "COMPLETE" else 1

    if arguments.command in {"demo-init", "demo-forecast", "demo-reconcile", "demo-evaluation",
                              "demo-ops", "serve", "dashboard", "demo-backup", "demo-restore"}:
        from marketpulse.service import DemoService

        try:
            if arguments.command == "demo-init":
                from marketpulse.demo import run_full_demo

                result = run_full_demo(arguments.data_dir, seed=arguments.seed)
            elif arguments.command == "demo-backup":
                from marketpulse.backup import backup_demo

                result = backup_demo(arguments.data_dir, arguments.destination)
            elif arguments.command == "demo-restore":
                from marketpulse.backup import restore_demo

                result = restore_demo(arguments.backup_dir, arguments.destination,
                                      arguments.manifest_hash)
            elif arguments.command in {"serve", "dashboard"}:
                if not 1024 <= arguments.port <= 65535:
                    raise ValueError("port must be 1024 to 65535")
                DemoService(arguments.data_dir).ready()
                if arguments.command == "serve":
                    import uvicorn

                    from marketpulse.api import create_app

                    uvicorn.run(create_app(arguments.data_dir), host="127.0.0.1",
                                port=arguments.port, log_level="warning")
                else:
                    import os
                    import subprocess

                    environment = os.environ.copy()
                    environment["MARKETPULSE_DEMO_DATA_DIR"] = str(arguments.data_dir.resolve())
                    return subprocess.call([
                        sys.executable, "-m", "streamlit", "run",
                        str(Path(__file__).with_name("ui.py")), "--server.address=127.0.0.1",
                        f"--server.port={arguments.port}", "--server.headless=true",
                        "--browser.gatherUsageStats=false"], env=environment)
                return 0
            else:
                service = DemoService(arguments.data_dir)
                if arguments.command == "demo-forecast":
                    result = service.forecast(arguments.symbol, arguments.session.isoformat(),
                                              fault=arguments.fault)
                else:
                    result = {"demo-reconcile": service.reconcile,
                              "demo-evaluation": service.evaluation,
                              "demo-ops": service.operations}[arguments.command]()
        except Exception as error:
            print(f"demo operation refused or failed: {type(error).__name__}; "
                  "check readiness and local fixture evidence; no secrets logged", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("state") in {None, "COMPLETE"} else 1

    if arguments.command in {"pipeline-plan", "pipeline-collect", "dataset-inspect",
                              "dataset-promote", "baseline-train"}:
        from marketpulse.research import (
            collect_dataset,
            collection_plan,
            inspect_dataset,
            load_review,
            promote_dataset,
            saved_pipeline,
            train_reviewed_baselines,
        )

        try:
            contract = load_contract(arguments.contract)
            if arguments.command == "pipeline-plan":
                result = collection_plan(contract, batch_sessions=arguments.batch_sessions)
            elif arguments.command == "pipeline-collect":
                # Rights and budget failures must occur before credentials or database writes.
                validate_contract(contract, require_approval=True)
                collection_plan(contract, batch_sessions=arguments.batch_sessions)
                if not 1 <= arguments.max_batches <= 50:
                    raise ValueError("collection budget must be 1 to 50 batches")
                settings = load_alpaca_settings(arguments.env_file)
                def pipeline_factory():
                    return ExtractionPipeline(arguments.data_dir, AlpacaClient(
                        settings.key, settings.secret, base_url=settings.data_url))

                pipeline = pipeline_factory()
                result = collect_dataset(
                    pipeline, contract, batch_sessions=arguments.batch_sessions,
                    max_batches=arguments.max_batches,
                    audit_each_batch=not arguments.audit_at_end,
                    workers=arguments.workers, pipeline_factory=pipeline_factory,
                    progress=lambda item: print(json.dumps(item, sort_keys=True), file=sys.stderr))
            else:
                if arguments.command != "dataset-inspect":
                    validate_contract(contract, require_approval=True)
                pipeline = saved_pipeline(arguments.data_dir)
                if arguments.command == "dataset-inspect":
                    result = inspect_dataset(pipeline, contract)
                elif arguments.command == "dataset-promote":
                    result = promote_dataset(pipeline, contract, load_review(arguments.review),
                                             news_models=arguments.news_models)
                else:
                    result = train_reviewed_baselines(pipeline, contract, arguments.promotion_hash)
        except Exception as error:
            print(f"research workflow refused or failed: {type(error).__name__}; "
                  "check approvals, review evidence and saved lineage; "
                  "no secrets or provider payloads logged", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        if result.get("state") not in {None, "COMPLETE"}:
            return 1
        failed = result.get("status") in {"BATCH_BLOCKED", "INTEGRITY_BLOCKED", "INCOMPLETE"}
        return 1 if failed else 0

    if arguments.command == "baseline-demo":
        from marketpulse.baselines import run_baseline_demo

        try:
            result = run_baseline_demo(arguments.data_dir, seed=arguments.seed)
        except Exception as error:
            print(f"fixture baseline failed: {type(error).__name__}; "
                  "no secrets or provider payloads logged", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["state"] == "COMPLETE" else 1

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
