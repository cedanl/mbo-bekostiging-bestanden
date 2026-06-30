"""Streamlit-interface voor de bekostigingsbestanden-pipeline.

Bevat geen bedrijfslogica; roept alleen de package-functies aan.
"""

import tempfile
import tomllib
from pathlib import Path

import polars as pl
import streamlit as st

from mbo_bekostiging_bestanden.pipeline import run_pipeline


def load_config() -> dict:
    """Lees de app-configuratie met datapaden."""
    config_path = Path(__file__).parent / "config.toml"
    with config_path.open("rb") as f:
        return tomllib.load(f)


def select_source(raw_dir: Path) -> Path | None:
    """Laat de gebruiker een demo-bestand kiezen of een eigen bestand uploaden.

    Returns:
        Het pad naar het te verwerken bronbestand, of ``None`` als er nog
        geen keuze/upload is.
    """
    mode = st.radio("Bron", ["Demo-data", "Eigen bestand uploaden"], horizontal=True)

    if mode == "Demo-data":
        sources = sorted(p for p in raw_dir.rglob("*") if p.is_file())
        if not sources:
            st.info(f"Geen bronbestanden gevonden in {raw_dir}.")
            return None
        return st.selectbox(
            "Kies een bronbestand",
            sources,
            format_func=lambda p: str(p.relative_to(raw_dir)),
        )

    uploaded = st.file_uploader("Upload een ruw bekostigingsbestand")
    if uploaded is None:
        return None
    tmp = Path(tempfile.gettempdir()) / Path(uploaded.name).name
    tmp.write_bytes(uploaded.getbuffer())
    return tmp


def main() -> None:
    st.title("MBO-bekostigingsbestanden")
    st.write("Lees ruwe bekostigingsbestanden in en zet ze om naar schone data.")

    config = load_config()
    raw_dir = Path(config["data"]["raw"])
    output_dir = Path(config["data"]["output"])

    source = select_source(raw_dir)
    if source is None:
        return

    if st.button("Verwerk"):
        target = output_dir / f"{source.stem}.parquet"
        data: pl.DataFrame = run_pipeline(source, target)
        st.success(f"Verwerkt: {len(data)} rijen geschreven naar {target}")
        st.dataframe(data.head(100).to_pandas())
        st.download_button(
            "Download resultaat (Parquet)",
            data=target.read_bytes(),
            file_name=target.name,
        )


if __name__ == "__main__":
    main()
