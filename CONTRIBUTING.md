# Contributing

Thanks for helping improve lsc-pop. The outputs are used for NHS planning and analysis, so changes go through review.

## How changes reach `main`

`main` is protected. Nobody pushes to it directly:

1. **Branch** from `main`: `git switch -c <short-description>`.
2. **Make the change** (see the rules below) and commit.
3. **Open a pull request.** The template has a checklist; fill it in.
4. **CI must pass**: lint and core tests, the pandas-2 compatibility job, and the Databricks local-Spark tests
   (`.github/workflows/tests.yml`).
5. **Review**: one approval from a code owner (`.github/CODEOWNERS`). All review conversations must be resolved.
   New commits dismiss earlier approvals.
6. **Squash-merge.** History stays linear, one commit per PR, and the branch is deleted automatically.

## Rules for changes

- **Anything that changes the numbers gets an ADR** in `docs/decisions/` (template in that folder), written before or
  with the code. Never edit an accepted ADR's decision: supersede it.
- **Settings live in `config/config.yaml` and `config/mappings/`, not in code.** New data sources are registered in
  `config/sources.yaml`.
- **Raw data is immutable.** Never commit `data/raw/`, `data/interim/`, `data/processed/` or `outputs/`.
- **Two implementations.** The local pipeline (`src/lsc_pop/`) is the reference, and the Databricks pipeline
  (`databricks/src/pipeline/`) must match it (ADR-0022, ADR-0024). Method changes go in both.
  `databricks/tests/test_pipeline_parity.py` enforces this.
- **Docs are part of the change.** Run `uv run lsc-pop docs`; `tests/test_docs.py` fails if the README command
  reference is stale. Define new terms in `docs/glossary.md`.
- **Outputs are modelled estimates, not official statistics.** Keep that statement wherever outputs are described.

## Setting up

```bash
uv sync --group databricks          # Python 3.12 and all dependencies (pinned by uv.lock)
brew install openjdk@17             # only for the Databricks tests (local Spark)
uv run pytest && uv run --group databricks pytest databricks/tests
uv run lsc-pop download && uv run lsc-pop run   # full pipeline on real data (~0.5 GB download)
```

See the [README](README.md) for every command, and [`databricks/README.md`](databricks/README.md) for Databricks.

## Questions and problems

Open an issue. There are templates for bugs and for questions about the data or method. Don't include patient-level or
other sensitive data in issues.
