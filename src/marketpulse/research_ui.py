"""Evidence-led Streamlit views. No provider, training, or broker effects."""

from __future__ import annotations

import html
import os
import sqlite3
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from trailforge.core import ContractError

from marketpulse.baselines import CLASSES
from marketpulse.dashboard_data import (
    COMPANIES,
    LABEL_NAMES,
    MODEL_NAMES,
    RELEASE,
    REPORTS,
    ResearchView,
    comparison,
    load_research,
    operations,
)

TEAL, RED, SLATE, AMBER = "#58ddbc", "#f4838b", "#91a6c3", "#e8bd75"
CLASS_COLORS = [RED, SLATE, TEAL]
DISPLAY_CLASSES = [LABEL_NAMES[label] for label in CLASSES]
CSS = """
<style>
:root {color-scheme:dark; --mp-line:#29343f; --mp-muted:#a2b2c5;}
.stApp {background:#10161d; color:#e7edf4;}
[data-testid="stHeader"] {background:#10161df2;}
[data-testid="stSidebar"] {background:#131c25; border-right:1px solid var(--mp-line);}
.block-container {max-width:1600px; padding-top:2rem; padding-bottom:3rem;}
h1 {font-size:2.3rem !important; letter-spacing:-.06em; font-weight:650 !important;}
h2 {font-size:1.35rem !important; letter-spacing:-.025em;}
h3 {font-size:1.06rem !important; font-weight:550 !important;}
p, label {line-height:1.6;}
.mp-wordmark {font-size:1.35rem; font-weight:650; letter-spacing:-.055em; margin:0 0 6px;}
.mp-wordmark span {color:#58ddbc;}
.mp-eyebrow {color:#a2b2c5; font-size:.71rem; letter-spacing:.15em; text-transform:uppercase;}
.mp-topline {display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap;
 border-bottom:1px solid #29343f; padding-bottom:15px; margin-bottom:25px;}
.mp-badge {border:1px solid #44645b; color:#8ce6cf; background:#183029;
 padding:3px 9px; border-radius:4px; font-size:.68rem; letter-spacing:.07em;}
.mp-note {border-left:2px solid #e8bd75; background:#24231f; padding:12px 16px;
 margin:14px 0 22px; color:#e8d5b7; font-size:.85rem; line-height:1.65;}
.mp-metrics {display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:0;
 border:1px solid #29343f; border-radius:5px; background:#151e27; margin:20px 0 28px;}
.mp-metric {padding:19px 22px; border-right:1px solid #29343f;}
.mp-metric:last-child {border:0;}
.mp-value {font-family:Consolas,monospace; font-size:2rem; letter-spacing:-.08em;
 font-variant-numeric:tabular-nums; margin:6px 0; color:#f1f5fa;}
.mp-detail {font-size:.74rem; color:#a2b2c5; line-height:1.5;}
.mp-models {display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:18px 0;}
.mp-model {background:#151e27; border:1px solid #29343f; border-top:2px solid #58ddbc;
 padding:18px; border-radius:4px;}
.mp-model h3 {margin:7px 0; color:#edf2f7;}
.mp-combiner {padding:15px 18px; border:1px solid #44645b; background:#152923;
 border-radius:4px; font-size:.86rem; margin-bottom:24px;}
[data-testid="stMetricValue"] {font-family:Consolas,monospace;}
[data-testid="stCaptionContainer"] {color:#a2b2c5;}
[data-testid="stExpander"] {background:#151e27; border-color:#29343f;}
button, a, input, [role="combobox"] {transition:border-color 140ms,background-color 140ms;}
button:focus-visible, a:focus-visible, input:focus-visible {outline:2px solid #58ddbc !important;
 outline-offset:3px;}
[data-testid="stDownloadButton"] button:hover, [data-testid="stButton"] button:hover
 {border-color:#58ddbc;}
hr {border-color:#29343f;}
@media(max-width:900px){.mp-metrics{grid-template-columns:repeat(2,minmax(0,1fr));}
 .mp-metric:nth-child(2){border-right:0;}
 .mp-metric:nth-child(-n+2){border-bottom:1px solid #29343f;}}
@media(max-width:600px){.block-container{padding:1.3rem 1rem;}h1{font-size:1.9rem !important;}
 .mp-models{grid-template-columns:1fr;}.mp-metric{padding:14px;}.mp-value{font-size:1.6rem;}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{transition:none !important;
 animation:none !important;scroll-behavior:auto !important;}}
</style>
"""


