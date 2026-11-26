"""
Visual layer for the AgentOps Streamlit app: a restrained, monochrome stylesheet and
small HTML builders (header, pipeline, measures, case list, trace log, fix diff).

Every builder returns an HTML string and escapes all data it shows, so the app
renders them with st.markdown(..., unsafe_allow_html=True) without trusting trace text.
"""

from __future__ import annotations

import json
from html import escape
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

# ── Palette: near-black neutrals, one quiet accent, muted status colours ─────
TEXT = "#ededed"
MUTED = "#8a8a8a"
FAINT = "#5c5c5c"
GREEN = "#4ade80"
RED = "#f87171"
AMBER = "#fbbf24"
BLUE = "#7aa2ff"

PIPELINE_STAGES: Tuple[Tuple[str, str, str], ...] = (
    ("run", "Run", "Six synthetic cases"),
    ("trace", "Trace", "Every step recorded"),
    ("evaluate", "Evaluate", "Scored against expected"),
    ("diagnose", "Diagnose", "Read-only, cites events"),
    ("autofix", "Autofix", "Tested on a copy"),
    ("approve", "Approve", "A person decides"),
)

EVENT_COLORS = {
    "PLANNING": MUTED,
    "TOOL_CALL": BLUE,
    "TOOL_RESULT": BLUE,
    "OBSERVATION": MUTED,
    "VALIDATION": GREEN,
    "ERROR": RED,
    "SAFE_STOP": AMBER,
    "FINAL_STATUS": TEXT,
}


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg: #0a0a0a; --panel: #111111; --panel-2: #161616;
  --line: #222222; --line-2: #2e2e2e;
  --text: #ededed; --muted: #8a8a8a; --faint: #5c5c5c;
  --green: #4ade80; --red: #f87171; --amber: #fbbf24; --blue: #7aa2ff;
  --radius: 10px;
}

html, body, [class*="css"], .stMarkdown, button, input, textarea, select {
  font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif !important;
  -webkit-font-smoothing: antialiased;
}
code, pre, .mono { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace !important; }

.stApp { background: var(--bg); }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.6rem; padding-bottom: 4rem; max-width: 1180px; }

