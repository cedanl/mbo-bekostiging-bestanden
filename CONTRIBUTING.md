# Bijdragen

## Werkwijze
- Eén branch en één PR per issue (`fix/<nr>-<slug>`), vanaf `main`.
- Test-first: eerst een falende test, dan de fix.
- Vóór de PR: `MBO_PSEUDONIMISERING_SALT="ci-test-key-do-not-use-in-production" uv run pytest`,
  `uv run ruff check .`, `uv run ty check` en `uv run --group docs mkdocs build --strict`.
- Pas de demodata in `data/*/demo/` nooit aan; gebruik synthetische fixtures in `tests/`.

## Releases
Een release ontstaat alleen door een `v*`-tag op `main` te pushen:

1. PR die `version` in `pyproject.toml` ophoogt → merge naar `main`.
2. Wacht tot CI en Docs op `main` groen zijn.
3. `git fetch && git tag vX.Y.Z origin/main && git push origin vX.Y.Z`.

`.github/workflows/release.yml` weigert de release als de tag niet op `main` staat,
niet gelijk is aan de pyproject-versie, of als CI of Docs voor die commit niet groen
is. De release-notes worden gegenereerd uit de gemergde PR's sinds de vorige tag.
Maak releases dus nooit handmatig met `gh release create`.