@st.cache_data(ttl=60, show_spinner=False)
def cached_research(parent: str, period: str) -> ResearchView:
    return load_research(Path(parent), period)


@st.cache_data(ttl=60, show_spinner=False)
def cached_operations(parent: str, period: str) -> dict:
    return operations(Path(parent), period)


def chart(value, height=280):
    value = (
        value.properties(height=height, background="#10161d")
        .configure_view(stroke=None)
        .configure_axis(
            labelColor="#a2b2c5",
            titleColor="#a2b2c5",
            gridColor="#25303b",
            domain=False,
            tickColor="#334150",
            labelFontSize=11,
            titleFontSize=11,
            labelPadding=9,
            titlePadding=14,
        )
        .configure_legend(labelColor="#c4cfdd", titleColor="#c4cfdd", orient="bottom")
    )
    st.altair_chart(value, width="stretch", theme=None)


def color_classes(field="Class:N"):
    return alt.Color(field, scale=alt.Scale(domain=DISPLAY_CLASSES, range=CLASS_COLORS), title=None)


def section(title: str, subtitle: str):
    st.subheader(title)
    st.caption(subtitle)


def metric_strip(items: list[tuple[str, str, str]]):
    cells = "".join(
        '<div class="mp-metric"><div class="mp-eyebrow">'
        + html.escape(label)
        + '</div><div class="mp-value">'
        + html.escape(value)
        + '</div><div class="mp-detail">'
        + html.escape(detail)
        + "</div></div>"
        for label, value, detail in items
    )
    st.html('<div class="mp-metrics">' + cells + "</div>")


def frame(view: ResearchView, indexes: np.ndarray, candidate: str) -> pd.DataFrame:
    data = view.rows.iloc[indexes].copy()
    probabilities = view.probabilities[candidate][indexes]
    data["prediction"] = [CLASSES[index] for index in probabilities.argmax(axis=1)]
    data["correct"] = data["label"] == data["prediction"]
    data["confidence"] = probabilities.max(axis=1)
    data["Class"] = data["label"].map(LABEL_NAMES)
    data["Date"] = pd.to_datetime(data["session"])
    return data


