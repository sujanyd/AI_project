"""
Visual layer for the AgentOps Streamlit app: the theme stylesheet and small HTML
builders (hero, pipeline tracker, metric rings, case grid, trace timeline, fix diff).

Every builder returns an HTML string and escapes all data it shows, so the app
renders them with st.markdown(..., unsafe_allow_html=True) without trusting trace text.
"""

from __future__ import annotations

import json
from html import escape
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ── Palette ──────────────────────────────────────────────────────────────────
CYAN = "#22d3ee"
VIOLET = "#a78bfa"
PINK = "#f472b6"
GREEN = "#34d399"
RED = "#fb7185"
AMBER = "#fbbf24"
MUTED = "#8b8fa8"

PIPELINE_STAGES: Tuple[Tuple[str, str, str], ...] = (
    ("run", "Run", "6 synthetic cases"),
    ("trace", "Trace", "every step saved"),
    ("evaluate", "Evaluate", "scored vs expected"),
    ("diagnose", "Diagnose", "read-only, cites events"),
    ("autofix", "Autofix", "tested on a copy"),
    ("approve", "Approve", "a person decides"),
)

STAGE_ICONS = {
    "run": "▶",
    "trace": "⌁",
    "evaluate": "◎",
    "diagnose": "⌕",
    "autofix": "⚙",
    "approve": "✓",
}

EVENT_COLORS = {
    "PLANNING": VIOLET,
    "TOOL_CALL": CYAN,
    "TOOL_RESULT": CYAN,
    "OBSERVATION": "#60a5fa",
    "VALIDATION": GREEN,
    "ERROR": RED,
    "SAFE_STOP": AMBER,
    "FINAL_STATUS": PINK,
}


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

:root {
  --ao-cyan: #22d3ee; --ao-violet: #a78bfa; --ao-pink: #f472b6;
  --ao-green: #34d399; --ao-red: #fb7185; --ao-amber: #fbbf24;
  --ao-muted: #8b8fa8; --ao-panel: rgba(255,255,255,0.035);
  --ao-border: rgba(167,139,250,0.18);
}

html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea {
  font-family: 'Space Grotesk', ui-sans-serif, system-ui, -apple-system, sans-serif !important;
}
code, pre, .ao-mono { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace !important; }

/* Living background: aurora glows over a faint grid (all in one background, nothing overlays content) */
.stApp {
  background:
    radial-gradient(1200px 600px at 10% -10%, rgba(34,211,238,0.14), transparent 60%),
    radial-gradient(900px 500px at 95% 0%, rgba(167,139,250,0.16), transparent 60%),
    radial-gradient(800px 600px at 50% 120%, rgba(244,114,182,0.10), transparent 60%),
    linear-gradient(rgba(255,255,255,0.022) 1px, transparent 1px) 0 0 / 44px 44px,
    linear-gradient(90deg, rgba(255,255,255,0.022) 1px, transparent 1px) 0 0 / 44px 44px,
    #06060c;
  background-attachment: fixed;
}
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; max-width: 1320px; }

/* Title → animated gradient wordmark */
h1 {
  font-weight: 700 !important; letter-spacing: -0.03em;
  background: linear-gradient(92deg, #e6e8f2 0%, var(--ao-cyan) 30%, var(--ao-violet) 60%, var(--ao-pink) 85%, #e6e8f2 100%);
  background-size: 250% auto;
  -webkit-background-clip: text; background-clip: text; color: transparent !important;
  animation: ao-shimmer 9s linear infinite;
}
@keyframes ao-shimmer { to { background-position: 250% center; } }
h2, h3, h4 { letter-spacing: -0.02em; }

/* Sidebar */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(14,15,26,0.96), rgba(8,8,16,0.98));
  border-right: 1px solid var(--ao-border);
}

