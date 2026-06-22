"""Home — kies een flow."""

import streamlit as st

st.markdown(
    """
<style>
.hero {
    background: linear-gradient(135deg, #1a56db 0%, #0e3fa8 100%);
    padding: 2rem 1.5rem;
    border-radius: 10px;
    color: white;
    margin-bottom: 1.5rem;
    text-align: center;
}
.hero h1 { margin: 0 0 .4rem 0; font-size: 2rem; font-weight: 700; }
.hero p  { margin: 0; opacity: .88; font-size: 1rem; }
.step-card {
    background: #f8f9fc;
    border: 1px solid #e2e6f0;
    border-radius: 8px;
    padding: .9rem 1rem;
    text-align: center;
    height: 100%;
}
.step-card .num  { font-size: .7rem; font-weight: 700; color: #7b8ab8;
                   text-transform: uppercase; letter-spacing: .08em; }
.step-card .name { font-size: .95rem; font-weight: 600; color: #1a1a2e;
                   margin: .2rem 0; }
.step-card .desc { font-size: .8rem; color: #666; line-height: 1.4; }
</style>

<div class="hero">
  <h1>MBO-bekostigingsbestanden</h1>
  <p>Zet ruwe DUO-bekostigingsbestanden om naar schone,
     onderzoeksklare Parquet-data.</p>
</div>
""",
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(
        """<div class="step-card">
      <div class="num">Stap 1</div>
      <div class="name">Bestand kiezen</div>
      <div class="desc">Selecteer een ruw bekostigingsbestand uit de invoermap.</div>
    </div>""",
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        """<div class="step-card">
      <div class="num">Stap 2</div>
      <div class="name">Verwerken</div>
      <div class="desc">Pipeline normaliseert het bestand naar getypeerde
      tabellen.</div>
    </div>""",
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        """<div class="step-card">
      <div class="num">Stap 3</div>
      <div class="name">Resultaten</div>
      <div class="desc">Bekijk en download de genormaliseerde output.</div>
    </div>""",
        unsafe_allow_html=True,
    )

st.write("")
st.markdown("#### Waarmee wil je beginnen?")

col_a, col_b = st.columns(2)
with col_a:
    if st.button(
        "Verwerk één bestand",
        type="primary",
        use_container_width=True,
        help="Lees een ruw RO-, GRONDSLAG- of TBGI-bestand in.",
    ):
        st.switch_page("pages/kiezen.py")
    st.caption("Eén ruw bestand → Parquet per tabel.")

with col_b:
    if st.button(
        "Stapel leveringen",
        type="secondary",
        use_container_width=True,
        help="Combineer al verwerkte leveringen tot één tabel per type.",
    ):
        st.switch_page("pages/stapelen.py")
    st.caption("Meerdere prepared-mappen → gecombineerde output.")

st.divider()
st.caption(
    "© CEDA · Npuls — [GitHub](https://github.com/cedanl/mbo-bekostiging-bestanden)"
)