h1 { font-weight: 600 !important; letter-spacing: -0.035em; font-size: 2.1rem !important; color: var(--text) !important; }
h2, h3, h4 { font-weight: 600 !important; letter-spacing: -0.02em; color: var(--text); }
p, li { color: #d4d4d4; }

/* Hide heading anchor icons for a cleaner read */
[data-testid="stHeaderActionElements"] { display: none !important; }

/* Sidebar */
section[data-testid="stSidebar"] { background: #0c0c0c; border-right: 1px solid var(--line); }
section[data-testid="stSidebar"] h3 { font-size: .95rem !important; letter-spacing: -0.01em; }

/* Tabs: plain text with a thin underline on the active one */
.stTabs [role="tablist"] { gap: 28px; border-bottom: 1px solid var(--line); margin-bottom: 1.6rem; }
.stTabs [role="tab"] {
  padding: 10px 0 !important; height: auto; background: transparent !important; border: none !important;
  border-bottom: 1px solid transparent !important; margin-bottom: -1px; border-radius: 0;
}
.stTabs [role="tab"] p { font-size: .9rem !important; font-weight: 500; color: var(--muted); transition: color .15s ease; }
.stTabs [role="tab"]:hover p { color: var(--text); }
.stTabs [role="tab"][aria-selected="true"] { border-bottom-color: var(--text) !important; }
.stTabs [role="tab"][aria-selected="true"] p { color: var(--text); }
.stTabs .react-aria-SelectionIndicator, .stTabs [role="tablist"]::after,
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none !important; }

/* Buttons: primary is solid white, secondary is a quiet outline */
.stButton > button {
  white-space: nowrap;
  border-radius: 8px; font-weight: 500; font-size: .88rem; padding: .5rem 1rem;
  background: transparent; color: var(--text); border: 1px solid var(--line-2);
  box-shadow: none; transition: background .15s ease, border-color .15s ease;
}
.stButton > button:hover { background: var(--panel-2); border-color: #3a3a3a; color: var(--text); }
.stButton > button[kind="primary"] { background: var(--text); color: #0a0a0a; border-color: var(--text); }
.stButton > button[kind="primary"]:hover { background: #ffffff; color: #0a0a0a; }
.stButton > button[kind="primary"] p { color: #0a0a0a; }
.stButton > button:disabled { opacity: .35; }

/* Native metrics */
div[data-testid="stMetric"] { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px 18px; }
div[data-testid="stMetricLabel"] p { color: var(--muted) !important; font-size: .78rem !important; font-weight: 500; }
div[data-testid="stMetricValue"] { font-weight: 600; font-size: 1.55rem !important; letter-spacing: -0.02em; }

/* Inputs, tables, expanders, alerts */
div[data-baseweb="select"] > div, .stTextInput input { border-radius: 8px !important; background: var(--panel) !important; border-color: var(--line-2) !important; }
div[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; }
div[data-testid="stExpander"] details { border: 1px solid var(--line) !important; border-radius: var(--radius) !important; background: transparent; }
div[data-testid="stExpander"] summary p { font-size: .88rem; color: var(--muted); }
div[data-testid="stAlert"] { border-radius: var(--radius); }
div[data-testid="stAlert"] > div { background: var(--panel) !important; border: 1px solid var(--line); border-radius: var(--radius); color: var(--text) !important; }
div[data-testid="stAlertContentInfo"] p, div[data-testid="stAlertContentSuccess"] p,
div[data-testid="stAlertContentWarning"] p, div[data-testid="stAlertContentError"] p { color: var(--text) !important; }
div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) > div { border-left: 2px solid var(--green); }
div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) > div { border-left: 2px solid var(--amber); }
div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) > div { border-left: 2px solid var(--red); }
div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) > div { border-left: 2px solid var(--blue); }

/* ── Custom components ─────────────────────────────────────────────── */
.ao-sub { color: var(--muted); font-size: .98rem; max-width: 640px; margin: -0.4rem 0 1.4rem 0; line-height: 1.55; }
.ao-stats { display: flex; gap: 28px; margin: 0 0 1.8rem 0; padding: 0; }
.ao-stat { display: flex; flex-direction: column; gap: 2px; }
.ao-stat b { font-size: 1.15rem; font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }
.ao-stat span { font-size: .76rem; color: var(--muted); }

/* Pipeline: numbered steps with a hairline status bar */
.ao-pipeline { display: grid; grid-template-columns: repeat(6, 1fr); border: 1px solid var(--line); border-radius: var(--radius); margin: 0 0 2rem 0; overflow: hidden; }
.ao-stage { padding: 14px 16px; border-right: 1px solid var(--line); background: var(--panel); position: relative; }
.ao-stage:last-child { border-right: none; }
.ao-stage::after { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 2px; background: transparent; }
.ao-stage.done::after { background: var(--text); }
.ao-stage.active::after { background: var(--blue); }
.ao-stage.blocked::after { background: var(--red); }
.ao-node { font-family: 'JetBrains Mono', monospace; font-size: .72rem; color: var(--faint); margin-bottom: 6px; display: flex; justify-content: space-between; }
.ao-node i { font-style: normal; font-family: 'Inter', sans-serif; }
.ao-stage.done .ao-node i { color: var(--text); }
.ao-stage.active .ao-node i { color: var(--blue); }
.ao-stage.blocked .ao-node i { color: var(--red); }
.ao-stage-name { font-weight: 600; font-size: .9rem; color: var(--text); }
.ao-stage.idle .ao-stage-name { color: var(--muted); }
.ao-stage-sub { font-size: .74rem; color: var(--muted); margin-top: 2px; }

/* Section header */
.ao-section { margin: 1.9rem 0 .8rem 0; }
.ao-kicker { display: block; font-size: .72rem; color: var(--muted); font-weight: 500; margin-bottom: 4px; }
.ao-section h3 { margin: 0; padding: 0; font-size: 1.12rem !important; }

/* Measures */
.ao-rings { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0; border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; margin: .2rem 0 1rem 0; }
.ao-ring-card { padding: 16px 18px; border-right: 1px solid var(--line); background: var(--panel); }
.ao-ring-card:last-child { border-right: none; }
.ao-ring-label { font-size: .76rem; color: var(--muted); font-weight: 500; }
.ao-ring-value { font-size: 1.6rem; font-weight: 600; letter-spacing: -0.03em; color: var(--text); margin: 6px 0 2px 0; font-variant-numeric: tabular-nums; }
.ao-ring-hint { font-size: .74rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.ao-bar { height: 3px; border-radius: 3px; background: var(--line); margin-top: 12px; overflow: hidden; }
.ao-bar i { display: block; height: 100%; background: var(--c); border-radius: 3px; }

/* Case list */
.ao-cases { border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; margin: .2rem 0 1rem 0; }
.ao-case { display: grid; grid-template-columns: 74px 1fr auto; align-items: center; gap: 16px; padding: 13px 18px; border-bottom: 1px solid var(--line); background: var(--panel); }
.ao-case:last-child { border-bottom: none; }
.ao-case-id { font-family: 'JetBrains Mono', monospace; font-size: .76rem; color: var(--muted); }
.ao-case-desc { font-size: .88rem; color: var(--text); }
.ao-case-meta { display: flex; gap: 6px; align-items: center; justify-content: flex-end; flex-wrap: wrap; }
.ao-badge { display: inline-flex; align-items: center; gap: 6px; font-size: .74rem; font-weight: 500; color: var(--text); min-width: 42px; }
.ao-badge::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--c); }
.ao-badge.pass { --c: var(--green); }
.ao-badge.fail { --c: var(--red); }
.ao-tag { font-size: .7rem; padding: 2px 7px; border-radius: 5px; border: 1px solid var(--line-2); color: var(--muted); font-family: 'JetBrains Mono', monospace; white-space: nowrap; }
.ao-tag.hot { color: var(--red); border-color: rgba(248,113,113,0.3); }

