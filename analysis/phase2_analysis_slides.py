from __future__ import annotations

import json
import math
import os
from pathlib import Path

TMP_DIR = Path("/tmp/codex-mpl-cache")
TMP_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(TMP_DIR))
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from statsmodels.stats.anova import AnovaRM
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[1]
PHASE1_DIR = ROOT / "output" / "phase1"
PHASE2_DIR = ROOT / "output" / "phase2_slides"
TABLE_DIR = ROOT / "report" / "tables_phase2_slides"
FIG_DIR = ROOT / "report" / "figures_phase2_slides"

CONDITION_ORDER = ["item_only", "both", "task_only"]
BOUNDARY_ORDER = ["post", "mid", "pre"]
ITEM_ROLE_ORDER = ["target", "lure", "foil"]

CONDITION_LABELS = {
    "item_only": "Item Shift Only",
    "both": "Item + Task Shift",
    "task_only": "Task Shift Only",
}


def ensure_dirs() -> None:
    for path in (PHASE2_DIR, TABLE_DIR, FIG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def set_plot_theme() -> None:
    sns.set_theme(style="whitegrid", context="talk")
    plt.rcParams.update(
        {
            "figure.dpi": 180,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.labelsize": 12,
            "axes.titlesize": 14,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
        }
    )


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    test_trials = pd.read_csv(PHASE1_DIR / "test_trials.csv")
    participant_level = pd.read_csv(PHASE1_DIR / "participant_level_metrics.csv")

    test_trials["condition"] = pd.Categorical(test_trials["condition"], CONDITION_ORDER, ordered=True)
    test_trials["test_boundary_position"] = pd.Categorical(
        test_trials["test_boundary_position"], [*BOUNDARY_ORDER, "foil"], ordered=True
    )
    test_trials["item_role"] = pd.Categorical(test_trials["item_role"], ITEM_ROLE_ORDER, ordered=True)
    test_trials["correct_int"] = test_trials["correct"].astype(int)
    test_trials["response_rt"] = pd.to_numeric(test_trials["response_rt"], errors="coerce")
    test_trials["log_response_rt"] = np.log(test_trials["response_rt"].where(test_trials["response_rt"] > 0))

    participant_level["condition"] = pd.Categorical(participant_level["condition"], CONDITION_ORDER, ordered=True)
    return test_trials, participant_level


def run_qc(test_trials: pd.DataFrame, participant_level: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for var in ["correct", "response_label", "response_rt", "test_boundary_position", "item_role", "lure_bin"]:
        rows.append(
            {
                "check": "missingness_test_trials",
                "variable": var,
                "n_missing": int(test_trials[var].isna().sum()),
                "pct_missing": float(test_trials[var].isna().mean()),
            }
        )

    rows.append(
        {
            "check": "missingness_participant_level",
            "variable": "encoding_task_accuracy",
            "n_missing": int(participant_level["encoding_task_accuracy"].isna().sum()),
            "pct_missing": float(participant_level["encoding_task_accuracy"].isna().mean()),
        }
    )

    rt = test_trials["response_rt"]
    rows.append(
        {
            "check": "rt_artifacts",
            "variable": "response_rt",
            "n_missing": int(rt.isna().sum()),
            "pct_missing": float(rt.isna().mean()),
            "n_very_fast_lt_0.2": int((rt < 0.2).sum()),
            "n_very_slow_gt_30": int((rt > 30).sum()),
        }
    )

    participant_mean_rt = (
        test_trials.groupby("participant_uid", observed=True)["response_rt"].mean().replace(0, np.nan).dropna()
    )
    if len(participant_mean_rt) >= 3:
        log_rt = np.log(participant_mean_rt)
        stat, p_value = stats.shapiro(log_rt)
        rows.append(
            {
                "check": "normality_shapiro",
                "variable": "participant_mean_log_rt",
                "statistic": float(stat),
                "p_value": float(p_value),
                "n": int(len(log_rt)),
            }
        )

    return pd.DataFrame(rows)


def build_target_correctness_means(test_trials: pd.DataFrame) -> pd.DataFrame:
    target = test_trials.loc[
        (test_trials["item_role"] == "target")
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
    ].copy()
    means = (
        target.groupby(["participant_uid", "condition", "test_boundary_position"], observed=True)["correct_int"]
        .mean()
        .reset_index()
    )
    return means


def build_rt_means(test_trials: pd.DataFrame) -> pd.DataFrame:
    working = test_trials.loc[
        test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
        & test_trials["item_role"].isin(["target", "lure"])
        & test_trials["responded"]
        & test_trials["log_response_rt"].notna()
    ].copy()
    means = (
        working.groupby(["participant_uid", "condition", "test_boundary_position"], observed=True)["log_response_rt"]
        .mean()
        .reset_index()
    )
    return means


def run_within_condition_tests(
    participant_means: pd.DataFrame,
    value_col: str,
    analysis_family: str,
    pairwise_test: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    omnibus_rows: list[dict[str, object]] = []
    pairwise_rows: list[dict[str, object]] = []

    for condition in CONDITION_ORDER:
        subset = participant_means.loc[participant_means["condition"] == condition].copy()
        pivot = subset.pivot(index="participant_uid", columns="test_boundary_position", values=value_col)
        pivot = pivot.reindex(columns=BOUNDARY_ORDER).dropna()
        if len(pivot) < 3:
            continue

        long_df = pivot.reset_index().melt(
            id_vars="participant_uid",
            value_vars=BOUNDARY_ORDER,
            var_name="boundary_position",
            value_name="value",
        )
        anova = AnovaRM(long_df, depvar="value", subject="participant_uid", within=["boundary_position"]).fit()
        effect_row = anova.anova_table.reset_index().iloc[0]

        friedman_stat, friedman_p = stats.friedmanchisquare(pivot["post"], pivot["mid"], pivot["pre"])
        kendall_w = float(friedman_stat) / (len(pivot) * (len(BOUNDARY_ORDER) - 1))

        omnibus_rows.append(
            {
                "analysis_family": analysis_family,
                "condition": condition,
                "condition_label": CONDITION_LABELS[condition],
                "n": int(len(pivot)),
                "anova_f": float(effect_row["F Value"]),
                "anova_num_df": float(effect_row["Num DF"]),
                "anova_den_df": float(effect_row["Den DF"]),
                "anova_p_value": float(effect_row["Pr > F"]),
                "friedman_chi2": float(friedman_stat),
                "friedman_p_value": float(friedman_p),
                "kendall_w": float(kendall_w),
            }
        )

        raw_pvals: list[float] = []
        buffered_results: list[dict[str, object]] = []
        for left, right in [("post", "mid"), ("post", "pre"), ("mid", "pre")]:
            diff = pivot[left] - pivot[right]
            t_stat, p_value = stats.ttest_rel(pivot[left], pivot[right])
            dz = diff.mean() / diff.std(ddof=1) if len(diff) > 1 and diff.std(ddof=1) > 0 else math.nan
            raw_pvals.append(float(p_value))
            buffered_results.append(
                {
                    "analysis_family": analysis_family,
                    "condition": condition,
                    "condition_label": CONDITION_LABELS[condition],
                    "contrast": f"{left} - {right}",
                    "test": pairwise_test,
                    "n": int(len(diff)),
                    "mean_difference": float(diff.mean()),
                    "t_value": float(t_stat),
                    "p_value": float(p_value),
                    "cohens_dz": float(dz) if pd.notna(dz) else math.nan,
                }
            )

        reject, holm_pvals, _, _ = multipletests(raw_pvals, method="holm")
        holm_pvals = np.atleast_1d(holm_pvals)
        reject = np.atleast_1d(reject)
        for row, holm_p, holm_reject in zip(buffered_results, holm_pvals, reject):
            row["p_value_holm"] = float(holm_p)
            row["reject_holm"] = bool(holm_reject)
            pairwise_rows.append(row)

    return pd.DataFrame(omnibus_rows), pd.DataFrame(pairwise_rows)


def response_profile_tests(test_trials: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    working = test_trials.loc[test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)].copy()

    for condition in CONDITION_ORDER:
        for item_role in ["target", "lure"]:
            subset = working.loc[(working["condition"] == condition) & (working["item_role"] == item_role)]
            contingency = pd.crosstab(subset["test_boundary_position"], subset["response_label"])
            if contingency.shape[0] < 2 or contingency.shape[1] < 2:
                continue
            chi2, p_value, dof, _ = stats.chi2_contingency(contingency)
            n = contingency.to_numpy().sum()
            min_dim = min(contingency.shape[0] - 1, contingency.shape[1] - 1)
            cramer_v = math.sqrt(chi2 / (n * min_dim)) if min_dim > 0 else math.nan
            rows.append(
                {
                    "analysis_family": "response_profile_chi_square",
                    "condition": condition,
                    "condition_label": CONDITION_LABELS[condition],
                    "item_role": item_role,
                    "chi2": float(chi2),
                    "dof": int(dof),
                    "p_value": float(p_value),
                    "cramers_v": float(cramer_v),
                    "n": int(n),
                }
            )

    return pd.DataFrame(rows)


def lure_bin_summary(test_trials: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    lure = test_trials.loc[
        (test_trials["item_role"] == "lure")
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
        & test_trials["lure_bin"].notna()
    ].copy()
    lure["similar_resp"] = lure["response_label"].eq("similar").astype(float)

    summary = (
        lure.groupby(["condition", "test_boundary_position", "lure_bin"], observed=True)["similar_resp"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "p_similar", "count": "n_trials"})
    )

    correlation_rows: list[dict[str, object]] = []
    for condition in CONDITION_ORDER:
        for boundary in BOUNDARY_ORDER:
            subset = lure.loc[
                (lure["condition"] == condition) & (lure["test_boundary_position"] == boundary),
                ["participant_uid", "lure_bin", "similar_resp"],
            ]
            participant_bin_means = (
                subset.groupby(["participant_uid", "lure_bin"], observed=True)["similar_resp"].mean().reset_index()
            )
            if participant_bin_means["lure_bin"].nunique() < 2 or len(participant_bin_means) < 3:
                continue
            rho, p_value = stats.spearmanr(participant_bin_means["lure_bin"], participant_bin_means["similar_resp"])
            correlation_rows.append(
                {
                    "analysis_family": "lure_bin_spearman",
                    "condition": condition,
                    "condition_label": CONDITION_LABELS[condition],
                    "boundary_position": boundary,
                    "spearman_rho": float(rho),
                    "p_value": float(p_value),
                    "n": int(len(participant_bin_means)),
                }
            )

    return summary, pd.DataFrame(correlation_rows)


def plot_target_correctness(participant_means: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14, 5), sharey=True)
    colors = sns.color_palette("Set2", 3)

    for ax, condition, color in zip(axes, CONDITION_ORDER, colors):
        sub = participant_means.loc[participant_means["condition"] == condition]
        ax.scatter(
            sub["test_boundary_position"].astype(str),
            sub["correct_int"],
            alpha=0.25,
            s=18,
            color=color,
            zorder=2,
        )
        sns.pointplot(
            data=sub,
            x="test_boundary_position",
            y="correct_int",
            order=BOUNDARY_ORDER,
            color=color,
            errorbar=("ci", 95),
            markers="D",
            linestyles="-",
            capsize=0.1,
            ax=ax,
        )
        ax.set_title(CONDITION_LABELS[condition])
        ax.set_xlabel("Boundary position")
        ax.set_ylim(0, 1.05)

    axes[0].set_ylabel("Target correctness")
    axes[1].set_ylabel("")
    axes[2].set_ylabel("")
    fig.suptitle("Target correctness by boundary")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "phase2_slides_target_correctness_by_boundary.png")
    plt.close(fig)


def plot_rt(participant_means: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14, 5), sharey=True)
    colors = sns.color_palette("Set2", 3)

    for ax, condition, color in zip(axes, CONDITION_ORDER, colors):
        sub = participant_means.loc[participant_means["condition"] == condition]
        ax.scatter(
            sub["test_boundary_position"].astype(str),
            sub["log_response_rt"],
            alpha=0.25,
            s=18,
            color=color,
            zorder=2,
        )
        sns.pointplot(
            data=sub,
            x="test_boundary_position",
            y="log_response_rt",
            order=BOUNDARY_ORDER,
            color=color,
            errorbar=("ci", 95),
            markers="D",
            linestyles="-",
            capsize=0.1,
            ax=ax,
        )
        ax.set_title(CONDITION_LABELS[condition])
        ax.set_xlabel("Boundary position")

    axes[0].set_ylabel("Mean log RT")
    axes[1].set_ylabel("")
    axes[2].set_ylabel("")
    fig.suptitle("Test RT by boundary")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "phase2_slides_test_rt_by_boundary.png")
    plt.close(fig)


