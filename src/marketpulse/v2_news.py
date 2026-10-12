"""Frozen financial sentiment plus explicit heuristic (not ground-truth) events."""

from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path

from marketpulse.clock import parse_time, session_window
from marketpulse.preprocessing import clean_financial_text
from marketpulse.storage import RawStore, digest
from marketpulse.v2_runtime import check_receipt, supervised

FINBERT_REPO = "ProsusAI/finbert"
FINBERT_REVISION = "0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031"
NEWS_VERSION = "financial-news-meaning/2"
MODEL_SPEC = {
    "repo": FINBERT_REPO,
    "revision": FINBERT_REVISION,
    "max_tokens": 96,
    "batch_size": 16,
    "cpu_threads": 2,
    "dtype": "float32",
    "weights_license": "CC-BY-NC-SA-4.0",
    "commercial_use_authorized": False,
    "historical_corpus_date_audit": "INCOMPLETE",
    "fine_tuned_on_market_labels": False,
}
ALIASES = {
    "AAPL": ("aapl", "apple"),
    "NVDA": ("nvda", "nvidia"),
    "AMZN": ("amzn", "amazon"),
    "JPM": ("jpm", "jpmorgan", "jp morgan"),
    "XOM": ("xom", "exxon", "exxonmobil"),
    "WMT": ("wmt", "walmart", "wal-mart"),
}
EVENTS = {
    "earnings": r"\b(?:earnings|quarterly results|eps|revenue)\b",
    "guidance": r"\b(?:guidance|outlook|forecast)\b",
    "acquisition": r"\b(?:acquisition|acquires?|merger|buyout|takeover)\b",
    "legal": r"\b(?:lawsuit|antitrust|litigation|sues?|regulator|ftc)\b",
    "analyst": r"\b(?:upgrade|downgrade|price target|rating)\b",
    "layoffs": r"\b(?:layoffs?|job cuts|restructuring)\b",
}


def article_text(article: dict) -> str:
    return " ".join(
        filter(
            None,
            (
                clean_financial_text(article["headline"]),
                clean_financial_text(article.get("summary")),
            ),
        )
    )


class FinbertEngine:
    def __init__(self, root: Path):
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        torch.set_num_threads(MODEL_SPEC["cpu_threads"])
        location = snapshot_download(
            FINBERT_REPO,
            revision=FINBERT_REVISION,
            cache_dir=str(root / "model-cache"),
            allow_patterns=["*.json", "vocab.txt", "model.safetensors", "README.md"],
            max_workers=2,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            location, local_files_only=True, trust_remote_code=False
        )
        self.model = AutoModelForSequenceClassification.from_pretrained(
            location, local_files_only=True, trust_remote_code=False, dtype=torch.float32
        )
        self.model.eval()
        self.torch = torch
        self.labels = [self.model.config.id2label[i].lower() for i in range(3)]
        if set(self.labels) != {"positive", "negative", "neutral"}:
            raise ValueError("unexpected frozen sentiment label order")

    def score(self, texts: list[str]) -> list[dict]:
        if not 1 <= len(texts) <= MODEL_SPEC["batch_size"]:
            raise ValueError("sentiment batch must be bounded")
        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=MODEL_SPEC["max_tokens"],
            return_tensors="pt",
        )
        with self.torch.inference_mode():
            values = self.torch.softmax(self.model(**encoded).logits, dim=-1).tolist()
        full_lengths = [len(self.tokenizer.encode(text, truncation=False)) for text in texts]
        return [
            {
                "probabilities": dict(zip(self.labels, row)),
                "truncated": length > MODEL_SPEC["max_tokens"],
            }
            for row, length in zip(values, full_lengths)
        ]


def validate_sentiment(value: dict) -> None:
    scores = value["probabilities"]
    if (
        set(scores) != {"positive", "negative", "neutral"}
        or any(
            isinstance(v, bool)
            or not isinstance(v, (float, int))
            or not math.isfinite(v)
            or not 0 <= v <= 1
            for v in scores.values()
        )
        or not math.isclose(sum(scores.values()), 1, abs_tol=1e-5)
        or type(value["truncated"]) is not bool
    ):
        raise ValueError("invalid frozen sentiment probabilities")


def sentiment_inputs(rows: list[dict]) -> dict[str, str]:
    texts = {}
    for row in rows:
        for article in row["news"]:
            text = article_text(article)
            if text:
                texts[digest({"text": text, "spec": MODEL_SPEC})] = text
    if len(texts) > 200000:
        raise ValueError("sentiment document count exceeds research bound")
    return dict(sorted(texts.items()))