def overview(view: ResearchView, indexes: np.ndarray, candidate: str):
    metrics = view.metrics(indexes, candidate)
    baseline = view.metrics(indexes, "majority")
    delta = 100 * (metrics["accuracy"] - baseline["accuracy"])
    metric_strip(
        [
            ("Model accuracy", f"{metrics['accuracy']:.2%}", MODEL_NAMES[candidate]),
            (
                "Against neutral-only",
                f"{delta:+.2f} pp",
                f"Baseline accuracy {baseline['accuracy']:.2%}",
            ),
            ("Macro-F1", f"{metrics['macro_f1']:.3f}", "Each movement class has equal weight"),
            (
                "Evaluation examples",
                f"{len(indexes):,}",
                f"{view.rows.iloc[indexes].session.nunique():,} sessions · company-day rows",
            ),
        ]
    )
    left, right = st.columns([1.8, 1], gap="large")
    with left:
        section(
            "Accuracy through time",
            "Monthly accuracy on the selected dates. Hover for sample size.",
        )
        series = []
        for key in dict.fromkeys((candidate, "majority")):
            data = frame(view, indexes, key)
            data["Month"] = data["Date"].dt.to_period("M").dt.to_timestamp()
            grouped = data.groupby("Month").agg(
                Accuracy=("correct", "mean"), Examples=("correct", "size")
            )
            grouped["Series"] = MODEL_NAMES[key]
            series.append(grouped.reset_index())
        monthly = pd.concat(series, ignore_index=True)
        chart(
            alt.Chart(monthly)
            .mark_line(point=alt.OverlayMarkDef(size=55), strokeWidth=2)
            .encode(
                x=alt.X("Month:T", title=None, axis=alt.Axis(format="%b %Y")),
                y=alt.Y("Accuracy:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
                color=alt.Color("Series:N", scale=alt.Scale(range=[TEAL, SLATE]), title=None),
                strokeDash=alt.StrokeDash("Series:N", legend=None),
                tooltip=[
                    alt.Tooltip("Month:T", format="%B %Y"),
                    "Series:N",
                    alt.Tooltip("Accuracy:Q", format=".2%"),
                    "Examples:Q",
                ],
            ),
            300,
        )
    with right:
        section("What actually moved", "Observed labels, not the model's predictions.")
        counts = view.rows.iloc[indexes].label.value_counts()
        distribution = pd.DataFrame(
            [
                {"Class": LABEL_NAMES[label], "Examples": int(counts.get(label, 0))}
                for label in CLASSES
            ]
        )
        distribution["Share"] = distribution.Examples / len(indexes)
        chart(
            alt.Chart(distribution)
            .mark_bar(size=40, cornerRadiusEnd=3)
            .encode(
                x=alt.X("Examples:Q", title="Company-day examples"),
                y=alt.Y("Class:N", sort=DISPLAY_CLASSES, title=None),
                color=color_classes(),
                tooltip=["Class:N", "Examples:Q", alt.Tooltip("Share:Q", format=".1%")],
            ),
            300,
        )
    st.divider()
    left, right = st.columns([1.8, 1], gap="large")
    with left:
        section("Company × month", "Accuracy by company. Cells include the number of examples.")
        data = frame(view, indexes, candidate)
        data["Month"] = data["Date"].dt.to_period("M").astype(str)
        cells = (
            data.groupby(["symbol", "Month"])
            .agg(Accuracy=("correct", "mean"), Examples=("correct", "size"))
            .reset_index()
        )
        base = alt.Chart(cells).encode(
            x=alt.X("Month:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("symbol:N", title=None),
        )
        chart(
            base.mark_rect(stroke="#10161d", strokeWidth=3).encode(
                color=alt.Color(
                    "Accuracy:Q",
                    scale=alt.Scale(domain=[0, 1], range=["#202c38", "#58ddbc"]),
                    legend=alt.Legend(format="%"),
                ),
                tooltip=[
                    "symbol:N",
                    "Month:O",
                    alt.Tooltip("Accuracy:Q", format=".1%"),
                    "Examples:Q",
                ],
            )
            + base.mark_text(fontSize=11).encode(
                text=alt.Text("Accuracy:Q", format=".0%"),
                color=alt.condition(
                    alt.datum.Accuracy > 0.5, alt.value("#071b16"), alt.value("#dce6f2")
                ),
            ),
            260,
        )
    with right:
        section("Read the result", "The baseline is part of the comparison, not an AI model.")
        st.write(
            f"The neutral-only baseline gets {baseline['accuracy']:.1%} right by always choosing "
            "no material move. It catches none of the up or down moves."
        )
        st.write(
            f"This model catches {metrics['per_class']['UP']['recall']:.1%} of up moves and "
            f"{metrics['per_class']['DOWN']['recall']:.1%} of down moves in your selection."
        )
        st.caption(
            "Equal-class recall averages the three recall values; "
            "macro-F1 averages their F1 scores."
        )
        st.info(
            "Filtered results are exploratory. They do not change the frozen research selection."
        )
    st.divider()
    section(
        "Observed session moves",
        "Actual open-to-close return proxies. The dashed lines mark the ±1% class boundaries.",
    )
    ticker = st.selectbox(
        "Inspect company returns",
        sorted(view.rows.iloc[indexes].symbol.unique()),
        format_func=lambda symbol: f"{symbol} · {COMPANIES[symbol][0]}",
    )
    movements = frame(view, indexes, candidate)
    movements = movements[movements.symbol == ticker]
    base = alt.Chart(movements).encode(
        x=alt.X("Date:T", title=None),
        y=alt.Y(
            "return_fraction:Q", title="Regular-minute session return", axis=alt.Axis(format="%")
        ),
    )
    boundaries = (
        alt.Chart(pd.DataFrame({"boundary": [-0.01, 0.01]}))
        .mark_rule(color=SLATE, strokeDash=[5, 5], opacity=0.7)
        .encode(y="boundary:Q")
    )
    chart(
        base.mark_bar(size=3).encode(
            color=color_classes(),
            tooltip=[
                alt.Tooltip("Date:T", format="%d %b %Y"),
                "symbol:N",
                "Class:N",
                alt.Tooltip("return_fraction:Q", title="Observed return", format="+.2%"),
            ],
        )
        + boundaries,
        240,
    )
    st.caption(
        "This is an observed return series, not a stock-price chart, "
        "strategy P&L or a forecast of return magnitude."
    )


def diagnostics(view: ResearchView, indexes: np.ndarray, candidate: str):
    section(
        "Model comparison",
        "Same examples, same labels. Sort columns to compare different trade-offs.",
    )
    table = comparison(view, indexes)
    st.dataframe(
        table.drop(columns="candidate"),
        hide_index=True,
        width="stretch",
        column_config={
            field: st.column_config.NumberColumn(format="percent", min_value=0, max_value=1)
            for field in ("Accuracy", "Equal-class recall", "Up recall", "Down recall")
        }
        | {
            "Macro-F1": st.column_config.NumberColumn(format="%.3f"),
            "Log loss": st.column_config.NumberColumn(format="%.3f"),
        },
    )
    st.download_button(
        "Download model comparison",
        table.drop(columns="candidate").to_csv(index=False),
        file_name="marketpulse-model-comparison.csv",
        mime="text/csv",
    )
    metrics = view.metrics(indexes, candidate)
    left, right = st.columns(2, gap="large")
    with left:
        section(
            "Where predictions land", "Rows are actual outcomes. Columns are predicted movements."
        )
        records = [
            {
                "Actual": LABEL_NAMES[actual],
                "Predicted": LABEL_NAMES[predicted],
                "Examples": metrics["confusion_matrix"][i][j],
            }
            for i, actual in enumerate(CLASSES)
            for j, predicted in enumerate(CLASSES)
        ]
        base = alt.Chart(pd.DataFrame(records)).encode(
            x=alt.X("Predicted:N", sort=DISPLAY_CLASSES, title="Predicted movement"),
            y=alt.Y("Actual:N", sort=DISPLAY_CLASSES, title="Actual movement"),
        )
        chart(
            base.mark_rect(stroke="#10161d", strokeWidth=5).encode(
                color=alt.Color(
                    "Examples:Q", scale=alt.Scale(range=["#1d2b37", "#58ddbc"]), legend=None
                ),
                tooltip=["Actual:N", "Predicted:N", "Examples:Q"],
            )
            + base.mark_text(fontSize=22).encode(
                text="Examples:Q",
                color=alt.condition(
                    alt.datum.Examples > max(r["Examples"] for r in records) / 2,
                    alt.value("#071b16"),
                    alt.value("#eef3fa"),
                ),
            ),
            280,
        )
    with right:
        section(
            "Probability calibration",
            "A calibrated 60% confidence should be correct about 60% of the time.",
        )
        bins = pd.DataFrame(metrics["calibration_bins"])
        ideal = (
            alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]}))
            .mark_line(color=SLATE, strokeDash=[5, 5], opacity=0.6)
            .encode(x="x:Q", y="y:Q")
        )
        observed = (
            alt.Chart(bins)
            .mark_line(color=TEAL, point=True, strokeWidth=2)
            .encode(
                x=alt.X(
                    "confidence:Q",
                    title="Mean predicted confidence",
                    scale=alt.Scale(domain=[0, 1]),
                    axis=alt.Axis(format="%"),
                ),
                y=alt.Y(
                    "accuracy:Q",
                    title="Observed accuracy",
                    scale=alt.Scale(domain=[0, 1]),
                    axis=alt.Axis(format="%"),
                ),
                tooltip=[
                    alt.Tooltip("confidence:Q", format=".1%"),
                    alt.Tooltip("accuracy:Q", format=".1%"),
                    "rows:Q",
                ],
            )
        )
        chart(ideal + observed, 280)
        st.caption(
            f"Log loss {metrics['log_loss']:.3f} · Brier {metrics['multiclass_brier']:.3f} · "
            f"Calibration error {metrics['ece_10_bins']:.3f}. Lower is better."
        )
    section("Recall by movement", "Of each actual class, how much did the model find?")
    recalls = pd.DataFrame(
        [{"Class": LABEL_NAMES[label], **metrics["per_class"][label]} for label in CLASSES]
    )
    chart(
        alt.Chart(recalls)
        .mark_bar(size=35, cornerRadiusEnd=3)
        .encode(
            y=alt.Y("Class:N", sort=DISPLAY_CLASSES, title=None),
            x=alt.X(
                "recall:Q",
                title="Recall",
                scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format="%"),
            ),
            color=color_classes(),
            tooltip=[
                "Class:N",
                alt.Tooltip("recall:Q", format=".2%"),
                alt.Tooltip("precision:Q", format=".2%"),
                "support:Q",
            ],
        ),
        180,
    )