def plot_lure_bins(summary: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    palette = {"post": "#d1495b", "mid": "#6c8b8b", "pre": "#edae49"}

    for ax, condition in zip(axes, CONDITION_ORDER):
        sub = summary.loc[summary["condition"] == condition]
        sns.pointplot(
            data=sub,
            x="lure_bin",
            y="p_similar",
            hue="test_boundary_position",
            hue_order=BOUNDARY_ORDER,
            palette=palette,
            errorbar=None,
            ax=ax,
        )
        ax.set_title(CONDITION_LABELS[condition])
        ax.set_xlabel("Lure bin")
        ax.set_ylim(0, 1)
        if ax is not axes[0]:
            ax.get_legend().remove()

    axes[0].set_ylabel("P(similar)")
    axes[1].set_ylabel("")
    axes[2].set_ylabel("")
    axes[0].legend(title="Boundary")
    fig.suptitle("Lure-bin descriptive summary")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "phase2_slides_lure_bins.png")
    plt.close(fig)


def write_registry() -> pd.DataFrame:
    rows = [
        {
            "analysis_name": "target_correctness_within_condition",
            "method": "Repeated-measures ANOVA + Friedman + Holm-corrected paired t-tests",
            "role": "primary",
        },
        {
            "analysis_name": "test_rt_within_condition",
            "method": "Repeated-measures ANOVA + Friedman + Holm-corrected paired t-tests",
            "role": "primary_secondary",
        },
        {
            "analysis_name": "response_profile",
            "method": "Chi-square test of independence + Cramer's V",
            "role": "secondary",
        },
        {
            "analysis_name": "lure_bin",
            "method": "Descriptive boundary-wise summary + Spearman correlation",
            "role": "secondary",
        },
    ]
    return pd.DataFrame(rows)


