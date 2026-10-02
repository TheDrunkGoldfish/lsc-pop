# Documentation licence

The documentation in this repository (`README.md`, `docs/` and other Markdown files, and the figures in
`docs/figures/`) is published under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) (OGL).

The source code (`src/`, `tests/`, configuration) is under the MIT licence in [`LICENSE`](LICENSE).

## Input data

This repository contains **no raw data**. `lsc-pop download` fetches it from the publishers. All inputs are
published under the OGL v3.0:

- Contains public sector information licensed under the Open Government Licence v3.0.
- Source: Office for National Statistics (Census 2021, mid-year population estimates, geography lookups).
- Source: Ministry of Housing, Communities and Local Government (English Indices of Deprivation 2025).
- Source: Office for Health Improvement and Disparities (NHS acute trust catchment populations).

Figures and validation results in `docs/` are derived from these sources. Outputs produced by the pipeline are
**modelled estimates, not official statistics**, and should be labelled as such wherever they're used.
