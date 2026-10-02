# 0021. Adopt git and publish as a public GitHub repository
Status: accepted (user, 2026-10-02; supersedes ADR-0009's "no git")
Date: 2026-10-02

## Context
ADR-0009 recorded the user's choice not to use git, so run provenance relied on config, code and lock hashes. The
user now wants to share the pipeline publicly with NHS organisations.

## Decision
- The repository is under git and published at `https://github.com/TheDrunkGoldfish/lsc-pop` (public).
- Licences: code MIT (`LICENSE`); documentation OGL v3.0 (`LICENSE-docs.md`). No raw data or outputs are committed
  (`.gitignore`). Users fetch data with `lsc-pop download`, which checks every file against the committed
  `data/manifest.json`.
- Run metadata now records `git_commit` and `git_dirty` automatically (already supported by `provenance.git_info`),
  alongside the config, code and lock hashes (ADR-0009), which stay.
- GitHub Actions runs lint and unit tests on every push (`.github/workflows/tests.yml`). The tests use synthetic data.
- The generated docs (`validation_report.md`, `transformations.md`, `sensitivity.md`, figures) are committed, so
  readers can see the results without running the pipeline. They come from run `20261002T140001Z_282797bf_318f4d5a`.

## Consequences
Code history is available. Contributors should commit config/code changes before producing outputs they intend to
share, so `git_dirty` is false in the run metadata. The `PROJECT_BRIEF.md` (kick-off brief) is published with a note
that later ADRs supersede parts of it.

## Related
ADR-0009, `provenance.git_info`, `README.md` (licence, clone instructions).