def replay(view: ResearchView, indexes: np.ndarray, candidate: str):
    section(
        "Historical prediction replay",
        "Inspect a saved pre-open prediction, then choose to reveal its outcome.",
    )
    st.caption(
        "No new inference or live signal is generated. "
        "The saved research probabilities are not trade instructions."
    )
    selected = view.rows.iloc[indexes]
    left, right = st.columns(2)
    session = left.selectbox("Replay session", sorted(selected.session.unique(), reverse=True))
    available = selected[selected.session == session]
    symbol = right.selectbox(
        "Replay company",
        sorted(available.symbol.unique()),
        format_func=lambda ticker: f"{ticker} · {COMPANIES[ticker][0]}",
    )
    index = int(available[available.symbol == symbol].index[0])
    identity = (view.period, session, symbol, candidate)
    if st.session_state.get("research_replay_identity") != identity:
        st.session_state["research_replay_identity"] = identity
        st.session_state.pop("research_revealed", None)
    prediction = view.prediction(index, candidate)
    metric_strip(
        [
            ("Saved prediction", prediction["predicted"], MODEL_NAMES[candidate]),
            (
                "Top probability",
                f"{max(prediction['probabilities'].values()):.1%}",
                "Stock-movement probability",
            ),
            ("Prediction cutoff", "09:00 ET", "America/New_York · before regular open"),
            ("Execution", "Research only", "No paper or live orders"),
        ]
    )
    probabilities = pd.DataFrame(
        [
            {"Class": LABEL_NAMES[label], "Probability": value}
            for label, value in prediction["probabilities"].items()
        ]
    )
    chart(
        alt.Chart(probabilities)
        .mark_bar(size=45, cornerRadiusEnd=3)
        .encode(
            y=alt.Y("Class:N", title=None, sort=DISPLAY_CLASSES),
            x=alt.X("Probability:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
            color=color_classes(),
            tooltip=["Class:N", alt.Tooltip("Probability:Q", format=".2%")],
        ),
        220,
    )
    with st.expander("Prediction identity and provenance"):
        st.json(prediction)
    if st.button("Reveal actual outcome", type="primary"):
        st.session_state["research_revealed"] = identity
    if st.session_state.get("research_revealed") == identity:
        outcome = view.outcome(index)
        st.info(
            f"Actual: {outcome['label']} · "
            f"regular-minute return {outcome['return_fraction']:+.2%}. "
            f"Prediction {'matched' if outcome['label'] == prediction['predicted'] else 'missed'}."
        )
        st.caption(
            "First regular-minute open to last regular-minute close; "
            "not an auction return or executable fill."
        )
    st.divider()
    section(
        "How the experts combine",
        "The stack sees nine class probabilities from three separately trained experts.",
    )
    st.html("""<div class="mp-models">
      <div class="mp-model"><div class="mp-eyebrow">Price expert</div><h3>CatBoost</h3>
      <div class="mp-detail">Lagged company returns, volatility, volume
      and company identity.</div></div>
      <div class="mp-model"><div class="mp-eyebrow">News expert</div><h3>Logistic Regression</h3>
      <div class="mp-detail">Frozen FinBERT headline sentiment, event tags
      and relevance features.</div></div>
      <div class="mp-model"><div class="mp-eyebrow">Market expert</div><h3>LightGBM</h3>
      <div class="mp-detail">SPY, sector context and relative performance
      available before the cutoff.</div></div>
      </div><div class="mp-combiner">3 experts × 3 probabilities → Logistic Regression stack →
      Down / Neutral / Up probabilities</div>""")
    st.caption(
        "The 2025-selected research candidate is the price CatBoost expert, not the stack. "
        "FinBERT sentiment alone does not predict stock direction."
    )


def provenance(view: ResearchView, indexes: np.ndarray):
    section(
        "Data coverage",
        "Accepted examples in the original 2018–2026 dataset. "
        "Evaluation filters do not rebalance labels.",
    )
    metric_strip(
        [
            ("Accepted company-days", "13,056", "Six companies · 2018–September 2026"),
            ("Original training", "10,458", "2018–2024 · expert-specific partitions differ"),
            ("Quarantined dates", "20", "120 company-day rows excluded for coverage failures"),
            ("Current selection", f"{len(indexes):,}", f"From {view.period}"),
        ]
    )
    section(
        "Chronological partitions",
        "Fit transformations on past training data; calibration and evaluation use later dates.",
    )
    partitions = pd.DataFrame(
        [
            {"Partition": "Training · 2018–2024", "Examples": 10458},
            {"Partition": "Calibration · early 2025", "Examples": 744},
            {"Partition": "Embargo · 2025", "Examples": 6},
            {"Partition": "Selection · later 2025", "Examples": 744},
            {"Partition": "Retrospective · 2026", "Examples": 1104},
        ]
    )
    chart(
        alt.Chart(partitions)
        .mark_bar(color=TEAL, size=27)
        .encode(
            y=alt.Y("Partition:N", sort=partitions.Partition.tolist(), title=None),
            x=alt.X("Examples:Q", title="Company-day examples"),
            tooltip=["Partition:N", "Examples:Q"],
        ),
        240,
    )
    left, right = st.columns(2, gap="large")
    with left:
        section(
            "Feature channels",
            "Inputs are limited to what was available before 09:00 New York time.",
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Channel": "Company price / volume",
                        "Source": "Alpaca",
                        "Use": "Past returns, volatility, volume",
                    },
                    {
                        "Channel": "Market / sector context",
                        "Source": "Alpaca",
                        "Use": "SPY, sector ETFs, relative moves",
                    },
                    {
                        "Channel": "Financial headlines",
                        "Source": "Alpaca / Benzinga",
                        "Use": "FinBERT and heuristic events",
                    },
                    {
                        "Channel": "Company identity",
                        "Source": "Fixed research universe",
                        "Use": "Ticker and sector mapping",
                    },
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Agent-Reach captures are supplementary; "
            "they are not canonical training inputs in this release."
        )
        st.write(
            "**Not available:** earnings consensus/surprises, "
            "audited historical earnings schedules, "
            "and a certified point-in-time news archive."
        )
    with right:
        section(
            "Research limits",
            "These gates remain open even though the computational runs completed.",
        )
        st.write(
            "Historical data is **HISTORICAL_APPROXIMATE**. Retrieval today does not prove "
            "the exact text or arrival time available on the original prediction date."
        )
        st.write(
            "FinBERT's historical corpus-date audit is incomplete. Its checkpoint postdates "
            "some early examples; event features are rules, not trained event classifiers."
        )
        st.write(
            "2026 was previously exposed. This evaluation is retrospective, not a fresh blind test."
        )
        st.write(
            "Human quality review, strict forward capture, forward evaluation, paper policy "
            "and deployment approval remain open. No trading connection is present."
        )
    with st.expander("Verified release evidence"):
        st.json(
            {
                "release_hash": RELEASE,
                "report_hash": view.report_hash,
                "run_id": view.receipt["run_id"],
                "verify_receipt": view.receipt["verify_receipt"],
                "native_verdict": "PASS",
                "availability_tier": "HISTORICAL_APPROXIMATE",
                "paper_authorized": False,
                "deployment_promoted": False,
            }
        )
    st.download_button(
        "Download evaluation rows",
        view.rows.iloc[indexes].drop(columns=["row_hash", "input_hash"]).to_csv(index=False),
        file_name="marketpulse-evaluation-rows.csv",
        mime="text/csv",
    )


