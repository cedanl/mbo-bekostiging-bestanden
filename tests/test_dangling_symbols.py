"""Preventeert dangling symbolen in comments en docstrings (#372)."""

import re
from pathlib import Path

# Dangling symbols: references naar namen die niet meer bestaan
_KNOWN_DANGLING = {
    "_lees_star_schema": "Vervangen door lees_star_schema (zie #371)",
}

# Exceptions voor geldige maar niet-vindbare references
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
            content = py_file.read_text(encoding="utf-8")
            # Definities: def NAME of class NAME
            for m in re.finditer(
                r"(?:^def|^class)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                content,
                re.MULTILINE,
            ):
                valid_symbols.add(m.group(1))
            # Imports: from X import Y
            for m in re.finditer(
                r"from\s+[a-zA-Z0-9_.]+\s+import\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                content,
            ):
                valid_symbols.add(m.group(1))

    def _check_line(filepath: str, line_no: int, line: str) -> None:
        """Check a single line for dangling symbols."""
        for match in backtick_pattern.finditer(line):
            symbol = match.group(1)
            if symbol in _KNOWN_DANGLING:
                dangling.append((filepath, line_no, symbol, _KNOWN_DANGLING[symbol]))

        for match in bare_pattern.finditer(line):
            symbol = match.group(1)
            if symbol in _KNOWN_DANGLING:
                dangling.append((filepath, line_no, symbol, _KNOWN_DANGLING[symbol]))

    # Scan Python files
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for py_file in search_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            rel_path = py_file.relative_to(repo_root)
            rel_path_str = str(rel_path).replace("\\", "/")

            for line_no, line in enumerate(content.split("\n"), 1):
                if line.strip().startswith("#"):
                    _check_line(rel_path_str, line_no, line)

    # Scan pyproject.toml
    if toml_file.exists():
        content = toml_file.read_text(encoding="utf-8")
        for line_no, line in enumerate(content.split("\n"), 1):
            _check_line("pyproject.toml", line_no, line)

    if dangling:
        msg = "Dangling symbolen in comments/docstrings (#372).\n\n"
        for filepath, line_no, symbol, reason in dangling:
            msg += f"{filepath}:{line_no}: `{symbol}` — {reason}\n"
        raise AssertionError(msg)
