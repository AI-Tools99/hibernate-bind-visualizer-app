"""Streamlit-based Hibernate Bind Visualizer.

This app parses Hibernate TRACE logs and binds parameters into the
corresponding SQL query.  The parsing logic is largely unchanged from the
previous Flask implementation, but the UI has been redesigned with Streamlit
to provide a modern, responsive dashboard with light/dark theming.
"""

from __future__ import annotations

import json
import re
from typing import List, Tuple

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


# ---------------------------------------------------------------------------
# Example data
# ---------------------------------------------------------------------------

EXAMPLE_SQL = """select
    e2_0."event_id",
    e2_0."input_source_data_id",
    e2_0."input_source_type",
    e2_0."event_level",
    e2_0."event_type_code",
    e2_0."place_name",
    e2_0."address",
    e2_0."person",
    e2_0."phone_number",
    e2_0."latitude",
    e2_0."longitude",
    e2_0."created_date_time",
    e2_0."province_code",
    e2_0."province_name",
    e2_0."district_code",
    e2_0."district_name",
    e2_0."ward_code",
    e2_0."ward_name",
    e1_0."event_status_code",
    e1_0."nearest_locality_code",
    e1_0."nearest_locality_name",
    e1_0."event_handle_id",
    m1_0."department_name",
    m1_0."department_code",
    e2_0."facility_id",
    e2_0."facility_name"
from "TTCH_ADMIN"."event_handles" e1_0
join "TTCH_ADMIN"."events" e2_0 on e1_0."event_id"=e2_0."event_id"
join "TTCH_ADMIN"."mobilizations" m1_0 on m1_0."event_handle_id"=e1_0."event_handle_id"
where
    (?=1 or (lower(e2_0."place_name") like ('%'||?||'%') or lower(e2_0."address") like ('%'||?||'%')))
    and m1_0."locality_code"=?
    and (?=1 or 1=0)
    and (e1_0."event_status_code"!=?)
    and (?=1 or e2_0."event_level"=?)
    and (?=1 or e1_0."verification_code" in (?))
order by e1_0."created_at" desc offset ? rows fetch first ? rows only"""

EXAMPLE_LOGS = """{"message":"binding parameter [1] as [BOOLEAN] - [true]"}
{"message":"binding parameter [2] as [VARCHAR] - []"}
{"message":"binding parameter [3] as [VARCHAR] - []"}
{"message":"binding parameter [4] as [VARCHAR] - [DOI_PCCC_PHUONG_BINH_THANH]"}
{"message":"binding parameter [5] as [BOOLEAN] - [true]"}
{"message":"binding parameter [6] as [INTEGER] - [1]"}
{"message":"binding parameter [7] as [BOOLEAN] - [false]"}
{"message":"binding parameter [8] as [INTEGER] - [3]"}
{"message":"binding parameter [9] as [BOOLEAN] - [false]"}
{"message":"binding parameter [10] as [VARCHAR] - [REAL]"}
{"message":"binding parameter [11] as [INTEGER] - [0]"}
{"message":"binding parameter [12] as [INTEGER] - [50]"}"""


# ---------------------------------------------------------------------------
# Parsing and binding logic (unchanged)
# ---------------------------------------------------------------------------

STRING_TYPES = {"VARCHAR", "CHAR", "LONGVARCHAR"}
NUMERIC_TYPES = {"INTEGER", "BIGINT", "DECIMAL", "DOUBLE"}
BOOLEAN_TYPES = {"BOOLEAN"}
DATE_TYPES = {"DATE", "TIMESTAMP"}


class Parameter(dict):
    """Container for a bound parameter."""

    index: int
    type: str
    original: str
    normalized: str
    error: str | None


def parse_logs(text: str) -> Tuple[List[Parameter], List[str]]:
    pattern = re.compile(r"binding parameter \[(\d+)\] as \[(\w+)\] - \[(.*?)\]")
    params: dict[int, Parameter] = {}
    warnings: List[str] = []
    for match in pattern.finditer(text):
        idx, typ, value = match.groups()
        idx_int = int(idx)
        typ_upper = typ.upper()
        if idx_int in params:
            warnings.append(
                f"Duplicate parameter index {idx_int}; ignoring subsequent value."
            )
            continue
        params[idx_int] = Parameter(
            index=idx_int, type=typ_upper, original=value, normalized="", error=None
        )
    ordered_indexes = sorted(params.keys())
    if ordered_indexes and ordered_indexes != list(range(1, len(ordered_indexes) + 1)):
        warnings.append("Parameter indexes are not contiguous starting at 1.")
    ordered_params = [params[i] for i in ordered_indexes]
    return ordered_params, warnings


