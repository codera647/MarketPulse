"""Local dashboard entrypoint. Empirical research and synthetic replay stay separate."""

from __future__ import annotations

import os
import runpy
from pathlib import Path

mode = os.environ.get("MARKETPULSE_DASHBOARD_MODE")
if mode == "fixture" or (mode is None and "MARKETPULSE_DEMO_DATA_DIR" in os.environ):
    runpy.run_path(str(Path(__file__).with_name("fixture_ui.py")))
else:
    from marketpulse.research_ui import render_dashboard

    render_dashboard()
