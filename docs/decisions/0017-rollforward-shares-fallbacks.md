# 0017. Roll-forward details: pooled source ages, share fallbacks, newborn proxy
Status: accepted (user, 2026-10-01)
Date: 2026-10-01

## Context
ADR-0004 fixed cohort ageing as the default. Implementing it needed four further choices.

## Decisions
1. **Source ages** (`rollforward.source_ages`). With k = `shift_years` (3 for mid-2024):
   - target age a, where k ≤ a < 90, takes the 2021 age a − k;
   - target **90+ pools 2021 ages 87–90+** (everyone who could be 90+ by mid-2024), weighted by their 2021 counts;
   - targets 0–2 (born after Census day) take the **2021 age-0 shares** (`rollforward.newborn_proxy_ages: [0]`, the
     brief's default).
   - `static` uses target age a ← 2021 age a.
2. **Shares** are pooled 2021 counts at the source ages ÷ their all-groups total, per LSOA × sex × target age.
3. **Fallback** when the LSOA × sex had nobody at the source ages in 2021, applied in order:
   1. the LSOA × sex pooled over the **RM032 band** of the source ages (keeps both the LSOA and the broad age);
   2. the LSOA × sex, all ages;
   3. the LSOA, both sexes, all ages;
   4. the LTLA × sex at the source ages.

   The level used is stored per cell (`share_fallback_level`). Mid-2024 England: level 0 (direct) for 99.78% of
   people; level 1 (band) for 131,022 people (0.22%); level 2 for 7 people; levels 3–4 not used.
4. **Estimates** = S5 × shares, which sum to S5 per LSOA × sex × age (max gap 2 × 10⁻¹³).

## Evidence for the newborn proxy (`docs/sensitivity.md`)
Alternative: pool 2021 ages 0–4. Effect at ages 0–9, mid-2024:

| | Asian | Black | Mixed | White British | White other | Other |
|---|---|---|---|---|---|---|
| England | +0.7% | +1.6% | −0.8% | −0.2% | 0.0% | +1.4% |
| L&SC | −0.4% | −2.3% | +0.5% | 0.0% | +0.8% | +3.2% |

At ages 0–2, age 0 alone needs a fallback in only 0.8% of cells. Age-0 shares reflect the ethnic mix of the most
recent births, which is closest to post-Census births. Pooling 0–4 is smoother but older. **Decision: keep age 0** (user accepted 2026-10-01).

## Consequences
The cohort approach can't see post-2021 migration or differential fertility (ADR-0004, limitations §1). The newborn
proxy assumes post-Census births in each LSOA share the ethnic mix of the LSOA's 2021 infants.

## Related
`lsc_pop.rollforward`, `config.rollforward.newborn_proxy_ages`, `config.variant`, checks ROL-05 to ROL-08,
assumptions A02, A03, A12, `tests/test_rollforward.py`.