def normalize(param: Parameter, diagnostics: List[str], expand_in: bool) -> None:
    typ = param["type"]
    val = param["original"]
    if val.lower() == "null":
        param["normalized"] = "NULL"
        return
    if typ in BOOLEAN_TYPES:
        v = val.lower()
        if v == "true":
            param["normalized"] = "1"
        elif v == "false":
            param["normalized"] = "0"
        else:
            param["error"] = f"Invalid boolean value '{val}'"
    elif typ in STRING_TYPES:
        if expand_in and "," in val:
            parts = [p.strip() for p in val.split(",")]
            quoted = ["'" + p.replace("'", "''") + "'" for p in parts]
            param["normalized"] = "(" + ",".join(quoted) + ")"
            diagnostics.append(f"Expanded parameter {param['index']} into IN list.")
        else:
            param["normalized"] = "'" + val.replace("'", "''") + "'"
    elif typ in NUMERIC_TYPES:
        if re.fullmatch(r"-?\d+(\.\d+)?", val.strip()):
            param["normalized"] = val.strip()
        else:
            param["error"] = f"Non-numeric value '{val}' for {typ}"
    elif typ in DATE_TYPES:
        param["normalized"] = "'" + val + "'"
    else:
        param["normalized"] = val
        diagnostics.append(f"Unknown JDBC type {typ}; inserted raw value.")


def bind_sql(sql: str, params: List[Parameter]) -> str:
    bound = sql
    for p in params:
        bound = bound.replace("?", p["normalized"], 1)
    return bound