def save_outputs(
    qc_summary: pd.DataFrame,
    target_omnibus: pd.DataFrame,
    target_pairwise: pd.DataFrame,
    rt_omnibus: pd.DataFrame,
    rt_pairwise: pd.DataFrame,
    response_profile: pd.DataFrame,
    lure_summary: pd.DataFrame,
    lure_corr: pd.DataFrame,
    registry: pd.DataFrame,
) -> None:
    qc_summary.to_csv(PHASE2_DIR / "qc_summary.csv", index=False)
    registry.to_csv(PHASE2_DIR / "analysis_registry.csv", index=False)
    target_omnibus.to_csv(TABLE_DIR / "phase2_slides_target_correctness_omnibus.csv", index=False)
    target_pairwise.to_csv(TABLE_DIR / "phase2_slides_target_correctness_pairwise.csv", index=False)
    rt_omnibus.to_csv(TABLE_DIR / "phase2_slides_test_rt_omnibus.csv", index=False)
    rt_pairwise.to_csv(TABLE_DIR / "phase2_slides_test_rt_pairwise.csv", index=False)
    response_profile.to_csv(TABLE_DIR / "phase2_slides_response_profile_chisq.csv", index=False)
    lure_summary.to_csv(TABLE_DIR / "phase2_slides_lure_bin_summary.csv", index=False)
    lure_corr.to_csv(TABLE_DIR / "phase2_slides_lure_bin_spearman.csv", index=False)

    notes = {
        "positioning": [
            "This script is the slide-aligned Phase 2 analysis.",
            "Primary analyses are participant-level and match class-taught methods.",
            "Advanced clustered models from phase2_analysis.py are intentionally omitted here.",
        ],
        "methods_kept": [
            "Repeated-measures ANOVA",
            "Friedman test",
            "Holm-corrected paired t-tests",
            "Chi-square with Cramer's V",
            "Spearman correlation for lure-bin trend",
        ],
        "methods_removed": [
            "GEE",
            "mixed-model fallback logic",
            "trial-level carryover GLM/GEE",
            "robustness reruns as primary evidence",
        ],
    }
    with (PHASE2_DIR / "analysis_notes.json").open("w", encoding="utf-8") as handle:
        json.dump(notes, handle, indent=2)