def capture_sentiment(root: Path, rows: list[dict], checkpoint, *, engine_factory=FinbertEngine):
    store = RawStore(root / "artifacts")
    texts = sentiment_inputs(rows)
    items, engine = list(texts.items()), None
    results = []
    for i in range(0, len(items), MODEL_SPEC["batch_size"]):
        chunk = items[i : i + MODEL_SPEC["batch_size"]]
        input_hash = store.put({"texts": chunk, "spec": MODEL_SPEC})
        checkpoint(
            {
                "stage": "EXTRACTING_NEWS_MEANING",
                "documents_complete": i,
                "documents_total": len(items),
            }
        )

        def execute():
            nonlocal engine
            if engine is None:
                engine = engine_factory(root)
            scores = engine.score([text for key, text in chunk])
            if len(scores) != len(chunk):
                raise ValueError("sentiment output count mismatch")
            for score in scores:
                validate_sentiment(score)
            return {
                "sentiment_hash": store.put(
                    {
                        "input_hash": input_hash,
                        "scores": dict(zip([key for key, text in chunk], scores)),
                    }
                )
            }

        def verify(result):
            saved = store.get(result["sentiment_hash"])
            if saved["input_hash"] != input_hash or set(saved["scores"]) != {
                key for key, text in chunk
            }:
                raise ValueError("sentiment text binding mismatch")
            for score in saved["scores"].values():
                validate_sentiment(score)
            # Independent first/last replay per batch; all outputs get shape/binding checks.
            # This is explicitly sampled inference verification, not full corpus rerunning.
            nonlocal engine
            if engine is None:
                engine = engine_factory(root)
            sample = [chunk[0]] if len(chunk) == 1 else [chunk[0], chunk[-1]]
            replay = engine.score([text for key, text in sample])
            for (key, text), score in zip(sample, replay):
                actual = saved["scores"][key]
                if score["truncated"] != actual["truncated"] or any(
                    not math.isclose(
                        score["probabilities"][name], actual["probabilities"][name], abs_tol=1e-5
                    )
                    for name in score["probabilities"]
                ):
                    raise ValueError("sentiment sampled inference replay mismatch")

        results.append(
            supervised(
                root,
                "sentiment",
                {"input_hash": input_hash, "spec_hash": digest(MODEL_SPEC)},
                execute,
                verify,
                lease=300,
            )
        )
    return {
        "manifest_hash": store.put(
            {"spec": MODEL_SPEC, "batches": results, "documents": len(items)}
        ),
        "documents": len(items),
    }


def load_sentiment(root: Path, manifest_hash: str) -> dict:
    store = RawStore(root / "artifacts")
    manifest, result = store.get(manifest_hash), {}
    if manifest["spec"] != MODEL_SPEC:
        raise ValueError("sentiment specification changed")
    for batch in manifest["batches"]:
        check_receipt(root, batch)
        saved = store.get(batch["sentiment_hash"])
        inputs = store.get(saved["input_hash"])
        if inputs["spec"] != MODEL_SPEC or set(saved["scores"]) != {
            key for key, text in inputs["texts"]
        }:
            raise ValueError("sentiment manifest differs from input documents")
        for key, text in inputs["texts"]:
            if digest({"text": text, "spec": MODEL_SPEC}) != key or key in result:
                raise ValueError("sentiment text identity mismatch")
            validate_sentiment(saved["scores"][key])
            result[key] = saved["scores"][key]
    if len(result) != manifest["documents"]:
        raise ValueError("sentiment corpus incomplete")
    return result


def news_values(row: dict, sentiments: dict) -> dict:
    symbol, session = row["symbol"], row["session"]
    window = session_window(date.fromisoformat(session))
    values = {f"news_event_{name}": 0 for name in EVENTS}
    weighted, ages, relevance, truncated = [], [], [], 0
    for article in row["news"]:
        created, updated = parse_time(article["created_at"]), parse_time(article["updated_at"])
        if not window.previous_close < created <= updated <= window.cutoff:
            raise ValueError("v2 news crosses the cutoff/version boundary")
        text = article_text(article)
        if not text:
            continue
        headline = clean_financial_text(article["headline"]).lower()
        direct = any(
            re.search(r"\b" + re.escape(alias) + r"\b", headline) for alias in ALIASES[symbol]
        )
        tags = article.get("symbols_json")
        if tags:
            import json

            tags = json.loads(tags)
        else:
            tags = article.get("symbols", [])
        if symbol not in tags:
            raise ValueError("v2 news lacks the target's source entity tag")
        weight = 1.0 if direct else 1 / max(len(tags), 1)
        age = (window.cutoff - updated).total_seconds() / 3600
        recency_weight = weight / (1 + age / 12)
        score = sentiments[digest({"text": text, "spec": MODEL_SPEC})]
        validate_sentiment(score)
        weighted.append((recency_weight, score["probabilities"]))
        ages.append(age)
        relevance.append(weight)
        truncated += int(score["truncated"])
        for name, pattern in EVENTS.items():
            values[f"news_event_{name}"] += int(bool(re.search(pattern, text, re.I)))
    denominator = sum(weight for weight, score in weighted)
    for name in ("positive", "negative", "neutral"):
        values[f"news_sentiment_{name}"] = (
            sum(weight * score[name] for weight, score in weighted) / denominator
            if weighted
            else None
        )
    values.update(
        {
            "news_meaning_missing": int(not weighted),
            "news_eligible_count": len(weighted),
            "news_entity_relevance_mean": sum(relevance) / len(relevance) if relevance else None,
            "news_latest_age_hours": min(ages) if ages else None,
            "news_truncated_count": truncated,
            "scheduled_earnings_today": None,
            "earnings_schedule_missing": 1,
            "numeric_earnings_surprise": None,
            "earnings_consensus_missing": 1,
        }
    )
    return values
