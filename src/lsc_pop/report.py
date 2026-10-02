"""Report rendering for generated docs.

* ``docs/data_sources.md``: rendered from ``config/sources.yaml`` (descriptive fields and the
  hand-written quirks) and ``data/manifest.json`` (retrieved-at, SHA-256, sizes). Phase 2.
* ``docs/transformations.md``: from the run log. Phase 8.
* ``docs/validation_report.md``: from validation results. Phase 8.
"""

from __future__ import annotations

import json
from pathlib import Path

from lsc_pop.config import Config
from lsc_pop.download import load_manifest, load_sources, manifest_entry

GENERATED_BANNER = (
    "> **Generated file.** Rendered by `lsc-pop docs` from `config/sources.yaml` and "
    "`data/manifest.json`.\n> Edit those, not this file. Terms: [glossary](glossary.md)."
)


def _human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    raise AssertionError


def render_data_sources(cfg: Config) -> str:
    registry = load_sources(cfg)
    manifest = load_manifest(cfg.resolve(cfg.paths.manifest))
    out = [
        "# Data sources (source register)",
        "",
        GENERATED_BANNER,
        "",
        "Every source is published under the Open Government Licence v3.0 unless stated otherwise.",
        "",
        "| ID | Role | Title | Release | Status | Enabled | Downloaded |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in registry.sources:
        got = sum(manifest_entry(manifest, s.id, f.name) is not None for f in s.files)
        out.append(
            f"| {s.id} | {s.role} | {s.title} | {s.release_date} | {s.status} | "
            f"{'yes' if s.enabled else 'no'} | {got}/{len(s.files)} |"
        )
    for s in registry.sources:
        out += [
            "",
            f"## {s.id}: {s.title}",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Role | {s.role} |",
            f"| Publisher | {s.publisher} |",
            f"| Landing page | <{s.landing_page}> |",
            f"| Release date | {s.release_date} |",
            f"| Edition | {s.edition} |",
            f"| Reference date | {s.reference_date} |",
            f"| Geography | {s.geography} |",
            f"| Status | {s.status} |",
            f"| Licence | {s.licence} |",
            f"| Enabled | {'yes' if s.enabled else 'no'} |",
            "",
            "**Files**",
            "",
            "| File | Retrieved | Size | SHA-256 | URL |",
            "|---|---|---|---|---|",
        ]
        for f in s.files:
            e = manifest_entry(manifest, s.id, f.name)
            if e is None:
                out.append(f"| `{f.name}` | _not downloaded_ | | | <{f.url}> |")
            else:
                out.append(
                    f"| `{f.name}` | {e['retrieved_at']} | {_human_bytes(e['size_bytes'])} | "
                    f"`{e['sha256']}` | <{f.url}> |"
                )
            if f.description:
                out.append(f"| ↳ {f.description} | | | | |")
        if s.quirks:
            out += ["", "**Known quirks**", ""]
            out += [f"- {q}" for q in s.quirks]
    return "\n".join(out) + "\n"


def write_data_sources(cfg: Config, path: Path | None = None) -> Path:
    path = path or cfg.root / "docs" / "data_sources.md"
    path.write_text(render_data_sources(cfg))
    return path


# --------------------------------------------------------------------------------------------
# Sensitivity (Stage C/D)
# --------------------------------------------------------------------------------------------


def latest_run_with(cfg: Config, filename: str) -> Path | None:
    runs = sorted(
        (p for p in cfg.resolve(cfg.paths.outputs).glob("*/") if (p / filename).is_file()),
        key=lambda p: p.name,
    )
    return runs[-1] if runs else None


def _md_table(df) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        cells = []
        for v in row:
            if isinstance(v, float):
                cells.append(f"{v:,.1f}" if abs(v) >= 100 else f"{v:.2f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_sensitivity(cfg: Config) -> str:
    import pandas as pd

    run = latest_run_with(cfg, "sensitivity_variants.csv")
    out = [
        "# Sensitivity analysis",
        "",
        "> **Generated file.** Rendered by `lsc-pop docs` from the latest run's "
        "`sensitivity_variants.csv` and `sensitivity_seed_floor.csv`. Don't edit by hand. Terms: [glossary](glossary.md).",
        "",
    ]
    if run is None:
        return "\n".join(out + ["_No run with sensitivity results yet._"]) + "\n"
    out += [
        f"Run: `{run.name}`. Reference year {cfg.reference_year}; default variant "
        f"`{cfg.variant}`; seed floor {cfg.ipf.seed_floor:g}; newborn proxy ages "
        f"{cfg.rollforward.newborn_proxy_ages}.",
        "",
    ]
    s = pd.read_csv(run / "sensitivity_variants.csv")
    default = f"default ({cfg.variant})"

    def by(keys, frame):
        g = frame.groupby(keys, sort=False)[["population", "default"]].sum().reset_index()
        g["diff"] = g["population"] - g["default"]
        g["% diff"] = g["diff"] / g["default"] * 100
        return g

    other = s[s["variant"] != default]
    out += [
        "## 1. Variants compared with the default, by ethnic group (6 groups)",
        "",
        "`population` = the variant's mid-year total and `default` = the default variant's. "
        "Seed-floor variants are refitted for the focus ICB only.",
        "",
    ]
    for geo in ("England", "Focus ICB"):
        t = by(["variant", "eth6"], other[other["geography"] == geo])
        out += [f"### {geo}", "", _md_table(t), ""]

    alt = "static" if cfg.variant == "cohort" else "cohort"
    out += [f"## 2. `{alt}` vs `{cfg.variant}` by age band (Focus ICB, % difference)", ""]
    t = by(["age_band", "eth6"], s[(s["variant"] == alt) & (s["geography"] == "Focus ICB")])
    piv = t.pivot(index="age_band", columns="eth6", values="% diff").reset_index()
    out += [_md_table(piv), ""]
    t = by(["age_band", "eth6"], s[(s["variant"] == alt) & (s["geography"] == "England")])
    piv = t.pivot(index="age_band", columns="eth6", values="% diff").reset_index()
    out += [f"### England ({alt} vs {cfg.variant}, % difference)", "", _md_table(piv), ""]

    out += [f"## 3. `{alt}` vs `{cfg.variant}` by detailed ethnic group (19), England", ""]
    t = by(["eth19"], s[(s["variant"] == alt) & (s["geography"] == "England")])
    out += [_md_table(t), ""]

    floor = run / "sensitivity_seed_floor.csv"
    if not floor.is_file():
        floor_run = latest_run_with(cfg, "sensitivity_seed_floor.csv")
        floor = floor_run / "sensitivity_seed_floor.csv" if floor_run else None
    if floor is not None:
        f = pd.read_csv(floor)
        out += [
            "## 4. Seed floor: 2021 base for the focus ICB (Stage C)",
            "",
            "`mae_vs_seed_ltla_cell`: mean absolute difference between the base aggregated to "
            "LTLA and the S3 seed at LTLA × sex × ethnic group × single year. This is partly "
            "circular, because "
            "the seed is that table. `*_vs_default`: differences from the default floor in "
            "persons (cells) and in ethnic shares.",
            "",
            _md_table(f),
            "",
        ]
    return "\n".join(out) + "\n"


def write_sensitivity(cfg: Config) -> Path:
    path = cfg.root / "docs" / "sensitivity.md"
    path.write_text(render_sensitivity(cfg))
    return path


# --------------------------------------------------------------------------------------------
# Transformations, validation report, figures
# --------------------------------------------------------------------------------------------

BRIEF_CHECKLIST = [
    (
        "Footprint LSOA count matches the lookup; no duplicates; every LSOA has ICB/sub-ICB/LA/IoD",
        ["GEO-01", "GEO-02", "GEO-03", "GEO-04", "DEP-01", "OUT-02"],
    ),
    ("RM032 'Does not apply' = 0 for all LSOAs", ["CEN-01", "CEN-07-age_91a"]),
    (
        "Margin reconciliation adjustments within tolerance (distribution logged)",
        ["CEN-09", "CEN-10", "CEN-12"],
    ),
    ("2021 base reproduces RM032 and RM200 margins within IPF tolerance", ["BAS-01", "BAS-02"]),
    ("2021 base ethnic totals vs TS021 (differences reported)", ["BAS-05"]),
    ("2021 base aggregated to LA vs LA ethnicity × age × sex (reported + chart)", ["BAS-06"]),
    ("Mid-year output sums exactly to S5 for every LSOA × sex × age", ["ROL-05"]),
    (
        "No negative/NaN values; shares in [0, 1] and summing to 1",
        ["BAS-07", "CEN-11", "ROL-06", "ROL-07"],
    ),
    (
        "Aggregates reconcile to constituent LSOAs; trust totals compared with OHID",
        ["OUT-03", "OUT-04", "CAT-07", "CAT-08"],
    ),
    ("Cohort vs static differences summarised by ethnic group and age", ["sensitivity.md"]),
    ("Re-running from a clean checkout reproduces identical output hashes", ["reproducibility"]),
]


def latest_complete_run(cfg: Config) -> Path | None:
    return latest_run_with(cfg, "output_hashes.json")


def _fmt_pop(p: dict | None) -> str:
    if not p:
        return ""
    s = f"{p['total']:,.0f}"
    if "by_sex" in p:
        s += " (" + ", ".join(f"{k} {v:,.0f}" for k, v in p["by_sex"].items()) + ")"
    return s


def render_transformations(cfg: Config) -> str:
    from lsc_pop.provenance import read_run_log

    run = latest_complete_run(cfg)
    out = [
        "# Transformations",
        "",
        "> **Generated file.** Rendered by `lsc-pop docs` from `outputs/<run_id>/run_log.jsonl` "
        "of the latest complete run. Don't edit by hand. Terms: [glossary](glossary.md).",
        "",
    ]
    if run is None:
        return "\n".join(out + ["_No complete run yet._"]) + "\n"
    meta = json.loads((run / "metadata.json").read_text())
    recs = list(read_run_log(run / "run_log.jsonl"))
    out += [
        f"Run `{meta['run_id']}` · started {meta['started_at']} · config `{meta['config_hash'][:12]}` · "
        f"code `{meta['code_hash'][:12]}` · uv.lock `{(meta['uv_lock_hash'] or '')[:12]}` · "
        f"git {meta['git_commit'] or 'n/a (not a git repo; ADR-0009)'}",
        "",
        "## Summary",
        "",
        "| # | Step | Status | Rows in | Rows out | Population in | Population out | Dropped / added |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(recs, 1):
        pin = next((d["population"] for d in r["inputs"] if d.get("population")), None)
        pout = next((d["population"] for d in r["outputs"] if d.get("population")), None)
        da = "; ".join(
            [f"−{d['rows']:,} {d['reason']}" for d in r["rows_dropped"] if d["rows"]]
            + [f"+{d['rows']:,} {d['reason']}" for d in r["rows_added"]]
        )
        out.append(
            f"| {i} | `{r['step']}` | {r['status']} | {r['rows_in']:,} | {r['rows_out']:,} | "
            f"{_fmt_pop(pin)} | {_fmt_pop(pout)} | {da} |"
        )
    out += ["", "## Steps in detail", ""]
    for i, r in enumerate(recs, 1):
        out += [
            f"### {i}. `{r['step']}`",
            "",
            f"{r['started_at']} → {r['finished_at']} · {r['status']}",
            "",
        ]
        if r["params"]:
            out += [f"Parameters: `{json.dumps(r['params'], default=str)[:600]}`", ""]
        for kind in ("inputs", "outputs"):
            for d in r[kind]:
                out.append(
                    f"- {kind[:-1]} **{d['name']}**: {d['rows']:,} rows · hash `{d['hash'][:12]}`"
                    + (f" · population {_fmt_pop(d['population'])}" if d.get("population") else "")
                )
        for n in r["notes"]:
            out.append(f"- note: {n if len(n) < 800 else n[:800] + ' …'}")
        out.append("")
    return "\n".join(out) + "\n"


def _check_summary(m) -> str:
    if not m:
        return ""
    s = json.dumps(m, default=str)
    return s if len(s) <= 220 else s[:220] + " …"


def render_validation_report(cfg: Config) -> str:
    import pandas as pd

    from lsc_pop.provenance import read_run_log

    run = latest_complete_run(cfg)
    out = [
        "# Validation report",
        "",
        "> **Generated file.** Rendered by `lsc-pop docs` from the latest complete run's "
        "`validation.jsonl` and comparison CSVs. Don't edit by hand. Terms: [glossary](glossary.md). Hard checks stop the pipeline "
        "when they fail; soft and informational checks are reported only.",
        "",
    ]
    if run is None:
        return "\n".join(out + ["_No complete run yet._"]) + "\n"
    checks = list(read_run_log(run / "validation.jsonl"))
    by_id = {}
    for c in checks:
        by_id.setdefault(c["check_id"], []).append(c)
    n_hard = sum(c["hard"] for c in checks)
    n_fail = sum(c["hard"] and not c["passed"] for c in checks)
    n_warn = sum((not c["hard"]) and not c["passed"] for c in checks)
    out += [
        f"Run `{run.name}`: **{len(checks)} checks; {n_hard} hard, {n_fail} hard failures; "
        f"{n_warn} soft warnings.**",
        "",
    ]

    repro = cfg.resolve(cfg.paths.outputs) / "reproducibility_check.json"
    rep = json.loads(repro.read_text()) if repro.is_file() else None
    out += ["## Brief §10 checklist", "", "| Check | Result | Evidence |", "|---|---|---|"]
    for desc, ids in BRIEF_CHECKLIST:
        if ids == ["sensitivity.md"]:
            res, ev = "reported", "[`sensitivity.md`](sensitivity.md), Figure 2"
        elif ids == ["reproducibility"]:
            if rep is None:
                res, ev = "not yet run", "`lsc-pop compare-runs`"
            else:
                res = "✅ identical" if rep["identical"] else "❌ differs"
                ev = f"{rep['run_a']} vs {rep['run_b']} ({rep['tables_compared']} tables)"
        else:
            found = [c for i in ids for c in by_id.get(i, [])]
            hard_ok = all(c["passed"] for c in found if c["hard"])
            soft_warn = any(not c["passed"] for c in found if not c["hard"])
            res = ("✅ pass" if hard_ok else "❌ FAIL") + (" (soft warning)" if soft_warn else "")
            ev = ", ".join(f"`{i}`" for i in ids)
        out.append(f"| {desc} | {res} | {ev} |")

    out += [
        "",
        "## All checks",
        "",
        "| ID | Stage | Type | Result | Description | Key metrics |",
        "|---|---|---|---|---|---|",
    ]
    for c in checks:
        kind = "hard" if c["hard"] else "soft/info"
        res = "✅" if c["passed"] else ("❌" if c["hard"] else "⚠️")
        out.append(
            f"| {c['check_id']} | {c['stage']} | {kind} | {res} | {c['description']} | "
            f"{_check_summary(c.get('metrics')).replace('|', '/')} |"
        )

    # Key comparisons
    out += ["", "## Key comparisons", "", "### 2021 base vs TS021, England ethnic totals", ""]
    b5 = by_id.get("BAS-05", [{}])[-1].get("metrics", {}).get("england_eth", {})
    if b5:
        from lsc_pop.mappings import load_ethnicity_mapping

        eth = load_ethnicity_mapping(cfg.resolve(cfg.ethnicity.mapping_file)).set_index("code_19")
        rows = [{"eth19": int(k), "group": eth.loc[int(k), "label_19"], **v} for k, v in b5.items()]
        df = pd.DataFrame(rows)
        df["% diff"] = df["diff"] / df["ts021"] * 100
        out += [
            _md_table(df),
            "",
            "Differences come from independent perturbation of RM032/RM200/TS021 and from "
            "reconciling to RM200 totals (ADR-0015). They aren't model error.",
            "",
        ]
    out += [
        "### 2021 base vs S3 (LTLA × sex × ethnic group × single year)",
        "",
        "![Figure 1](figures/fig1_base_vs_seed.png)",
        "",
        f"`BAS-06`: {_check_summary(by_id.get('BAS-06', [{}])[-1].get('metrics'))}",
        "",
    ]
    for name, title in (
        ("totals", "Trust catchment totals vs OHID T1"),
        ("ethnicity", "Trust 5-group ethnicity vs OHID T5"),
        ("imd", "Trust mean IMD 2025 score vs OHID T6"),
    ):
        f = run / f"trust_comparison_{name}.csv"
        if not f.is_file():
            continue
        df = pd.read_csv(f)
        df = df[df["trust_code"].isin(cfg.focus_trusts + ["RBN"])]
        if name == "ethnicity":
            keep = ["trust_code", "selection_method"] + [
                c for c in df.columns if c.startswith(("modelled_pct", "ohid_pct"))
            ]
            df = df[keep]
        out += [f"### {title} (focus trusts + RBN)", "", _md_table(df.round(2)), ""]
    out += [
        "Notes on the OHID comparison:",
        "- OHID T1 totals use **mid-2022** populations, so modelled mid-2024 totals are expected to be "
        "somewhat higher. `modelled_published` excludes the ~2% suppressed remainder (`UNASSIGNED`) "
        "and `modelled_rescaled` includes it (ADR-0019).",
        "- Under OHID's **first-past-the-post** method, modelled 5-group percentages agree closely "
        "(median absolute difference about 0.1 percentage points across all trusts).",
        "- Under OHID's **'All (5% and above)'** method they do **not** agree well for some trusts "
        "(e.g. RXL Asian 2.0% modelled vs 8.5% OHID), while the mean IMD score computed with the same "
        "weighting matches OHID's T6 closely. OHID's exact ethnicity method for that table isn't "
        "published, so this difference is **unexplained**. We don't treat it as evidence for or "
        "against the model.",
        "",
        "### Why OHID's 'All (5% and above)' ethnicity can't be reproduced (CAT-11)",
        "",
        "Hypothesis test, regenerated every run. For each candidate geography, each LSOA's ethnic mix is replaced "
        "by the mix of its whole MSOA / LTLA / upper-tier LA / sub-ICB / ICB / NHS region. Trust percentages are "
        "then recomputed with OHID's 5%-threshold, share-weighted method and compared with OHID T5 across the "
        "128 trusts it covers (5 groups).",
        "",
        "__DIAG__",
        "",
        "Reading: using our own LSOA mix gives the *largest* error. Smoothing the mix over large areas "
        "brings the figures closer to OHID (ICB best overall), but **no single geography reproduces OHID**. ICB "
        "averaging explains the central Lancashire trusts (RXL, RXR, RXN ≈ the L&SC average) but not "
        "Morecambe Bay (RTX). Meanwhile OHID's **first-past-the-post** ethnicity, built from the same MSOA "
        "ethnicity, matches ours to about 0.1 pp, and its T6 IMD (same 5% weighting) matches to within 1 "
        "point. So the inputs agree, and the difference lies in how OHID aggregated this one table. OHID "
        "doesn't publish the method. We treat it as **not comparable** and validate against FPTP instead "
        "(ADR-0019).",
        "",
        "### Cohort vs static (sensitivity)",
        "",
        "![Figure 2](figures/fig2_cohort_vs_static.png)",
        "",
        "### Trust ethnicity vs OHID (first past the post)",
        "",
        "![Figure 3](figures/fig3_trust_ethnicity_fptp.png)",
        "",
    ]
    text = "\n".join(out) + "\n"
    diag = run / "trust_comparison_ethnicity_diagnostic.csv"
    table = (
        _md_table(pd.read_csv(diag).round(2)) if diag.is_file() else "_Diagnostic not in this run._"
    )
    return text.replace("__DIAG__", table)


# Reference categorical palette (dataviz skill, light mode; validated, adjacent pairs).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def render_figures(cfg: Config) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    from lsc_pop.mappings import load_ethnicity_mapping

    run = latest_complete_run(cfg)
    fig_dir = cfg.root / "docs" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    if run is None:
        return []
    paths = []
    eth = load_ethnicity_mapping(cfg.resolve(cfg.ethnicity.mapping_file))
    lab6 = dict(zip(eth["code_6"], eth["label_6"], strict=False))
    short = {
        "A": "Asian",
        "B": "Black",
        "M": "Mixed",
        "O": "Other",
        "WB": "White British",
        "WO": "White other",
    }
    order6 = ["A", "B", "M", "O", "WB", "WO"]

    # Fig 1: base vs seed at LTLA x eth6 x sex x 10-year band (focus ICB LTLAs).
    comp = pd.read_parquet(cfg.resolve(cfg.paths.interim) / "base2021" / "ltla_comparison.parquet")
    lk = pd.read_parquet(cfg.resolve(cfg.paths.interim) / "geography" / "lsoa_lookup.parquet")
    foc = set(lk.loc[lk["in_focus_icb"], "ltla21cd"])
    c = comp[comp["ltla21cd"].isin(foc)].merge(
        eth[["code_19", "code_6"]], left_on="eth19", right_on="code_19"
    )
    c["band"] = (c["age"] // 10).clip(upper=9)
    g = c.groupby(["ltla21cd", "code_6", "sex", "band"])[["seed", "base"]].sum().reset_index()
    fig, ax = plt.subplots(figsize=(6.4, 5.6), facecolor=SURFACE)
    _style(ax)
    ax.scatter(g["seed"] + 1, g["base"] + 1, s=10, color=SERIES[0], alpha=0.55, linewidths=0)
    lim = [1, float(max(g["seed"].max(), g["base"].max())) * 1.3]
    ax.plot(lim, lim, color=INK2, linewidth=1, linestyle="--")
    ax.text(lim[1] * 0.5, lim[1] * 0.8, "y = x", color=INK2, fontsize=9)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("S3 published count + 1 (LTLA)", color=INK)
    ax.set_ylabel("2021 base aggregated from LSOAs + 1", color=INK)
    ax.set_title(
        "Figure 1. 2021 base vs Census S3, L&SC LTLAs\n"
        "LTLA × 6 ethnic groups × sex × 10-year band (log scales)",
        color=INK,
        fontsize=10,
        loc="left",
    )
    fig.tight_layout()
    paths.append(fig_dir / "fig1_base_vs_seed.png")
    fig.savefig(paths[-1], dpi=150)
    plt.close(fig)

    # Fig 2: static vs cohort % difference by age band, focus ICB, 6 groups (direct-labelled).
    s = pd.read_csv(run / "sensitivity_variants.csv")
    alt = "static" if cfg.variant == "cohort" else "cohort"
    t = s[(s["variant"] == alt) & (s["geography"] == "Focus ICB")]
    t = t.groupby(["age_band", "eth6"])[["population", "default"]].sum().reset_index()
    t["pct"] = (t["population"] / t["default"] - 1) * 100
    bands = sorted(t["age_band"].unique(), key=lambda b: int(b.split("-")[0].rstrip("+")))
    fig, ax = plt.subplots(figsize=(7.6, 4.8), facecolor=SURFACE)
    _style(ax)
    ax.axhline(0, color=INK2, linewidth=1)
    ends = {}
    for i, code in enumerate(order6):
        y = t[t["eth6"] == code].set_index("age_band").reindex(bands)["pct"]
        ax.plot(
            range(len(bands)),
            y,
            color=SERIES[i],
            linewidth=2,
            marker="o",
            markersize=4,
            label=short[code],
        )
        ends[code] = float(y.iloc[-1])
    # Direct labels at the line ends, nudged apart so they never overlap.
    gap, placed = float(t["pct"].max() - t["pct"].min()) * 0.045, []
    for code, yv in sorted(ends.items(), key=lambda kv: kv[1]):
        y_lab = max(yv, placed[-1] + gap) if placed else yv
        placed.append(y_lab)
        ax.annotate(
            short[code],
            (len(bands) - 1, yv),
            xytext=(len(bands) - 0.75, y_lab),
            color=INK,
            fontsize=8,
            va="center",
        )
    ax.set_xticks(range(len(bands)), bands)
    ax.set_xlim(-0.3, len(bands) + 0.9)
    ax.set_ylabel(f"% difference, {alt} vs {cfg.variant}", color=INK)
    ax.set_xlabel(f"Age band (mid-{cfg.reference_year})", color=INK)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="lower left", labelcolor=INK)
    ax.set_title(
        f"Figure 2. Effect of {alt} vs {cfg.variant} ethnic shares, L&SC ICB, "
        f"mid-{cfg.reference_year}",
        color=INK,
        fontsize=10,
        loc="left",
    )
    fig.tight_layout()
    paths.append(fig_dir / "fig2_cohort_vs_static.png")
    fig.savefig(paths[-1], dpi=150)
    plt.close(fig)

    # Fig 3: modelled vs OHID % non-White British-equivalent ("not White") per trust, FPTP.
    e = pd.read_csv(run / "trust_comparison_ethnicity.csv")
    e = e[e["selection_method"] == "First past the post"].dropna(subset=["ohid_pct_W"])
    e["mod"] = 100 - e["modelled_pct_W"]
    e["ohid"] = 100 - e["ohid_pct_W"]
    fig, ax = plt.subplots(figsize=(6.4, 5.6), facecolor=SURFACE)
    _style(ax)
    other = e[~e["trust_code"].isin(cfg.focus_trusts)]
    focus = e[e["trust_code"].isin(cfg.focus_trusts)]
    ax.scatter(
        other["ohid"],
        other["mod"],
        s=22,
        color=SERIES[0],
        alpha=0.6,
        linewidths=0,
        label="Other acute trusts",
    )
    ax.scatter(
        focus["ohid"],
        focus["mod"],
        s=48,
        color=SERIES[1],
        edgecolors=SURFACE,
        linewidths=2,
        label="OneLSC acute trusts",
        zorder=3,
    )
    for k, r in enumerate(focus.sort_values("ohid").itertuples()):
        dy = (-14, 10)[k % 2]  # alternate below/above so close points stay legible
        ax.annotate(
            r.trust_code,
            (r.ohid, r.mod),
            xytext=(10, dy),
            textcoords="offset points",
            color=INK,
            fontsize=8,
            arrowprops={"arrowstyle": "-", "color": INK2, "lw": 0.6},
        )
    m = float(max(e["ohid"].max(), e["mod"].max())) * 1.05
    ax.plot([0, m], [0, m], color=INK2, linewidth=1, linestyle="--")
    ax.set_xlabel("OHID T5: % not White (first past the post)", color=INK)
    ax.set_ylabel("Modelled: % not White", color=INK)
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK)
    ax.set_title(
        "Figure 3. Trust catchment ethnicity, modelled vs OHID (FPTP)",
        color=INK,
        fontsize=10,
        loc="left",
    )
    fig.tight_layout()
    paths.append(fig_dir / "fig3_trust_ethnicity_fptp.png")
    fig.savefig(paths[-1], dpi=150)
    plt.close(fig)
    _ = lab6
    return paths


def compare_runs(cfg: Config, a: Path, b: Path) -> dict:
    ha = json.loads((a / "output_hashes.json").read_text())
    hb = json.loads((b / "output_hashes.json").read_text())
    diff = sorted(k for k in set(ha) | set(hb) if ha.get(k) != hb.get(k))
    outputs = cfg.resolve(cfg.paths.outputs).resolve()

    def label(p: Path) -> str:  # run id only; never record absolute local paths
        p = p.resolve()
        return (
            p.name if p.parent == outputs else f"{p.name} (outside outputs/, e.g. a clean checkout)"
        )

    res = {
        "run_a": label(a),
        "run_b": label(b),
        "tables_compared": len(set(ha) | set(hb)),
        "identical": not diff,
        "differing_tables": diff,
    }
    (cfg.resolve(cfg.paths.outputs) / "reproducibility_check.json").write_text(
        json.dumps(res, indent=2) + "\n"
    )
    return res


def write_all(cfg: Config) -> list[Path]:
    paths = [write_data_sources(cfg), write_sensitivity(cfg), write_cli_reference(cfg)]
    for name, fn in (
        ("transformations.md", render_transformations),
        ("validation_report.md", render_validation_report),
    ):
        p = cfg.root / "docs" / name
        p.write_text(fn(cfg))
        paths.append(p)
    return paths + render_figures(cfg)


# --------------------------------------------------------------------------------------------
# CLI reference (README) — generated from the typer app so it can't drift from the code
# --------------------------------------------------------------------------------------------

CLI_START = "<!-- cli-reference:start (generated by `lsc-pop docs`; don't edit by hand) -->"
CLI_END = "<!-- cli-reference:end -->"


def render_cli_reference() -> str:
    import typer

    from lsc_pop.cli import STAGES, app

    commands = typer.main.get_command(app).commands  # name -> command, in registration order
    out = [CLI_START, ""]
    out += [
        "Run any command as `uv run lsc-pop <command> [options]` from the repo root, or "
        "`python -m lsc_pop <command>` inside the activated `.venv`. Every command accepts `--help`.",
        "",
    ]
    out += ["| Command | What it does |", "|---|---|"]
    for name, cmd in commands.items():
        out.append(f"| `lsc-pop {name}` | {(cmd.help or '').strip().splitlines()[0]} |")
    for name, cmd in commands.items():
        out += ["", f"#### `lsc-pop {name}`", "", (cmd.help or "").strip(), ""]
        rows = []
        for p in cmd.params:
            if p.name == "help":
                continue
            if p.param_type_name == "argument":
                rows.append(
                    (f"`{p.name.upper()}` (argument)", getattr(p, "help", "") or "", "required")
                )
                continue
            opts = ", ".join(f"`{o}`" for o in p.opts + p.secondary_opts)
            if p.name == "config":
                default = "`config/config.yaml`"
            elif p.is_flag:
                default = "off"
            elif p.default is None or isinstance(p.default, (list, tuple)):
                default = "–"
            else:
                default = f"`{p.default}`"
            rows.append((opts, (p.help or "").strip(), default))
        if rows:
            out += ["| Option | Description | Default |", "|---|---|---|"]
            out += [f"| {o} | {h} | {d} |" for o, h, d in rows]
    out += [
        "",
        "**Stages** (for `lsc-pop run --stage`), in run order:",
        "",
        "| Stage | Step |",
        "|---|---|",
    ]
    out += [f"| `{s.key}` | {s.title} |" for s in STAGES]
    out += ["", CLI_END]
    return "\n".join(out)


def write_cli_reference(cfg: Config) -> Path:
    path = cfg.root / "README.md"
    text = path.read_text()
    if CLI_START not in text or CLI_END not in text:
        raise ValueError("README.md lacks the cli-reference markers")
    i, j = text.index(CLI_START), text.index(CLI_END) + len(CLI_END)
    path.write_text(text[:i] + render_cli_reference() + text[j:])
    return path
