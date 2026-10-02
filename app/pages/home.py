"""Home — ontdek de bestanden en maak de twee producten, elk in een eigen stap.

1. Brondata: ruw → per levering en recordtype (``mbo verwerk``).
2. Analysemodel: brondata → star schema (``mbo star``), uit de brondata op
   schijf, zodat de dure ster los opnieuw te bouwen is (#264).
"""

import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _invoer import maak_werkmap, synchroniseer_selectie
from _utils import (
    persoonsverwerking,
    prepared_dir,
    raw_dir,
    scenario,
    star_dir,
    vind_star_dir,
)

from mbo_bekostiging_bestanden.identiteit import (
    WAARSCHUWING_IDENTIFIERS_BEHOUDEN,
    Persoonsverwerking,
)
from mbo_bekostiging_bestanden.pipeline import (
    detect_bestandstype,
    run_auto_pipeline,
    run_star,
)
from mbo_bekostiging_bestanden.quality import (
    controleer_koppelingen,
    controleer_niveau,
    controleer_sleuteluniciteit,
    lees_onbekende_xml_elementen,
    lees_status,
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
        "**Dubbele sleutels** — een rij staat meer dan één keer op de sleutel "
        "van haar feit (inschrijvingsperiode, schooljaar of de business key "
        "van een detailfeit); joins en tellingen tellen deze rijen dubbel:"
    ),
    "niveau_onbekend": (
        "**Niveau onbekend** — voor deze opleidingscodes kent geen bron of "
        "referentietabel een niveau; ze tellen niet mee in JR/DR (niveau ≥ 2):"
    ),
    "onbekende_xml_elementen": (
        "**Onbekende XML-elementen** — DUO levert elementen die het schema niet "
        "kent. Ze zijn doorgelaten maar zitten niet in de analyse; controleer of "
        "er een nieuw veld bij is gekomen:"
    ),
}

_VERWERKING_LABELS = {
    Persoonsverwerking.PSEUDONIMISEREN: "Pseudonimiseren (aanbevolen)",
    Persoonsverwerking.IDENTIFIERS_BEHOUDEN: "Identifiers behouden",
}
_VERWERKING_TOELICHTING = {
    Persoonsverwerking.PSEUDONIMISEREN: (
        "Persoonsidentifiers worden vervangen door een pseudoniem. Vereist een "
        "salt (`MBO_PSEUDONIMISERING_SALT`)."
    ),
    Persoonsverwerking.IDENTIFIERS_BEHOUDEN: (
        "Persoonsidentifiers blijven beschikbaar voor interne koppeling. Gebruik "
        "deze optie alleen in een vertrouwde omgeving; er is geen salt nodig."
    ),
}
_BRON_MAP = "Vaste invoermap"
_BRON_SELECTIE = "Bestanden selecteren"
_SESSIE_WERKMAP = "selectie_werkmap"

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


def _kies_invoer() -> tuple[Path, str]:
    """Invoer uit de vaste map of uit gekozen bestanden: ``(map, omschrijving)``.

    Gekozen bestanden gaan naar een tijdelijke werkmap (niet naar de
    configureerbare invoermap, die demo-bronbestanden in git kan bevatten).
    """
    bron = st.radio(
        "Invoer",
        [_BRON_MAP, _BRON_SELECTIE],
        horizontal=True,
        help="Lees alle bestanden uit de vaste invoermap, of kies zelf bestanden.",
    )
    if bron == _BRON_MAP:
        raw = raw_dir()
        return raw, f"`{raw}`"

    gekozen = st.file_uploader(
        "Selecteer RO-, GRONDSLAG- of TBGI-bestanden",
        accept_multiple_files=True,
        help="De bestanden blijven lokaal en worden alleen in een tijdelijke "
        "werkmap gezet om te verwerken.",
    )
    werkmap = st.session_state.setdefault(_SESSIE_WERKMAP, str(maak_werkmap()))
    synchroniseer_selectie(((f.name, f.getvalue()) for f in gekozen), Path(werkmap))
    return Path(werkmap), "de geselecteerde bestanden"


def _prepared_subdir(raw_file: Path, raw: Path, prepared: Path) -> Path:
    """Consistente prepared-mapnaam op basis van de bestandsstam."""
    rel = raw_file.relative_to(raw)
    groep = rel.parts[0] if len(rel.parts) > 1 else "overig"
    return prepared / groep / raw_file.stem


