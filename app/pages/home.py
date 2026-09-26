"""Home — auto-ontdek en verwerk alle bestanden in één stap."""

import json
import sys
from collections import defaultdict
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils import prepared_dir, raw_dir, scenario, star_dir

from mbo_bekostiging_bestanden.pipeline import (
    detect_bestandstype,
    run_auto_pipeline,
    run_star,
)
from mbo_bekostiging_bestanden.quality import (
    controleer_koppelingen,
    controleer_niveau,
    controleer_sleuteluniciteit,
    slr_status_icoon,
)

# Star-kwaliteitsmeldingen op Home: sleutel in star_summary → toelichting.
_KWALITEITSMELDINGEN = {
    "wees_feiten": (
        "**Niet-gekoppelde feiten** — deze rijen horen bij geen enkele "
        "inschrijving (bijv. een levering van een andere instelling of "
        "periode) en tellen niet mee in analyses per inschrijving:"
    ),
    "dubbele_sleutels": (
        "**Dubbele periodesleutels** — dezelfde inschrijvingsperiode staat "
        "meer dan één keer in de bron; joins op `_inschrijving_periode_id` "
        "tellen deze rijen dubbel:"
    ),
    "niveau_onbekend": (
        "**Niveau onbekend** — voor deze opleidingscodes kent geen bron of "
        "referentietabel een niveau; ze tellen niet mee in JR/DR (niveau ≥ 2):"
    ),
}

# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------


def _scan_raw(raw: Path) -> dict[str, list[Path]]:
    """Alle herkenbare bestanden in raw, gegroepeerd op eerste submap."""
    groepen: dict[str, list[Path]] = defaultdict(list)
    for p in sorted(raw.rglob("*")):
        if p.is_file() and detect_bestandstype(p) is not None:
            rel = p.relative_to(raw)
            groep = rel.parts[0] if len(rel.parts) > 1 else "overig"
            groepen[groep].append(p)
    return dict(groepen)


def _prepared_subdir(raw_file: Path, raw: Path, prepared: Path) -> Path:
    """Consistente prepared-mapnaam op basis van de bestandsstam."""
    rel = raw_file.relative_to(raw)
    groep = rel.parts[0] if len(rel.parts) > 1 else "overig"
    return prepared / groep / raw_file.stem


def _reset_verwerking() -> None:
    """Wis de verwerkings-state zodat een nieuwe run schoon begint."""
    for sleutel in (
        "alles_verwerkt",
        "star_pad",
        "prepared_dirs",
        "star_summary",
        "fouten",
    ):
        st.session_state.pop(sleutel, None)


def _instelling_per_levering(star: dict) -> dict[str, str]:
    """Map elke levering naar 'Instellingsnaam (BRIN)'.

    Bron: elke star-tabel met zowel ``levering`` als ``BRIN`` — RO/GRONDSLAG
    via o.a. ``meta_leveringen``, TBGI (h16) via de bekostigingsfeiten die
    geen VLP-record leveren. BRIN wordt verrijkt met de naam uit
    ``dim_instelling`` (BRIN → Instelling_naam); zonder herkenbare naam valt
    het label terug op de losse BRIN.
    """
    dim = star.get("dim_instelling")
    naam_per_brin: dict[str, str] = {}
    if (
        dim is not None
        and not dim.is_empty()
        and {"BRIN", "Instelling_naam"} <= set(dim.columns)
    ):
        naam_per_brin = {
            rij["BRIN"]: rij["Instelling_naam"]
            for rij in dim.select(["BRIN", "Instelling_naam"]).iter_rows(named=True)
        }

    labels_per_levering: dict[str, set[str]] = defaultdict(set)
    for tbl in star.values():
        if tbl.is_empty() or "levering" not in tbl.columns or "BRIN" not in tbl.columns:
            continue
        koppels = tbl.select(["levering", "BRIN"]).drop_nulls().unique()
        for rij in koppels.iter_rows(named=True):
            brin = rij["BRIN"]
            naam = naam_per_brin.get(brin)
            labels_per_levering[rij["levering"]].add(
                f"{naam} ({brin})" if naam else brin
            )

    return {
        levering: ", ".join(sorted(labels))
        for levering, labels in labels_per_levering.items()
    }


def _toon_kwaliteitsmeldingen(toelichting: str, meldingen: list[str]) -> None:
    """Toon meldingen als één waarschuwing onder ``toelichting``; niets als leeg."""
    if not meldingen:
        return
    st.warning(toelichting + "\n\n" + "\n".join(f"- `{m}`" for m in meldingen))


