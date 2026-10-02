"""Streamlit-app entrypoint."""

import streamlit as st

st.set_page_config(
    page_title="MBO-bekostigingsbestanden",
    page_icon="📊",
    layout="wide",
)

pg = st.navigation(
    [
        st.Page("pages/home.py", title="Home", default=True),
        st.Page("pages/werkbare_data.py", title="Werkbare data"),
        st.Page("pages/analysemodel.py", title="Analysemodel"),
        st.Page("pages/dashboard.py", title="Dashboard"),
    ],
    position="sidebar",
)
pg.run()