def operation_view(parent: str, view: ResearchView):
    section(
        "Execution evidence",
        "Native Trailforge receipts are checked, not inferred from a progress percentage.",
    )
    try:
        status = cached_operations(parent, view.period)
    except (OSError, ValueError, KeyError, sqlite3.Error, ContractError):
        st.error("Operation receipts could not be verified. No jobs have been restarted.")
        return
    counts = status["counts"]
    metric_strip(
        [
            (
                "Verified tasks",
                f"{counts.get('Verified complete', 0):,}",
                "Native COMPLETED / PASS",
            ),
            (
                "Other task states",
                f"{sum(v for k, v in counts.items() if k != 'Verified complete'):,}",
                "Retained states · no automatic retries",
            ),
            (
                "Recorded stage",
                status["reported_stage"],
                "Last saved status, not a live process probe",
            ),
            (
                "Build lock",
                "Present" if status["build_lock_present"] else "Absent",
                "A lock alone does not prove an active worker",
            ),
        ]
    )
    if status["updated_at_utc"]:
        st.caption(
            "Last recorded update: "
            + str(pd.Timestamp(status["updated_at_utc"]).tz_convert("Asia/Karachi"))
            + " · Pakistan time"
        )
    st.dataframe(
        pd.DataFrame([{"State": key, "Tasks": value} for key, value in counts.items()]),
        hide_index=True,
        width="stretch",
    )
    section(
        "Release gates", "Computational completion is separate from permission to deploy or trade."
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Gate": "Saved evaluation receipt",
                    "Status": "Verified PASS",
                    "Meaning": "Software execution accepted",
                },
                {"Gate": "Human data quality", "Status": "Open", "Meaning": "Review required"},
                {
                    "Gate": "Strict point-in-time capture",
                    "Status": "Open",
                    "Meaning": "Historical approximation only",
                },
                {
                    "Gate": "Forward evaluation",
                    "Status": "Open",
                    "Meaning": "No fresh blind forward evidence",
                },
                {
                    "Gate": "Paper / live execution",
                    "Status": "Not authorized",
                    "Meaning": "No order adapter",
                },
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    st.info(
        "This screen is read-only. It cannot collect data, start training, "
        "reset held tasks or place orders."
    )