def _load_quality_reports(prep_dirs: list[Path]) -> dict[str, dict]:
    """Lees alle quality.json bestanden uit prepared directories.

    Returns:
        {levering_naam: {slr_status, slr_details, warnings, errors}}
    """
    reports = {}
    for prep_dir in prep_dirs:
        quality_file = Path(prep_dir) / "quality.json"
        if quality_file.exists():
            try:
                with open(quality_file, encoding="utf-8") as f:
                    data = json.load(f)
                    reports[data.get("levering", prep_dir.name)] = data
            except (json.JSONDecodeError, OSError):
                pass
    return reports


def _show_quality_report(report: dict) -> None:
    """Toon kwaliteitsrapport in Streamlit UI."""
    status = report.get("slr_status")
    status_icoon = slr_status_icoon(status)
    schema = report.get("schema_type", "?")
    st.markdown(f"**{status_icoon} SLR-reconciliatie**: {schema}")

    slr_details = report.get("slr_details", {})
    if slr_details:
        detail_lines = []
        for rt, counts in sorted(slr_details.items()):
            exp = counts.get("verwacht", 0)
            got = counts.get("gelezen", 0)
            status = "✓" if exp == got else "✗"
            detail_lines.append(f"{status} {rt}: {got}/{exp}")
        st.caption(" | ".join(detail_lines))

    for warning in report.get("warnings", []):
        st.caption(f"⚠️ {warning}")
    for error in report.get("errors", []):
        st.caption(f"❌ {error}")


# ---------------------------------------------------------------------------
# Pagina
# ---------------------------------------------------------------------------

st.markdown(
    """<style>
.hero { background: linear-gradient(135deg,#1a56db 0%,#0e3fa8 100%);
        padding: 2rem 1.5rem; border-radius: 10px; color: white;
        margin-bottom: 1.5rem; text-align: center; }
.hero h1 { margin: 0 0 .4rem 0; font-size: 2rem; font-weight: 700; }
.hero p  { margin: 0; opacity: .88; font-size: 1rem; }
</style>
<div class="hero">
  <h1>MBO-bekostigingsbestanden</h1>
  <p>Zet ruwe DUO-bekostigingsbestanden automatisch om naar star schema-data.</p>
</div>""",
    unsafe_allow_html=True,
)

# ── Ontdek bestanden ─────────────────────────────────────────────────────────
raw = raw_dir()
groepen = _scan_raw(raw)

if not groepen:
    st.info(
        f"Geen herkenbare bestanden gevonden in `{raw}`.  \n"
        "Zet RO-, GRONDSLAG- of TBGI-bestanden in de invoermap."
    )
    st.stop()

totaal_bestanden = sum(len(v) for v in groepen.values())
st.write(
    f"**{totaal_bestanden} bestand(en) gevonden** in `{raw}` — {len(groepen)} map(pen):"
)

for periode in sorted(groepen):
    with st.expander(f"📁 {periode}  ({len(groepen[periode])} bestand(en))"):
        for f in groepen[periode]:
            bestandstype = detect_bestandstype(f) or "?"
            st.write(f"• `{f.name}` — *{bestandstype}*")

st.write("")

# ── Verwerk alles ────────────────────────────────────────────────────────────
done = st.session_state.get("alles_verwerkt", False)