/* Tabs → glowing pills */
.stTabs [role="tablist"] {
  gap: 6px; padding: 6px; border-radius: 16px;
  background: var(--ao-panel); border: 1px solid var(--ao-border);
}
.stTabs [role="tablist"] { display: inline-flex; width: auto; margin-bottom: 1rem; }
.stTabs [role="tab"] {
  border-radius: 11px; padding: 9px 20px !important; height: auto; font-weight: 600; color: var(--ao-muted);
  transition: all .2s ease; border: none !important;
}
.stTabs [role="tab"] p { font-size: .95rem !important; font-weight: 600; }
.stTabs [role="tab"]:hover { color: #fff; background: rgba(255,255,255,0.04); }
.stTabs [role="tab"][aria-selected="true"] {
  color: #06060c !important;
  background: linear-gradient(92deg, var(--ao-cyan), var(--ao-violet));
  box-shadow: 0 0 24px rgba(34,211,238,0.35);
}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }
.stTabs [role="tab"][aria-selected="true"] p { color: #06060c !important; }
.stTabs .react-aria-SelectionIndicator, .stTabs [role="tablist"]::after { display: none !important; }

/* Buttons */
.stButton > button {
  border-radius: 12px; font-weight: 600; border: 1px solid var(--ao-border);
  background: rgba(255,255,255,0.04); transition: transform .15s ease, box-shadow .2s ease;
}
.stButton > button:hover { transform: translateY(-1px); box-shadow: 0 6px 24px rgba(167,139,250,0.25); border-color: var(--ao-violet); }
.stButton > button[kind="primary"] {
  color: #06060c; border: none;
  background: linear-gradient(92deg, var(--ao-cyan), var(--ao-violet) 55%, var(--ao-pink));
  background-size: 200% auto; animation: ao-shimmer 6s linear infinite;
  box-shadow: 0 0 28px rgba(34,211,238,0.35);
}

/* Native metrics → glass cards */
div[data-testid="stMetric"] {
  background: var(--ao-panel); border: 1px solid var(--ao-border); border-radius: 16px;
  padding: 14px 16px; backdrop-filter: blur(8px);
}
div[data-testid="stMetricLabel"] p { color: var(--ao-muted) !important; text-transform: uppercase; letter-spacing: .08em; font-size: .72rem !important; }
div[data-testid="stMetricValue"] { font-weight: 700; }

/* Inputs, dataframes, expanders, alerts */
div[data-baseweb="select"] > div, .stTextInput input { border-radius: 12px !important; }
div[data-testid="stDataFrame"], div[data-testid="stExpander"] { border-radius: 14px; overflow: hidden; border: 1px solid var(--ao-border); }
div[data-testid="stAlert"] { border-radius: 14px; backdrop-filter: blur(6px); }

/* ── Custom components ─────────────────────────────────────────────── */
.ao-tagline { color: var(--ao-muted); margin: -0.6rem 0 1.1rem 0; font-size: 1.02rem; }
.ao-tagline b { color: #e6e8f2; font-weight: 600; }
.ao-chiprow { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 1.2rem; }
.ao-chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px;
  font-size: .78rem; font-weight: 600; border: 1px solid var(--ao-border); background: var(--ao-panel); color: #cfd3e6;
}
.ao-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ao-green); box-shadow: 0 0 10px var(--ao-green); animation: ao-pulse 1.8s ease-in-out infinite; }
@keyframes ao-pulse { 50% { opacity: .35; transform: scale(.8); } }

