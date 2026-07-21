"""Godmode Bloomberg Terminal — Streamlit implementation of DESIGN.md v3.5.

Visual identity: Dark Obsidian bg, Cyber Neon Cyan primary, Deep Quantum Purple accent,
glassmorphism panels, JetBrains Mono typography, dual-monitor split.

Run: `streamlit run dashboard/streamlit_app.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is importable when streamlit runs from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import streamlit as st  # type: ignore
import time

try:
    import plotly.graph_objects as go  # type: ignore
    _PLOTLY_AVAILABLE = True
except ImportError:
    _PLOTLY_AVAILABLE = False
    go = None  # type: ignore

st.set_page_config(
    page_title="Godmode Terminal",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=Inter:wght@400;600;800&display=swap');

:root {
  --primary: #00F0FF;
  --accent: #7B2CBF;
  --success: #00F5D4;
  --danger: #FF0055;
  --warning: #FFBE0B;
  --info: #3A86FF;
  --goldBloomberg: #FFAA00;
  --bg: #030712;
  --surface: rgba(10, 15, 30, 0.75);
  --borderCyan: rgba(0, 240, 255, 0.15);
  --textPrimary: #F8FAFC;
  --textSecondary: #94A3B8;
}

.stApp {
  background-color: var(--bg);
  color: var(--textPrimary);
  font-family: 'Inter', sans-serif;
}

.stApp h1, .stApp h2, .stApp h3, .stApp .stMetricLabel, .stApp code {
  font-family: 'JetBrains Mono', monospace !important;
  letter-spacing: 0.05em;
}

.godmode-panel {
  background: var(--surface);
  border: 1px solid var(--borderCyan);
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.37);
  backdrop-filter: blur(12px);
}

.godmode-ticker {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--goldBloomberg);
  letter-spacing: 0.1em;
}

.godmode-status-running {
  color: var(--success);
  text-shadow: 0 0 20px rgba(0, 245, 212, 0.35);
  font-weight: 800;
}

.godmode-status-halted {
  color: var(--danger);
  text-shadow: 0 0 20px rgba(255, 0, 85, 0.35);
  font-weight: 800;
}

.godmode-positive { color: var(--success); }
.godmode-negative { color: var(--danger); }
.godmode-neutral { color: var(--textSecondary); }
.godmode-warning { color: var(--warning); }

.godmode-header-bar {
  background: linear-gradient(90deg, rgba(0,240,255,0.05) 0%, rgba(123,44,191,0.05) 100%);
  border-bottom: 1px solid var(--borderCyan);
  padding: 10px 16px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  letter-spacing: 0.15em;
  color: var(--primary);
  text-transform: uppercase;
}

.stMetric {
  background: var(--surface);
  border-radius: 8px;
  padding: 12px;
  border: 1px solid var(--borderCyan);
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def _safe_fetch_intel():
    try:
        from godmode.data.live_intelligence import get_live_intelligence
        return get_live_intelligence().get_combined_intelligence()
    except Exception as exc:
        st.warning(f"Live intelligence unavailable: {exc}")
        return {"international": {"fear_greed": {}, "assets": {}, "news": []}, "indian": {"indices": {}, "stocks": {}, "news": []}}


def _safe_kill_status():
    try:
        from godmode.core.killswitch import get_kill_switch
        return get_kill_switch().status()
    except Exception as exc:
        return {"halted": False, "reason": None, "heartbeat_age_seconds": None}


def _safe_arena_status():
    try:
        from godmode.backtest.arena import get_arena
        return get_arena().status()
    except Exception:
        return {"population": 0, "live_slots": 0, "live_strategy_ids": []}


def _safe_oracle_status():
    try:
        from godmode.risk.neuro_symbolic import get_neuro_symbolic_oracle
        return get_neuro_symbolic_oracle().status()
    except Exception:
        return {"active_rules": 0, "total_proposals": 0, "rule_names": []}


def _safe_godel_status():
    try:
        from godmode.agents.godel_trader import get_godel_trader
        return get_godel_trader().status()
    except Exception:
        return {"history_size": 0, "last_verdict": None, "accept_count": 0, "reject_count": 0}


def _safe_key_rotator():
    try:
        from godmode.core.key_rotator import KeyRotator
        rot = KeyRotator()
        rot.fetch_keys()
        return rot.summary()
    except Exception:
        return {}


def _color_pct(p: float) -> str:
    try:
        v = float(p)
    except Exception:
        return "godmode-neutral"
    if v > 0:
        return "godmode-positive"
    if v < 0:
        return "godmode-negative"
    return "godmode-neutral"


# ========= HEADER =========
st.markdown('<div class="godmode-header-bar">GODMODE TERMINAL · v4.0 · Bloomberg-Style Realtime HUD</div>', unsafe_allow_html=True)

ks = _safe_kill_status()
status_class = "godmode-status-running" if not ks.get("halted") else "godmode-status-halted"
status_text = "RUNNING" if not ks.get("halted") else "HALTED"
col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    st.markdown(f"### Status")
    st.markdown(f'<span class="{status_class}">{status_text}</span>', unsafe_allow_html=True)
with col_b:
    st.metric("Heartbeat (s)", str(ks.get("heartbeat_age_seconds")), help="Time since last heartbeat beat")
with col_c:
    rot_summary = _safe_key_rotator()
    st.metric("LLM Providers", str(sum(rot_summary.values())) if rot_summary else "0")
with col_d:
    st.metric("Time", time.strftime("%H:%M:%S UTC", time.gmtime()))

# ========= DUAL MONITOR SPLIT: INDIAN / INTERNATIONAL =========
st.markdown("---")
st.markdown("### SCREEN 1 · INDIAN EQUITIES  |  SCREEN 2 · INTERNATIONAL & CRYPTO")

intel = _safe_fetch_intel()
indian = intel.get("indian", {})
intl = intel.get("international", {})

left_col, right_col = st.columns(2)

with left_col:
    st.markdown('<div class="godmode-panel">', unsafe_allow_html=True)
    st.markdown("#### NSE / BSE Live Tick")
    indices = indian.get("indices", {})
    for name, data in indices.items():
        try:
            price = float(data.get("price", 0))
            chg = float(data.get("change_24h_pct", 0))
        except Exception:
            continue
        st.metric(name, f"₹{price:,.2f}", f"{chg:+.2f}%")
    st.markdown("---")
    st.markdown("##### Indian Stocks")
    for name, data in indian.get("stocks", {}).items():
        try:
            price = float(data.get("price", 0))
            chg = float(data.get("change_24h_pct", 0))
        except Exception:
            continue
        cls = _color_pct(chg)
        st.markdown(f'<span class="{cls}">{name}: ₹{price:,.2f} ({chg:+.2f}%)</span>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with right_col:
    st.markdown('<div class="godmode-panel">', unsafe_allow_html=True)
    st.markdown("#### BTC / ETH / SOL Live")
    assets = intl.get("assets", {})
    for name, data in assets.items():
        try:
            price = float(data.get("price", 0))
            chg = float(data.get("change_24h_pct", 0))
        except Exception:
            continue
        st.metric(name, f"${price:,.2f}", f"{chg:+.2f}%")
    st.markdown("---")
    fg = intl.get("fear_greed", {})
    st.metric("Fear & Greed", f"{fg.get('score', 0)} ({fg.get('label', '')})")
    st.markdown("</div>", unsafe_allow_html=True)

# ========= NEWS TICKER =========
st.markdown("---")
st.markdown("### NEWS WIRE")
intl_news = intl.get("news", [])
indian_news = indian.get("news", [])
all_news = list(intl_news) + list(indian_news)
if all_news:
    news_stream = "    ·    ".join(
        f"[{n.get('source', '?')}] {n.get('headline', '')}" for n in all_news[:20]
    )
    st.markdown(
        f'<div class="godmode-panel"><div style="overflow-x: auto; white-space: nowrap;"><span class="godmode-ticker">{news_stream}</span></div></div>',
        unsafe_allow_html=True,
    )
else:
    st.info("News wire offline — set FINNHUB_API_KEY or NEWSAPI_API_KEY in .env")

# ========= AGENT / V4 INTELLIGENCE GRID =========
st.markdown("---")
st.markdown("### AUTONOMOUS INTELLIGENCE")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown('<div class="godmode-panel">', unsafe_allow_html=True)
    st.markdown("##### Arena Tournament")
    arena_status = _safe_arena_status()
    st.metric("Population", arena_status.get("population", 0))
    st.metric("Live Slots", arena_status.get("live_slots", 0))
    st.metric("Best IDs", ", ".join((arena_status.get("live_strategy_ids") or [])[:2]))
    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    st.markdown('<div class="godmode-panel">', unsafe_allow_html=True)
    st.markdown("##### Neuro-Symbolic Oracle")
    oracle_status = _safe_oracle_status()
    st.metric("Active Rules", oracle_status.get("active_rules", 0))
    st.metric("Total Proposals", oracle_status.get("total_proposals", 0))
    st.markdown("</div>", unsafe_allow_html=True)

with col3:
    st.markdown('<div class="godmode-panel">', unsafe_allow_html=True)
    st.markdown("##### Gödel Self-Improver")
    godel_status = _safe_godel_status()
    st.metric("History", godel_status.get("history_size", 0))
    st.metric("Accepted", godel_status.get("accept_count", 0))
    st.metric("Rejected", godel_status.get("reject_count", 0))
    st.metric("Last Verdict", str(godel_status.get("last_verdict", "—")))
    st.markdown("</div>", unsafe_allow_html=True)

with col4:
    st.markdown('<div class="godmode-panel">', unsafe_allow_html=True)
    st.markdown("##### Key Rotator")
    for k, v in rot_summary.items():
        st.metric(k.title(), v)
    st.markdown("</div>", unsafe_allow_html=True)

# ========= EMERGENCY CONTROLS =========
st.markdown("---")
st.markdown("### EMERGENCY CONTROLS")
ccol1, ccol2 = st.columns(2)
with ccol1:
    if st.button("ENGAGE KILL SWITCH", help="Halt all trading immediately"):
        try:
            from godmode.core.killswitch import get_kill_switch
            get_kill_switch().engage("Engaged from dashboard", source="dashboard")
            st.error("KILL SWITCH ENGAGED — Trading halted")
        except Exception as exc:
            st.error(f"Failed: {exc}")

with ccol2:
    if st.button("CLEAR KILL SWITCH", help="Resume trading"):
        try:
            from godmode.core.killswitch import get_kill_switch
            get_kill_switch().reset(source="dashboard")
            st.success("Kill switch cleared. Trading may resume.")
        except Exception as exc:
            st.error(f"Failed: {exc}")

st.markdown(
    '<div class="godmode-panel" style="text-align:center; margin-top: 20px;"><span class="godmode-ticker">GODMODE TERMINAL · ALL SIGNALS NOMINAL · BLOOMBERG-STYLE DENSITY · PONYTAIL MINDSET</span></div>',
    unsafe_allow_html=True,
)
