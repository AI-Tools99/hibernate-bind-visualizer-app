"""Streamlit entrypoint.

This module serves two purposes:

* When executed with ``python streamlit_app.py`` (as some hosted platforms do),
  it bootstraps Streamlit's runtime and runs ``hibernate_bind_visualizer_app``.
* When run via ``streamlit run`` it simply delegates to the application's
  ``main`` function so that the UI renders as expected.
"""

from pathlib import Path


def _bootstrap() -> None:
    """Start Streamlit's server for direct ``python`` execution."""

    from streamlit.web import bootstrap

    app_path = Path(__file__).with_name("hibernate_bind_visualizer_app.py")
    # ``bootstrap.run`` mirrors ``streamlit run`` so the app behaves the same
    # whether launched via the CLI or by executing this script directly.
    bootstrap.run(str(app_path), False, [], {})


if __name__ == "__main__":
    _bootstrap()
else:
    # Streamlit imports the file as a module when running via ``streamlit run``.
    # Import and render the application in that case.
    from hibernate_bind_visualizer_app import main as render

    render()
