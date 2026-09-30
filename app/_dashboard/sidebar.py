"""Schooljaarselectie in de sidebar."""

import streamlit as st

_PILLS_KEY = "schooljaar_pills"
_JAREN_KEY = "beschikbare_jaren"


def schooljaar_selectie(jaren: list[int]) -> list[int]:
    """Rendert schooljaar-pills in de sidebar en geeft de selectie terug.

    Nieuw beschikbare jaren (bijv. na een nieuwe verwerking) worden aan de
    selectie toegevoegd; verdwenen jaren vallen eruit.
    """
    if _JAREN_KEY not in st.session_state:
        st.session_state[_JAREN_KEY] = jaren
        st.session_state[_PILLS_KEY] = jaren
    elif st.session_state[_JAREN_KEY] != jaren:
        oud = st.session_state[_JAREN_KEY]
        huidig = set(st.session_state.get(_PILLS_KEY, []))
        st.session_state[_JAREN_KEY] = jaren
        st.session_state[_PILLS_KEY] = [j for j in jaren if j in huidig or j not in oud]

    with st.sidebar:
        st.header("Filters")
        st.caption(
            "**Schooljaar** — loopt van 1 augustus t/m 31 juli (bijv. 2024 = "
            "aug 2024 – jul 2025); peildatum 1 oktober. Elk feit filtert op zijn "
            "eigen jaar: inschrijvingen op 1 oktober op hun schooljaar, "
            "bekostiging op het schooljaar van de teldatum, perioden als ze in het "
            "schooljaar beginnen of er op 1 oktober actief zijn."
        )
        col_all, col_none = st.columns(2)
        if col_all.button("Alle", width="stretch"):
            st.session_state[_PILLS_KEY] = jaren
        if col_none.button("Geen", width="stretch"):
            st.session_state[_PILLS_KEY] = []
        geselecteerd = st.pills(
            "Schooljaar",
            options=jaren,
            selection_mode="multi",
            key=_PILLS_KEY,
        )
        if geselecteerd and len(geselecteerd) < len(jaren):
            st.info(f"ℹ️ {len(geselecteerd)} van {len(jaren)} schooljaren geselecteerd")
        if not geselecteerd:
            st.warning("Geen schooljaar geselecteerd.")
    return list(geselecteerd or [])
