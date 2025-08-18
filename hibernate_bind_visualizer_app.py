from __future__ import annotations

import re
from typing import List, Tuple
from flask import Flask, request, render_template_string, Response

app = Flask(__name__)

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

TEMPLATE = """<!doctype html>
<title>Hibernate Bind Visualizer</title>
<h1>Hibernate Bind Visualizer</h1>
<form method=post>
<textarea name=sql rows=20 cols=60>{{ sql }}</textarea>
<textarea name=logs rows=20 cols=60>{{ logs }}</textarea><br>
<button name=action value=parse>Parse &amp; Bind</button>
<button name=action value=reset>Reset</button>
<button name=action value=example>Load Example</button>
</form>
{% if results %}
<h2>Parameter Table</h2>
<table border=1>
<tr><th>#</th><th>JDBC Type</th><th>Original</th><th>Normalized</th></tr>
{% for p in results['params'] %}
<tr>
<td>{{p['index']}}</td><td>{{p['type']}}</td><td>{{p['original']}}</td><td>{% if p['error'] %}ERROR: {{p['error']}}{% else %}{{p['normalized']}}{% endif %}</td>
</tr>
{% endfor %}
</table>
<h2>Final SQL</h2>
{% if results['final_sql'] %}
<pre>{{results['final_sql']}}</pre>
<form method=post action="/download">
<input type=hidden name=sql value="{{results['final_sql']}}">
<button type=submit>Download SQL</button>
</form>
{% else %}
<p>Final SQL unavailable due to errors.</p>
{% endif %}
<h2>Diagnostics</h2>
<p>Placeholders: {{results['placeholders']}}, Params: {{results['param_count']}}</p>
<ul>
{% for msg in results['diagnostics'] %}
<li>{{msg}}</li>
{% endfor %}
</ul>
{% endif %}
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    sql = request.form.get('sql', '')
    logs = request.form.get('logs', '')
    action = request.form.get('action')
    results = None
    if request.method == 'POST':
        if action == 'parse':
            results = process(sql, logs)
        elif action == 'example':
            sql = EXAMPLE_SQL
            logs = EXAMPLE_LOGS
        elif action == 'reset':
            sql = ''
            logs = ''
    return render_template_string(TEMPLATE, sql=sql, logs=logs, results=results)

@app.post('/download')
def download():
    sql = request.form.get('sql', '')
    return Response(sql, mimetype='text/sql', headers={'Content-Disposition': 'attachment; filename=bound.sql'})

if __name__ == '__main__':
    app.run(debug=True)
