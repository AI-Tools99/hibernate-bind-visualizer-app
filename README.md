# Hibernate Bind Visualizer

A Streamlit-based tool to visualize bound SQL queries from Hibernate TRACE logs.

## Local development

```bash
pip install -r requirements.txt
streamlit run hibernate_bind_visualizer_app.py
```

The single-file app includes an example query and logs that can be loaded from
the UI. Paste your own SQL with `?` placeholders and corresponding Hibernate
TRACE logs to see the bound query, parameter table and diagnostics.

