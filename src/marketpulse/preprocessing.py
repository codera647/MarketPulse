"""Deterministic financial-text cleaning; raw evidence remains immutable."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from html.parser import HTMLParser

from marketpulse.storage import digest

PREPROCESSING_VERSION = "financial-text/1"
FINANCIAL_TOKEN_PATTERN = r"(?u)(?:[+-]?\d+(?:\.\d+)?%?|\b[^\W\d]\w{1,63}\b)"
NEWS_MASK_POLICY = "earlier-date-story-mask/1"


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"br", "p", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        else:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_financial_text(value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > 100000:
        raise ValueError("text must be a bounded string or null")
    parser = _VisibleText()
    parser.feed(value)
    text = unicodedata.normalize("NFKC", " ".join(parser.parts))
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = "".join(" " if unicodedata.category(char).startswith("C") else char for char in text)
    # Do not remove negation, financial numbers, signs, percentage symbols or outlier stories.
    return " ".join(text.split())


def clean_news_text(news: list[dict]) -> str:
    seen, texts = set(), []
    for article in news:
        text = clean_financial_text(article["headline"])
        summary = clean_financial_text(article.get("summary"))
        if summary:
            text = f"{text} {summary}"
        group = text.casefold()
        if text and group not in seen:
            seen.add(group)
            texts.append(text)
    return " ".join(texts) or "noeligibleheadline"


def story_keys(article: dict) -> tuple[str, str]:
    return (digest(str(article["provider_id"])),
            digest(" ".join(article["headline"].casefold().split())))


def extend_news_registry(registry: dict, rows: list[dict]) -> None:
    """Input metadata only: no labels, returns, outcomes or feature-fitting here."""
    for row in rows:
        session = row["features"]["session"]
        date.fromisoformat(session)
        for article in row.get("news", []):
            for field, key in zip(("provider_ids", "headline_groups"), story_keys(article)):
                previous = registry[field].get(key)
                registry[field][key] = min(previous, session) if previous else session
    if any(len(registry[field]) > 500000 for field in ("provider_ids", "headline_groups")):
        raise ValueError("seen-story registry exceeds the bounded research size")


def mask_seen_stories(registry: dict, news: list[dict], session: str) -> list[dict]:
    date.fromisoformat(session)
    kept = []
    for article in news:
        keys = story_keys(article)
        seen_earlier = False
        for field, key in zip(("provider_ids", "headline_groups"), keys):
            previous = registry[field].get(key)
            if previous is not None:
                date.fromisoformat(previous)
                seen_earlier |= previous < session
        if not seen_earlier:
            kept.append(article)
    return kept
