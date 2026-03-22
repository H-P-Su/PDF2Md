import streamlit as st

from services.db import init_db

st.set_page_config(page_title="My Apps", layout="wide", initial_sidebar_state="expanded")

init_db()

# ── Page registry ─────────────────────────────────────────────────────────────
# Add new st.Page() entries here to register additional apps.

pdf_library = st.Page(
    "pages/pdf_library.py",
    title="PDF Library",
    icon="📚",
)

biorxiv_updates = st.Page(
    "pages/biorxiv_updates.py",
    title="bioRxiv Updates",
    icon="🧬",
)

pg = st.navigation([pdf_library, biorxiv_updates])
pg.run()