def process(sql: str, logs: str, expand_in: bool):
    diagnostics: List[str] = []
    params, warnings = parse_logs(logs)
    diagnostics.extend(warnings)
    placeholders = sql.count("?")
    for p in params:
        normalize(p, diagnostics, expand_in)
    errors = [p for p in params if p["error"]]
    if errors:
        for p in errors:
            diagnostics.append(f"Parameter {p['index']} error: {p['error']}")
        final_sql = None
    elif placeholders != len(params):
        diagnostics.append(
            f"Placeholder count ({placeholders}) does not match parameter count ({len(params)})."
        )
        final_sql = None
    else:
        final_sql = bind_sql(sql, params)
    return {
        "params": params,
        "placeholders": placeholders,
        "param_count": len(params),
        "final_sql": final_sql,
        "diagnostics": diagnostics,
    }


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def init_state() -> None:
    defaults = {
        "sql": "",
        "logs": "",
        "auto_parse": True,
        "expand_in": True,
        "theme_mode": "auto",
        "results": None,
        "force_parse": False,
        "sql_font": 14,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def load_example() -> None:
    st.session_state.sql = EXAMPLE_SQL
    st.session_state.logs = EXAMPLE_LOGS
    st.session_state.force_parse = True


def reset_all() -> None:
    st.session_state.sql = ""
    st.session_state.logs = ""
    st.session_state.results = None


def trigger_parse() -> None:
    st.session_state.force_parse = True


def copy_button(label: str, text: str, key: str) -> None:
    components.html(
        f"""
        <button onclick="navigator.clipboard.writeText({json.dumps(text)})" class='copy-btn'>
            {label}
        </button>
        <style>.copy-btn {{ padding:0.25rem 0.5rem; margin-top:0.5rem; }}</style>
        """,
        height=40,
    )


def inject_table_copy_script() -> None:
    components.html(
        """
        <script>
        const tables = parent.document.querySelectorAll('div[data-testid="stDataFrame"] table');
        const table = tables[tables.length - 1];
        if (table) {
            table.querySelectorAll('td').forEach(td => {
                td.style.cursor = 'pointer';
                td.title = 'Click to copy';
                td.addEventListener('click', () => navigator.clipboard.writeText(td.innerText));
            });
        }
        </script>
        """,
        height=0,
    )


def keyboard_shortcuts_script() -> None:
    components.html(
        """
        <script>
        document.addEventListener('keydown', function(e) {
            const mod = e.metaKey || e.ctrlKey;
            if (mod && e.key === 'Enter') {
                [...parent.document.querySelectorAll('button')]
                  .find(b => b.innerText === 'Parse & Bind')?.click();
            }
            if (mod && e.key.toLowerCase() === 'l') {
                [...parent.document.querySelectorAll('button')]
                  .find(b => b.innerText === 'Load Example')?.click();
            }
            if (e.key === 'Escape') {
                [...parent.document.querySelectorAll('button')]
                  .find(b => b.innerText === 'Reset')?.click();
            }
        });
        </script>
        """,
        height=0,
    )


def apply_theme() -> None:
    mode = st.session_state.get("theme_mode", "auto")
    if mode == "dark":
        st.markdown("""<style>body{background-color:#0e1117;color:#fafafa;}</style>""", unsafe_allow_html=True)
    elif mode == "light":
        st.markdown("""<style>body{background-color:white;color:black;}</style>""", unsafe_allow_html=True)
    else:
        components.html(
            """
            <script>
            const theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            const msg = {'theme': theme};
            window.parent.postMessage(msg, '*');
            </script>
            """,
            height=0,
        )


# ---------------------------------------------------------------------------
# Layout sections
# ---------------------------------------------------------------------------

def top_bar(final_sql: str | None) -> None:
    st.markdown(
        """
        <style>
        .top-bar {display:flex;justify-content:space-between;align-items:center;
                  padding:0.5rem 0; border-bottom:1px solid #ddd;}
        .top-title {font-size:1.3rem; font-weight:600;}
        .actions button {margin-left:0.25rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container():
        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown(
                "<div class='top-title'>Hibernate Bind Visualizer<br><span style='font-size:0.8rem;font-weight:400;'>Parse Hibernate TRACE logs</span></div>",
                unsafe_allow_html=True,
            )
        with col2:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.button("Load Example", on_click=load_example)
            c2.button("Parse & Bind", on_click=trigger_parse)
            c3.button("Reset", on_click=reset_all)
            c4.download_button(
                "Download .sql",
                data=final_sql or "",
                file_name="bound.sql",
                disabled=not final_sql,
            )
            c5.selectbox(
                "Theme",
                ["Auto", "Light", "Dark"],
                key="theme_mode",
                label_visibility="collapsed",
            )


def input_section() -> None:
    with st.container():
        st.markdown("#### SQL with ? placeholders")
        st.text_area(
            "SQL",
            key="sql",
            height=300,
            placeholder="Paste SQL with ? placeholders",
        )
    with st.container():
        st.markdown("#### Hibernate TRACE logs")
        st.text_area(
            "Logs",
            key="logs",
            height=300,
            placeholder="Paste TRACE logs",
        )
    st.checkbox("Auto-parse", key="auto_parse")
    st.checkbox("Expand CSV in IN (?)", key="expand_in")


def results_section(results: dict | None) -> None:
    if not results:
        st.info("Provide SQL and TRACE logs to see results.")
        return

    tabs = st.tabs(["Params", "Final SQL", "Diagnostics"])

    with tabs[0]:
        data = [
            {
                "#": p["index"],
                "JDBC Type": p["type"],
                "Original": "''" if p["original"] == "" else p["original"],
                "Normalized": p["normalized"],
                "Notes": p["error"] or "",
            }
            for p in results["params"]
        ]
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
        inject_table_copy_script()

    with tabs[1]:
        if results["final_sql"]:
            st.slider("Font size", 8, 32, key="sql_font")
            st.markdown(
                f"<pre style='font-family:monospace;font-size:{st.session_state.sql_font}px;'>{results['final_sql']}</pre>",
                unsafe_allow_html=True,
            )
            copy_button("Copy", results["final_sql"], "copy-sql")
        else:
            st.warning("Final SQL unavailable due to errors.")

    with tabs[2]:
        c1, c2 = st.columns(2)
        c1.metric("Placeholders", results["placeholders"])
        c2.metric("Params", results["param_count"])
        if results["diagnostics"]:
            for msg in results["diagnostics"]:
                st.write(f"- {msg}")
        else:
            st.success("No diagnostics")


def how_it_works() -> None:
    with st.expander("How it works"):
        st.markdown(
            """
            - `?=1` bypasses conditions when the parameter is `1`.
            - `LIKE '%'||?||'%'` shows how wildcard searches are constructed.
            - `IN (?)` placeholders can expand CSV values when *Expand CSV in IN (?)* is enabled.
            """
        )


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Hibernate Bind Visualizer", layout="wide")
    init_state()
    apply_theme()

    if st.session_state.auto_parse or st.session_state.force_parse:
        if st.session_state.sql.strip() and st.session_state.logs.strip():
            st.session_state.results = process(
                st.session_state.sql,
                st.session_state.logs,
                st.session_state.expand_in,
            )
            if st.session_state.results["final_sql"]:
                st.toast("Parse & Bind successful", icon="✅")
            else:
                st.toast("Check diagnostics for issues", icon="⚠️")
        st.session_state.force_parse = False

    top_bar(
        st.session_state.results["final_sql"]
        if st.session_state.results
        else None
    )

    left, right = st.columns([1, 1])
    with left:
        input_section()
    with right:
        results_section(st.session_state.results)

    how_it_works()
    keyboard_shortcuts_script()


if __name__ == "__main__":
    main()

