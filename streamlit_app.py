"""Streamlit entrypoint.

This module serves two purposes:

* When executed with ``python streamlit_app.py`` (as some hosted platforms do),
  it bootstraps Streamlit's runtime and runs ``hibernate_bind_visualizer_app``.
* When run via ``streamlit run`` it simply delegates to the application's
  ``main`` function so that the UI renders as expected.
"""

from pathlib import Path

try:
    # Streamlit 1.25+ exposes ``get_script_run_ctx`` which lets us detect
    # whether ``streamlit run`` is managing the execution context.  Older
    # versions do not provide this utility, so fall back to a no-op that
    # mimics the absence of a running context.  Without this guard, attempting
    # to import from ``streamlit.runtime.scriptrunner`` on such versions raises
    # an ``ImportError`` which prevents the app from starting and surfaces as a
    # 404 to end users.
    from streamlit.runtime.scriptrunner import get_script_run_ctx
except Exception:  # pragma: no cover - defensive for older Streamlit releases
    def get_script_run_ctx() -> None:  # type: ignore
        return None


def _bootstrap() -> None:
    """Start Streamlit's server for direct ``python`` execution."""

    from streamlit.web import bootstrap

    app_path = Path(__file__).with_name("hibernate_bind_visualizer_app.py")
    # ``bootstrap.run`` mirrors ``streamlit run`` so the app behaves the same
    # whether launched via the CLI or by executing this script directly.
    bootstrap.run(str(app_path), False, [], {})


def _render() -> None:
    """Render the app when running via ``streamlit run``."""

    from hibernate_bind_visualizer_app import main as render

    render()


if __name__ == "__main__" and get_script_run_ctx() is None:
    _bootstrap()
else:
    # When executed with ``streamlit run`` there is already a running context,
    # so simply render the application.
    _render()