def _prepared_dirs_op_schijf(
    groepen: dict[str, list[Path]], raw: Path, prepared: Path
) -> list[Path]:
    """Brondata-mappen van de huidige ruwe bestanden die al verwerkt zijn.

    Alleen mappen van bestanden die nu in de invoermap staan: een verwijderd
    bestand mag niet via achtergebleven brondata in de ster belanden.
    """
    kandidaten = (
        _prepared_subdir(raw_file, raw, prepared)
        for bestanden in groepen.values()
        for raw_file in bestanden
    )
    return [d for d in kandidaten if any(d.glob("*.parquet"))]


def _kies_persoonsverwerking() -> Persoonsverwerking:
    """Keuze vóór de verwerking; pseudonimiseren tenzij de gebruiker anders kiest."""
    opties = list(Persoonsverwerking)
    labels = [_VERWERKING_LABELS[o] for o in opties]
    gekozen = st.radio(
        "Hoe moeten persoonsidentifiers worden verwerkt?",
        labels,
        index=opties.index(persoonsverwerking()),
        captions=[_VERWERKING_TOELICHTING[o] for o in opties],
    )
    keuze = opties[labels.index(gekozen)]
    if keuze == Persoonsverwerking.IDENTIFIERS_BEHOUDEN:
        st.warning(WAARSCHUWING_IDENTIFIERS_BEHOUDEN, icon="⚠️")
    return keuze


def _verwerk_bestanden(
    groepen: dict[str, list[Path]],
    raw: Path,
    prepared: Path,
    verwerking: Persoonsverwerking,
) -> list[str]:
    """Stap 1: elk ruw bestand naar brondata; geeft de fouten terug."""
    bestanden = [f for periode in sorted(groepen) for f in groepen[periode]]
    voortgang = st.progress(0, text="Start…")
    fouten: list[str] = []
    for stap, raw_file in enumerate(bestanden, start=1):
        voortgang.progress(
            (stap - 1) / len(bestanden), text=f"Verwerk `{raw_file.name}`…"
        )
        target = _prepared_subdir(raw_file, raw, prepared)
        target.mkdir(parents=True, exist_ok=True)
        try:
            run_auto_pipeline(raw_file, target, persoonsverwerking=verwerking)
        except Exception as exc:
            # Geen verouderde brondata of diagnose: die zou stil in de ster
            # belanden (de pipeline zelf laat bij een fout de vorige versie staan).
            shutil.rmtree(target)
            fouten.append(f"{raw_file.name}: {exc}")
    voortgang.empty()
    return fouten


def _bouw_analysemodel(prep_dirs: list[Path], prepared: Path) -> tuple[dict, list[str]]:
    """Stap 2: stapel de brondata en bouw de ster; ``(samenvatting, fouten)``."""
    star_output = star_dir()
    star_output.mkdir(parents=True, exist_ok=True)
    try:
        with st.spinner("Stapel alle leveringen en bouw het analysemodel…"):
            star = run_star(
                prep_dirs,
                star_output,
                relative_to=prepared,
                scenario=scenario(),
                fail_on_errors=False,
            )
    except Exception as exc:
        melding = str(exc)
        if "ISP- of Inschrijving" in melding:
            melding = (
                "Geen inschrijvingen (ISP) in de verwerkte bestanden. Het "
                "star schema wordt rond inschrijvingen gebouwd en vereist "
                "een RO-bestand (h15). De brondata van deze bestanden staat "
                "wél onder Werkbare data."
            )
        return {}, [f"Star schema: {melding}"]
    status, kwaliteitsfouten = lees_status(star_output / "quality.json")
    return {
        "status": status,
        "kwaliteitsfouten": kwaliteitsfouten,
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
        "onbekende_xml_elementen": lees_onbekende_xml_elementen(
            star_output / "quality.json"
        ),
    }, []


def _toon_fouten(fouten: list[str]) -> None:
    if fouten:
        with st.expander(f"⚠️ {len(fouten)} fout(en)"):
            for f in fouten:
                st.write(f"• {f}")


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
  <p>Zet ruwe DUO-bekostigingsbestanden om naar brondata per levering
  en een analysemodel (star schema).</p>
