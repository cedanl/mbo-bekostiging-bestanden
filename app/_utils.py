"""Gedeelde hulpfuncties voor de Streamlit-app."""

import tomllib
from pathlib import Path


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.toml"
    with config_path.open("rb") as f:
        return tomllib.load(f)


def raw_dir() -> Path:
    return Path(load_config()["data"]["raw"])


def prepared_dir() -> Path:
    return Path(load_config()["data"]["prepared"])


def output_dir() -> Path:
    return Path(load_config()["data"]["output"])