if not done:
    if st.button("Verwerk alles", type="primary", width="stretch"):
        prepared = prepared_dir()

        # +1 voor de star-schema-stap aan het eind
        totaal_stappen = totaal_bestanden + 1
        voortgang = st.progress(0, text="Start…")
        status = st.empty()
        stap = 0
        fouten: list[str] = []
        alle_prep_dirs: list[Path] = []

        # Stap 1: verwerk ieder ruw bestand naar prepared
        for periode in sorted(groepen):
            for raw_file in groepen[periode]:
                target = _prepared_subdir(raw_file, raw, prepared)
                target.mkdir(parents=True, exist_ok=True)
                status.info(f"Verwerk `{raw_file.name}`…")
                try:
                    run_auto_pipeline(raw_file, target)
                    alle_prep_dirs.append(target)
                except Exception as exc:
                    fouten.append(f"{raw_file.name}: {exc}")
                stap += 1
                voortgang.progress(
                    stap / totaal_stappen, text=f"{stap}/{totaal_stappen}"
                )

        # Stap 2: alle prepared dirs stapelen en star schema bouwen
        status.info("Stapel alle leveringen en bouw star schema…")
        prep_dirs_met_data = [
            d for d in alle_prep_dirs if d.exists() and any(d.glob("*.parquet"))
        ]
        star_output = star_dir()
        star_output.mkdir(parents=True, exist_ok=True)

        try:
            star = run_star(
                prep_dirs_met_data,
                star_output,
                relative_to=prepared,
                scenario=scenario(),
            )
            star_summary = {
                "isp_rijen": star["fact_inschrijving"].height,
                "bekostiging_rijen": star["fact_bekostiging"].height,
                "bpv_rijen": star["fact_bpv"].height,
                "leveringen": sorted(
                    {
                        lev
                        for tbl in star.values()
                        if "levering" in tbl.columns and not tbl.is_empty()
                        for lev in tbl["levering"].drop_nulls().unique().to_list()
                    }
                ),
                "instelling_per_levering": _instelling_per_levering(star),
                "wees_feiten": controleer_koppelingen(star),
                "dubbele_sleutels": controleer_sleuteluniciteit(star),
                "niveau_onbekend": controleer_niveau(star),
            }
        except Exception as exc:
            melding = str(exc)
            if "ISP- of Inschrijving" in melding:
                melding = (
                    "Geen inschrijvingen (ISP) in de verwerkte bestanden. Het "
                    "star schema wordt rond inschrijvingen gebouwd en vereist "
                    "een RO-bestand (h15). De losse verwerkte tabellen van dit "
                    "bestand staan wél onder Resultaten."
                )
            fouten.append(f"Star schema: {melding}")
            star_summary = {}

        stap += 1
        voortgang.progress(1.0, text="Klaar")
        status.empty()
        st.session_state["alles_verwerkt"] = True
        st.session_state["star_pad"] = str(star_output)
        st.session_state["prepared_dirs"] = [str(d) for d in prep_dirs_met_data]
        st.session_state["star_summary"] = star_summary
        if fouten:
            st.session_state["fouten"] = fouten
        # Laad en sla quality reports op
        quality_reports = _load_quality_reports(prep_dirs_met_data)
        if quality_reports:
            st.session_state["quality_reports"] = quality_reports
        st.rerun()

if done:
    star_pad = st.session_state.get("star_pad", "")
    star_summary: dict = st.session_state.get("star_summary", {})
    fouten: list[str] = st.session_state.get("fouten", [])

    if fouten:
        with st.expander(f"⚠️ {len(fouten)} fout(en)"):
            for f in fouten:
                st.write(f"• {f}")

    if star_summary:
        st.success("Verwerkt — star schema klaar")
        for sleutel, toelichting in _KWALITEITSMELDINGEN.items():
            _toon_kwaliteitsmeldingen(toelichting, star_summary.get(sleutel, []))
        col1, col2, col3 = st.columns(3)
        col1.metric("Inschrijvingen (ISP)", star_summary.get("isp_rijen", "—"))
        col2.metric("Bekostiging detail", star_summary.get("bekostiging_rijen", "—"))
        col3.metric("BPV detail", star_summary.get("bpv_rijen", "—"))

        with st.expander("Leveringen opgenomen"):
            inst_per_lev = star_summary.get("instelling_per_levering", {})
            for lev in star_summary.get("leveringen", []):
                instelling = inst_per_lev.get(lev)
                if instelling:
                    st.write(f"• `{lev}` — {instelling}")
                else:
                    st.write(f"• `{lev}`")

        # Toon kwaliteitrapporten indien beschikbaar
        quality_reports = st.session_state.get("quality_reports", {})
        if quality_reports:
            with st.expander("📊 Datakwaliteit (SLR-reconciliatie)"):
                for levering, report in sorted(quality_reports.items()):
                    with st.container(border=True):
                        st.subheader(levering, divider="gray")
                        _show_quality_report(report)

        st.write("")
        col_bekijk, col_opnieuw = st.columns(2)
        with col_bekijk:
            if st.button("Bekijk resultaten →", type="primary", width="stretch"):
                st.session_state["resultaten_dir"] = star_pad
                st.switch_page("pages/resultaten.py")
        with col_opnieuw:
            if st.button("Opnieuw verwerken", width="stretch"):
                _reset_verwerking()
                st.rerun()
    elif st.session_state.get("prepared_dirs"):
        # Geen star schema, maar de losse tabellen zijn wel verwerkt.
        st.info(
            "Geen star schema gebouwd, maar de bestanden zijn wél verwerkt. "
            "Bekijk de losse tabellen per bestand onder Resultaten."
        )
        col_bekijk, col_opnieuw = st.columns(2)
        with col_bekijk:
            if st.button(
                "Bekijk verwerkte tabellen →",
                type="primary",
                width="stretch",
            ):
                st.session_state["resultaten_dir"] = star_pad
                st.switch_page("pages/resultaten.py")
        with col_opnieuw:
            if st.button("Opnieuw verwerken", width="stretch"):
                _reset_verwerking()
                st.rerun()

st.divider()
st.caption(
    "© CEDA · Npuls — [GitHub](https://github.com/cedanl/mbo-bekostiging-bestanden)"
)
