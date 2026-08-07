"""Dashboard — visueel overzicht van de verwerkte bekostigingsdata."""

import sys
import tomllib
from pathlib import Path

import altair as alt
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

_BPV_DUUR_GRENZEN = (30, 90, 180)  # dagen — grenzen voor de duurklasse-buckets
_KZD_TOP_N = 15  # maximaal aantal keuzedelen in de detailtabel
_KZD_BEHAALD_RE = "(?i)behaald"  # patroon om behaald-status te herkennen
_KZD_LAGE_GRENS = 50  # drempel waaronder slagingskans als laag wordt beschouwd (%)
_SBB_BEROEP_TOP_N = 20  # maximaal aantal beroepen in de S-BB-grafiek
_GEO_SLAAGGRENS = 5.5  # minimaal eindcijfer om als geslaagd te tellen


def _resolve_dir() -> Path | None:
    for key in ("resultaten_dir", "star_pad"):
        val = st.session_state.get(key)
        if val:
            p = Path(val)
            if (p / "datamodel" / "fact_inschrijving.parquet").exists():
                return p
    fallback = output_dir() / "star"
    if (fallback / "datamodel" / "fact_inschrijving.parquet").exists():
        return fallback
    return None


@st.cache_resource(show_spinner=False)
def _lees_parquet(pad: str, mtime: float) -> pl.DataFrame:
    """Lees een parquet-bestand en cache op pad + wijzigingsdatum."""
    return pl.read_parquet(pad)


def _parquet_max_mtime(data_dir: Path) -> float:
    dm = data_dir / "datamodel"
    if not dm.exists():
        return 0.0
    mtimes = [p.stat().st_mtime for p in dm.glob("*.parquet")]
    return max(mtimes, default=0.0)


@st.cache_data(show_spinner=False)
def _lees_star_schema(
    data_dir: Path,
    max_mtime: float,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Laad het star schema en lever (df, fact_geo, fact_bpv, fact_kzd, fact_bek).

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

    fact_bek = _laad("fact_bekostiging")
    if not fact_bek.is_empty() and not dim_opleiding.is_empty() and (
        "Opleidingcode" in fact_bek.columns
    ):
        fact_bek = fact_bek.join(dim_opleiding, on="Opleidingcode", how="left")
        fact_bek = fact_bek.drop([c for c in fact_bek.columns if c.endswith("_right")])
    if not fact_bek.is_empty() and not dim_instelling.is_empty() and (
        "BRIN" in fact_bek.columns
    ):
        fact_bek = fact_bek.join(dim_instelling, on="BRIN", how="left")
        fact_bek = fact_bek.drop([c for c in fact_bek.columns if c.endswith("_right")])

    # Leid Studiejaar af uit Teldatum zodat TBGI-data jaargebonden filterbaar is.
    if "Teldatum" in fact_bek.columns:
        teldatum = pl.col("Teldatum").cast(pl.Date, strict=False)
        fact_bek = fact_bek.with_columns(
            pl.when(teldatum.dt.month() >= 8)
            .then(teldatum.dt.year())
            .otherwise(teldatum.dt.year() - 1)
            .alias("Studiejaar")
        )

    return (
        df,
        _laad("fact_geo"),
        _laad("fact_bpv"),
        _laad("fact_kzd"),
        fact_bek,
    )


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
        "demo-data in `data/03-output/demo/obt/datamodel/`."
    )
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()

df, fact_geo, fact_bpv, fact_kzd, fact_bekostiging = _lees_star_schema(
    data_dir, _parquet_max_mtime(data_dir)
)
df = _sidebar_studiejaar_filter(df)

# Sleutels voor join op detail-feiten, gefilterd op geselecteerde studiejaren.
_FK = ["levering", "_persoon_id", "Inschrijvingvolgnummer"]
_filter_keys = df.select([k for k in _FK if k in df.columns])


def _filter_fact(f: pl.DataFrame) -> pl.DataFrame:
    """Filter een detail-fact op de gefilterde inschrijvingen via FK-join."""
    join_on = [k for k in _FK if k in f.columns]
    if f.is_empty():
        return f
    if not join_on:
        return f.clear()
    # Lege _filter_keys (geen studiejaar geselecteerd) → lege fact teruggeven.
    keys = _filter_keys.select(join_on).unique()
    if keys.is_empty():
        return f.clear()
    return f.join(keys, on=join_on, how="inner")


