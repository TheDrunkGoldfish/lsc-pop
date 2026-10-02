# Limitations: read before using these figures

> **These are modelled estimates, not official statistics.** They combine Census 2021, ONS mid-2024 small-area
> estimates, IoD 2025 and OHID catchments through statistical modelling. Read this page before using the figures.
>
> **Abbreviations on this page:** ADR = architecture decision record; FPTP = first past the post (OHID method); HES = Hospital Episode Statistics; ICB = Integrated Care Board; IoD = English Indices of Deprivation; L&SC = Lancashire and South Cumbria; LSOA = Lower layer Super Output Area; MSOA = Middle layer Super Output Area; OGL = Open Government Licence; OHID = Office for Health Improvement and Disparities; ONS = Office for National Statistics. Full definitions: [glossary](glossary.md).

1. **Migration drift.** Ethnic composition is held at 2021 levels within each age cohort. Changes since the Census from
   migration and differential births/deaths are **not** captured. No official LSOA-level source corrects for this.
   The error grows with each year after 2021. Treat recent-migration groups (e.g. Other White, African, Other Asian,
   Arab) and areas with large population change since 2021 with most caution. Mid-2024 totals are always ONS's;
   only the ethnic split is modelled.
1a. **Cohort vs static assumption.** Assuming the 2021 ethnic mix moves with each cohort (the default) and not staying
   with each age changes some group totals noticeably. Static shares give 8.6% fewer Mixed-ethnicity people in
   England (`docs/sensitivity.md`). The default is the better-founded assumption, but the gap shows how much
   depends on it.
2. **Census perturbation.** Census 2021 tables are independently perturbed (cell key perturbation, record swapping), so
   different tables don't agree exactly at LSOA level. For example, RM032 and RM200 match exactly in only 17% of
   LSOA × sex × age-band cells, with a typical gap of 2 people (max 16). We rescale ethnic counts to the
   single-year-of-age totals (ADR-0015), but small-area detail carries this noise.
3. **Small numbers.** Most LSOA × single-year × 19-group cells are below 5 people. The worked example in
   `methodology.md` §2 has cells of 0.15–3 people. Use small cells only as building
   blocks for aggregates, never on their own. Suggested suppression rules for published tables: §8.
4. **Single-year LSOA estimates are "supporting information".** ONS's single-year-of-age LSOA estimates aren't
   accredited official statistics. Only the broad-age version is.
5. **Catchment apportionment.** Trust figures apportion small-area populations with OHID catchment proportions. These
   are published only for MSOAs (2021) and all ages, so every LSOA, age, sex and ethnic group within an MSOA is assumed
   to use each trust in the same proportion. OHID's own catchments use mid-2022 populations and three years of HES
   admissions, so our trust totals (mid-2024) won't match OHID's exactly.
6. **Age-shape assumption.** Within each broad Census age band, the split into single years borrows each ethnic group's
   age shape from the LSOA's 2021 local authority district (seed S3). Seven small rural districts and the Isles of
   Scilly use a regional or neighbouring shape (ADR-0011). In L&SC this affects only the 6 LSOAs in former Copeland.
7. **Current NHS geography.** ICB and sub-ICB figures use the April 2026 boundaries (36 ICBs after the 2026 mergers).
   They aren't directly comparable with figures on 2025 or earlier ICBs.
8. **Disclosure and appropriate use.** The tables are for internal analysts (ADR-0013). They aren't Census or
   official counts: every cell is a model estimate, so publishing them doesn't disclose any individual. However:
   - **Don't publish or quote LSOA × single-year × 19-group cells.** Most are below 5 people and carry no reliable
     information on their own. Aggregate first.
   - **Suggested rules for published tables:**
     - aggregate to at least MSOA, or to ICB/LA/trust;
     - use 5- or 10-year bands and the 6-group ethnicity;
     - round published values to the nearest 5 (or 10);
     - suppress cells below 10 after rounding, and secondary-suppress where totals would reveal them;
     - always label figures "modelled estimates (not official statistics)" and cite ONS/OHID/MHCLG sources under
       the OGL.
   - **Rates.** Small modelled denominators give unstable rates. Use them only where the denominator is at least
     about 100 people, and prefer pooled years or wider groups.
9. **Trust catchments.**
   - OHID's MSOA shares are for all ages and all admission types combined, and are applied unchanged to every
     subgroup. Trusts with different catchments by age or specialty (e.g. maternity, paediatrics) are approximated.
   - `proportion_published` omits ~2% suppressed flows (held in `UNASSIGNED`). `proportion_rescaled` assigns them to
     each area's listed trusts, slightly favouring its main trusts (ADR-0019).
   - OHID's own figures use mid-2022 populations and HES FY2022/23–2024/25.
   - OHID's "All (5% and above)" ethnicity percentages (also shown in OHID's dashboard) can't be reproduced and
     look as if they used a coarse, near-ICB-wide ethnic mix. For example, East Lancashire is 10.8% Asian there vs
     22.7% here. Its first-past-the-post figures match ours closely. Compare with FPTP, not with "All (5% and
     above)" (ADR-0019).
10. **IoD vintage.** IoD 2025 ranks describe deprivation largely from 2021–2023 indicator data. Core20 and the local
    quintiles are defined on the 2021 LSOAs and the April 2026 ICBs.