def main() -> None:
    ensure_dirs()
    set_plot_theme()

    test_trials, participant_level = load_data()
    qc_summary = run_qc(test_trials, participant_level)

    target_means = build_target_correctness_means(test_trials)
    rt_means = build_rt_means(test_trials)

    target_omnibus, target_pairwise = run_within_condition_tests(
        participant_means=target_means,
        value_col="correct_int",
        analysis_family="target_correctness",
        pairwise_test="paired_t",
    )
    rt_omnibus, rt_pairwise = run_within_condition_tests(
        participant_means=rt_means,
        value_col="log_response_rt",
        analysis_family="test_rt",
        pairwise_test="paired_t",
    )

    response_profile = response_profile_tests(test_trials)
    lure_summary, lure_corr = lure_bin_summary(test_trials)

    plot_target_correctness(target_means)
    plot_rt(rt_means)
    plot_lure_bins(lure_summary)

    registry = write_registry()
    save_outputs(
        qc_summary=qc_summary,
        target_omnibus=target_omnibus,
        target_pairwise=target_pairwise,
        rt_omnibus=rt_omnibus,
        rt_pairwise=rt_pairwise,
        response_profile=response_profile,
        lure_summary=lure_summary,
        lure_corr=lure_corr,
        registry=registry,
    )

    print("Saved slide-aligned Phase 2 outputs to", PHASE2_DIR)
    print("Saved slide-aligned Phase 2 tables to", TABLE_DIR)
    print("Saved slide-aligned Phase 2 figures to", FIG_DIR)


if __name__ == "__main__":
    main()