def footer():
    st.divider()
    st.caption(
        "MarketPulse / Private research · ±1% movement threshold · "
        "Regular-minute open-to-close proxy · "
        "Historical availability approximate · Saved models unchanged"
        " · Verification cached for up to 60 seconds"
    )


def render_dashboard():
    st.set_page_config(page_title="MarketPulse · Research", page_icon="↗", layout="wide")
    st.html(CSS)
    with st.sidebar:
        st.html(
            '<div class="mp-wordmark">Market<span>Pulse</span></div>'
            '<div class="mp-eyebrow">Research workspace</div>'
        )
        st.divider()
        page = st.radio(
            "Workspace",
            [
                "Overview",
                "Model diagnostics",
                "Prediction replay",
                "Data & provenance",
                "Operations",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        period = st.selectbox("Evaluation population", list(REPORTS))
        parent = str(Path(os.environ.get("MARKETPULSE_RESEARCH_DATA_DIR", "data")).resolve())
        st.caption("Local saved artifacts · no live data feed")
        if st.button("Reload verified results", width="stretch"):
            cached_research.clear()
            cached_operations.clear()
        st.divider()
        st.caption("Six companies. One pre-open cutoff. Three movement classes.")
        st.caption("Research only. No orders or investment advice.")
    st.html(
        '<div class="mp-topline"><span class="mp-eyebrow">US equities / model research</span>'
        '<span class="mp-badge">HISTORICAL · READ ONLY</span></div>'
    )
    titles = {
        "Overview": "Pre-open stock movement.",
        "Model diagnostics": "Model performance & diagnostics.",
        "Prediction replay": "Saved pre-open predictions.",
        "Data & provenance": "Dataset & source provenance.",
        "Operations": "Execution & release gates.",
    }
    st.title(titles[page])
    st.caption(f"{period} · AAPL / AMZN / JPM / NVDA / WMT / XOM · SPY is benchmark context")
    try:
        with st.spinner("Checking saved results and native verification…"):
            view = cached_research(parent, period)
    except (OSError, ValueError, KeyError, sqlite3.Error, ContractError):
        st.error(
            "Verified research results are unavailable. No demo results have been substituted."
        )
        st.write(
            "Check the local dataset/artifact folders and Trailforge verification databases. "
            "Restore the original matching artifacts, then use Reload verified results."
        )
        st.code("marketpulse dashboard --research-data-dir data")
        return
    st.html(
        '<div class="mp-note">'
        + (
            "2026 is a retrospective check on previously exposed dates, not a fresh blind test. "
            if period.startswith("2026")
            else "2025 is development data used for research selection. "
        )
        + "No learned model beats neutral-only overall accuracy in the full population. "
        "Models are not approved for trading.</div>"
    )
    if page == "Operations":
        operation_view(parent, view)
        footer()
        return
    with st.expander("Filter research view", expanded=True):
        a, b, c = st.columns([1.25, 1.2, 1.5])
        candidate = a.selectbox(
            "Model in focus",
            [key for key in MODEL_NAMES if key in view.probabilities],
            format_func=MODEL_NAMES.get,
        )
        dates = b.date_input(
            "Evaluation dates",
            value=(
                pd.Timestamp(view.rows.session.min()).date(),
                pd.Timestamp(view.rows.session.max()).date(),
            ),
            min_value=pd.Timestamp(view.rows.session.min()).date(),
            max_value=pd.Timestamp(view.rows.session.max()).date(),
            key=f"dates_{period}",
        )
        symbols = c.multiselect(
            "Companies",
            sorted(COMPANIES),
            default=sorted(COMPANIES),
            placeholder="Select at least one company",
        )
    if len(dates) != 2:
        st.info("Choose a start and end date to display results.")
        return
    indexes = view.filter(symbols, dates[0].isoformat(), dates[1].isoformat())
    if not len(indexes):
        st.info("No company-day examples match these filters. Select a company or widen the dates.")
        return
    {
        "Overview": overview,
        "Model diagnostics": diagnostics,
        "Prediction replay": replay,
        "Data & provenance": lambda v, i, _: provenance(v, i),
        "Operations": lambda v, i, _: operation_view(parent, v),
    }[page](view, indexes, candidate)
    footer()
