"""Application entrypoint for hosting platforms that invoke ``python index.py``.

This module now detects whether it is being executed by ``streamlit run`` or
directly via ``python``.  Some hosting providers launch apps with
``streamlit run index.py`` which previously caused the app to start Streamlit's
runtime twice and could result in the source file being served for download.
By checking for an active Streamlit script run context we ensure that we only
bootstrap the server when necessary and otherwise render the application
normally.
"""

from streamlit_app import _bootstrap, _render, get_script_run_ctx


if __name__ == "__main__":
    if get_script_run_ctx() is None:
        # Running as ``python index.py`` – start Streamlit's server manually.
        _bootstrap()
    else:
        # Invoked via ``streamlit run`` – Streamlit is already managing the
        # runtime, so just render the app.
        _render()
