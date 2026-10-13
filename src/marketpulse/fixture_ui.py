"""Separate synthetic replay UI; never presented as empirical market results."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from marketpulse.service import FAULTS, DemoService

st.set_page_config(page_title="MarketPulse", page_icon="📈", layout="wide")
st.title("MarketPulse")
st.warning(
    "SYNTHETIC SOFTWARE DEMO — not market performance or investment advice. "
    "No real or broker-paper orders. Empirical research uses the separate research dashboard."
)
service = DemoService(Path(os.environ.get("MARKETPULSE_DEMO_DATA_DIR", "data/demo")))
try:
    readiness = service.ready()
except (ValueError, KeyError, OSError):
    st.info("Initialize first: marketpulse demo-init --data-dir data/demo")
    st.stop()

replay, comparison, operations, guide = st.tabs(["Replay", "Evaluation", "Operations", "Guide"])
with replay:
    catalog = service.catalog()
    session = st.selectbox("Synthetic session", sorted({row["session"] for row in catalog}))
    symbol = st.selectbox("Company ticker", ["AAPL", "NVDA", "AMZN", "JPM", "XOM", "WMT"])
    fault = st.selectbox("Failure fixture", sorted(FAULTS), index=sorted(FAULTS).index("NONE"))
    request = (session, symbol, fault, readiness["release_hash"])
    if st.session_state.get("request") != request:
        st.session_state["request"] = request
        st.session_state.pop("decision", None)
        st.session_state.pop("outcome", None)
    if st.button("Forecast", type="primary"):
        try:
            st.session_state["decision"] = service.forecast(symbol, session, fault=fault)
        except (ValueError, KeyError, OSError, RuntimeError):
            st.error("Forecast refused; inspect local readiness and audit evidence.")
    current = st.session_state.get("decision")
    if current:
        if current["state"] != "COMPLETE":
            st.error("Held by Trailforge; no accepted decision or simulated position.")
            st.json(current)
        else:
            columns = st.columns(3)
            columns[0].metric("Predicted move", current["top_class"] or "Unavailable")
            columns[1].metric("Simulation action", current["action"])
            columns[2].metric("Availability", current["availability_tier"])
            if current["probabilities"]:
                st.bar_chart(
                    pd.DataFrame(
                        {"Probability": current["probabilities"]}, index=current["class_names"]
                    )
                )
            st.caption("Reasons: " + ", ".join(current["reason_codes"]))
            with st.expander("Pre-open inputs and immutable decision audit"):
                item = service.inputs.get(current["binding"]["input_hash"])
                for article in item["news"]:
                    st.text(article["headline"])
                st.json(item["features"])
                st.json(current)
            if st.button("Reveal outcome"):
                st.session_state["outcome"] = service.reveal_outcome(current["decision_id"])
            if "outcome" in st.session_state:
                actual = st.session_state["outcome"]
                st.info(
                    f"Manufactured outcome: {actual['label']} "
                    f"({float(actual['return_fraction']):+.2%}); "
                    f"prediction {'matched' if actual['prediction_correct'] else 'missed'}."
                )
                st.json(actual)

with comparison:
    st.subheader("Four models on the same synthetic rows")
    st.caption(
        "Training-only vocabulary; separate calibration and policy dates; "
        "synthetic final test opened after choices were frozen. "
        "These numbers establish software behavior, not predictive accuracy."
    )
    evaluation = service.evaluation()
    st.json(evaluation)

with operations:
    st.json(service.operations())
    if st.button("Reconcile known runs"):
        st.json(service.reconcile())
    st.caption(
        "Known completed runs can repair missing product records. Unknown/held "
        "tasks are not automatically retried. SQLite and artifacts stay local."
    )

with guide:
    st.markdown(
        "Choose a synthetic date and ticker, press Forecast, then Reveal outcome. "
        "Try STALE, MISSING_NEWS, EXPIRED, LOW_CONFIDENCE and TIMEOUT. "
        "The final synthetic AAPL session deliberately contains a missed prediction."
    )
    st.code(
        "marketpulse demo-init --data-dir data/demo\n"
        "marketpulse serve --data-dir data/demo\n"
        "marketpulse dashboard --mode fixture --data-dir data/demo"
    )
    st.write(
        "Saved empirical specialist/stacking results are available in research dashboard mode. "
        "Human quality review, strict forward evaluation, paper policy and deployment "
        "approval remain separate open gates."
    )
