"""Streamlit-app entrypoint — registreert pagina's en verbergt de sidebar."""

import streamlit as st

st.set_page_config(
    page_title="MBO-bekostigingsbestanden",
    page_icon="📊",
    layout="centered",
)

pg = st.navigation(
    [
        st.Page("pages/home.py", title="Home", default=True),
        st.Page("pages/kiezen.py", title="Stap 1 – Bestand kiezen"),
        st.Page("pages/verwerken.py", title="Stap 2 – Verwerken"),
        st.Page("pages/stapelen.py", title="Stap 1 – Leveringen stapelen"),
        st.Page("pages/resultaten.py", title="Resultaten"),
    ],
    position="hidden",
)
pg.run()
