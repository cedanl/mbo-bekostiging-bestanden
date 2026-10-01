# PvE-versies

De veldindelingen komen uit de bestandsbeschrijvingen (hoofdstuk 13–17) van het
DUO Programma van Eisen MBO-instelling. De repo bevat daarvan een beknopte
extractie, `bestandsbeschrijving_beknopt.pdf`. Versie, datum en sha256 staan op
één plek: `metadata/pve_bron.json`. De schema's herhalen de versie niet.

Het manifest heeft twee hashes: `sha256` dekt de beknopte extractie in de repo
(`bestandsbeschrijving_beknopt.pdf`, door een test bewaakt) en `sha256_volledig`
de volledige PDF op duo.nl op het moment van de laatste verwerking. Een
afwijkende `sha256_volledig` bij gelijke inhoud is alleen een melding in de
workflow; DUO kan de PDF opnieuw genereren.

## Een nieuwe versie verwerken

1. De wekelijkse workflow `pve-upstream` (`scripts/controleer_pve_upstream.py`)
   faalt als duo.nl een andere versie publiceert, of als de bestandsbeschrijvingen
   inhoudelijk afwijken van de extractie terwijl de versie gelijk is (#368).
2. Vergelijk de bestandsbeschrijvingen per pagina en schrijf een nieuwe extractie:

    ```bash
    uv run --with pypdf python scripts/vergelijk_pve.py \
        bestandsbeschrijving_beknopt.pdf pve-mbo-instellingen.pdf \
        --extractie bestandsbeschrijving_beknopt.pdf
    ```

    Versiestrings en witruimte tellen niet mee. Het script koppelt pagina's op
    het footernummer; verschuift de paginering, dan meldt het ontbrekende
    pagina's en is handwerk nodig.
3. Werk per inhoudelijk verschil het schema of de waardenlijst bij, of leg vast
   waarom er geen gevolg is (hieronder).
4. Zet `versie`, `sha256` en `sha256_volledig` in `pve_bron.json`; de tests in `test_pve_bron.py` en
   `test_pve_versie.py` controleren dat PDF, manifest en schema's kloppen.

## 4.8.2 → 4.8.3 (12-05-2026)

Volgens het versiebeheer van het PvE:

| Wijziging | PvE-§ | Gevolg voor deze repo |
|---|---|---|
| Nieuwe kwaliteitscontroles op een verschil in leerroutefase en leerroute tussen mbo en v(s)o | 7.3.1 | Geen. Het zijn signalen in de berichtenuitwisseling (ROD), geen velden of waarden in RO, GRONDSLAG of TBG-i |
| Controles op geldige examenlicenties voor niet-bekostigde instellingen | 10.1.14 | Geen. Het betreft berichten, niet de bestandsbeschrijvingen |

`scripts/vergelijk_pve.py` op de pagina's 154–210 (hoofdstuk 13–17): **geen
inhoudelijke verschillen**. Het enige tekstverschil is een extra spatie op
pagina 174 (§14, verschillenbestand BPV). Paragraafnummers zijn gelijk
gebleven, dus verwijzingen als "PvE 4.8.2 §17.1" in code en tests gelden ook
voor 4.8.3.

De afwijkingen van het PvE die echte leveringen hebben (GRONDSLAG-VLP met BRIN,
RO-DIP met positie 7) bestaan in beide versies; de ingest herkent beide layouts
(#236, #321).
