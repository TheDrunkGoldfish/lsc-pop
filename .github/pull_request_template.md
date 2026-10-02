## What and why

<!-- What does this change, and why? Link any issue. -->

## Effect on the numbers

- [ ] No change to outputs (refactor, docs, CI). Output `data_hash`es are unchanged: `lsc-pop compare-runs` against the previous run
- [ ] Changes outputs. Describe the expected effect and the size of the change:

## Checklist

- [ ] Decision recorded: a new or superseding ADR in `docs/decisions/` for anything that affects the numbers
- [ ] **Both implementations changed** if the method changed: `src/lsc_pop/` and `databricks/src/pipeline/` (ADR-0022)
- [ ] Tests pass locally: `uv run pytest` and `uv run --group databricks pytest databricks/tests`
- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] Docs regenerated: `uv run lsc-pop docs` (command reference, validation report, sensitivity, figures)
- [ ] Hand-written docs updated where relevant (methodology, limitations, data dictionary, assumptions, glossary, CHANGELOG)
- [ ] New sources registered in `config/sources.yaml` and downloaded (manifest updated)
- [ ] No raw data, outputs, secrets or workspace-specific settings committed

## Validation

<!-- Paste `uv run lsc-pop validate` output and, if relevant, the parity result. -->
