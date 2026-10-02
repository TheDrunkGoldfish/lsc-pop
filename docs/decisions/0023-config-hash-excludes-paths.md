# 0023. The config hash excludes `paths`
Status: accepted (2026-10-02; refines ADR-0009)
Date: 2026-10-02

## Context
The config hash (ADR-0009) fingerprints everything that can change the numbers. It also included `paths` (where raw,
interim and output files live). A Databricks run points `paths.raw` at a Unity Catalog Volume, so its config hash
would differ from a local run with identical settings, and run ids would suggest different settings.

## Decision
`Config.config_hash()` hashes the validated config **excluding `paths`**, plus the mapping files and `sources.yaml` as
before. `config.with_paths()` relocates files (e.g. to `/Volumes/...`) without changing the hash.

## Consequences
- **Run ids change once.** The config part went from `282797bf` to `d1033f90` with no setting changed. Output data
  hashes are unchanged: run `20261002T155325Z_d1033f90_6cc3e8e2` is identical to `20261002T140001Z_282797bf_318f4d5a`.
- **Local and Databricks runs with the same settings now share a config hash.** The Databricks pipeline records it in
  `audit.run_metadata`.

## Related
`lsc_pop.config`, ADR-0009, ADR-0022.