</div>""",
    unsafe_allow_html=True,
)

# ── Ontdek bestanden ─────────────────────────────────────────────────────────
raw, invoer = _kies_invoer()
groepen = _scan_raw(raw)

if not groepen:
    st.info(
        f"Geen herkenbare bestanden gevonden in {invoer}.  \n"
        "Gebruik RO-, GRONDSLAG- of TBGI-bestanden."
    )
    st.stop()

totaal_bestanden = sum(len(v) for v in groepen.values())
st.write(
    f"**{totaal_bestanden} bestand(en) gevonden** in {invoer} — "
    f"{len(groepen)} map(pen):"
)

for periode in sorted(groepen):
    with st.expander(f"📁 {periode}  ({len(groepen[periode])} bestand(en))"):
        for f in groepen[periode]:
            bestandstype = detect_bestandstype(f) or "?"
            st.write(f"• `{f.name}` — *{bestandstype}*")

st.write("")

prepared = prepared_dir()

# ── Stap 1: Brondata ─────────────────────────────────────────────────────────
st.subheader("1. Brondata", divider="gray")
st.caption(
    "Ruwe bestanden → per levering en recordtype, getrouw aan de levering "
    "(`data/02-prepared`)."
)
verwerking = _kies_persoonsverwerking()
if st.button("Verwerk bestanden", type="primary", width="stretch"):
    fouten_brondata = _verwerk_bestanden(groepen, raw, prepared, verwerking)
    prep_dirs = _prepared_dirs_op_schijf(groepen, raw, prepared)
    st.session_state["prepared_dirs"] = [str(d) for d in prep_dirs]
    st.session_state["fouten_brondata"] = fouten_brondata

_toon_fouten(st.session_state.get("fouten_brondata", []))
prep_dirs = _prepared_dirs_op_schijf(groepen, raw, prepared)
if prep_dirs:
    st.success(f"Brondata klaar — {len(prep_dirs)} levering(en)")
    quality_reports = _load_quality_reports(prep_dirs)
    if quality_reports:
        with st.expander("📊 Datakwaliteit per levering (SLR-reconciliatie)"):
            for levering, report in sorted(quality_reports.items()):
                with st.container(border=True):
                    st.subheader(levering, divider="gray")
                    _show_quality_report(report)

# ── Stap 2: Analysemodel ─────────────────────────────────────────────────────
st.subheader("2. Analysemodel", divider="gray")
st.caption(
    "Brondata → star schema met inhoudelijke keuzes (zie Ontwerpkeuzes in de "
    "documentatie). Gebouwd uit de brondata hierboven; de ruwe bestanden "
    "worden niet opnieuw verwerkt."
)
if st.button(
    "Bouw analysemodel",
    type="primary",
    width="stretch",
    disabled=not prep_dirs,
    help=None if prep_dirs else "Verwerk eerst de bestanden (stap 1).",
):
    star_summary, fouten_ster = _bouw_analysemodel(prep_dirs, prepared)
    st.session_state["star_pad"] = str(star_dir())
    st.session_state["star_summary"] = star_summary
    st.session_state["fouten_ster"] = fouten_ster

_toon_fouten(st.session_state.get("fouten_ster", []))
star_summary: dict = st.session_state.get("star_summary", {})
if star_summary:
    if star_summary.get("status") == "fail":
        st.error(
            f"Analysemodel gebouwd, maar met {star_summary['kwaliteitsfouten']} "
            "kwaliteitsfout(en): gebruik het niet als betrouwbaar resultaat. "
            "Zie `quality.json` en het kwaliteitsoverzicht in het dashboard."
        )
    else:
        st.success("Analysemodel klaar — star schema gebouwd")
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
            st.write(f"• `{lev}` — {instelling}" if instelling else f"• `{lev}`")

elif vind_star_dir(st.session_state):
    st.info(
        "Er staat een eerder gebouwd analysemodel op schijf. Bouw het opnieuw "
        "om nieuwe of gewijzigde brondata mee te nemen."
    )

if prep_dirs:
    st.write("")
    kol_werkbaar, kol_ster = st.columns(2)
    if kol_werkbaar.button("Bekijk werkbare data →", width="stretch"):
        st.switch_page("pages/werkbare_data.py")
    if kol_ster.button(
        "Bekijk analysemodel →",
        width="stretch",
        disabled=not vind_star_dir(st.session_state),
    ):
        st.switch_page("pages/analysemodel.py")

st.divider()
st.caption(
    "© CEDA · Npuls — [GitHub](https://github.com/cedanl/mbo-bekostiging-bestanden)"
)