/* Pipeline tracker */
.ao-pipeline {
  display: grid; grid-template-columns: repeat(6, 1fr); gap: 0; margin: .2rem 0 1.6rem 0;
  padding: 18px 14px; border-radius: 20px; background: var(--ao-panel); border: 1px solid var(--ao-border);
  position: relative; overflow: hidden;
}
.ao-stage { position: relative; text-align: center; padding: 0 4px; }
.ao-stage:not(:last-child)::after {
  content: ""; position: absolute; top: 22px; left: calc(50% + 26px); width: calc(100% - 52px); height: 2px;
  background: rgba(255,255,255,0.08); border-radius: 2px;
}
.ao-stage.done:not(:last-child)::after {
  background: linear-gradient(90deg, var(--ao-cyan), var(--ao-violet));
  background-size: 200% 100%; animation: ao-flow 2.4s linear infinite;
  box-shadow: 0 0 12px rgba(34,211,238,0.5);
}
@keyframes ao-flow { to { background-position: -200% 0; } }
.ao-node {
  width: 44px; height: 44px; margin: 0 auto 8px auto; border-radius: 14px; display: grid; place-items: center;
  font-size: 1.15rem; font-weight: 700; color: var(--ao-muted);
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1);
  transition: all .3s ease;
}
.ao-stage.done .ao-node { color: #06060c; background: linear-gradient(135deg, var(--ao-cyan), var(--ao-violet)); border: none; box-shadow: 0 0 22px rgba(34,211,238,0.45); }
.ao-stage.active .ao-node { color: #fff; border: 1px solid var(--ao-cyan); box-shadow: 0 0 0 0 rgba(34,211,238,.6); animation: ao-ring 1.6s ease-out infinite; }
.ao-stage.blocked .ao-node { color: #06060c; background: var(--ao-red); border: none; box-shadow: 0 0 22px rgba(251,113,133,0.5); }
@keyframes ao-ring { 0% { box-shadow: 0 0 0 0 rgba(34,211,238,.55); } 100% { box-shadow: 0 0 0 14px rgba(34,211,238,0); } }
.ao-stage-name { font-weight: 700; font-size: .92rem; color: #e6e8f2; }
.ao-stage.idle .ao-stage-name { color: var(--ao-muted); }
.ao-stage-sub { font-size: .72rem; color: var(--ao-muted); margin-top: 2px; }

/* Section header */
.ao-section { display: flex; flex-direction: column; gap: 2px; margin: 1.3rem 0 .7rem 0; }
.ao-section h3 { margin: 0; font-size: 1.25rem; }
.ao-kicker { font-size: .72rem; letter-spacing: .14em; text-transform: uppercase; color: var(--ao-cyan); font-weight: 700; }

/* Metric rings */
.ao-rings { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin: .4rem 0 1.2rem 0; }
.ao-ring-card {
  display: flex; flex-direction: column; align-items: center; text-align: center; gap: 10px; padding: 18px 12px; border-radius: 18px;
  background: var(--ao-panel); border: 1px solid var(--ao-border); position: relative; overflow: hidden;
}
.ao-ring-card::before { content: ""; position: absolute; inset: 0; background: radial-gradient(160px 80px at 0% 0%, var(--glow), transparent 70%); opacity: .18; }
.ao-ring {
  --p: 0; width: 84px; height: 84px; flex: 0 0 84px; border-radius: 50%; position: relative;
  background: conic-gradient(var(--c) calc(var(--p) * 1%), rgba(255,255,255,0.07) 0);
  animation: ao-fill 1.1s cubic-bezier(.2,.8,.2,1) both;
}
.ao-ring::after { content: ""; position: absolute; inset: 8px; border-radius: 50%; background: #0b0c16; }
.ao-ring span { position: absolute; inset: 0; display: grid; place-items: center; z-index: 1; font-weight: 700; font-size: 1.05rem; color: #fff; }
@property --p { syntax: '<number>'; inherits: false; initial-value: 0; }
@keyframes ao-fill { from { --p: 0; } }
.ao-ring-label { font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; color: var(--ao-muted); font-weight: 700; }
.ao-ring-value { font-size: 1.05rem; font-weight: 700; color: #fff; margin-top: 2px; }
.ao-ring-hint { font-size: .72rem; color: var(--ao-muted); }

/* Case grid */
.ao-cases { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: .4rem 0 1rem 0; }
.ao-case {
  padding: 14px 16px; border-radius: 16px; background: var(--ao-panel); border: 1px solid var(--ao-border);
  position: relative; overflow: hidden; animation: ao-rise .5s ease both;
}
.ao-case::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--accent); box-shadow: 0 0 14px var(--accent); }
@keyframes ao-rise { from { opacity: 0; transform: translateY(8px); } }
.ao-case-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.ao-case-id { font-family: 'JetBrains Mono', monospace; font-size: .78rem; color: #cfd3e6; }
.ao-badge { font-size: .7rem; font-weight: 700; padding: 3px 9px; border-radius: 999px; letter-spacing: .05em; }
.ao-badge.pass { color: #052e22; background: var(--ao-green); box-shadow: 0 0 14px rgba(52,211,153,.45); }
.ao-badge.fail { color: #3b0714; background: var(--ao-red); box-shadow: 0 0 14px rgba(251,113,133,.45); }
.ao-case-desc { font-size: .84rem; color: #e6e8f2; margin: 8px 0 10px 0; line-height: 1.35; }
.ao-case-meta { display: flex; flex-wrap: wrap; gap: 6px; }
.ao-tag { font-size: .68rem; padding: 2px 8px; border-radius: 6px; background: rgba(255,255,255,0.06); color: var(--ao-muted); font-family: 'JetBrains Mono', monospace; }
.ao-tag.hot { color: var(--ao-red); background: rgba(251,113,133,0.1); }

/* Trace timeline */
.ao-timeline { position: relative; margin: .6rem 0 1rem 0; padding-left: 30px; }
.ao-timeline::before { content: ""; position: absolute; left: 10px; top: 6px; bottom: 6px; width: 2px; background: linear-gradient(180deg, var(--ao-cyan), var(--ao-violet), var(--ao-pink)); opacity: .45; }
.ao-ev { position: relative; margin-bottom: 10px; padding: 10px 14px; border-radius: 14px; background: var(--ao-panel); border: 1px solid rgba(255,255,255,0.07); animation: ao-rise .4s ease both; }
.ao-ev::before { content: ""; position: absolute; left: -25px; top: 15px; width: 12px; height: 12px; border-radius: 50%; background: var(--c); box-shadow: 0 0 12px var(--c); }
.ao-ev.err { border-color: rgba(251,113,133,0.45); background: rgba(251,113,133,0.06); }
.ao-ev-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.ao-ev-seq { font-family: 'JetBrains Mono', monospace; font-size: .72rem; color: var(--ao-muted); }
.ao-ev-type { font-weight: 700; font-size: .8rem; color: var(--c); letter-spacing: .04em; }
.ao-ev-detail { font-size: .8rem; color: #cfd3e6; margin-top: 4px; font-family: 'JetBrains Mono', monospace; word-break: break-word; }
.ao-ev-right { margin-left: auto; display: flex; gap: 6px; align-items: center; }

/* Output bubble */
.ao-bubble { padding: 14px 16px; border-radius: 16px 16px 16px 4px; background: linear-gradient(135deg, rgba(34,211,238,0.10), rgba(167,139,250,0.10)); border: 1px solid var(--ao-border); color: #e6e8f2; margin: .4rem 0 1rem 0; }
.ao-bubble small { display: block; color: var(--ao-muted); font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 6px; font-weight: 700; }

/* Hypothesis card */
.ao-hypo { padding: 18px 20px; border-radius: 18px; background: linear-gradient(135deg, rgba(167,139,250,0.12), rgba(34,211,238,0.06)); border: 1px solid rgba(167,139,250,0.35); margin: .4rem 0 1rem 0; }
.ao-hypo h4 { margin: 4px 0 8px 0; font-size: 1.08rem; color: #fff; }
.ao-hypo p { margin: 0 0 6px 0; color: #cfd3e6; font-size: .9rem; }
.ao-evi { display: flex; gap: 10px; align-items: flex-start; padding: 8px 12px; margin-top: 6px; border-radius: 10px; background: rgba(0,0,0,0.25); font-size: .78rem; color: #cfd3e6; font-family: 'JetBrains Mono', monospace; }
.ao-evi b { color: var(--ao-red); }

/* Fix diff */
.ao-diff { border-radius: 18px; overflow: hidden; border: 1px solid var(--ao-border); margin: .4rem 0 1rem 0; }
.ao-diff-head { padding: 10px 16px; background: rgba(255,255,255,0.05); font-family: 'JetBrains Mono', monospace; font-size: .8rem; color: var(--ao-cyan); display: flex; justify-content: space-between; }
.ao-diff-line { padding: 10px 16px; font-family: 'JetBrains Mono', monospace; font-size: .84rem; white-space: pre-wrap; word-break: break-word; }
.ao-diff-line.del { background: rgba(251,113,133,0.10); color: #fecdd3; }
.ao-diff-line.add { background: rgba(52,211,153,0.10); color: #bbf7d0; }
.ao-diff-line .sign { display: inline-block; width: 18px; font-weight: 700; }
.ao-diff-why { padding: 10px 16px; font-size: .82rem; color: var(--ao-muted); background: rgba(0,0,0,0.2); }

/* Verdict banner */
.ao-verdict { display: flex; align-items: center; gap: 16px; padding: 18px 22px; border-radius: 18px; margin: .6rem 0 1rem 0; border: 1px solid; }
.ao-verdict.ok { border-color: rgba(52,211,153,0.45); background: linear-gradient(90deg, rgba(52,211,153,0.14), rgba(34,211,238,0.06)); }
.ao-verdict.bad { border-color: rgba(251,113,133,0.45); background: linear-gradient(90deg, rgba(251,113,133,0.14), rgba(244,114,182,0.06)); }
.ao-verdict-icon { width: 46px; height: 46px; border-radius: 14px; display: grid; place-items: center; font-size: 1.4rem; font-weight: 800; color: #06060c; }
.ao-verdict.ok .ao-verdict-icon { background: var(--ao-green); box-shadow: 0 0 26px rgba(52,211,153,.6); }
.ao-verdict.bad .ao-verdict-icon { background: var(--ao-red); box-shadow: 0 0 26px rgba(251,113,133,.6); }
.ao-verdict-title { font-weight: 700; font-size: 1.05rem; color: #fff; }
.ao-verdict-sub { color: #cfd3e6; font-size: .86rem; }

/* Sidebar status */
.ao-side-stat { display: flex; justify-content: space-between; padding: 8px 12px; border-radius: 10px; background: var(--ao-panel); border: 1px solid rgba(255,255,255,0.06); margin-bottom: 6px; font-size: .85rem; }
.ao-side-stat b { color: var(--ao-cyan); font-family: 'JetBrains Mono', monospace; }
.ao-guard { font-size: .8rem; color: #cfd3e6; padding: 3px 0; }
.ao-guard::before { content: "◆ "; color: var(--ao-violet); }

@media (max-width: 1000px) {
  .ao-rings { grid-template-columns: repeat(2, 1fr); }
  .ao-cases { grid-template-columns: 1fr; }
  .ao-pipeline { grid-template-columns: repeat(3, 1fr); row-gap: 18px; }
  .ao-stage:nth-child(3)::after { display: none; }
}
</style>
"""


def _e(value: Any) -> str:
    return escape("" if value is None else str(value))


def tagline(stats: Dict[str, int]) -> str:
    chips = [
        f'<span class="ao-chip"><span class="ao-dot"></span>Local · synthetic data only</span>',
        f'<span class="ao-chip">⌁ {stats.get("runs", 0)} runs traced</span>',
        f'<span class="ao-chip">◎ {stats.get("evaluations", 0)} evaluations</span>',
        f'<span class="ao-chip">✓ {stats.get("decisions", 0)} human decisions</span>',
    ]
    return (
        '<div class="ao-tagline">Run a shop-support agent, <b>trace</b> every step, <b>score</b> it, '
        '<b>pinpoint</b> the failing step, and <b>test a fix on a copy</b> — a person has the final say.</div>'
        f'<div class="ao-chiprow">{"".join(chips)}</div>'
    )


def pipeline(states: Dict[str, str]) -> str:
    """states maps stage key -> 'done' | 'active' | 'blocked' | 'idle'."""
    parts = []
    for key, name, sub in PIPELINE_STAGES:
        state = states.get(key, "idle")
        icon = "✕" if state == "blocked" else STAGE_ICONS[key]
        parts.append(
            f'<div class="ao-stage {state}"><div class="ao-node">{icon}</div>'
            f'<div class="ao-stage-name">{_e(name)}</div><div class="ao-stage-sub">{_e(sub)}</div></div>'
        )
    return f'<div class="ao-pipeline">{"".join(parts)}</div>'


def section(kicker: str, title: str) -> str:
    return f'<div class="ao-section"><span class="ao-kicker">{_e(kicker)}</span><h3>{_e(title)}</h3></div>'


# (label, metrics key, rate key, count key, total key, higher_is_better, hint)
RING_METRICS: Tuple[Tuple[str, str, str, str, str, bool, str], ...] = (
    ("Task Success", "task_success", "task_success_rate", "passed_count", "total_cases", True, "cases passed"),
    ("Tool Failures", "tool_failures", "tool_failure_rate", "failed_tool_calls", "total_tool_calls", False, "tool calls failed"),
    ("Recovery", "recovery", "recovery_rate", "recovered_count", "error_cases_total", True, "errors handled"),
    ("Safety Violations", "safety_violations", "safety_violation_rate", "violation_count", "total_cases", False, "unsafe answers"),
    ("Localization", "failure_localization", "localization_accuracy", "matched_count", "failed_cases_total", True, "root causes found"),
)


def _ring_color(rate: Optional[float], higher_is_better: bool) -> str:
    if rate is None:
        return MUTED
    good = rate if higher_is_better else 1 - rate
    if good >= 0.8:
        return GREEN
    if good >= 0.5:
        return AMBER
    return RED


def metric_rings(metrics: Dict[str, Any]) -> str:
    cards = []
    for label, key, rate_key, count_key, total_key, higher, hint in RING_METRICS:
        data = metrics.get(key, {}) or {}
        rate = data.get(rate_key)
        count, total = data.get(count_key, 0), data.get(total_key, 0)
        color = _ring_color(rate, higher)
        pct = 0 if rate is None else round(rate * 100)
        shown = "N/A" if rate is None else f"{pct}%"
        cards.append(
            f'<div class="ao-ring-card" style="--glow:{color}">'
            f'<div class="ao-ring" style="--p:{pct};--c:{color}"><span>{shown}</span></div>'
            f'<div><div class="ao-ring-label">{_e(label)}</div>'
            f'<div class="ao-ring-value">{count}/{total}</div>'
            f'<div class="ao-ring-hint">{_e(hint)}</div></div></div>'
        )
    return f'<div class="ao-rings">{"".join(cards)}</div>'


def case_grid(evaluations: Iterable[Any], descriptions: Dict[str, str]) -> str:
    cards = []
    for i, ev in enumerate(evaluations):
        passed = bool(ev.passed)
        accent = GREEN if passed else RED
        category = ev.failure_category.value if getattr(ev, "failure_category", None) else None
        calls = (getattr(ev, "details", None) or {}).get("observed_tool_calls", 0)
        tags = [f'<span class="ao-tag">{calls} tool call{"s" if calls != 1 else ""}</span>',
                f'<span class="ao-tag">score {ev.score:.2f}</span>']
        if category:
            tags.insert(0, f'<span class="ao-tag hot">{_e(category)}</span>')
        cards.append(
            f'<div class="ao-case" style="--accent:{accent};animation-delay:{i * 60}ms">'
            f'<div class="ao-case-top"><span class="ao-case-id">{_e(ev.case_id)}</span>'
            f'<span class="ao-badge {"pass" if passed else "fail"}">{"PASS" if passed else "FAIL"}</span></div>'
            f'<div class="ao-case-desc">{_e(descriptions.get(ev.case_id, ""))}</div>'
            f'<div class="ao-case-meta">{"".join(tags)}</div></div>'
        )
    return f'<div class="ao-cases">{"".join(cards)}</div>'


def _short_json(raw: Optional[str], limit: int = 160) -> str:
    if not raw:
        return ""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        value = raw
    if isinstance(value, dict):
        for key in ("thought", "answer", "parameters", "data", "error", "stop_reason", "status"):
            if value.get(key) not in (None, "", {}, []):
                value = {key: value[key]}
                break
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def trace_timeline(events: Sequence[Any]) -> str:
    rows = []
    for i, ev in enumerate(events):
        color = EVENT_COLORS.get(ev.event_type, MUTED)
        is_err = bool(ev.error_code) or ev.status == "ERROR"
        detail = _short_json(ev.output) or _short_json(ev.input)
        right = []
        if ev.tool_name:
            right.append(f'<span class="ao-tag">{_e(ev.tool_name)}</span>')
        if ev.error_code:
            right.append(f'<span class="ao-tag hot">{_e(ev.error_code)}</span>')
        if ev.duration_ms is not None:
            right.append(f'<span class="ao-tag">{ev.duration_ms:.1f} ms</span>')
        rows.append(
            f'<div class="ao-ev{" err" if is_err else ""}" style="--c:{color};animation-delay:{min(i, 20) * 35}ms">'
            f'<div class="ao-ev-head"><span class="ao-ev-seq">#{ev.sequence_no:02d}</span>'
            f'<span class="ao-ev-type">{_e(ev.event_type)}</span>'
            f'<span class="ao-tag">{_e(ev.stage or "-")}</span>'
            f'<span class="ao-ev-right">{"".join(right)}</span></div>'
            + (f'<div class="ao-ev-detail">{_e(detail)}</div>' if detail else "")
            + "</div>"
        )
    return f'<div class="ao-timeline">{"".join(rows)}</div>'


def output_bubble(text: Optional[str], status: Optional[str]) -> str:
    return f'<div class="ao-bubble"><small>Agent reply · {_e(status or "-")}</small>{_e(text or "(No output)")}</div>'


def hypothesis_card(likely_cause: str, next_step: str, uncertainty: str, facts: Sequence[str]) -> str:
    evidence = "".join(f'<div class="ao-evi"><b>●</b><span>{_e(f)}</span></div>' for f in facts)
    return (
        '<div class="ao-hypo"><span class="ao-kicker">Read-only diagnosis</span>'
        f'<h4>{_e(likely_cause)}</h4>'
        f'<p><b>Next step:</b> {_e(next_step)}</p>'
        f'<p style="color:#8b8fa8">{_e(uncertainty)}</p>'
        f'{evidence}</div>'
    )


def diff_card(setting_path: str, old: Any, new: Any, rationale: str) -> str:
    return (
        '<div class="ao-diff">'
        f'<div class="ao-diff-head"><span>{_e(setting_path)}</span><span>applied to a copy only</span></div>'
        f'<div class="ao-diff-line del"><span class="sign">−</span>{_e(old)}</div>'
        f'<div class="ao-diff-line add"><span class="sign">+</span>{_e(new)}</div>'
        f'<div class="ao-diff-why">{_e(rationale)}</div></div>'
    )


def verdict_banner(ok: bool, title: str, subtitle: str) -> str:
    return (
        f'<div class="ao-verdict {"ok" if ok else "bad"}">'
        f'<div class="ao-verdict-icon">{"✓" if ok else "✕"}</div>'
        f'<div><div class="ao-verdict-title">{_e(title)}</div><div class="ao-verdict-sub">{_e(subtitle)}</div></div></div>'
    )


def sidebar_status(stats: Dict[str, int]) -> str:
    rows = "".join(
        f'<div class="ao-side-stat"><span>{_e(label)}</span><b>{stats.get(key, 0)}</b></div>'
        for label, key in (("Runs traced", "runs"), ("Evaluations", "evaluations"),
                           ("Failed runs", "failed"), ("Human decisions", "decisions"))
    )
    guards = "".join(
        f'<div class="ao-guard">{_e(g)}</div>'
        for g in (
            "Synthetic data only",
            "Read-only tools; no orders or messages",
            "Fixes from a narrow allowlist",
            "Fixes tested on a copy, same 6 cases",
            "Step, tool-call and time limits",
            "A person approves or rejects",
        )
    )
    return rows + '<div style="height:10px"></div><div class="ao-kicker">Safeguards</div>' + guards


def pipeline_states(
    has_runs: bool,
    has_evals: bool,
    has_failures: bool,
    diagnosed: bool,
    trial_ok: Optional[bool],
    decided: bool,
) -> Dict[str, str]:
    """Light up the loop from what has actually happened in this session and store."""
    states = {key: "idle" for key, _, _ in PIPELINE_STAGES}
    if has_runs:
        states["run"] = states["trace"] = "done"
    else:
        states["run"] = "active"
        return states
    if has_evals:
        states["evaluate"] = "done"
    if not has_failures and not diagnosed:
        return states
    states["diagnose"] = "done" if diagnosed else "active"
    if not diagnosed:
        return states
    if trial_ok is None:
        states["autofix"] = "active"
        return states
    states["autofix"] = "done" if trial_ok else "blocked"
    if trial_ok:
        states["approve"] = "done" if decided else "active"
    return states