def _hbar(df: pl.DataFrame, label: str, value: str) -> None:
    """Horizontaal staafdiagram gesorteerd op waarde (aflopend = meest boven)."""
    chart = (
        alt.Chart(df.select([label, value]))
        .mark_bar()
        .encode(
            y=alt.Y(f"{label}:N", sort="-x", title=label),
            x=alt.X(f"{value}:Q", title=value),
        )
    )
    st.altair_chart(chart, use_container_width=True)


fact_geo_f = _filter_fact(fact_geo)
fact_bpv_f = _filter_fact(fact_bpv)
fact_kzd_f = _filter_fact(fact_kzd)
# TBGI-leveringen overlappen niet met ISP; filter op Studiejaar afgeleid uit Teldatum.
if "Studiejaar" in fact_bekostiging.columns and not df.is_empty():
    _bek_jaren = df["Studiejaar"].drop_nulls().unique().to_list()
    fact_bek_f = (
        fact_bekostiging.filter(pl.col("Studiejaar").is_in(_bek_jaren))
        if _bek_jaren
        else fact_bekostiging.clear()
    )
else:
    fact_bek_f = fact_bekostiging.clear() if df.is_empty() else fact_bekostiging

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
    help="Aantal rijen in fact_inschrijving na toepassing van de "
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

