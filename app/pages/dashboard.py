"""Dashboard — visueel overzicht van de verwerkte bekostigingsdata."""

import sys
import tomllib
from pathlib import Path

import polars as pl
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _chart_docs import chart_help
from _utils import output_dir

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from mbo_bekostiging_bestanden.indicatoren import (
    bereken_oordeel,
    entree_indicatoren,
    entree_totaal,
    norm_voor,
    populatie_regele_filter,
)

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


@st.cache_resource(show_spinner=False)
def _lees_parquet(pad: str, mtime: float) -> pl.DataFrame:
    """Lees een parquet-bestand en cache op pad + wijzigingsdatum."""
    return pl.read_parquet(pad)


def _lees_star_schema(
    data_dir: Path,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Laad het star schema en lever (df, fact_geo, fact_bpv, fact_kzd).

    ``df`` is fact_inschrijving gejoined met de drie dim-tabellen, wat een
    vergelijkbaar kolomset geeft als de oude OBT (zonder GEO-pivotkolommen).
    De losse fact-tabellen zijn beschikbaar voor gedetailleerde analyses.
    """
    dm = data_dir / "datamodel"

    def _laad(name: str) -> pl.DataFrame:
        p = dm / f"{name}.parquet"
        if not p.exists():
            return pl.DataFrame()
        return _lees_parquet(str(p), p.stat().st_mtime)

    fact = _laad("fact_inschrijving")
    dim_deelnemer = _laad("dim_deelnemer")
    dim_opleiding = _laad("dim_opleiding")
    dim_instelling = _laad("dim_instelling")

    df = fact
    if not dim_deelnemer.is_empty() and "_persoon_id" in df.columns:
        df = df.join(dim_deelnemer, on="_persoon_id", how="left")
    if not dim_opleiding.is_empty() and "Opleidingcode" in df.columns:
        df = df.join(dim_opleiding, on="Opleidingcode", how="left")
    if not dim_instelling.is_empty() and "BRIN" in df.columns:
        df = df.join(dim_instelling, on="BRIN", how="left")

    return df, _laad("fact_geo"), _laad("fact_bpv"), _laad("fact_kzd")


_PILLS_KEY = "studiejaar_pills"


def _sidebar_studiejaar_filter(df: pl.DataFrame) -> pl.DataFrame:
    """Rendert studiejaar-pills met select/deselect-all in de sidebar en filtert df."""
    if "Studiejaar" not in df.columns:
        return df
    jaren = sorted(df["Studiejaar"].drop_nulls().unique().to_list())
    if _PILLS_KEY not in st.session_state:
        st.session_state[_PILLS_KEY] = jaren
    with st.sidebar:
        st.header("Filters")
        st.caption(
            "**Studiejaar** — schooljaar dat start op 1 augustus "
            "(bijv. 2024 = aug 2024 – jul 2025)."
        )
        col_all, col_none = st.columns(2)
        if col_all.button("Alle", use_container_width=True):
            st.session_state[_PILLS_KEY] = jaren
        if col_none.button("Geen", use_container_width=True):
            st.session_state[_PILLS_KEY] = []
        geselecteerd = st.pills(
            "Studiejaar",
            options=jaren,
            selection_mode="multi",
            key=_PILLS_KEY,
        )
        if not geselecteerd:
            st.warning("Geen studiejaar geselecteerd.")
    if not geselecteerd:
        return df.clear()
    return df.filter(pl.col("Studiejaar").is_in(geselecteerd))


st.markdown(
    '<span style="font-size:.75rem;font-weight:700;color:#7b8ab8;'
    'text-transform:uppercase;letter-spacing:.08em">Dashboard</span>',
    unsafe_allow_html=True,
)
st.title("Dashboard")

data_dir = _resolve_dir()

if data_dir is None:
    st.warning(
        "Geen data gevonden — verwerk eerst bestanden via Home of zet "
        "demo-data in `data/03-output/demo/obt/`."
    )
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()

df, fact_geo, fact_bpv, fact_kzd = _lees_star_schema(data_dir)
df = _sidebar_studiejaar_filter(df)

# Sleutels voor join op detail-feiten, gefilterd op geselecteerde studiejaren.
_FK = ["levering", "_persoon_id", "Inschrijvingvolgnummer"]
_filter_keys = df.select([k for k in _FK if k in df.columns])


def _filter_fact(f: pl.DataFrame) -> pl.DataFrame:
    """Filter een detail-fact op de gefilterde inschrijvingen via FK-join."""
    join_on = [k for k in _FK if k in f.columns]
    if not join_on or f.is_empty():
        return f
    # Lege _filter_keys (geen studiejaar geselecteerd) → lege fact teruggeven.
    keys = _filter_keys.select(join_on).unique()
    if keys.is_empty():
        return f.clear()
    return f.join(keys, on=join_on, how="inner")


fact_geo_f = _filter_fact(fact_geo)
fact_bpv_f = _filter_fact(fact_bpv)
fact_kzd_f = _filter_fact(fact_kzd)

# ---------------------------------------------------------------------------
# Header metrics
# ---------------------------------------------------------------------------

totaal = df.height

bekostigd_n = 0
if "IndicatieBekostigbaar" in df.columns:
    bekostigd_n = df.filter(pl.col("IndicatieBekostigbaar").is_in(["J", "1"])).height

diplomas_n = 0
if "DIP_DatumResultaat" in df.columns:
    diplomas_n = df.filter(pl.col("DIP_DatumResultaat").is_not_null()).height

n_leveringen = df["levering"].n_unique() if "levering" in df.columns else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Inschrijvingen",
    f"{totaal:,}",
    help="Aantal rijen in de OBT-inschrijvingentabel na toepassing van de "
    "studiejaarfilters.",
)
col2.metric(
    "Bekostigd (indicatie)",
    f"{bekostigd_n:,}",
    help="Aantal inschrijvingen met `IndicatieBekostigbaar` in ('J','1').",
)
col3.metric(
    "Diploma's behaald",
    f"{diplomas_n:,}",
    help="Aantal inschrijvingen met een ingevulde `DIP_DatumResultaat`.",
)
col4.metric(
    "Leveringen",
    n_leveringen,
    help="Aantal unieke leveringen (bronbestanden) in de data.",
)

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_rendementen, tab_bekostiging, tab_opleidingen, tab_studenten, tab_examens = st.tabs(
    ["Rendementen", "Bekostiging", "Opleidingen", "Studenten", "Examens"]
)

# ---------------------------------------------------------------------------
# Tab 1 — Rendementen
# ---------------------------------------------------------------------------

with tab_rendementen:
    st.subheader("Jaarresultaat (JR) — indicatief, per niveau")
    chart_help("jr_indicatief")

    # Populatieregels (bijlage 3): alleen bol/bbl/ex-leerwegen en niveau ≥ 2.
    jr_pop = populatie_regele_filter(df, min_niveau=2)

    if "_actief_1_oktober" in df.columns and "_gediplomeerd_in_jaar" in df.columns:
        if jr_pop.is_empty() or "Niveau" not in jr_pop.columns:
            st.info(
                "Geen rijen in de indicator-populatie (leerweg bol/bbl/ex, "
                "niveau ≥ 2, actief op 1-okt)."
            )
        else:
            jr = (
                jr_pop.filter(pl.col("_actief_1_oktober").is_not_null())
                .group_by(["levering", "Niveau"])
                .agg(
                    pl.col("_actief_1_oktober").sum().alias("Actief 1-okt (N)"),
                    pl.col("_gediplomeerd_in_jaar").sum().alias("Gediplomeerd (N)"),
                )
                .with_columns(
                    (pl.col("Gediplomeerd (N)") / pl.col("Actief 1-okt (N)") * 100)
                    .round(1)
                    .alias("JR (%)")
                )
                .sort(["Niveau", "levering"])
            )
            if jr.is_empty():
                st.info("Geen rijen met bekende `_actief_1_oktober`-status.")
            else:
                jr = (
                    jr.with_columns(
                        pl.col("Niveau")
                        .str.extract(r"(\d+)$")
                        .cast(pl.Int32)
                        .alias("_niv"),
                    )
                    .with_columns(
                        pl.struct(["Niveau", "_niv"])
                        .map_elements(
                            lambda r: norm_voor("jr", r["_niv"], "voldoende"),
                            return_dtype=pl.Int64,
                        )
                        .alias("Norm voldoende (%)"),
                        pl.struct(["Niveau", "_niv"])
                        .map_elements(
                            lambda r: norm_voor("jr", r["_niv"], "hoog"),
                            return_dtype=pl.Int64,
                        )
                        .alias("Norm hoog (%)"),
                    )
                    .drop("_niv")
                )
                jr = jr.with_columns(
                    (pl.col("JR (%)") >= pl.col("Norm voldoende (%)")).alias(
                        "Voldoet aan voldoende-norm"
                    )
                )
                st.dataframe(jr, use_container_width=True, hide_index=True)

                st.scatter_chart(
                    jr,
                    x="levering",
                    y="JR (%)",
                    size="Actief 1-okt (N)",
                    color="Niveau",
                    x_label="Levering",
                    y_label="JR (%)",
                    height=400,
                )
                st.caption(
                    "Normen voor voldoende (JR): niveau 2 = "
                    f"{norm_voor('jr', 2, 'voldoende')}%, niveau 3/4 = "
                    f"{norm_voor('jr', 3, 'voldoende')}%. Voor hoog: niveau 2 = "
                    f"{norm_voor('jr', 2, 'hoog')}%, niveau 3/4 = "
                    f"{norm_voor('jr', 3, 'hoog')}%. "
                    "Zie `_chart_docs` voor de indicatieve definitie."
                )
    else:
        st.info(
            "Kolommen `_actief_1_oktober` en `_gediplomeerd_in_jaar` niet beschikbaar."
        )

    st.subheader("Berekend oordeel Studiesucces (indicatief)")
    chart_help("berekend_oordeel")
    if "Niveau" in jr_pop.columns and "levering" in jr_pop.columns:
        oordeel_df = (
            jr_pop.filter(pl.col("_actief_1_oktober").is_not_null())
            .group_by(["Niveau"])
            .agg(
                pl.col("_actief_1_oktober").sum().alias("Actief 1-okt (N)"),
                pl.col("_gediplomeerd_in_jaar").sum().alias("Gediplomeerd (N)"),
            )
            .with_columns(
                (pl.col("Gediplomeerd (N)") / pl.col("Actief 1-okt (N)") * 100)
                .round(1)
                .alias("JR (%)")
            )
        )
        rows = []
        for r in oordeel_df.to_dicts():
            niv = int(r["Niveau"].split("-")[-1])
            if niv not in (2, 3, 4):
                continue
            oordeel, _, hoge = bereken_oordeel(
                {"waarde": r["JR (%)"], "noemer": r["Actief 1-okt (N)"]},
                None,
                None,
                niveau=niv,
            )
            rows.append(
                {
                    "Niveau": r["Niveau"],
                    "Actief (N)": r["Actief 1-okt (N)"],
                    "JR (%)": r["JR (%)"],
                    "Norm vold. JR (%)": norm_voor("jr", niv, "voldoende"),
                    "Norm hoog JR (%)": norm_voor("jr", niv, "hoog"),
                    "Berekend oordeel": oordeel,
                }
            )
        if rows:
            st.dataframe(pl.DataFrame(rows), use_container_width=True, hide_index=True)
            st.warning(
                "Het oordeel is alleen op JR-basis (DR en SR zijn niet beschikbaar "
                "in de OBT) en daarmee indicatief. Bij één indicator is een oordeel "
                "alleen mogelijk als de overige twee dezelfde richting uitwijzen "
                "(§3.5)."
            )
        else:
            st.info("Geen beoordeelbare rijen (niveau 2–4).")
    else:
        st.info("Kolommen `Niveau` of `levering` niet beschikbaar.")

    st.subheader("Entree-indicatoren (niveau 1)")
    chart_help("entree")
    entree_df = entree_indicatoren(df)
    if entree_df.is_empty():
        st.info("Geen niveau-1-inschrijvingen in de data.")
    else:
        st.metric(
            "Niveau-1-inschrijvingen (noemer)",
            f"{entree_totaal(df):,}",
            help="Aantal inschrijvingen op niveau 1 (Entree).",
        )
        st.dataframe(entree_df, use_container_width=True, hide_index=True)
        if "Categorie" in entree_df.columns:
            st.bar_chart(entree_df, x="Categorie", y="Aantal", color="Categorie")

    st.subheader("Diploma's per Leertraject")
    chart_help("diplomas_leertraject")
    if "Leertraject" in df.columns and "DIP_DatumResultaat" in df.columns:
        dip_lt = (
            df.with_columns(
                pl.when(pl.col("DIP_DatumResultaat").is_not_null())
                .then(pl.lit("Diploma behaald"))
                .otherwise(pl.lit("Geen diploma"))
                .alias("Diplomastatus")
            )
            .filter(pl.col("Leertraject").is_not_null() & (pl.col("Leertraject") != ""))
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
    chart_help("bekostigingstrechter")

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
    chart_help("bekostiging_levering")
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
    chart_help("na_1okt")
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
    chart_help("top10_opleidingen")
    if "Opleidingcode" in df.columns:
        top10 = (
            df.filter(
                pl.col("Opleidingcode").is_not_null() & (pl.col("Opleidingcode") != "")
            )
            .group_by("Opleidingcode")
            .agg(pl.len().alias("Inschrijvingen"))
            .sort("Inschrijvingen", descending=True)
            .head(10)
        )
        if not top10.is_empty():
            if "Opleiding_naam" in df.columns:
                naam_lookup = (
                    df.select("Opleidingcode", "Opleiding_naam")
                    .filter(pl.col("Opleiding_naam").is_not_null())
                    .unique(subset=["Opleidingcode"], keep="first")
                )
                top10 = top10.join(naam_lookup, on="Opleidingcode", how="left")
                top10 = top10.with_columns(
                    pl.coalesce("Opleiding_naam", "Opleidingcode").alias("Opleiding")
                )
            else:
                top10 = top10.with_columns(
                    ("CREBO " + pl.col("Opleidingcode")).alias("Opleiding")
                )
            top10 = top10.with_columns(
                pl.col("Opleiding").cast(pl.Enum(top10["Opleiding"].to_list()))
            )
            st.bar_chart(top10, x="Opleiding", y="Inschrijvingen")
        else:
            st.info("Geen data beschikbaar voor deze grafiek.")
    else:
        st.info("Kolom `Opleidingcode` niet beschikbaar.")

    st.subheader("BOL vs BBL per levering")
    chart_help("bol_bbl_levering")
    if "Leertraject" in df.columns and "levering" in df.columns:
        bol_bbl = (
            df.filter(
                pl.col("Leertraject").is_not_null() & (pl.col("Leertraject") != "")
            )
            .group_by(["levering", "Leertraject"])
            .agg(pl.len().alias("Inschrijvingen"))
            .sort(["levering", "Leertraject"])
        )
        if not bol_bbl.is_empty():
            st.bar_chart(bol_bbl, x="levering", y="Inschrijvingen", color="Leertraject")
        else:
            st.info("Geen data beschikbaar voor deze grafiek.")
    else:
        st.info("Kolommen `levering` of `Leertraject` niet beschikbaar.")

    st.subheader("BPV-coverage")
    chart_help("bpv_coverage")
    if "BPV_Aantal" in df.columns and "Leertraject" in df.columns:
        bpv = (
            df.filter(
                pl.col("Leertraject").is_not_null() & (pl.col("Leertraject") != "")
            )
            .with_columns(
                pl.when(pl.col("BPV_Aantal").is_not_null() & (pl.col("BPV_Aantal") > 0))
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
    chart_help("kzd")
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

    st.subheader("BPV-periodes — duur en omvang")
    chart_help("bpv_periodes")
    if (
        not fact_bpv_f.is_empty()
        and "DatumBegin" in fact_bpv_f.columns
        and "DatumEindWerkelijk" in fact_bpv_f.columns
    ):
        bpv_periodes = fact_bpv_f.filter(
            pl.col("DatumBegin").is_not_null()
            & pl.col("DatumEindWerkelijk").is_not_null()
        ).with_columns(
            (
                (pl.col("DatumEindWerkelijk") - pl.col("DatumBegin")).dt.total_days()
            ).alias("Duur (dagen)")
        )
        if not bpv_periodes.is_empty():
            bp1, bp2 = st.columns(2)
            bp1.metric(
                "Periodes met bekende duur",
                f"{bpv_periodes.height:,}",
            )
            bp2.metric(
                "Gem. duur (dagen)",
                f"{bpv_periodes['Duur (dagen)'].mean():.0f}",
            )
            if "Omvang" in bpv_periodes.columns:
                omvang_vals = bpv_periodes["Omvang"].drop_nulls()
                if not omvang_vals.is_empty():
                    gem_omvang = omvang_vals.cast(pl.Float64).mean()
                    st.metric("Gem. omvang", f"{gem_omvang:.1f}")
            bucket_order = ["< 30 dgn", "30–90 dgn", "90–180 dgn", "> 180 dgn"]
            bpv_buckets = (
                bpv_periodes.with_columns(
                    pl.when(pl.col("Duur (dagen)") < 30)
                    .then(pl.lit("< 30 dgn"))
                    .when(pl.col("Duur (dagen)") < 90)
                    .then(pl.lit("30–90 dgn"))
                    .when(pl.col("Duur (dagen)") < 180)
                    .then(pl.lit("90–180 dgn"))
                    .otherwise(pl.lit("> 180 dgn"))
                    .alias("Duur-klasse")
                )
                .group_by("Duur-klasse")
                .agg(pl.len().alias("Periodes"))
                .with_columns(pl.col("Duur-klasse").cast(pl.Enum(bucket_order)))
                .sort("Duur-klasse")
            )
            st.bar_chart(bpv_buckets, x="Duur-klasse", y="Periodes")
        else:
            st.info("Geen BPV-periodes met bekende begin- én einddatum.")
    else:
        st.info("fact_bpv niet beschikbaar of kolommen ontbreken.")

    st.subheader("Keuzedelen — resultaten per code")
    chart_help("kzd_detail")
    if not fact_kzd_f.is_empty() and "CodeKeuzedeel" in fact_kzd_f.columns:
        kzd_detail = (
            fact_kzd_f.filter(pl.col("CodeKeuzedeel").is_not_null())
            .with_columns(
                pl.when(
                    pl.col("Resultaat").is_not_null()
                    & pl.col("Resultaat").str.contains("(?i)behaald")
                )
                .then(pl.lit(1))
                .otherwise(pl.lit(0))
                .alias("_behaald")
            )
            .group_by("CodeKeuzedeel")
            .agg(
                pl.len().alias("Totaal"),
                pl.col("_behaald").sum().alias("Behaald"),
            )
            .with_columns(
                (pl.col("Behaald") / pl.col("Totaal") * 100)
                .round(1)
                .alias("Behaald (%)")
            )
            .sort("Totaal", descending=True)
            .head(15)
        )
        if not kzd_detail.is_empty():
            st.dataframe(kzd_detail, use_container_width=True, hide_index=True)
        else:
            st.info("Geen keuzedeel-data beschikbaar.")
    else:
        st.info("fact_kzd niet beschikbaar of kolom `CodeKeuzedeel` ontbreekt.")

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
            chart_help("instelling")
            st.dataframe(instelling_info, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Tab 4 — Studenten
# ---------------------------------------------------------------------------

with tab_studenten:
    st.subheader("Geslachtsverdeling per Leertraject")
    chart_help("geslacht_leertraject")
    if "Geslacht" in df.columns and "Leertraject" in df.columns:
        _GESLACHT = {"M": "Man", "V": "Vrouw", "O": "Onbekend"}
        geslacht = (
            df.filter(
                pl.col("Geslacht").is_not_null()
                & (pl.col("Geslacht") != "")
                & pl.col("Leertraject").is_not_null()
                & (pl.col("Leertraject") != "")
            )
            .with_columns(pl.col("Geslacht").replace(_GESLACHT).alias("Geslacht"))
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
        chart_help("herkomst")
        herkomst = (
            df.filter(pl.col("Nationaliteit1_migratieachtergrond").is_not_null())
            .group_by("Nationaliteit1_migratieachtergrond")
            .agg(pl.len().alias("Inschrijvingen"))
            .sort("Inschrijvingen", descending=True)
            .rename({"Nationaliteit1_migratieachtergrond": "Migratieachtergrond"})
        )
        if not herkomst.is_empty():
            herkomst = herkomst.with_columns(
                pl.col("Migratieachtergrond").cast(
                    pl.Enum(herkomst["Migratieachtergrond"].to_list())
                )
            )
            st.bar_chart(herkomst, x="Migratieachtergrond", y="Inschrijvingen")
        else:
            st.info("Geen herkomstdata beschikbaar.")

    if "Gemeente" in df.columns:
        st.subheader("Top 10 gemeenten")
        chart_help("top10_gemeenten")
        top10_gem = (
            df.filter(pl.col("Gemeente").is_not_null() & (pl.col("Gemeente") != ""))
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
        chart_help("top10_geboorteland")
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
    chart_help("uitstroomredenen")
    if "RedenUitschrijving" in df.columns:
        reden_code = pl.col("RedenUitschrijving")
        uitstroom = (
            df.with_columns(
                pl.when(reden_code.is_null() | (reden_code == ""))
                .then(pl.lit("Nog ingeschreven"))
                .when(reden_code.is_in(REDEN_LABELS))
                .then(reden_code.replace(REDEN_LABELS))
                .otherwise(pl.format("Overig (code: {})", reden_code))
                .alias("Reden")
            )
            .group_by("Reden")
            .agg(pl.len().alias("Aantal"))
            .sort("Aantal", descending=True)
        )
        if not uitstroom.is_empty():
            uitstroom = uitstroom.with_columns(
                pl.col("Reden").cast(pl.Enum(uitstroom["Reden"].to_list()))
            )
            st.bar_chart(uitstroom, x="Reden", y="Aantal")
        else:
            st.info("Geen uitstroomdata beschikbaar.")
    else:
        st.info("Kolom `RedenUitschrijving` niet beschikbaar.")

    st.subheader("Duur inschrijving (maanden)")
    chart_help("duur_inschrijving")
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

    st.subheader("GEO-examencijfers")
    chart_help("geo_eindcijfers")
    if (
        not fact_geo_f.is_empty()
        and "CodeGeneriekExamenonderdeel" in fact_geo_f.columns
        and "Eindcijfer" in fact_geo_f.columns
    ):
        geo_rows = []
        for (code,), grp in fact_geo_f.group_by("CodeGeneriekExamenonderdeel"):
            vals = grp["Eindcijfer"].drop_nulls()
            if vals.is_empty():
                continue
            _mean = vals.cast(pl.Float64).mean()
            geo_rows.append(
                {
                    "Onderdeel": _geo_labels.get(str(code), f"GEO {code}"),
                    "Gemiddeld eindcijfer": round(
                        _mean if isinstance(_mean, float) else 0.0, 1
                    ),
                    "N": len(vals),
                }
            )
        if geo_rows:
            geo_tbl = pl.DataFrame(geo_rows).sort("N", descending=True)
            st.dataframe(geo_tbl, use_container_width=True, hide_index=True)
        else:
            st.info("Geen GEO-eindcijfers gevuld in de data.")
    else:
        st.info("fact_geo niet beschikbaar of kolommen ontbreken.")

    st.subheader("GEO IE vs CE — vergelijking")
    chart_help("geo_ie_ce")
    if (
        not fact_geo_f.is_empty()
        and "CodeGeneriekExamenonderdeel" in fact_geo_f.columns
        and "CijferIE" in fact_geo_f.columns
        and "CijferCE" in fact_geo_f.columns
    ):
        _showed_any = False
        codes_in_data = (
            fact_geo_f.filter(
                pl.col("CijferIE").is_not_null() | pl.col("CijferCE").is_not_null()
            )["CodeGeneriekExamenonderdeel"]
            .cast(pl.Utf8)
            .unique()
            .sort()
            .to_list()
        )
        for geo_code in codes_in_data:
            grp = fact_geo_f.filter(
                pl.col("CodeGeneriekExamenonderdeel").cast(pl.Utf8) == geo_code
            )
            ie_vals = grp["CijferIE"].drop_nulls()
            ce_vals = grp["CijferCE"].drop_nulls()
            if ie_vals.is_empty() and ce_vals.is_empty():
                continue
            _showed_any = True
            label = _geo_labels.get(geo_code, f"GEO {geo_code}")
            st.markdown(f"**{label} (code {geo_code})**")
            gc1, gc2 = st.columns(2)
            if not ie_vals.is_empty():
                gc1.metric(
                    "Gem. IE",
                    f"{ie_vals.cast(pl.Float64).mean():.1f}",
                    help="Instituutsexamen",
                )
            if not ce_vals.is_empty():
                gc2.metric(
                    "Gem. CE",
                    f"{ce_vals.cast(pl.Float64).mean():.1f}",
                    help="Centraal examen",
                )
        if not _showed_any:
            st.info("Geen IE/CE-cijfers beschikbaar in de data.")
    else:
        st.info("fact_geo niet beschikbaar of IE/CE-kolommen ontbreken.")

    st.subheader("AMO-onderdelen")
    chart_help("amo")
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
