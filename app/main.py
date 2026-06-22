"""Streamlit-interface voor de bekostigingsbestanden-pipeline.

Bevat geen bedrijfslogica; roept alleen de package-functies aan.
"""

import tomllib
from pathlib import Path

import streamlit as st

from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline


def load_config() -> dict:
    """Lees de app-configuratie met datapaden."""
    config_path = Path(__file__).parent / "config.toml"
    with config_path.open("rb") as f:
        return tomllib.load(f)


def main() -> None:
    st.title("MBO-bekostigingsbestanden")
    st.write("Lees ruwe bekostigingsbestanden in en zet ze om naar schone data.")

    config = load_config()
    raw_dir = Path(config["data"]["raw"])
    output_dir = Path(config["data"]["output"])

    sources = sorted(p for p in raw_dir.rglob("*") if p.is_file())
    if not sources:
        st.info(f"Geen bronbestanden gevonden in {raw_dir}.")
        return

    source = st.selectbox(
        "Kies een bronbestand",
        sources,
        format_func=lambda p: str(p.relative_to(raw_dir)),
    )
    if st.button("Verwerk"):
        target = output_dir / source.stem
        frames = run_auto_pipeline(source, target)
        total = sum(df.height for df in frames.values())
        st.success(f"Verwerkt: {len(frames)} tabellen, {total} rijen totaal → {target}")

        rt = st.selectbox("Bekijk tabel", sorted(frames.keys()))
        st.dataframe(frames[rt].head(100))


if __name__ == "__main__":
    main()
