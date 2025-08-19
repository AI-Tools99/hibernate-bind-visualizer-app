"""Application entrypoint for hosting platforms that invoke `python index.py`."""

from streamlit_app import _bootstrap

if __name__ == "__main__":
    _bootstrap()
