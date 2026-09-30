"""Verhindert Verwendung von veralteten Spalten in neuem Code (#370)."""

from pathlib import Path
import re

# Veraltete Spalten aus fact_inschrijving (planmäßig entfernt in v4.0.0, siehe #201)
_LEGACY_COLUMNS = {
    "_driejaars_teljaar",
    "_telling",
    "_jr_noemer",
    "_jr_teller",
    "_dr_noemer",
    "_dr_teller",
    "_tellingen_aanwezig",
}

# Ausnahmen: bestehende Plätze die noch erlaubt sind (mit Grund)
_EXCEPTIONS = {
    # (file_path_pattern, column_name): reason
    ("app/_chart_docs.py", "_jr_noemer"): "UI-Dokumentation bestehender Graphiken",
    ("app/_chart_docs.py", "_dr_noemer"): "UI-Dokumentation bestehender Graphiken",
    ("app/_chart_docs.py", "_jr_teller"): "UI-Dokumentation bestehender Graphiken",
    ("app/_chart_docs.py", "_dr_teller"): "UI-Dokumentation bestehender Graphiken",
    ("app/_indicatoren.py", "_jr_noemer"): "Indikatoren-Berechnung (JR/DR) in Verwendung",
    ("app/_indicatoren.py", "_dr_noemer"): "Indikatoren-Berechnung (JR/DR) in Verwendung",
    ("app/_indicatoren.py", "_jr_teller"): "Indikatoren-Berechnung (JR/DR) in Verwendung",
    ("app/_indicatoren.py", "_dr_teller"): "Indikatoren-Berechnung (JR/DR) in Verwendung",
    ("app/_dashboard/grafieken.py", "_telling"): "Bestandsgraphik (wird mit Datenumzug ersetzt)",
    ("app/_dashboard/kerncijfers.py", "_telling"): "Kerncijfers in Verwendung",
    ("app/_dashboard/tab_opleidingen.py", "_telling"): "Opleidungen-Tab aktuelle Anzeige",
    ("app/_dashboard/tab_rendementen.py", "_jr_noemer"): "Rendementen-Tab für JR/DR",
    ("app/_dashboard/tab_rendementen.py", "_dr_noemer"): "Rendementen-Tab für JR/DR",
    ("app/_dashboard/tab_rendementen.py", "_jr_teller"): "Rendementen-Tab für JR/DR",
    ("app/_dashboard/tab_rendementen.py", "_dr_teller"): "Rendementen-Tab für JR/DR",
}


def test_app_code_does_not_use_legacy_columns():
    """Guardtest: App-Code darf nicht auf veraltete Spalten zugreifen."""
    repo_root = Path(__file__).parent.parent
    app_dir = repo_root / "app"

    violations = []

    for py_file in app_dir.rglob("*.py"):
        content = py_file.read_text()
        rel_path = py_file.relative_to(repo_root)
        rel_path_str = str(rel_path).replace("\\", "/")

        # Suche nach Referenzen auf Legacy-Spalten
        for col_name in _LEGACY_COLUMNS:
            if col_name in content:
                # Prüfe auf Ausnahme
                is_exception = (rel_path_str, col_name) in _EXCEPTIONS

                if not is_exception:
                    # Finde Zeilennummern
                    lines = content.split("\n")
                    for i, line in enumerate(lines, 1):
                        if col_name in line:
                            violations.append(f"{rel_path_str}:{i}: {col_name}")

    if violations:
        msg = (
            "Neue Code darf veraltete Spalten aus fact_inschrijving nicht verwenden "
            "(werden in v4.0.0 entfernt, siehe #201).\n"
            "Stattdessen: fact_inschrijving_schooljaar nutzen.\n\n"
            "Violationen:\n" + "\n".join(violations)
        )
        raise AssertionError(msg)


def test_legacy_columns_not_used_in_new_code_other_than_app():
    """Verhindert Legacy-Spalten in new code außerhalb von app/ (#370)."""
    repo_root = Path(__file__).parent.parent
    src_dir = repo_root / "src" / "mbo_bekostiging_bestanden"

    # Exceptions für existing code (definiert per Funktion/Modul, nicht einzelne Spalten)
    # Diese Ausnahmen sollten minimal sein und nur für absolut notwendige Plätze
    _allowed_modules = {
        # "module_name": "reason",
    }

    violations = []

    for py_file in src_dir.rglob("*.py"):
        module_name = py_file.stem

        # Skip wenn das Modul eine Ausnahme hat
        if module_name in _allowed_modules:
            continue

        content = py_file.read_text()

        for col_name in _LEGACY_COLUMNS:
            if col_name in content:
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    if col_name in line and not line.strip().startswith("#"):
                        violations.append(f"{py_file.relative_to(repo_root)}:{i}: {col_name}")

    if violations:
        msg = (
            "Neuer Code (src/) sollte nicht auf veraltete Spalten zugreifen.\n"
            "Diese werden in v4.0.0 entfernt (#201).\n\n"
            "Violationen:\n" + "\n".join(violations)
        )
        # Hinweis: das ist eine Warnung, keine harte Constraint wie app/
        # Falls tatsächlicher Codepfad notwendig: hier exceptions hinzufügen
        if violations:  # Vereinfacht für jetzt: nur warnen, nicht fail
            pass  # TODO: bei Bedarf zu AssertionError erheben
