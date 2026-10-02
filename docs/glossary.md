# Glossary

Terms and acronyms used across this repository's documentation, code and outputs. Where a term has a fuller
explanation elsewhere, the link points to it.

## Geography

| Term | Meaning |
|---|---|
| **OA** | Output Area: the smallest Census geography (40–250 households). Used here only inside the lookup that links LSOAs to MSOAs. |
| **LSOA** | Lower layer Super Output Area: small areas of ~1,000–3,000 residents (~1,500 typical), built from OAs. This project uses the **2021** set: 33,755 in England. Codes start `E01`. The base unit of every output (ADR-0001). |
| **MSOA** | Middle layer Super Output Area: groups of ~4–5 LSOAs (5,000–15,000 residents). 6,856 in England (2021). Codes start `E02`. OHID publishes catchments at this level. |
| **LTLA** | Lower-tier local authority: a district, unitary or borough council area. `ltla21cd` is the **2021** set (309 in England), before the 2023 reorganisations in Cumbria, North Yorkshire and Somerset. Census tables and the IPF seed use it. |
| **UTLA** | Upper-tier local authority: a county council or unitary authority (e.g. Lancashire County Council, Blackpool). Used only in a diagnostic (CAT-11). |
| **LAD** | Local Authority District: the current set (April 2026 lookup), `lad_cd`. Where councils have merged since 2021 it differs from LTLA 2021 (e.g. Barrow-in-Furness and South Lakeland are now part of Westmorland and Furness). |
| **Region** (`rgn21cd`) | One of England's 9 ONS statistical regions (e.g. North West). |
| **ICB** | Integrated Care Board: the NHS body that plans and funds health services for an area. 36 in England (April 2026). L&SC ICB is `E54000048` (ONS code) / `QE1` (ODS code). |
| **Sub-ICB / SICBL** | Sub-ICB Location: a sub-division of an ICB, usually corresponding to a former Clinical Commissioning Group (CCG) or "place". L&SC has 8. |
| **NHSER** | NHS England region (7), e.g. North West (`Y62`). |
| **Footprint** | The set of LSOAs modelled. Here, all of England (ADR-0002). |
| **Focus ICB** | L&SC: the priority area for reporting and validation (`in_focus_icb`). |
| **Vintage** | The edition/date of a geography lookup (e.g. `2026-04`). Boundaries and codes change between vintages. |
| **ONS code vs ODS code** | ONS codes are 9-character statistical codes (`E54000048`). ODS codes are short NHS organisation codes (`QE1`, `RXL`), issued by the NHS Organisation Data Service. |

## Organisations and areas

| Term | Meaning |
|---|---|
| **ONS** | Office for National Statistics: publishes the Census, population estimates and geography lookups. |
| **Nomis** | ONS's labour-market and Census data service (nomisweb.co.uk), used to download Census LSOA tables. |
| **OHID** | Office for Health Improvement and Disparities (part of DHSC). Publishes the NHS acute trust catchment populations. |
| **DHSC** | Department of Health and Social Care. |
| **MHCLG** | Ministry of Housing, Communities and Local Government: publishes the Indices of Deprivation. |
| **L&SC** | Lancashire and South Cumbria. |
| **OneLSC** | The L&SC NHS provider collaborative. Its acute trusts are Blackpool Teaching Hospitals (`RXL`), East Lancashire Hospitals (`RXR`), Lancashire Teaching Hospitals (`RXN`) and University Hospitals of Morecambe Bay (`RTX`). Lancashire & South Cumbria NHS Foundation Trust (LSCFT, `RW5`) is mental health/community, not acute. |
| **FT** | Foundation Trust (an NHS trust with foundation status). |
| **RBN** | Mersey and West Lancashire Teaching Hospitals NHS Trust (includes former Southport & Ormskirk), which serves West Lancashire. |
| **OGL** | Open Government Licence v3.0, the licence for all input data. |

## Data sources and tables

| Term | Meaning |
|---|---|
| **Census 2021** | The census of England and Wales on 21 March 2021 ("Census day"). |
| **RM032** | Census table: ethnic group × sex × age in 5 broad bands (≤24, 25–34, 35–49, 50–64, 65+), at LSOA. Source S1. |
| **RM200** | Census table: sex × single year of age (0–90+), at LSOA. Source S2. |
| **TS021** | Census table: ethnic group, at LSOA. Used only for validation (S4). |
| **S3 / seed table** | Census ethnic group × sex × single year of age at LTLA, from the ONS "Create a custom dataset" API. |
| **MYE** | Mid-year estimates: ONS's official population estimates for 30 June each year. The LSOA single-year-of-age version is S5. |
| **SAPE** | Small Area Population Estimates: ONS's name for the LSOA/MSOA MYE release. |
| **SYOA** | Single year of age. |
| **Supporting information** | ONS's label for the single-year-of-age LSOA estimates: published, but not accredited official statistics. |
| **Accredited official statistics** | Statistics independently assessed as meeting the Code of Practice (formerly "National Statistics"). |
| **IoD / IMD** | English Indices of Deprivation 2025 / Index of Multiple Deprivation (the overall index). Ranks LSOAs from 1 (most deprived) to 33,755. Deciles and quintiles split them into 10ths and 5ths by rank. |
| **Domains** | The 7 parts of the IMD: income, employment, education, health, crime, barriers to housing and services, living environment. |
| **IDACI / IDAOPI** | Income Deprivation Affecting Children Index / Older People Index: supplementary indices. |
| **Core20** | NHS England's "Core20PLUS5" definition of the most deprived 20% of the population: LSOAs in national IMD deciles 1–2. |
| **Local quintile** | Here, IMD quintiles ranked **within each ICB** and weighted by population, so each holds ~20% of that ICB's residents (ADR-0008). |
| **HES** | Hospital Episode Statistics: NHS England's record of hospital activity, used by OHID to measure where each trust's patients live. |
| **Catchment** | The population a trust effectively serves, estimated from where its patients come from. Not a fixed boundary. |
| **FPTP** | "First past the post": an OHID method that assigns each MSOA wholly to the trust treating most of its patients. |
| **"All (5% and above)"** | An OHID method that gives each trust its share of every MSOA where it treats ≥ 5% of patients. |
| **UNASSIGNED** | Our bridge row holding the ~2% of each MSOA's patients that OHID suppressed (cells under 8 patients) or rounded away (ADR-0019). |

