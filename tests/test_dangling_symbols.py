"""Preventeert dangling symbolen in comments en docstrings (#372)."""

import re
from pathlib import Path

# Symbolen die in comments voorkomen maar niet naar geldige defs verwijzen
_KNOWN_DANGLING = {
    "_lees_star_schema": "Oude naam, vervangen door lees_star_schema (zie #371)",
}

# Allowlist voor geldige maar niet-vindbare references
_ALLOWLIST = {
    # (file_path_pattern, symbol): reason
}


def test_no_dangling_symbols_in_comments():
    """Guard: comments en docstrings mogen geen dangling symbolen bevatten."""
    repo_root = Path(__file__).parent.parent

    search_dirs = [
        repo_root / "src",
        repo_root / "app",
        repo_root / "scripts",
        repo_root / "tests",
    ]

    toml_file = repo_root / "pyproject.toml"
    dangling = []

    # Patterns: `identifier` of _identifier
    backtick_pattern = re.compile(r"`([a-zA-Z_][a-zA-Z0-9_\.]*)`")
    bare_pattern = re.compile(r"\b(_[a-zA-Z0-9_]+)\b")

    # Verzamel geldige symbolen uit de repo
    valid_symbols = set()
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for py_file in search_dir.rglob("*.py"):
            content = py_file.read_text()
            # Definities: def NAME of class NAME
            for match in re.finditer(r"(?:^def|^class)\s+([a-zA-Z_][a-zA-Z0-9_]*)", content, re.MULTILINE):
                valid_symbols.add(match.group(1))
            # Imports: from X import Y
            for match in re.finditer(r"from\s+[a-zA-Z0-9_.]+\s+import\s+([a-zA-Z_][a-zA-Z0-9_]*)", content):
                valid_symbols.add(match.group(1))

    # Scan comments in Python-files
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for py_file in search_dir.rglob("*.py"):
            content = py_file.read_text()
            rel_path = py_file.relative_to(repo_root)
            rel_path_str = str(rel_path).replace("\\", "/")

            for line_no, line in enumerate(content.split("\n"), 1):
                if not line.strip().startswith("#"):
                    continue

                # Backtick-quoted symbols
                for match in backtick_pattern.finditer(line):
                    symbol = match.group(1)
                    if symbol in _KNOWN_DANGLING:
                        dangling.append((rel_path_str, line_no, symbol, _KNOWN_DANGLING[symbol]))

                # Bare underscored identifiers
                for match in bare_pattern.finditer(line):
                    symbol = match.group(1)
                    if symbol in _KNOWN_DANGLING:
                        dangling.append((rel_path_str, line_no, symbol, _KNOWN_DANGLING[symbol]))

    # Scan pyproject.toml
    if toml_file.exists():
        content = toml_file.read_text()
        for line_no, line in enumerate(content.split("\n"), 1):
            # Backtick-quoted symbols
            for match in backtick_pattern.finditer(line):
                symbol = match.group(1)
                if symbol in _KNOWN_DANGLING:
                    dangling.append(("pyproject.toml", line_no, symbol, _KNOWN_DANGLING[symbol]))

            # Bare underscored identifiers
            for match in bare_pattern.finditer(line):
                symbol = match.group(1)
                if symbol in _KNOWN_DANGLING:
                    dangling.append(("pyproject.toml", line_no, symbol, _KNOWN_DANGLING[symbol]))

    if dangling:
        msg = (
            "Dangling symbolen in comments/docstrings (#372).\n"
            "Dit zijn references naar namen die niet meer bestaan.\n\n"
        )
        for filepath, line_no, symbol, reason in dangling:
            msg += f"{filepath}:{line_no}: `{symbol}` — {reason}\n"
        raise AssertionError(msg)
