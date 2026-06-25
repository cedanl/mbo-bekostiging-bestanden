"""Streamlit-app entrypoint."""

import streamlit as st

st.set_page_config(
    page_title="MBO-bekostigingsbestanden",
    page_icon="📊",
    layout="centered",
)

pg = st.navigation(
    [
        st.Page("pages/home.py", title="Home", default=True),
        st.Page("pages/resultaten.py", title="Resultaten"),
    ],
    position="sidebar",
)
pg.run()
