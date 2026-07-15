"""Dashboard — visueel overzicht van de gecombineerde OBT-data."""

import sys
import tomllib
from pathlib import Path

import polars as pl
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils import output_dir

_GEO_META = (
    Path(__file__).parent.parent.parent
    / "src/mbo_bekostiging_bestanden/metadata/geo_codes.toml"
)

REDEN_LABELS = {
    "01": "Diploma BOL",
    "02": "Diploma BBL",
    "06": "Eigen verzoek",
    "08": "Verwijdering instelling",
    "4": "Geslaagd (oud)",
    "7": "Uitstroom zonder diploma",
    "8": "Verwijderd (oud)",
}


def _resolve_dir() -> Path | None:
    for key in ("resultaten_dir", "obt_pad"):
        val = st.session_state.get(key)
        if val:
            p = Path(val)
            if (p / "obt_inschrijvingen.parquet").exists():
                return p
    fallback = output_dir() / "obt"
    if (fallback / "obt_inschrijvingen.parquet").exists():
        return fallback
    return None


st.markdown(
    '<span style="font-size:.75rem;font-weight:700;color:#7b8ab8;'
    'text-transform:uppercase;letter-spacing:.08em">Dashboard</span>',
    unsafe_allow_html=True,
)
st.title("Dashboard")

data_dir = _resolve_dir()

if data_dir is None:
    st.warning(
        "Geen OBT-data gevonden — verwerk eerst bestanden via Home of zet "
        "demo-data in `data/03-output/demo/obt/`."
    )
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()

df = pl.read_parquet(data_dir / "obt_inschrijvingen.parquet")

# ---------------------------------------------------------------------------
# Header metrics
# ---------------------------------------------------------------------------

totaal = df.height

bekostigd_n = 0
if "IndicatieBekostigbaar" in df.columns:
    bekostigd_n = df.filter(
        pl.col("IndicatieBekostigbaar").is_in(["J", "1"])
    ).height

diplomas_n = 0
if "DIP_DatumResultaat" in df.columns:
    diplomas_n = df.filter(pl.col("DIP_DatumResultaat").is_not_null()).height

n_leveringen = df["levering"].n_unique() if "levering" in df.columns else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Inschrijvingen", f"{totaal:,}")
col2.metric("Bekostigd (indicatie)", f"{bekostigd_n:,}")
col3.metric("Diploma's behaald", f"{diplomas_n:,}")
col4.metric("Leveringen", n_leveringen)

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_rendementen, tab_bekostiging, tab_opleidingen, tab_studenten, tab_examens = (
    st.tabs(["Rendementen", "Bekostiging", "Opleidingen", "Studenten", "Examens"])
)

# ---------------------------------------------------------------------------
# Tab 1 — Rendementen
# ---------------------------------------------------------------------------

with tab_rendementen:
    st.subheader("Jaarresultaat (JR) — indicatief")

    if "_actief_1_oktober" in df.columns and "_gediplomeerd_in_jaar" in df.columns:
        jr_base = df.filter(pl.col("_actief_1_oktober").is_not_null())
        if not jr_base.is_empty() and "levering" in df.columns:
            jr = (
                jr_base.group_by("levering")
                .agg(
                    pl.col("_actief_1_oktober").sum().alias("Actief 1-okt (N)"),
                    pl.col("_gediplomeerd_in_jaar").sum().alias("Gediplomeerd (N)"),
                )
                .sort("levering")
                .with_columns(
                    (
                        pl.col("Gediplomeerd (N)")
                        / pl.col("Actief 1-okt (N)")
                        * 100
                    )
                    .round(1)
                    .alias("JR (%)")
                )
                .rename({"levering": "Levering"})
            )
            st.dataframe(jr, use_container_width=True, hide_index=True)
            st.info("DUO-norm: ≥ 75% voor positieve beoordeling")
        else:
            st.info("Geen rijen met bekende `_actief_1_oktober`-status.")
    else:
        st.info(
            "Kolommen `_actief_1_oktober` en `_gediplomeerd_in_jaar` niet beschikbaar."
        )

    st.subheader("Diploma's per Leertraject")
    if "Leertraject" in df.columns and "DIP_DatumResultaat" in df.columns:
        dip_lt = (
            df.with_columns(
                pl.when(pl.col("DIP_DatumResultaat").is_not_null())
                .then(pl.lit("Diploma behaald"))
                .otherwise(pl.lit("Geen diploma"))
                .alias("Diplomastatus")
            )
            .filter(
                pl.col("Leertraject").is_not_null()
                & (pl.col("Leertraject") != "")
            )
            .group_by(["Leertraject", "Diplomastatus"])
            .agg(pl.len().alias("Inschrijvingen"))
            .sort(["Leertraject", "Diplomastatus"])
        )
        if not dip_lt.is_empty():
            st.bar_chart(
                dip_lt, x="Leertraject", y="Inschrijvingen", color="Diplomastatus"
            )
        else:
            st.info("Geen data beschikbaar voor deze grafiek.")
    else:
        st.info("Kolommen `Leertraject` of `DIP_DatumResultaat` niet beschikbaar.")