/* Trace log */
.ao-timeline { border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; margin: .2rem 0 1rem 0; background: var(--panel); }
.ao-ev { display: grid; grid-template-columns: 34px 120px 1fr; gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--line); align-items: start; }
.ao-ev:last-child { border-bottom: none; }
.ao-ev.err { background: rgba(248,113,113,0.04); }
.ao-ev-seq { font-family: 'JetBrains Mono', monospace; font-size: .74rem; color: var(--faint); padding-top: 2px; }
.ao-ev-type { font-family: 'JetBrains Mono', monospace; font-size: .74rem; color: var(--c); padding-top: 2px; }
.ao-ev-body { min-width: 0; }
.ao-ev-head { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.ao-ev-detail { font-size: .8rem; color: #cfcfcf; margin-top: 5px; font-family: 'JetBrains Mono', monospace; word-break: break-word; line-height: 1.5; }

/* Reply */
.ao-bubble { padding: 14px 18px; border-radius: var(--radius); background: var(--panel); border: 1px solid var(--line); color: var(--text); margin: .6rem 0 1rem 0; font-size: .92rem; line-height: 1.55; }
.ao-bubble small { display: block; color: var(--muted); font-size: .74rem; margin-bottom: 6px; }

/* Diagnosis */
.ao-hypo { padding: 18px 20px; border-radius: var(--radius); background: var(--panel); border: 1px solid var(--line); margin: .6rem 0 1rem 0; }
.ao-hypo .ao-h { margin: 0 0 10px 0; font-size: 1rem; font-weight: 600; color: var(--text); }
.ao-hypo p { margin: 0 0 6px 0; color: #cfcfcf; font-size: .88rem; }
.ao-evi { display: flex; gap: 10px; align-items: flex-start; padding: 8px 0; border-top: 1px solid var(--line); font-size: .78rem; color: #cfcfcf; font-family: 'JetBrains Mono', monospace; }
.ao-evi:first-of-type { margin-top: 10px; }
.ao-evi b { color: var(--red); font-weight: 400; }

/* Fix diff */
.ao-diff { border-radius: var(--radius); overflow: hidden; border: 1px solid var(--line); margin: .2rem 0 1rem 0; }
.ao-diff-head { padding: 10px 16px; background: var(--panel-2); font-family: 'JetBrains Mono', monospace; font-size: .78rem; color: var(--text); display: flex; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--line); }
.ao-diff-head span:last-child { color: var(--muted); font-family: 'Inter', sans-serif; }
.ao-diff-line { padding: 10px 16px; font-family: 'JetBrains Mono', monospace; font-size: .82rem; white-space: pre-wrap; word-break: break-word; }
.ao-diff-line.del { background: rgba(248,113,113,0.07); color: #fca5a5; }
.ao-diff-line.add { background: rgba(74,222,128,0.07); color: #86efac; }
.ao-diff-line .sign { display: inline-block; width: 18px; opacity: .7; }
.ao-diff-why { padding: 10px 16px; font-size: .82rem; color: var(--muted); background: var(--panel); border-top: 1px solid var(--line); }

/* Verdict */
.ao-verdict { display: flex; align-items: center; gap: 14px; padding: 14px 18px; border-radius: var(--radius); margin: .8rem 0 1rem 0; border: 1px solid var(--line); background: var(--panel); }
.ao-verdict-icon { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 8px; }
.ao-verdict.ok .ao-verdict-icon { background: var(--green); }
.ao-verdict.bad .ao-verdict-icon { background: var(--red); }
.ao-verdict-title { font-weight: 600; font-size: .95rem; color: var(--text); }
.ao-verdict-sub { color: var(--muted); font-size: .85rem; margin-top: 1px; }

/* Sidebar status */
.ao-side-stat { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid var(--line); font-size: .84rem; color: var(--muted); }
.ao-side-stat b { color: var(--text); font-weight: 500; font-variant-numeric: tabular-nums; }
.ao-side-head { font-size: .74rem; color: var(--muted); margin: 22px 0 8px 0; }
.ao-guard { font-size: .82rem; color: #cfcfcf; padding: 4px 0; }

@media (max-width: 1000px) {
  .ao-rings { grid-template-columns: repeat(2, 1fr); }
  .ao-ring-card { border-bottom: 1px solid var(--line); }
  .ao-pipeline { grid-template-columns: repeat(3, 1fr); }
  .ao-stage { border-bottom: 1px solid var(--line); }
  .ao-case { grid-template-columns: 1fr; gap: 6px; }
  .ao-case-meta { justify-content: flex-start; }
  .ao-ev { grid-template-columns: 30px 1fr; }
  .ao-ev-body { grid-column: 1 / -1; }
  .ao-stats { flex-wrap: wrap; gap: 18px; }
}
</style>
"""


def _e(value: Any) -> str:
    return escape("" if value is None else str(value))


def tagline(stats: Dict[str, int]) -> str:
    items = (
        ("runs", "Runs traced"),
        ("evaluations", "Evaluations"),
        ("failed", "Failed runs"),
        ("decisions", "Human decisions"),
    )
    stats_html = "".join(
        f'<div class="ao-stat"><b>{stats.get(key, 0)}</b><span>{_e(label)}</span></div>' for key, label in items
    )
    return (
        '<div class="ao-sub">Evaluate a shop-support agent on six synthetic cases, trace every step, '
        'find the failing step, and test a fix on a copy before a person approves it.</div>'
        f'<div class="ao-stats">{stats_html}</div>'
    )


def pipeline(states: Dict[str, str]) -> str:
    """states maps stage key -> 'done' | 'active' | 'blocked' | 'idle'."""
    marks = {"done": "Done", "active": "Next", "blocked": "Blocked", "idle": ""}
    parts = []
    for i, (key, name, sub) in enumerate(PIPELINE_STAGES, start=1):
        state = states.get(key, "idle")
        parts.append(
            f'<div class="ao-stage {state}"><div class="ao-node"><span>{i:02d}</span><i>{marks[state]}</i></div>'
            f'<div class="ao-stage-name">{_e(name)}</div><div class="ao-stage-sub">{_e(sub)}</div></div>'
        )
    return f'<div class="ao-pipeline">{"".join(parts)}</div>'


def section(kicker: str, title: str) -> str:
    return f'<div class="ao-section"><span class="ao-kicker">{_e(kicker)}</span><h3>{_e(title)}</h3></div>'


# (label, metrics key, rate key, count key, total key, higher_is_better, hint)
RING_METRICS: Tuple[Tuple[str, str, str, str, str, bool, str], ...] = (
    ("Task success", "task_success", "task_success_rate", "passed_count", "total_cases", True, "cases passed"),
    ("Tool failures", "tool_failures", "tool_failure_rate", "failed_tool_calls", "total_tool_calls", False, "tool calls failed"),
    ("Recovery", "recovery", "recovery_rate", "recovered_count", "error_cases_total", True, "errors handled"),
    ("Safety violations", "safety_violations", "safety_violation_rate", "violation_count", "total_cases", False, "unsafe answers"),
    ("Localization", "failure_localization", "localization_accuracy", "matched_count", "failed_cases_total", True, "root causes found"),
)


def _ring_color(rate: Optional[float], higher_is_better: bool) -> str:
    if rate is None:
        return FAINT
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
        pct = 0 if rate is None else round(rate * 100)
        shown = "N/A" if rate is None else f"{pct}%"
        cards.append(
            f'<div class="ao-ring-card"><div class="ao-ring-label">{_e(label)}</div>'
            f'<div class="ao-ring-value">{shown}</div>'
            f'<div class="ao-ring-hint">{count} of {total} {_e(hint)}</div>'
            f'<div class="ao-bar"><i style="width:{pct}%;--c:{_ring_color(rate, higher)}"></i></div></div>'
        )
    return f'<div class="ao-rings">{"".join(cards)}</div>'


def case_grid(evaluations: Iterable[Any], descriptions: Dict[str, str]) -> str:
    rows = []
    for ev in evaluations:
        passed = bool(ev.passed)
        category = ev.failure_category.value if getattr(ev, "failure_category", None) else None
        calls = (getattr(ev, "details", None) or {}).get("observed_tool_calls", 0)
        short_id = "-".join(str(ev.case_id).split("-")[:2])
        meta = [f'<span class="ao-tag">{calls} call{"s" if calls != 1 else ""}</span>']
        if category:
            meta.insert(0, f'<span class="ao-tag hot">{_e(category)}</span>')
        meta.append(f'<span class="ao-badge {"pass" if passed else "fail"}">{"Pass" if passed else "Fail"}</span>')
        rows.append(
            f'<div class="ao-case" title="{_e(ev.case_id)}"><span class="ao-case-id">{_e(short_id)}</span>'
            f'<span class="ao-case-desc">{_e(descriptions.get(ev.case_id, ev.case_id))}</span>'
            f'<span class="ao-case-meta">{"".join(meta)}</span></div>'
        )
    return f'<div class="ao-cases">{"".join(rows)}</div>'


def _short_json(raw: Optional[str], limit: int = 180) -> str:
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
    for ev in events:
        color = EVENT_COLORS.get(ev.event_type, MUTED)
        is_err = bool(ev.error_code) or ev.status == "ERROR"
        detail = _short_json(ev.output) or _short_json(ev.input)
        tags = [f'<span class="ao-tag">{_e(ev.stage or "-")}</span>']
        if ev.tool_name:
            tags.append(f'<span class="ao-tag">{_e(ev.tool_name)}</span>')
        if ev.error_code:
            tags.append(f'<span class="ao-tag hot">{_e(ev.error_code)}</span>')
        if ev.duration_ms is not None:
            tags.append(f'<span class="ao-tag">{ev.duration_ms:.1f} ms</span>')
        rows.append(
            f'<div class="ao-ev{" err" if is_err else ""}" style="--c:{color}">'
            f'<span class="ao-ev-seq">{ev.sequence_no:02d}</span>'
            f'<span class="ao-ev-type">{_e(ev.event_type)}</span>'
            f'<div class="ao-ev-body"><div class="ao-ev-head">{"".join(tags)}</div>'
            + (f'<div class="ao-ev-detail">{_e(detail)}</div>' if detail else "")
            + "</div></div>"
        )
    return f'<div class="ao-timeline">{"".join(rows)}</div>'


def output_bubble(text: Optional[str], status: Optional[str]) -> str:
    return f'<div class="ao-bubble"><small>Agent reply · {_e(status or "-")}</small>{_e(text or "(No output)")}</div>'


def hypothesis_card(likely_cause: str, next_step: str, uncertainty: str, facts: Sequence[str]) -> str:
    evidence = "".join(f'<div class="ao-evi"><b>●</b><span>{_e(f)}</span></div>' for f in facts)
    return (
        f'<div class="ao-hypo"><div class="ao-h">{_e(likely_cause)}</div>'
        f'<p><b>Next step</b> — {_e(next_step)}</p>'
        f'<p style="color:#8a8a8a">{_e(uncertainty)}</p>'
        f'{evidence}</div>'
    )


def diff_card(setting_path: str, old: Any, new: Any, rationale: str) -> str:
    return (
        '<div class="ao-diff">'
        f'<div class="ao-diff-head"><span>{_e(setting_path)}</span><span>Applied to a copy only</span></div>'
        f'<div class="ao-diff-line del"><span class="sign">−</span>{_e(old)}</div>'
        f'<div class="ao-diff-line add"><span class="sign">+</span>{_e(new)}</div>'
        f'<div class="ao-diff-why">{_e(rationale)}</div></div>'
    )


def verdict_banner(ok: bool, title: str, subtitle: str) -> str:
    return (
        f'<div class="ao-verdict {"ok" if ok else "bad"}"><span class="ao-verdict-icon"></span>'
        f'<div><div class="ao-verdict-title">{_e(title)}</div><div class="ao-verdict-sub">{_e(subtitle)}</div></div></div>'
    )


def sidebar_status(stats: Dict[str, int]) -> str:
    # Store counts live in the page header; the sidebar lists the safeguards.
    guards = "".join(
        f'<div class="ao-guard">{_e(g)}</div>'
        for g in (
            "Synthetic data only",
            "Read-only tools; no orders or messages",
            "Fixes from a narrow allowlist",
            "Fixes re-tested on the same six cases",
            "Step, tool-call and time limits",
            "A person approves or rejects",
        )
    )
    return '<div class="ao-side-head">Safeguards</div>' + guards


def pipeline_states(
    has_runs: bool,
    has_evals: bool,
    has_failures: bool,
    diagnosed: bool,
    trial_ok: Optional[bool],
    decided: bool,
) -> Dict[str, str]:
    """Mark each stage of the loop from what has actually happened in this session and store."""
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
