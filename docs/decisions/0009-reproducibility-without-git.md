# 0009. Reproducibility without git
Status: accepted
Date: 2026-10-01

## Context
The brief (§3.5) asks for each run's git commit to be recorded. The user chose **not to use git** for this project for now.

## Decision
Run metadata and every output sidecar record:
- `config_hash`: SHA-256 of the validated config plus the content of every referenced mapping file;
- `uv_lock_hash`: SHA-256 of `uv.lock` (exact dependency versions);
- `code_hash`: SHA-256 over all `src/lsc_pop/**/*.py` (sorted relative paths + content);
- `git_available` / `git_commit` / `git_dirty`: filled in automatically if the project is later put under git, null otherwise.

Together these identify the exact code, dependencies and settings behind an output. Stages are deterministic
(sorted outputs, fixed seeds), so a rerun with identical hashes must reproduce identical `data_hash` values.

## Consequences
No history or diff of code changes. `docs/CHANGELOG.md` has to be kept up to date by hand. Moving to git later
needs no code change.

## Related
`provenance.RunContext`, `provenance.write_output`, `tests/test_provenance.py`.
