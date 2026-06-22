"""Streamlit-interface voor de bekostigingsbestanden-pipeline.

Bevat geen bedrijfslogica; roept alleen de package-functies aan.
"""

import tomllib
from pathlib import Path

import streamlit as st

from mbo_bekostiging_bestanden.export import export_frames
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.stack import stack_prepared


def load_config() -> dict:
    """Lees de app-configuratie met datapaden."""
    config_path = Path(__file__).parent / "config.toml"
    with config_path.open("rb") as f:
        return tomllib.load(f)


def main() -> None:
    st.title("MBO-bekostigingsbestanden")

    config = load_config()
    raw_dir = Path(config["data"]["raw"])
    prepared_dir = Path(config["data"]["prepared"])
    output_dir = Path(config["data"]["output"])

    tab_verwerk, tab_stapel = st.tabs(["Verwerk bestand", "Stapel leveringen"])

    with tab_verwerk:
        st.write("Lees een ruw bekostigingsbestand in en zet het om naar schone data.")
        sources = sorted(p for p in raw_dir.rglob("*") if p.is_file())
        if not sources:
            st.info(f"Geen bronbestanden gevonden in {raw_dir}.")
        else:
            source = st.selectbox(
                "Kies een bronbestand",
                sources,
                format_func=lambda p: str(p.relative_to(raw_dir)),
            )
            if st.button("Verwerk"):
                sub = source.parent.relative_to(raw_dir)
                target = prepared_dir / sub / source.stem[:4]
                frames = run_auto_pipeline(source, target)
                total = sum(df.height for df in frames.values())
                st.success(
                    f"Verwerkt: {len(frames)} tabellen, {total} rijen → {target}"
                )
                tabel = st.selectbox("Bekijk tabel", sorted(frames.keys()))
                st.dataframe(frames[tabel].head(100))

    with tab_stapel:
        st.write("Voeg genormaliseerde tabellen van meerdere leveringen samen.")
        prepared_dirs = sorted(
            d
            for d in prepared_dir.rglob("*")
            if d.is_dir() and any(d.glob("*.parquet"))
        )
        if not prepared_dirs:
            st.info(f"Geen prepared-mappen gevonden in {prepared_dir}.")
        else:
            selected = st.multiselect(
                "Kies mappen om te stapelen",
                prepared_dirs,
                format_func=lambda p: str(p.relative_to(prepared_dir)),
            )
            if selected and st.button("Stapel"):
                target = output_dir / "gestapeld"
                frames = stack_prepared(selected, relative_to=prepared_dir)
                export_frames(frames, target)
                total = sum(df.height for df in frames.values())
                st.success(
                    f"Gestapeld: {len(frames)} tabellen, {total} rijen → {target}"
                )
                tabel = st.selectbox(
                    "Bekijk tabel", sorted(frames.keys()), key="stapel_tabel"
                )
                st.dataframe(frames[tabel].head(100))


if __name__ == "__main__":
    main()
