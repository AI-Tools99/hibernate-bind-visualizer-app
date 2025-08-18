import streamlit as st
import re
from typing import List, Tuple

st.set_page_config(page_title="Hibernate Bind Visualizer", layout="wide")

st.title("Hibernate Bind Visualizer")

st.markdown(
    """
    **How to use**

    1. Paste the SQL with `?` placeholders in the left box.
    2. Paste Hibernate TRACE log lines on the right (plain text or JSON lines).
    3. Click **Parse & Bind** to render the final SQL and parameter table.
    4. Use **Reset** to clear the inputs. **Load Example** fills sample data.
    """
)

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

if "sql" not in st.session_state:
    st.session_state.sql = ""
if "logs" not in st.session_state:
    st.session_state.logs = ""
if "results" not in st.session_state:
    st.session_state.results = None


def load_example():
    st.session_state.sql = EXAMPLE_SQL
    st.session_state.logs = EXAMPLE_LOGS
    st.session_state.results = None


def reset():
    st.session_state.sql = ""
    st.session_state.logs = ""
    st.session_state.results = None


STRING_TYPES = {"VARCHAR", "CHAR", "LONGVARCHAR"}
NUMERIC_TYPES = {"INTEGER", "BIGINT", "DECIMAL", "DOUBLE"}
BOOLEAN_TYPES = {"BOOLEAN"}
DATE_TYPES = {"DATE", "TIMESTAMP"}


class Parameter(dict):
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
            warnings.append(f"Duplicate parameter index {idx_int}; ignoring subsequent value.")
            continue
        params[idx_int] = Parameter(index=idx_int, type=typ_upper, original=value, normalized="", error=None)
    ordered_indexes = sorted(params.keys())
    if ordered_indexes and ordered_indexes != list(range(1, len(ordered_indexes) + 1)):
        warnings.append("Parameter indexes are not contiguous starting at 1.")
    ordered_params = [params[i] for i in ordered_indexes]
    return ordered_params, warnings


def normalize(param: Parameter, diagnostics: List[str]) -> None:
    typ = param["type"]
    val = param["original"]
    if typ in BOOLEAN_TYPES:
        v = val.lower()
        if v == "true":
            param["normalized"] = "1"
        elif v == "false":
            param["normalized"] = "0"
        else:
            param["error"] = f"Invalid boolean value '{val}'"
    elif typ in STRING_TYPES:
        if "," in val:
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


def process(sql: str, logs: str):
    diagnostics: List[str] = []
    params, warnings = parse_logs(logs)
    diagnostics.extend(warnings)
    placeholders = sql.count("?")
    for p in params:
        normalize(p, diagnostics)
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


col1, col2 = st.columns(2)
with col1:
    st.session_state.sql = st.text_area(
        "SQL with ? placeholders", value=st.session_state.sql, height=400
    )
with col2:
    st.session_state.logs = st.text_area(
        "Hibernate TRACE logs", value=st.session_state.logs, height=400
    )

btn_cols = st.columns([1, 1, 1])
with btn_cols[0]:
    if st.button("Parse & Bind"):
        st.session_state.results = process(st.session_state.sql, st.session_state.logs)
with btn_cols[1]:
    st.button("Reset", on_click=reset)
with btn_cols[2]:
    st.button("Load Example", on_click=load_example)

results = st.session_state.results
if results:
    st.subheader("Parameter Table")
    table_rows = [
        {
            "#": p["index"],
            "JDBC Type": p["type"],
            "Original": p["original"],
            "Normalized": p["normalized"] if not p["error"] else f"ERROR: {p['error']}",
        }
        for p in results["params"]
    ]
    st.table(table_rows)

    st.subheader("Final SQL")
    if results["final_sql"] is not None:
        st.code(results["final_sql"])
        st.download_button(
            "Download SQL", results["final_sql"], file_name="bound.sql", mime="text/sql"
        )
    else:
        st.write("Final SQL unavailable due to errors.")

    st.subheader("Diagnostics")
    st.write(
        f"Placeholders: {results['placeholders']}, Params: {results['param_count']}"
    )
    for msg in results["diagnostics"]:
        st.write("- " + msg)

st.markdown("---")
st.markdown("### How to Run")
st.code("pip install streamlit\nstreamlit run hibernate_bind_visualizer_app.py", language="bash")