# ---------------------------------------------------------------------------
# Tab 2 — Bekostiging
# ---------------------------------------------------------------------------

with tab_bekostiging:
    st.subheader("Bekostigingstrechter")

    actief_1okt_n: int | str = "—"
    bekostigd_1okt_n: int | str = "—"
    niet_bekostigd_n: int | str = "—"

    if "_actief_1_oktober" in df.columns:
        actief_1okt_n = df.filter(pl.col("_actief_1_oktober")).height

    if "_bekostigd_eerste_1okt" in df.columns:
        bekostigd_1okt_n = df.filter(pl.col("_bekostigd_eerste_1okt")).height

    if "_deelnemer_niet_bekostigd_eerste_1okt" in df.columns:
        niet_bekostigd_n = df.filter(
            pl.col("_deelnemer_niet_bekostigd_eerste_1okt")
        ).height

    tc1, tc2, tc3, tc4 = st.columns(4)
    tc1.metric("Totaal inschrijvingen", f"{totaal:,}")
    tc2.metric(
        "Actief op 1-oktober",
        f"{actief_1okt_n:,}" if isinstance(actief_1okt_n, int) else actief_1okt_n,
    )
    tc3.metric(
        "Bekostigd op 1-oktober",
        f"{bekostigd_1okt_n:,}"
        if isinstance(bekostigd_1okt_n, int)
        else bekostigd_1okt_n,
    )
    tc4.metric(
        "Actief maar niet bekostigd",
        f"{niet_bekostigd_n:,}"
        if isinstance(niet_bekostigd_n, int)
        else niet_bekostigd_n,
    )

    st.subheader("Bekostigd vs niet-bekostigd per levering")
    if "IndicatieBekostigbaar" in df.columns and "levering" in df.columns:
        bek_lev = (
            df.with_columns(
                pl.when(pl.col("IndicatieBekostigbaar").is_in(["J", "1"]))
                .then(pl.lit("Bekostigd"))
                .otherwise(pl.lit("Niet bekostigd"))
                .alias("Bekostigingstatus")
            )
            .group_by(["levering", "Bekostigingstatus"])
            .agg(pl.len().alias("Inschrijvingen"))
            .sort(["levering", "Bekostigingstatus"])
        )
        if not bek_lev.is_empty():
            st.bar_chart(
                bek_lev,
                x="levering",
                y="Inschrijvingen",
                color="Bekostigingstatus",
            )
        else:
            st.info("Geen data beschikbaar voor deze grafiek.")
    else:
        st.info("Kolommen `IndicatieBekostigbaar` of `levering` niet beschikbaar.")

    st.subheader("Inschrijvingen na 1-oktober")
    if "_ingeschreven_jaar_later" in df.columns:
        na_1okt = df.filter(pl.col("_ingeschreven_jaar_later")).height
        st.metric(
            "Ingeschreven na 1-oktober",
            f"{na_1okt:,}",
            help="Tellen niet mee voor de 1-oktober-bekostiging.",
        )
    else:
        st.info("Kolom `_ingeschreven_jaar_later` niet beschikbaar.")

# ---------------------------------------------------------------------------
# Tab 3 — Opleidingen
# ---------------------------------------------------------------------------