## Method

| Term | Meaning |
|---|---|
| **IPF** | Iterative proportional fitting (also "raking"): builds a table that matches known row and column totals while keeping the pattern of a starting ("seed") table, by alternately rescaling rows and columns until both match. Used to split Census broad-age ethnic counts into single years of age (`methodology.md` §1, §3.3; ADR-0003). |
| **Margin** | A row or column total that IPF must match (here: RM032 ethnic counts and RM200 single-year counts). |
| **Seed** | The starting table for IPF: here, each ethnic group's age pattern in the LSOA's 2021 local authority. |
| **Seed floor** | A small amount (0.5) added to every seed cell so groups or ages with no seed people can still be fitted (ADR-0016). |
| **Reconciliation** | Making the two Census tables agree on each band's total before IPF (ADR-0015). |
| **Perturbation / cell key perturbation / record swapping** | ONS's disclosure-control methods, which slightly alter Census counts so individuals can't be identified. They're why different Census tables don't agree exactly. |
| **Base / 2021 base** | The modelled Census-day population by LSOA × sex × single year × ethnic group. |
| **Roll-forward** | Moving the 2021 ethnic mix to the reference year by applying it to the mid-year estimates. |
| **Cohort ageing / cohort variant** | The default roll-forward: people keep their ethnicity as they age, so mid-2024 age *a* takes the 2021 mix at age *a* − 3 (ADR-0004). |
| **Static variant** | Sensitivity alternative: mid-2024 age *a* takes the 2021 mix at age *a*. |
| **Newborn proxy** | The 2021 ages whose ethnic mix is used for children born after Census day (default: age 0; ADR-0017). |
| **Share fallback** | Where an LSOA had nobody of the needed age in 2021, its ethnic shares come from a wider group (ADR-0017). |
| **Sensitivity analysis** | Re-running with an alternative assumption to see how much results change (`sensitivity.md`). |
| **pp** | Percentage points (the difference between two percentages). |
| **MAE / RMSE** | Mean absolute error / root mean square error: average size of differences. |

## Pipeline, outputs and tooling

| Term | Meaning |
|---|---|
| **Stage** | One step of the pipeline (download, geography, census, ipf, rollforward, deprivation, catchments, outputs). See the README command reference. |
| **Run / run id** | One execution of `lsc-pop run`, written to `outputs/<run_id>/`. The run id is `<UTC time>_<config hash[:8]>_<code hash[:8]>`. |
| **Config hash / code hash / data hash** | SHA-256 fingerprints of, respectively: the settings, mappings and source register; the package source code; a table's contents. Identical hashes mean identical inputs, code or data (ADR-0009). |
| **SHA-256** | A standard cryptographic checksum. A file's SHA-256 changes if even one byte changes. |
| **Manifest** | `data/manifest.json`: the record of every downloaded raw file (URL, date, size, SHA-256). |
| **Hard / soft check** | A hard check stops the pipeline if it fails. A soft (informational) check is only reported. IDs like `GEO-01`, `CEN-10` and `ROL-05` are listed in `validation_report.md`. |
| **ADR** | Architecture decision record: a short document recording one decision, the options and why (`docs/decisions/`). |
| **Star schema** | A table design with one large **fact** table of numbers (`fact_population`), plus small **dimension** tables (`dim_lsoa`, `dim_ethnicity`, …) joined to it by keys. Suited to SQL/BI (ADR-0018). |
| **Bridge table** | A table linking two dimensions many-to-many with weights: here LSOA ↔ trust with catchment proportions. |
| **Parquet** | A compressed, column-oriented file format read by pandas, Databricks, DuckDB, Power BI and others. The canonical output format. |
| **BI** | Business intelligence (tools such as Power BI or Databricks SQL dashboards). |
| **Databricks / Delta / Unity Catalog** | A data platform / its table format / its catalogue of tables and permissions. |
| **uv** | The Python package and environment manager used to install exact dependency versions (`uv.lock`). |
| **CLI** | Command-line interface: the `lsc-pop` command. |
| **API** | Application programming interface: here, the ONS and Nomis web services that return data on request. |
| **UTC** | Coordinated Universal Time (run ids use it). |