(
    tab_rendementen,
    tab_bekostiging,
    tab_opleidingen,
    tab_studenten,
    tab_examens,
    tab_opl_structuur,
) = st.tabs(
    ["Rendementen", "Bekostiging", "Opleidingen", "Studenten", "Examens",
     "Opleidingsstructuur"]
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

                st.bar_chart(jr, x="Niveau", y="JR (%)", color="levering")
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

    st.subheader("Diplomaresultaat (DR) — indicatief, per niveau")
    chart_help("dr_indicatief")
    if "_dr_noemer" in df.columns and "_dr_teller" in df.columns:
        dr_pop = populatie_regele_filter(df, min_niveau=2)
        dr_agg = (
            dr_pop.filter(pl.col("_dr_noemer").fill_null(False))
            .group_by(["levering", "Niveau"])
            .agg(
                pl.col("_dr_noemer").sum().alias("Uitstromers (N)"),
                pl.col("_dr_teller").sum().alias("Gediplomeerd (N)"),
            )
            .with_columns(
                (pl.col("Gediplomeerd (N)") / pl.col("Uitstromers (N)") * 100)
                .round(1)
                .alias("DR (%)")
            )
            .sort(["Niveau", "levering"])
        )
        if dr_agg.is_empty():
            st.info(
                "Geen uitstromers in de populatie (mogelijk geen meerdere "
                "studiejaren beschikbaar)."
            )
        else:
            dr_agg = (
                dr_agg.with_columns(
                    pl.col("Niveau").str.extract(r"(\d+)$").cast(pl.Int32).alias("_niv")
                )
                .with_columns(
                    pl.struct(["Niveau", "_niv"])
                    .map_elements(
                        lambda r: norm_voor("dr", r["_niv"], "voldoende"),
                        return_dtype=pl.Int64,
                    )
                    .alias("Norm voldoende (%)"),
                    pl.struct(["Niveau", "_niv"])
                    .map_elements(
                        lambda r: norm_voor("dr", r["_niv"], "hoog"),
                        return_dtype=pl.Int64,
                    )
                    .alias("Norm hoog (%)"),
                )
                .drop("_niv")
                .with_columns(
                    (pl.col("DR (%)") >= pl.col("Norm voldoende (%)")).alias(
                        "Voldoet aan voldoende-norm"
                    )
                )
            )
            st.dataframe(dr_agg, use_container_width=True, hide_index=True)
            st.bar_chart(dr_agg, x="Niveau", y="DR (%)", color="levering")
            st.caption(
                "Normen voor voldoende (DR): niveau 2 = "
                f"{norm_voor('dr', 2, 'voldoende')}%, niveau 3/4 = "
                f"{norm_voor('dr', 3, 'voldoende')}%. Voor hoog: niveau 2 = "
                f"{norm_voor('dr', 2, 'hoog')}%, niveau 3/4 = "
                f"{norm_voor('dr', 3, 'hoog')}%. "
                "Uitstromer = actief op 1-10-t én niet ingeschreven bij "
                "zelfde BRIN in t+1."
            )
    else:
        st.info("Kolommen `_dr_noemer` en `_dr_teller` niet beschikbaar.")

    st.subheader("Berekend oordeel Studiesucces (indicatief)")
    chart_help("berekend_oordeel")
    _heeft_jr = all(c in df.columns for c in ("_jr_noemer", "_jr_teller"))
    _heeft_dr = all(c in df.columns for c in ("_dr_noemer", "_dr_teller"))
    if "Niveau" in jr_pop.columns and (_heeft_jr or _heeft_dr):
        oordeel_basis = jr_pop.group_by("Niveau").agg(
            *([
                pl.col("_jr_noemer").fill_null(False).sum().alias("_jr_n"),
                pl.col("_jr_teller").fill_null(False).sum().alias("_jr_t"),
            ] if _heeft_jr else [
                pl.lit(0).alias("_jr_n"),
                pl.lit(0).alias("_jr_t"),
            ]),
            *([
                pl.col("_dr_noemer").fill_null(False).sum().alias("_dr_n"),
                pl.col("_dr_teller").fill_null(False).sum().alias("_dr_t"),
            ] if _heeft_dr else [
                pl.lit(0).alias("_dr_n"),
                pl.lit(0).alias("_dr_t"),
            ]),
        )
        rows = []
        for r in oordeel_basis.to_dicts():
            niv_str = r["Niveau"]
            niv = int(niv_str.split("-")[-1]) if "-" in niv_str else None
            if niv not in (2, 3, 4):
                continue
            jr_ind = (
                {"waarde": r["_jr_t"] / r["_jr_n"] * 100, "noemer": r["_jr_n"]}
                if _heeft_jr and r["_jr_n"] > 0
                else None
            )
            dr_ind = (
                {"waarde": r["_dr_t"] / r["_dr_n"] * 100, "noemer": r["_dr_n"]}
                if _heeft_dr and r["_dr_n"] > 0
                else None
            )
            oordeel, _, _ = bereken_oordeel(jr_ind, dr_ind, None, niveau=niv)
            row: dict = {"Niveau": niv_str, "Berekend oordeel": oordeel}
            if jr_ind:
                row["JR (%)"] = round(jr_ind["waarde"], 1)
                row["Norm vold. JR (%)"] = norm_voor("jr", niv, "voldoende")
            if dr_ind:
                row["DR (%)"] = round(dr_ind["waarde"], 1)
                row["Norm vold. DR (%)"] = norm_voor("dr", niv, "voldoende")
            rows.append(row)
        if rows:
            st.dataframe(pl.DataFrame(rows), use_container_width=True, hide_index=True)
            st.warning(
                "SR (startersresultaat) is niet beschikbaar — dit vereist zes "
                "jaar inschrijvingshistorie die buiten de eigen leveringen valt. "
                "Het oordeel is op JR + DR gebaseerd en daarmee indicatief. "
                "Bij één ontbrekende "
                "indicator is een oordeel alleen mogelijk als de twee aanwezige "
                "indicatoren dezelfde richting uitwijzen (§3.5)."
            )
        else:
            st.info("Geen beoordeelbare rijen (niveau 2–4).")
    else:
        st.info("Kolommen voor JR/DR of `Niveau` niet beschikbaar.")

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
            st.bar_chart(entree_df, x="Categorie", y="Aandeel (%)")

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

    st.subheader("Bekostigingsgrondslagen (TBGI)")
    chart_help("bekostigingsgrondslagen")
    if not fact_bek_f.is_empty() and "Bekostigingsstatus" in fact_bek_f.columns:
        bek_status = (
            fact_bek_f.filter(pl.col("Bekostigingsstatus").is_not_null())
            .group_by("Bekostigingsstatus")
            .agg(pl.len().alias("Inschrijvingen"))
        )
        if not bek_status.is_empty():
            _hbar(bek_status, "Bekostigingsstatus", "Inschrijvingen")
        if "BijdrageInschrijvingAanDeelnemerswaarde" in fact_bek_f.columns:
            totaal_dw = fact_bek_f["BijdrageInschrijvingAanDeelnemerswaarde"].sum()
            st.metric(
                "Totale deelnemerswaarde (som)",
                f"{totaal_dw:,.2f}" if totaal_dw is not None else "—",
                help="Som van `BijdrageInschrijvingAanDeelnemerswaarde` over alle "
                "TBGI-rijen in de selectie.",
            )
    else:
        st.info(
            "fact_bekostiging niet beschikbaar of kolom `Bekostigingsstatus` ontbreekt."
        )

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
            _hbar(top10, "Opleiding", "Inschrijvingen")
        else:
            st.info("Geen data beschikbaar voor deze grafiek.")
    else:
        st.info("Kolom `Opleidingcode` niet beschikbaar.")

    st.subheader("Inschrijvingen per domein")
    chart_help("inschrijvingen_domein")
    if "Opleiding_domein" in df.columns:
        domein = (
            df.filter(
                pl.col("Opleiding_domein").is_not_null()
                & (pl.col("Opleiding_domein") != "")
            )
            .group_by("Opleiding_domein")
            .agg(pl.len().alias("Inschrijvingen"))
            .rename({"Opleiding_domein": "Domein"})
        )
        if not domein.is_empty():
            _hbar(domein, "Domein", "Inschrijvingen")
        else:
            st.info("Geen domeindata beschikbaar.")
    else:
        st.info("Kolom `Opleiding_domein` niet beschikbaar.")

    st.subheader("Inschrijvingen per sectorkamer")
    chart_help("inschrijvingen_sectorkamer")
    if "Opleiding_sectorkamer" in df.columns:
        sectorkamer = (
            df.filter(
                pl.col("Opleiding_sectorkamer").is_not_null()
                & (pl.col("Opleiding_sectorkamer") != "")
            )
            .group_by("Opleiding_sectorkamer")
            .agg(pl.len().alias("Inschrijvingen"))
            .rename({"Opleiding_sectorkamer": "Sectorkamer"})
        )
        if not sectorkamer.is_empty():
            _hbar(sectorkamer, "Sectorkamer", "Inschrijvingen")
        else:
            st.info("Geen sectorkamerdata beschikbaar.")
    else:
        st.info("Kolom `Opleiding_sectorkamer` niet beschikbaar.")

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
            _d1, _d2, _d3 = _BPV_DUUR_GRENZEN
            bucket_order = [
                f"< {_d1} dgn",
                f"{_d1}–{_d2} dgn",
                f"{_d2}–{_d3} dgn",
                f"> {_d3} dgn",
            ]
            bpv_buckets = (
                bpv_periodes.with_columns(
                    pl.when(pl.col("Duur (dagen)") < _d1)
                    .then(pl.lit(f"< {_d1} dgn"))
                    .when(pl.col("Duur (dagen)") < _d2)
                    .then(pl.lit(f"{_d1}–{_d2} dgn"))
                    .when(pl.col("Duur (dagen)") < _d3)
                    .then(pl.lit(f"{_d2}–{_d3} dgn"))
                    .otherwise(pl.lit(f"> {_d3} dgn"))
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
                    & pl.col("Resultaat").str.contains(_KZD_BEHAALD_RE)
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
            .head(_KZD_TOP_N)
        )
        if not kzd_detail.is_empty():
            st.dataframe(kzd_detail, use_container_width=True, hide_index=True)
            lage_kzd = kzd_detail.filter(pl.col("Behaald (%)") < _KZD_LAGE_GRENS)
            if not lage_kzd.is_empty():
                st.warning(
                    f"{lage_kzd.height} keuzedeel(en) in de top-{_KZD_TOP_N} "
                    f"met minder dan {_KZD_LAGE_GRENS}% behaald:"
                )
                st.dataframe(lage_kzd, use_container_width=True, hide_index=True)
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
            _hbar(herkomst, "Migratieachtergrond", "Inschrijvingen")
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
            _hbar(uitstroom, "Reden", "Aantal")
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

    # Bereken GEO-stats éénmalig (cijfergemiddelde + slagingspercentage).
    _geo_heeft_data = (
        not fact_geo_f.is_empty()
        and "CodeGeneriekExamenonderdeel" in fact_geo_f.columns
        and "Eindcijfer" in fact_geo_f.columns
    )
    _geo_stats: list[dict] = []
    if _geo_heeft_data:
        for (code,), grp in fact_geo_f.group_by("CodeGeneriekExamenonderdeel"):
            vals = grp["Eindcijfer"].drop_nulls().cast(pl.Float64)
            if vals.is_empty():
                continue
            n = len(vals)
            _mean = vals.mean()
            _geo_stats.append({
                "Onderdeel": _geo_labels.get(str(code), f"GEO {code}"),
                "Gemiddeld eindcijfer": round(
                    _mean if isinstance(_mean, float) else 0.0, 1
                ),
                "Geslaagd (%)": round(
                    int((vals >= _GEO_SLAAGGRENS).sum()) / n * 100, 1
                ),
                "N": n,
            })

    st.subheader("GEO-examencijfers")
    chart_help("geo_eindcijfers")
    if _geo_stats:
        geo_tbl = pl.DataFrame(_geo_stats).sort("N", descending=True)
        st.dataframe(
            geo_tbl.select(["Onderdeel", "Gemiddeld eindcijfer", "N"]),
            use_container_width=True,
            hide_index=True,
        )
    elif _geo_heeft_data:
        st.info("Geen GEO-eindcijfers gevuld in de data.")
    else:
        st.info("fact_geo niet beschikbaar of kolommen ontbreken.")

    st.subheader("GEO slagingspercentage (eindcijfer ≥ 5,5)")
    chart_help("geo_slagingspercentage")
    if _geo_stats:
        slag_tbl = pl.DataFrame(_geo_stats)
        _hbar(slag_tbl, "Onderdeel", "Geslaagd (%)")
    elif _geo_heeft_data:
        st.info("Geen GEO-eindcijfers beschikbaar voor slagingspercentage.")
    else:
        st.info("fact_geo niet beschikbaar of kolom `Eindcijfer` ontbreekt.")

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

# ---------------------------------------------------------------------------
# Tab 6 — Opleidingsstructuur
# ---------------------------------------------------------------------------

with tab_opl_structuur:
    st.markdown(
        "Overzicht van de CREBO-structuur: **kwalificatiedossiers (23xxx)**, "
        "**kwalificaties/beroepen (25xxx/27xxx)** via de S-BB koppeltabel, "
        "en **hercodering** bij dossierherziening. "
        "Klik op ℹ️ bij elke grafiek voor de exacte definitie."
    )

    # ── Dossiers (23xxx) ────────────────────────────────────────────────────

    st.subheader("Inschrijvingen per kwalificatiedossier (23xxx)")
    chart_help("dossier_inschrijvingen")
    if "Opleiding_dossiercode" in df.columns and "Opleiding_dossier" in df.columns:
        dossier = (
            df.filter(pl.col("Opleiding_dossiercode").is_not_null())
            .with_columns(
                pl.format(
                    "{} — {}", "Opleiding_dossiercode", "Opleiding_dossier"
                ).alias("Dossier")
            )
            .group_by("Dossier")
            .agg(pl.len().alias("Inschrijvingen"))
            .sort("Inschrijvingen", descending=True)
        )
        if not dossier.is_empty():
            _hbar(dossier, "Dossier", "Inschrijvingen")
        else:
            st.info("Geen dossierdata beschikbaar.")
    else:
        st.info(
            "Kolommen `Opleiding_dossiercode` of `Opleiding_dossier` niet beschikbaar."
        )

    # ── S-BB beroepen (25xxx / 27xxx) ───────────────────────────────────────

    st.subheader("Inschrijvingen per beroep (S-BB koppeltabel)")
    chart_help("sbb_beroep_inschrijvingen")
    if "Opleiding_beroep" in df.columns:
        beroep = (
            df.filter(
                pl.col("Opleiding_beroep").is_not_null()
                & (pl.col("Opleiding_beroep") != "")
            )
            .group_by("Opleiding_beroep")
            .agg(pl.len().alias("Inschrijvingen"))
            .sort("Inschrijvingen", descending=True)
            .head(_SBB_BEROEP_TOP_N)
            .rename({"Opleiding_beroep": "Beroep"})
        )
        if not beroep.is_empty():
            _hbar(beroep, "Beroep", "Inschrijvingen")
        else:
            st.info("Geen beroepsdata beschikbaar (S-BB koppeltabel).")
    else:
        st.info("Kolom `Opleiding_beroep` niet beschikbaar.")

    st.subheader("Looptijd van opleidingen (S-BB)")
    chart_help("sbb_looptijd")
    if (
        "Opleiding_laatste_schooljaar" in df.columns
        and "Opleiding_eerste_schooljaar" in df.columns
    ):
        looptijd_cols = [
            "Opleidingcode",
            "Opleiding_eerste_schooljaar",
            "Opleiding_laatste_schooljaar",
        ]
        if "Opleiding_naam" in df.columns:
            looptijd_cols.insert(1, "Opleiding_naam")
        looptijd = (
            df.filter(pl.col("Opleiding_laatste_schooljaar").is_not_null())
            .select([c for c in looptijd_cols if c in df.columns])
            .unique(subset=["Opleidingcode"])
            .sort("Opleiding_laatste_schooljaar")
        )
        if not looptijd.is_empty():
            # Distributiebalk: hoeveel inschrijvingen per "laatste schooljaar"
            dist = (
                df.filter(pl.col("Opleiding_laatste_schooljaar").is_not_null())
                .group_by("Opleiding_laatste_schooljaar")
                .agg(pl.len().alias("Inschrijvingen"))
                .sort("Opleiding_laatste_schooljaar")
                .rename({"Opleiding_laatste_schooljaar": "Laatste schooljaar"})
            )
            st.bar_chart(dist, x="Laatste schooljaar", y="Inschrijvingen")
            with st.expander("Detailtabel opleidingen met looptijd"):
                st.dataframe(looptijd, use_container_width=True, hide_index=True)
        else:
            st.info("Geen looptijddata beschikbaar.")
    else:
        st.info(
            "Kolommen `Opleiding_eerste_schooljaar` of `Opleiding_laatste_schooljaar` "
            "niet beschikbaar."
        )

    # ── Hercodering 25xxx → 27xxx ────────────────────────────────────────────

    st.subheader("Hercodering: 25xxx → 27xxx (via S-BB opvolger)")
    chart_help("hercodering_25_27")
    if "Opleiding_opvolger" in df.columns and "Opleidingcode" in df.columns:
        met_opvolger_dim = (
            df.filter(pl.col("Opleiding_opvolger").is_not_null())
            .select(
                [
                    c
                    for c in [
                        "Opleidingcode",
                        "Opleiding_naam",
                        "Opleiding_opvolger",
                        "Opleiding_dossier",
                    ]
                    if c in df.columns
                ]
            )
            .unique(subset=["Opleidingcode"])
            .sort("Opleidingcode")
        )
        inschrijvingen_oud = (
            df.filter(pl.col("Opleiding_opvolger").is_not_null()).height
        )
        hc1, hc2 = st.columns(2)
        hc1.metric(
            "Unieke codes mét opvolger",
            met_opvolger_dim.height,
            help="Aantal unieke CREBO-codes (25xxx) waarvoor de S-BB koppeltabel "
            "een opvolger (27xxx) vermeldt.",
        )
        hc2.metric(
            "Inschrijvingen op 'oude' code",
            f"{inschrijvingen_oud:,}",
            help="Inschrijvingen waarbij de Opleidingcode een opvolger heeft; "
            "voor longitudinale analyses samenvoegen met de 27xxx-opvolger.",
        )
        if not met_opvolger_dim.is_empty():
            st.dataframe(met_opvolger_dim, use_container_width=True, hide_index=True)
        else:
            st.info("Geen opleidingen met opvolger in de geselecteerde data.")
    else:
        st.info("Kolom `Opleiding_opvolger` niet beschikbaar.")

st.caption(
    "© CEDA · Npuls — [GitHub](https://github.com/cedanl/mbo-bekostiging-bestanden)"
)