with tab_opleidingen:
    st.subheader("Top-10 opleidingen naar inschrijvingen")
    if "Opleidingcode" in df.columns:
        top10 = (
            df.filter(
                pl.col("Opleidingcode").is_not_null()
                & (pl.col("Opleidingcode") != "")
            )
            .group_by("Opleidingcode")
            .agg(pl.len().alias("Inschrijvingen"))
            .sort("Inschrijvingen", descending=True)
            .head(10)
        )
        if not top10.is_empty():
            top10 = top10.with_columns(
                ("CREBO " + pl.col("Opleidingcode")).alias("Opleiding")
            )
            st.bar_chart(top10, x="Opleiding", y="Inschrijvingen")
            st.caption(
                "CREBO-namen zijn niet beschikbaar in de huidige decodeertabellen. "
                "Zie het SBB CREBO-register voor volledige namen."
            )
        else:
            st.info("Geen data beschikbaar voor deze grafiek.")
    else:
        st.info("Kolom `Opleidingcode` niet beschikbaar.")

    st.subheader("BOL vs BBL per levering")
    if "Leertraject" in df.columns and "levering" in df.columns:
        bol_bbl = (
            df.filter(
                pl.col("Leertraject").is_not_null()
                & (pl.col("Leertraject") != "")
            )
            .group_by(["levering", "Leertraject"])
            .agg(pl.len().alias("Inschrijvingen"))
            .sort(["levering", "Leertraject"])
        )
        if not bol_bbl.is_empty():
            st.bar_chart(
                bol_bbl, x="levering", y="Inschrijvingen", color="Leertraject"
            )
        else:
            st.info("Geen data beschikbaar voor deze grafiek.")
    else:
        st.info("Kolommen `levering` of `Leertraject` niet beschikbaar.")

    st.subheader("BPV-coverage")
    if "BPV_Aantal" in df.columns and "Leertraject" in df.columns:
        bpv = (
            df.filter(
                pl.col("Leertraject").is_not_null()
                & (pl.col("Leertraject") != "")
            )
            .with_columns(
                pl.when(
                    pl.col("BPV_Aantal").is_not_null() & (pl.col("BPV_Aantal") > 0)
                )
                .then(pl.lit("Met BPV"))
                .otherwise(pl.lit("Zonder BPV"))
                .alias("BPV_status")
            )
            .group_by(["Leertraject", "BPV_status"])
            .agg(pl.len().alias("Inschrijvingen"))
            .sort(["Leertraject", "BPV_status"])
        )
        if not bpv.is_empty():
            st.bar_chart(bpv, x="Leertraject", y="Inschrijvingen", color="BPV_status")
        else:
            st.info("Geen BPV-data beschikbaar.")
    else:
        st.info("Kolommen `BPV_Aantal` of `Leertraject` niet beschikbaar.")

    st.subheader("KZD-behaaldverhouding per levering")
    if (
        "KZD_Aantal" in df.columns
        and "KZD_AantalBehaald" in df.columns
        and "levering" in df.columns
    ):
        kzd = (
            df.filter(
                pl.col("KZD_Aantal").is_not_null()
                & (pl.col("KZD_Aantal") > 0)
                & pl.col("KZD_AantalBehaald").is_not_null()
            )
            .with_columns(
                (pl.col("KZD_AantalBehaald") / pl.col("KZD_Aantal") * 100).alias(
                    "_ratio"
                )
            )
            .group_by("levering")
            .agg(pl.col("_ratio").mean().round(1).alias("Gem. KZD behaald (%)"))
            .sort("levering")
            .rename({"levering": "Levering"})
        )
        if not kzd.is_empty():
            st.dataframe(kzd, use_container_width=True, hide_index=True)
        else:
            st.info("Geen KZD-data beschikbaar.")
    else:
        st.info("Kolommen `KZD_Aantal` of `KZD_AantalBehaald` niet beschikbaar.")

    if "Instelling_naam" in df.columns:
        instelling_cols = ["Instelling_naam"]
        if "Instelling_plaats" in df.columns:
            instelling_cols.append("Instelling_plaats")
        instelling_info = (
            df.select(instelling_cols)
            .filter(pl.col("Instelling_naam").is_not_null())
            .unique()
            .sort("Instelling_naam")
        )
        if not instelling_info.is_empty():
            st.subheader("Instelling")
            st.dataframe(instelling_info, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Tab 4 — Studenten
# ---------------------------------------------------------------------------

with tab_studenten:
    st.subheader("Geslachtsverdeling per Leertraject")
    if "Geslacht" in df.columns and "Leertraject" in df.columns:
        _GESLACHT = {"M": "Man", "V": "Vrouw", "O": "Onbekend"}
        geslacht = (
            df.filter(
                pl.col("Geslacht").is_not_null()
                & (pl.col("Geslacht") != "")
                & pl.col("Leertraject").is_not_null()
                & (pl.col("Leertraject") != "")
            )
            .with_columns(
                pl.col("Geslacht").replace(_GESLACHT).alias("Geslacht")
            )
            .group_by(["Geslacht", "Leertraject"])
            .agg(pl.len().alias("Inschrijvingen"))
            .sort(["Geslacht", "Leertraject"])
        )
        if not geslacht.is_empty():
            st.bar_chart(
                geslacht, x="Leertraject", y="Inschrijvingen", color="Geslacht"
            )
        else:
            st.info("Geen data beschikbaar voor deze grafiek.")
    else:
        st.info("Kolommen `Geslacht` of `Leertraject` niet beschikbaar.")

    if "Nationaliteit1_migratieachtergrond" in df.columns:
        st.subheader("Herkomst (migratieachtergrond)")
        herkomst = (
            df.filter(pl.col("Nationaliteit1_migratieachtergrond").is_not_null())
            .group_by("Nationaliteit1_migratieachtergrond")
            .agg(pl.len().alias("Inschrijvingen"))
            .sort("Inschrijvingen", descending=True)
            .rename({"Nationaliteit1_migratieachtergrond": "Migratieachtergrond"})
        )
        if not herkomst.is_empty():
            st.bar_chart(herkomst, x="Migratieachtergrond", y="Inschrijvingen")
        else:
            st.info("Geen herkomstdata beschikbaar.")

    if "Gemeente" in df.columns:
        st.subheader("Top 10 gemeenten")
        top10_gem = (
            df.filter(
                pl.col("Gemeente").is_not_null() & (pl.col("Gemeente") != "")
            )
            .group_by("Gemeente")
            .agg(pl.len().alias("Studenten"))
            .sort("Studenten", descending=True)
            .head(10)
        )
        if not top10_gem.is_empty():
            st.dataframe(top10_gem, use_container_width=True, hide_index=True)
        else:
            st.info("Geen gemeentedata beschikbaar.")

    if "CodeGeboorteland_naam" in df.columns:
        st.subheader("Top 10 geboorteland")
        top10_land = (
            df.filter(
                pl.col("CodeGeboorteland_naam").is_not_null()
                & (pl.col("CodeGeboorteland_naam") != "")
                & (pl.col("CodeGeboorteland_naam") != "Onbekend")
                & (pl.col("CodeGeboorteland_naam") != "NULL")
            )
            .group_by("CodeGeboorteland_naam")
            .agg(pl.len().alias("Studenten"))
            .sort("Studenten", descending=True)
            .head(10)
            .rename({"CodeGeboorteland_naam": "Geboorteland"})
        )
        if not top10_land.is_empty():
            st.dataframe(top10_land, use_container_width=True, hide_index=True)
        else:
            st.info("Geen geboortelanddata beschikbaar.")

    st.subheader("Uitstroomredenen")
    if "RedenUitschrijving" in df.columns:

        def _label_reden(code: str | None) -> str:
            if code is None or code == "":
                return "Nog ingeschreven"
            lbl = REDEN_LABELS.get(code)
            return lbl if lbl is not None else f"Overig (code: {code})"

        uitstroom = (
            df.with_columns(
                pl.col("RedenUitschrijving")
                .map_elements(_label_reden, return_dtype=pl.String)
                .alias("Reden")
            )
            .group_by("Reden")
            .agg(pl.len().alias("Aantal"))
            .sort("Aantal", descending=True)
        )
        if not uitstroom.is_empty():
            st.bar_chart(uitstroom, x="Reden", y="Aantal")
        else:
            st.info("Geen uitstroomdata beschikbaar.")
    else:
        st.info("Kolom `RedenUitschrijving` niet beschikbaar.")

    st.subheader("Duur inschrijving (maanden)")
    if (
        "DatumInschrijving" in df.columns
        and "DatumUitschrijvingWerkelijk" in df.columns
    ):
        duur_df = (
            df.filter(
                pl.col("DatumInschrijving").is_not_null()
                & pl.col("DatumUitschrijvingWerkelijk").is_not_null()
            )
            .with_columns(
                (
                    (
                        pl.col("DatumUitschrijvingWerkelijk")
                        - pl.col("DatumInschrijving")
                    ).dt.total_days()
                    / 30
                ).alias("Duur_maanden")
            )
            .filter(pl.col("Duur_maanden") > 0)
        )
        if not duur_df.is_empty():
            bucket_order = [
                "< 6 mnd",
                "6–12 mnd",
                "12–24 mnd",
                "24–36 mnd",
                "> 36 mnd",
            ]
            buckets = (
                duur_df.with_columns(
                    pl.when(pl.col("Duur_maanden") < 6)
                    .then(pl.lit("< 6 mnd"))
                    .when(pl.col("Duur_maanden") < 12)
                    .then(pl.lit("6–12 mnd"))
                    .when(pl.col("Duur_maanden") < 24)
                    .then(pl.lit("12–24 mnd"))
                    .when(pl.col("Duur_maanden") < 36)
                    .then(pl.lit("24–36 mnd"))
                    .otherwise(pl.lit("> 36 mnd"))
                    .alias("Bucket")
                )
                .group_by("Bucket")
                .agg(pl.len().alias("Inschrijvingen"))
                .with_columns(pl.col("Bucket").cast(pl.Enum(bucket_order)))
                .sort("Bucket")
            )
            st.bar_chart(buckets, x="Bucket", y="Inschrijvingen")
        else:
            st.info("Geen inschrijvingen met bekende in- en uitschrijfdatum.")
    else:
        st.info(
            "Kolommen `DatumInschrijving` of `DatumUitschrijvingWerkelijk` "
            "niet beschikbaar."
        )

# ---------------------------------------------------------------------------
# Tab 5 — Examens
# ---------------------------------------------------------------------------

with tab_examens:
    _geo_labels: dict[str, str] = {}
    if _GEO_META.exists():
        with _GEO_META.open("rb") as _f:
            _geo_toml = tomllib.load(_f)
        for _code, _meta in _geo_toml.get("codes", {}).items():
            _geo_labels[_code] = _meta.get("label", _code)

    geo_eindcijfer_cols = [
        c for c in df.columns if c.startswith("GEO_") and c.endswith("_Eindcijfer")
    ]

    st.subheader("GEO-examencijfers")
    if geo_eindcijfer_cols:
        geo_rows = []
        for col in sorted(geo_eindcijfer_cols):
            code = col.replace("GEO_", "").replace("_Eindcijfer", "")
            serie = df[col].drop_nulls()
            if serie.is_empty():
                continue
            geo_rows.append(
                {
                    "Onderdeel": _geo_labels.get(code, f"GEO {code}"),
                    "Gemiddeld eindcijfer": serie.to_frame().select(
                        pl.col(col).cast(pl.Float64).mean().round(1)
                    ).item(),
                    "N": len(serie),
                }
            )
        if geo_rows:
            geo_tbl = pl.DataFrame(geo_rows)
            st.dataframe(geo_tbl, use_container_width=True, hide_index=True)
        else:
            st.info("Geen GEO-eindcijfers gevuld in de data.")
    else:
        st.info("Geen GEO-eindcijferkolommen aanwezig in de data.")

    st.subheader("GEO IE vs CE — vergelijking")
    for geo_code in ("3001", "3002"):
        ie_col = f"GEO_{geo_code}_CijferIE"
        ce_col = f"GEO_{geo_code}_CijferCE"
        if ie_col in df.columns and ce_col in df.columns:
            ie_vals = df[ie_col].drop_nulls()
            ce_vals = df[ce_col].drop_nulls()
            if not ie_vals.is_empty() and not ce_vals.is_empty():
                label = "Nederlands" if geo_code == "3001" else "Rekenen"
                st.markdown(f"**{label} (GEO {geo_code})**")
                gc1, gc2 = st.columns(2)
                gc1.metric(
                    f"Gem. IE ({label})",
                    f"{ie_vals.mean():.1f}",
                    help="Instituutsexamen",
                )
                gc2.metric(
                    f"Gem. CE ({label})",
                    f"{ce_vals.mean():.1f}",
                    help="Centraal examen",
                )

    st.subheader("AMO-onderdelen")
    if "AMO_Aantal" in df.columns:
        amo_serie = df["AMO_Aantal"].drop_nulls()
        if not amo_serie.is_empty():
            amo_totaal = int(amo_serie.sum())
            amo_gem = amo_serie.mean()
            ac1, ac2 = st.columns(2)
            ac1.metric("Totaal AMO-onderdelen", f"{amo_totaal:,}")
            ac2.metric("Gemiddeld per inschrijving", f"{amo_gem:.1f}")
        else:
            st.info("Kolom `AMO_Aantal` is volledig leeg.")
    else:
        st.info("Kolom `AMO_Aantal` niet beschikbaar.")

st.caption(
    "© CEDA · Npuls — [GitHub](https://github.com/cedanl/mbo-bekostiging-bestanden)"
)
