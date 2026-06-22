# MBO-bekostigingsbestanden

DUO levert aan MBO-instellingen periodiek bestanden waarmee de instelling kan controleren of haar studenten bekostigd worden en op welke grondslag. Deze bestanden zijn technisch van opzet: ze bevatten meerdere recordtypes per bestand, gecodeerde velden en geen kolomkoppen.

Deze documentatie legt uit **wat elk bestand is**, **hoe het is opgebouwd** en **wat elke waarde betekent**.

---

## Drie bestandstypen

| Bestand | Map | Wat het is |
|---|---|---|
| `RO_*.csv` | `h15/` | Registratieoverzicht – alle inschrijvingen en diploma's in een selectieperiode |
| `TBGI_*.XML` | `h16/` | TBG-i – bekostigingsgrondslagen per inschrijving en diploma, inclusief signalen |
| `GRONDSLAG_IP_MBO_*.csv` | `h17/` | Afslag register-levering IP – bekostigingsrelevante data voor de peildatum 1-10 |

---

## Opbouw

Alle CSV-bestanden zijn **multi-record**: elke regel begint met een recordtype-code (zoals `VLP`, `PER`, `ISG`). Er zijn geen kolomkoppen. De velden zijn gescheiden door `;`.

```
VLP;27DV;2025;20251119;V
PER;100000001;37;37;38;37;V;1234;...
ISG;100000001;27DV;1;20230901;20250731;...
ISP;100000001;27DV;1;20230901;25655;;BBL;;J;...
```

Lees meer in [Databestanden](databestanden/index.md).

---

## Bronnen

- Bestandsbeschrijving DUO PvE MBO-instelling v4.8.3 (12-05-2026)
- Demo-data: [cedanl/duo-mbo-datafiles](https://github.com/cedanl/duo-mbo-datafiles)
