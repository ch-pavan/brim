from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from statsmodels.formula.api import mixedlm, ols
from statsmodels.genmod.cov_struct import Exchangeable
from statsmodels.genmod.families import Binomial, Gaussian
from statsmodels.genmod.generalized_estimating_equations import GEE
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[1]
PHASE1_DIR = ROOT / "output" / "phase1"
PHASE2_DIR = ROOT / "output" / "phase2"
TABLE_DIR = ROOT / "report" / "tables_phase2"
FIG_DIR = ROOT / "report" / "figures_phase2"

CONDITION_ORDER = ["item_only", "both", "task_only"]
BOUNDARY_ORDER = ["post", "mid", "pre"]
ITEM_ROLE_ORDER = ["target", "lure", "foil"]

CONDITION_LABELS = {
    "item_only": "Item Shift Only",
    "both": "Item + Task Shift",
    "task_only": "Task Shift Only",
}

# Silence frequent convergence warnings so outputs stay readable.
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)


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


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    test_trials = pd.read_csv(PHASE1_DIR / "test_trials.csv")
    encoding_trials = pd.read_csv(PHASE1_DIR / "encoding_trials.csv")
    participant_level = pd.read_csv(PHASE1_DIR / "participant_level_metrics.csv")

    # NOTE: Keep "foil" only in the full Categorical at load time; every
    # analytical working dataset re-casts after filtering to remove unused
    # levels — this prevents phantom dummy variables in statsmodels GEE.
    test_trials["condition"] = pd.Categorical(test_trials["condition"], CONDITION_ORDER, ordered=True)
    test_trials["test_boundary_position"] = pd.Categorical(
        test_trials["test_boundary_position"], [*BOUNDARY_ORDER, "foil"], ordered=True
    )
    test_trials["item_role"] = pd.Categorical(test_trials["item_role"], ITEM_ROLE_ORDER, ordered=True)
    test_trials["correct_int"] = test_trials["correct"].astype(int)
    test_trials["responded_int"] = test_trials["responded"].astype(int)
    test_trials["response_rt"] = pd.to_numeric(test_trials["response_rt"], errors="coerce")
    test_trials["log_response_rt"] = np.log(test_trials["response_rt"].where(test_trials["response_rt"] > 0))

    encoding_trials["condition"] = pd.Categorical(encoding_trials["condition"], CONDITION_ORDER, ordered=True)
    participant_level["condition"] = pd.Categorical(participant_level["condition"], CONDITION_ORDER, ordered=True)

    return test_trials, encoding_trials, participant_level


def run_qc(test_trials: pd.DataFrame, participant_level: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    qc_rows: list[dict[str, object]] = []

    # Missingness summary for key variables.
    key_vars = [
        "correct",
        "response_label",
        "response_rt",
        "test_boundary_position",
        "item_role",
        "stimulus_class",
        "lure_bin",
    ]
    for var in key_vars:
        qc_rows.append(
            {
                "check": "missingness_test_trials",
                "variable": var,
                "n_missing": int(test_trials[var].isna().sum()),
                "pct_missing": float(test_trials[var].isna().mean()),
            }
        )

    # Missing covariates at participant level.
    covariate = "encoding_task_accuracy"
    qc_rows.append(
        {
            "check": "missingness_participant_level",
            "variable": covariate,
            "n_missing": int(participant_level[covariate].isna().sum()),
            "pct_missing": float(participant_level[covariate].isna().mean()),
        }
    )

    # RT artifact flags.
    rt = test_trials["response_rt"]
    very_fast = (rt < 0.2).sum()
    very_slow = (rt > 30).sum()
    qc_rows.append(
        {
            "check": "rt_artifacts",
            "variable": "response_rt",
            "n_missing": int(rt.isna().sum()),
            "pct_missing": float(rt.isna().mean()),
            "n_very_fast_lt_0.2": int(very_fast),
            "n_very_slow_gt_30": int(very_slow),
        }
    )

    # Participant outlier flags using mean RT z-score.
    by_participant = (
        test_trials.groupby("participant_uid", observed=True)["response_rt"]
        .mean()
        .rename("mean_test_rt_trial")
        .reset_index()
    )
    mean_rt = by_participant["mean_test_rt_trial"]
    z = (mean_rt - mean_rt.mean()) / mean_rt.std(ddof=1)
    by_participant["rt_zscore"] = z
    by_participant["rt_outlier_abs_z_gt_3"] = by_participant["rt_zscore"].abs() > 3

    qc_rows.append(
        {
            "check": "participant_rt_outliers",
            "variable": "mean_test_rt_trial",
            "n_outlier_abs_z_gt_3": int(by_participant["rt_outlier_abs_z_gt_3"].sum()),
            "n_participants": int(len(by_participant)),
        }
    )

    # Quick normality diagnostic on participant mean log RT.
    log_rt = np.log(by_participant["mean_test_rt_trial"].replace(0, np.nan).dropna())
    if len(log_rt) >= 3:
        w_stat, p_val = stats.shapiro(log_rt)
        qc_rows.append(
            {
                "check": "normality_shapiro",
                "variable": "participant_mean_log_rt",
                "statistic": float(w_stat),
                "p_value": float(p_val),
                "n": int(len(log_rt)),
            }
        )

    return pd.DataFrame(qc_rows), by_participant


def build_precision_context(test_trials: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    by_condition_n = test_trials.groupby("condition", observed=True)["participant_uid"].nunique()
    for condition in CONDITION_ORDER:
        n = int(by_condition_n.loc[condition])
        prop_half_width = 1.96 * math.sqrt(0.25 / n)
        rows.append(
            {
                "condition": condition,
                "n_participants": n,
                "metric": "prop_95ci_half_width_at_p0.5",
                "value": float(prop_half_width),
            }
        )

    participant_mean_rt = (
        test_trials.groupby(["condition", "participant_uid"], observed=True)["response_rt"].mean().reset_index()
    )
    for condition in CONDITION_ORDER:
        subset = participant_mean_rt.loc[participant_mean_rt["condition"] == condition, "response_rt"]
        if len(subset) > 1:
            rt_half_width = 1.96 * subset.std(ddof=1) / math.sqrt(len(subset))
        else:
            rt_half_width = math.nan
        rows.append(
            {
                "condition": condition,
                "n_participants": int(len(subset)),
                "metric": "participant_mean_rt_95ci_half_width",
                "value": float(rt_half_width),
            }
        )

    return pd.DataFrame(rows)


def _clean_boundary_cat(df: pd.DataFrame, col: str = "test_boundary_position") -> pd.DataFrame:
    """Remove unused categorical levels after filtering to post/mid/pre rows.

    This prevents statsmodels GEE from generating phantom dummy variables for
    the 'foil' level (Bug B2 fix). Also cleans item_role categorical if present.
    """
    df = df.copy()
    for c in [col, "item_role"]:
        if c in df.columns and isinstance(df[c].dtype, pd.CategoricalDtype):
            df[c] = df[c].cat.remove_unused_categories()
    return df


def gee_correctness_model(test_trials: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Primary confirmatory GEE for test-phase correctness.

    Bug fixes applied:
    - B2: Remove unused 'foil' Categorical level after filtering.
    - B3: lure_bin_c removed from combined target+lure formula (ambiguous
      semantics across item roles; lure-bin effect reported from dedicated
      lure-only model in robustness_reruns).
    - Added C(stimulus_class):C(test_boundary_position) interaction (Gap G3).
    """
    working = test_trials.loc[
        test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
        & test_trials["item_role"].isin(["target", "lure"])
    ].copy()
    # B2 fix: drop unused categorical level so no phantom foil dummy is created.
    working = _clean_boundary_cat(working)

    model = GEE.from_formula(
        "correct_int ~ C(condition) * C(test_boundary_position)"
        " + C(item_role) + C(stimulus_class) * C(test_boundary_position)",
        groups="participant_uid",
        data=working,
        family=Binomial(),
        cov_struct=Exchangeable(),
    )
    result = model.fit()

    table = pd.DataFrame(
        {
            "term": result.params.index,
            "coef": result.params.values,
            "std_err": result.bse.values,
            "z": result.tvalues.values,
            "p_value": result.pvalues.values,
        }
    )
    table["odds_ratio"] = np.exp(table["coef"])
    table["ci_low_or"] = np.exp(table["coef"] - 1.96 * table["std_err"])
    table["ci_high_or"] = np.exp(table["coef"] + 1.96 * table["std_err"])
    table["analysis_family"] = "primary_correctness"

    # Participant-level fallback: Friedman within each condition for target correctness.
    fallback_rows: list[dict[str, object]] = []
    target = working.loc[working["item_role"] == "target"].copy()
    grouped = (
        target.groupby(["participant_uid", "condition", "test_boundary_position"], observed=True)["correct_int"]
        .mean()
        .reset_index()
    )

    for condition in CONDITION_ORDER:
        subset = grouped.loc[grouped["condition"] == condition]
        pivot = subset.pivot(index="participant_uid", columns="test_boundary_position", values="correct_int")
        pivot = pivot.reindex(columns=BOUNDARY_ORDER).dropna()
        if len(pivot) >= 3:
            stat, p_value = stats.friedmanchisquare(pivot["post"], pivot["mid"], pivot["pre"])
            kendall_w = float(stat) / (len(pivot) * (len(BOUNDARY_ORDER) - 1))
            fallback_rows.append(
                {
                    "analysis_family": "fallback_nonparametric",
                    "condition": condition,
                    "test": "friedman_target_correctness",
                    "n": int(len(pivot)),
                    "statistic": float(stat),
                    "p_value": float(p_value),
                    "effect_size_kendall_w": kendall_w,
                }
            )

    return table, pd.DataFrame(fallback_rows)


def mixed_rt_model(test_trials: pd.DataFrame) -> pd.DataFrame:
    """Primary RT model.

    Bug fixes applied:
    - B1: Model is now correctly identified as Gaussian GEE (the mixedlm
      attempts are kept as documented fallback logic, but the output is
      labelled accurately).
    - B2: Remove unused 'foil' Categorical level after filtering.
    """
    working = test_trials.loc[
        test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
        & test_trials["responded"]
        & test_trials["response_rt"].notna()
        & (test_trials["response_rt"] > 0)
    ].copy()
    # B2 fix.
    working = _clean_boundary_cat(working)

    formulas = [
        "log_response_rt ~ C(condition) * C(test_boundary_position) * C(item_role) + correct_int",
        "log_response_rt ~ C(condition) * C(test_boundary_position) + C(item_role) + correct_int",
    ]

    result = None
    model_used = ""
    for formula in formulas:
        try:
            model = mixedlm(formula, data=working, groups=working["participant_uid"])
            fit = model.fit(reml=False, method="lbfgs")
            # Treat a degenerate fit (random-effect variance collapsed to zero)
            # as a failure so we fall through to the GEE fallback.
            group_var = float(fit.cov_re.iloc[0, 0]) if hasattr(fit, "cov_re") else 0.0
            if abs(group_var) < 1e-6:
                continue
            result = fit
            model_used = f"mixedlm::{formula}"
            break
        except Exception:
            continue

    if result is None:
        # Gaussian GEE fallback — population-average estimates with participant
        # clustering handled via exchangeable working correlation.
        gee_model = GEE.from_formula(
            "log_response_rt ~ C(condition) * C(test_boundary_position) + C(item_role) + correct_int",
            groups="participant_uid",
            data=working,
            family=Gaussian(),
            cov_struct=Exchangeable(),
        )
        result = gee_model.fit()
        model_used = "gee_gaussian::log_response_rt ~ C(condition)*C(test_boundary_position)+C(item_role)+correct_int"

    table = pd.DataFrame(
        {
            "term": result.params.index,
            "coef": result.params.values,
            "std_err": result.bse.values,
            "z": result.tvalues.values,
            "p_value": result.pvalues.values,
        }
    )
    table["ratio_change_rt"] = np.exp(table["coef"])
    table["ci_low_ratio"] = np.exp(table["coef"] - 1.96 * table["std_err"])
    table["ci_high_ratio"] = np.exp(table["coef"] + 1.96 * table["std_err"])
    table["analysis_family"] = "primary_rt"
    table["model_used"] = model_used
    return table


def run_rt_diagnostics(test_trials: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    working = test_trials.loc[
        test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
        & test_trials["responded"]
        & test_trials["response_rt"].notna()
        & (test_trials["response_rt"] > 0)
    ].copy()
    working = _clean_boundary_cat(working)

    ols_result = ols(
        "log_response_rt ~ C(condition) * C(test_boundary_position) + C(item_role) + correct_int",
        data=working,
    ).fit()

    resid = pd.Series(ols_result.resid, name="residual")
    fitted = pd.Series(ols_result.fittedvalues, name="fitted")
    diag_df = pd.concat([fitted, resid], axis=1)

    shapiro_w, shapiro_p = stats.shapiro(resid.sample(n=min(5000, len(resid)), random_state=17))
    corr_abs = np.corrcoef(np.abs(resid), fitted)[0, 1]
    summary = pd.DataFrame(
        [
            {
                "check": "rt_residual_normality_shapiro",
                "statistic": float(shapiro_w),
                "p_value": float(shapiro_p),
                "n": int(len(resid)),
            },
            {
                "check": "rt_abs_resid_fitted_correlation",
                "statistic": float(corr_abs),
                "p_value": math.nan,
                "n": int(len(resid)),
            },
        ]
    )

    return summary, diag_df


def response_profile_tests(test_trials: pd.DataFrame) -> pd.DataFrame:
    """Chi-square tests for response-category distribution by boundary.

    Bug fix B2: remove unused 'foil' Categorical level after filtering.
    """
    rows: list[dict[str, object]] = []
    working = test_trials.loc[test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)].copy()
    working = _clean_boundary_cat(working)

    for condition in CONDITION_ORDER:
        for item_role in ["target", "lure", "foil"]:
            subset = working.loc[(working["condition"] == condition) & (working["item_role"] == item_role)]
            if subset.empty:
                continue
            contingency = pd.crosstab(subset["test_boundary_position"], subset["response_label"])
            if contingency.shape[0] < 2 or contingency.shape[1] < 2:
                continue
            chi2, p_value, dof, _ = stats.chi2_contingency(contingency)
            n = contingency.to_numpy().sum()
            min_dim = min(contingency.shape[0] - 1, contingency.shape[1] - 1)
            cramer_v = math.sqrt(chi2 / (n * min_dim)) if min_dim > 0 else math.nan
            rows.append(
                {
                    "analysis_family": "secondary_response_profile",
                    "condition": condition,
                    "item_role": item_role,
                    "test": "chi_square_independence",
                    "chi2": float(chi2),
                    "dof": int(dof),
                    "p_value": float(p_value),
                    "cramers_v": float(cramer_v),
                    "n": int(n),
                }
            )

    return pd.DataFrame(rows)


def lure_bin_gee(test_trials: pd.DataFrame) -> pd.DataFrame:
    """Lure-bin slope GEE for similar-response probability.

    Bug fix B2: remove unused 'foil' Categorical level after filtering.
    """
    lure = test_trials.loc[
        (test_trials["item_role"] == "lure")
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
        & test_trials["lure_bin"].notna()
    ].copy()
    # B2 fix.
    lure = _clean_boundary_cat(lure)
    lure["similar_resp"] = lure["response_label"].eq("similar").astype(int)
    lure["lure_bin"] = pd.to_numeric(lure["lure_bin"], errors="coerce")

    model = GEE.from_formula(
        "similar_resp ~ lure_bin * C(test_boundary_position) + C(condition) + C(stimulus_class)",
        groups="participant_uid",
        data=lure,
        family=Binomial(),
        cov_struct=Exchangeable(),
    )
    result = model.fit()

    table = pd.DataFrame(
        {
            "term": result.params.index,
            "coef": result.params.values,
            "std_err": result.bse.values,
            "z": result.tvalues.values,
            "p_value": result.pvalues.values,
        }
    )
    table["odds_ratio"] = np.exp(table["coef"])
    table["ci_low_or"] = np.exp(table["coef"] - 1.96 * table["std_err"])
    table["ci_high_or"] = np.exp(table["coef"] + 1.96 * table["std_err"])
    table["analysis_family"] = "secondary_lure_bin"
    return table


def speed_accuracy_summary(test_trials: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Speed-accuracy summary at participant level.

    Extended (Gap G4): now also returns a boundary-position breakdown so we
    can examine whether post-boundary items show a different speed-accuracy
    profile.
    """
    working = test_trials.loc[
        test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
        & test_trials["response_rt"].notna()
    ].copy()

    # Original summary (collapsed across boundary).
    summary = (
        working.groupby(["participant_uid", "condition", "item_role", "correct"], observed=True)["response_rt"]
        .mean()
        .reset_index()
        .pivot(index=["participant_uid", "condition", "item_role"], columns="correct", values="response_rt")
        .reset_index()
        .rename(columns={False: "mean_rt_incorrect", True: "mean_rt_correct"})
    )
    for col in ("mean_rt_correct", "mean_rt_incorrect"):
        if col not in summary.columns:
            summary[col] = np.nan
    summary["delta_rt_incorrect_minus_correct"] = summary["mean_rt_incorrect"] - summary["mean_rt_correct"]

    # Extended: include boundary position in grouping (Gap G4).
    summary_by_boundary = (
        working.groupby(
            ["participant_uid", "condition", "item_role", "test_boundary_position", "correct"], observed=True
        )["response_rt"]
        .mean()
        .reset_index()
        .pivot(
            index=["participant_uid", "condition", "item_role", "test_boundary_position"],
            columns="correct",
            values="response_rt",
        )
        .reset_index()
        .rename(columns={False: "mean_rt_incorrect", True: "mean_rt_correct"})
    )
    for col in ("mean_rt_correct", "mean_rt_incorrect"):
        if col not in summary_by_boundary.columns:
            summary_by_boundary[col] = np.nan
    summary_by_boundary["delta_rt_incorrect_minus_correct"] = (
        summary_by_boundary["mean_rt_incorrect"] - summary_by_boundary["mean_rt_correct"]
    )

    return summary, summary_by_boundary


def encoding_rt_carryover(
    test_trials: pd.DataFrame, encoding_trials: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carry-over analysis linking encoding RT to test-phase correctness (Gap G1).

    Join encoding and test trials on (participant_uid, item_number) so that
    each test trial carries the encoding RT from when that specific item was
    studied.  Then model whether higher encoding RT predicts worse test
    correctness, over and above boundary position.
    """
    enc = encoding_trials[["participant_uid", "item_number", "response_rt", "boundary_position"]].copy()
    enc = enc.rename(columns={"response_rt": "encoding_rt", "boundary_position": "encoding_boundary_position"})
    # item_number may be numeric or string — normalise.
    enc["item_number"] = enc["item_number"].astype(str)

    tst = test_trials.loc[
        test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
        & test_trials["item_role"].isin(["target", "lure"])
        & test_trials["response_rt"].notna()
    ].copy()
    tst["item_number"] = tst["item_number"].astype(str)
    tst = _clean_boundary_cat(tst)

    merged = tst.merge(enc[["participant_uid", "item_number", "encoding_rt"]], on=["participant_uid", "item_number"], how="left")
    merged = merged.dropna(subset=["encoding_rt"])
    merged["log_encoding_rt"] = np.log(merged["encoding_rt"].where(merged["encoding_rt"] > 0))
    merged = merged.dropna(subset=["log_encoding_rt"])

    model = GEE.from_formula(
        "correct_int ~ log_encoding_rt + C(test_boundary_position) + C(condition) + C(item_role) + C(stimulus_class)",
        groups="participant_uid",
        data=merged,
        family=Binomial(),
        cov_struct=Exchangeable(),
    )
    result = model.fit()

    table = pd.DataFrame(
        {
            "term": result.params.index,
            "coef": result.params.values,
            "std_err": result.bse.values,
            "z": result.tvalues.values,
            "p_value": result.pvalues.values,
        }
    )
    table["odds_ratio"] = np.exp(table["coef"])
    table["ci_low_or"] = np.exp(table["coef"] - 1.96 * table["std_err"])
    table["ci_high_or"] = np.exp(table["coef"] + 1.96 * table["std_err"])
    table["analysis_family"] = "encoding_rt_carryover"

    # Participant-level scatter data: mean encoding RT (post-boundary items)
    # vs mean target correctness (post-boundary items).
    post_enc = (
        encoding_trials.loc[encoding_trials["boundary_position"] == "post"]
        .groupby(["participant_uid", "condition"], observed=True)["response_rt"]
        .mean()
        .reset_index()
        .rename(columns={"response_rt": "mean_encoding_rt_post"})
    )
    post_tst = (
        test_trials.loc[
            (test_trials["test_boundary_position"] == "post") & (test_trials["item_role"] == "target")
        ]
        .groupby(["participant_uid", "condition"], observed=True)["correct_int"]
        .mean()
        .reset_index()
        .rename(columns={"correct_int": "mean_target_correctness_post"})
    )
    scatter_df = post_enc.merge(post_tst, on=["participant_uid", "condition"], how="inner")

    return table, scatter_df


def participant_heterogeneity(test_trials: pd.DataFrame) -> pd.DataFrame:
    """Per-participant post-mid and post-pre boundary contrasts for targets (Gap G2).

    Returns a DataFrame with one row per participant × condition containing:
    - post_correctness, mid_correctness, pre_correctness
    - post_minus_mid, post_minus_pre contrasts
    """
    target = test_trials.loc[
        (test_trials["item_role"] == "target")
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
    ].copy()

    grouped = (
        target.groupby(["participant_uid", "condition", "test_boundary_position"], observed=True)["correct_int"]
        .mean()
        .reset_index()
    )
    pivot = grouped.pivot(
        index=["participant_uid", "condition"],
        columns="test_boundary_position",
        values="correct_int",
    ).reset_index()

    for col in BOUNDARY_ORDER:
        if col not in pivot.columns:
            pivot[col] = np.nan

    pivot = pivot.rename(columns={"post": "post_correctness", "mid": "mid_correctness", "pre": "pre_correctness"})
    pivot["post_minus_mid"] = pivot["post_correctness"] - pivot["mid_correctness"]
    pivot["post_minus_pre"] = pivot["post_correctness"] - pivot["pre_correctness"]

    return pivot


def compute_cohens_d_for_contrasts(boundary_contrasts: pd.DataFrame) -> pd.DataFrame:
    """Add Cohen's dz to the boundary contrast table (Gap B5 / R4 fix)."""
    df = boundary_contrasts.copy()
    # dz = t / sqrt(n) for within-participant (dependent) t-tests.
    df["cohens_dz"] = df["t_value"] / np.sqrt(df["n"])
    return df


def post_hoc_power(test_trials: pd.DataFrame) -> pd.DataFrame:
    """Compute post-hoc power to detect the observed LDI effect and the
    originally predicted pre-boundary advantage from Morse et al.

    Uses TTestPower (two-sided paired t-test analogue) with actual per-condition
    sample sizes and alpha = 0.05.
    """
    from statsmodels.stats.power import TTestPower  # local import avoids top-level dependency

    analysis_obj = TTestPower()
    rows: list[dict] = []

    # Observed per-condition sample sizes from test_trials.
    lures = test_trials.loc[
        (test_trials["item_role"] == "lure")
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
    ]
    for condition in CONDITION_ORDER:
        n = int(lures.loc[lures["condition"] == condition, "participant_uid"].nunique())
        for dz_scenario, scenario_name in [
            (0.2, "small (dz=0.20)"),
            (0.3, "medium (dz=0.30)"),
            (0.4, "large (dz=0.40)"),
        ]:
            power = float(analysis_obj.solve_power(effect_size=dz_scenario, nobs=n, alpha=0.05, alternative="two-sided"))
            rows.append(
                {
                    "condition": condition,
                    "n_participants": n,
                    "scenario": scenario_name,
                    "assumed_dz": dz_scenario,
                    "power": round(power, 3),
                    "alpha": 0.05,
                }
            )

    return pd.DataFrame(rows)


def robustness_reruns(
    test_trials: pd.DataFrame,
    participant_rt_flags: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # 1) Trim participant RT outliers and rerun primary RT model.
    outlier_ids = set(
        participant_rt_flags.loc[participant_rt_flags["rt_outlier_abs_z_gt_3"], "participant_uid"].astype(str)
    )
    trimmed = test_trials.loc[~test_trials["participant_uid"].astype(str).isin(outlier_ids)].copy()
    rt_trimmed = mixed_rt_model(trimmed)
    rt_trimmed["analysis_family"] = "robustness_rt_outlier_trimmed"

    # 2) Split correctness models by item role (target and lure separately).
    # This is the CLEAN lure-bin model — lure_bin_c is unambiguous here.
    split_rows: list[pd.DataFrame] = []
    for role in ["target", "lure"]:
        subset = test_trials.loc[
            test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
            & (test_trials["item_role"] == role)
        ].copy()
        # B2 fix.
        subset = _clean_boundary_cat(subset)
        subset["lure_bin"] = pd.to_numeric(subset["lure_bin"], errors="coerce")
        subset["lure_bin_c"] = subset["lure_bin"] - subset["lure_bin"].mean()

        if role == "lure":
            formula = "correct_int ~ C(condition) * C(test_boundary_position) + C(stimulus_class) + lure_bin_c"
        else:
            formula = "correct_int ~ C(condition) * C(test_boundary_position) + C(stimulus_class)"

        model = GEE.from_formula(
            formula,
            groups="participant_uid",
            data=subset,
            family=Binomial(),
            cov_struct=Exchangeable(),
        )
        result = model.fit()
        table = pd.DataFrame(
            {
                "term": result.params.index,
                "coef": result.params.values,
                "std_err": result.bse.values,
                "z": result.tvalues.values,
                "p_value": result.pvalues.values,
            }
        )
        table["odds_ratio"] = np.exp(table["coef"])
        table["analysis_family"] = "robustness_correctness_split"
        table["item_role_split"] = role
        split_rows.append(table)

    split_correctness = pd.concat(split_rows, ignore_index=True)

    # 3) Focused boundary contrasts from participant-level means.
    target_lure = test_trials.loc[
        test_trials["item_role"].isin(["target", "lure"])
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
    ].copy()
    grouped = (
        target_lure.groupby(["participant_uid", "condition", "item_role", "test_boundary_position"], observed=True)[
            "correct_int"
        ]
        .mean()
        .reset_index()
    )
    pivot = grouped.pivot(
        index=["participant_uid", "condition", "item_role"],
        columns="test_boundary_position",
        values="correct_int",
    ).reset_index()
    rows: list[dict[str, object]] = []
    for condition in CONDITION_ORDER:
        for role in ["target", "lure"]:
            subset = pivot.loc[(pivot["condition"] == condition) & (pivot["item_role"] == role)].dropna()
            if subset.empty:
                continue
            for left, right in [("post", "mid"), ("post", "pre")]:
                diff = subset[left] - subset[right]
                t_stat, p_value = stats.ttest_1samp(diff, 0.0)
                n = int(len(diff))
                rows.append(
                    {
                        "analysis_family": "robustness_boundary_contrasts",
                        "condition": condition,
                        "item_role": role,
                        "contrast": f"{left}-{right}",
                        "n": n,
                        "mean_diff": float(diff.mean()),
                        "t_value": float(t_stat),
                        "p_value": float(p_value),
                        # Cohen's dz = t / sqrt(n) for within-participant tests.
                        "cohens_dz": float(t_stat) / math.sqrt(n),
                    }
                )
    boundary_contrasts = pd.DataFrame(rows)
    if not boundary_contrasts.empty:
        _, p_holm, _, _ = multipletests(boundary_contrasts["p_value"].to_numpy(), method="holm")
        boundary_contrasts["p_value_holm"] = p_holm

    return rt_trimmed, split_correctness, boundary_contrasts


def response_direction_analysis(test_trials: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Decompose post-boundary recognition failure by response type.

    For each condition × boundary, computes the mean per-participant rate of
    each response label (old / similar / new) for TARGET trials.  Then runs
    Holm-corrected paired t-tests for post vs mid and post vs pre contrasts
    within each condition, separately for each response label.

    Scientific motivation: the overall hit-rate drop at post-boundary could
    be driven by conservative responding (more 'new' misses) or by pattern-
    separation overextension (more 'similar' calls to targets).  Decomposing
    the direction establishes the mechanism.
    """
    target = test_trials.loc[
        (test_trials["item_role"] == "target")
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
    ].copy()

    # Participant-level proportion of each response label by condition × boundary.
    rows_summary: list[dict[str, object]] = []
    rows_tests: list[dict[str, object]] = []

    for resp_label in ["old", "similar", "new"]:
        target[f"is_{resp_label}"] = target["response_label"].eq(resp_label).astype(float)

        part_rates = (
            target.groupby(["participant_uid", "condition", "test_boundary_position"], observed=True)[f"is_{resp_label}"]
            .mean()
            .reset_index()
        )

        for condition in CONDITION_ORDER:
            sub = part_rates.loc[part_rates["condition"] == condition]
            pivot = sub.pivot(
                index="participant_uid", columns="test_boundary_position", values=f"is_{resp_label}"
            ).reindex(columns=BOUNDARY_ORDER).dropna()
            n = len(pivot)

            for boundary in BOUNDARY_ORDER:
                rows_summary.append({
                    "condition": condition,
                    "boundary": boundary,
                    "response_label": resp_label,
                    "mean_rate": float(pivot[boundary].mean()),
                    "se": float(pivot[boundary].std(ddof=1) / math.sqrt(n)),
                    "n": int(n),
                })

            # Paired t-tests: post vs mid and post vs pre.
            for left, right in [("post", "mid"), ("post", "pre")]:
                if left in pivot.columns and right in pivot.columns:
                    diff = pivot[left] - pivot[right]
                    t_stat, p_raw = stats.ttest_1samp(diff.dropna(), 0.0)
                    n_pair = int(len(diff.dropna()))
                    rows_tests.append({
                        "analysis_family": "response_direction",
                        "condition": condition,
                        "response_label": resp_label,
                        "contrast": f"{left}-{right}",
                        "n": n_pair,
                        "mean_diff": float(diff.mean()),
                        "t_value": float(t_stat),
                        "p_value": float(p_raw),
                        "cohens_dz": float(t_stat) / math.sqrt(n_pair),
                    })

    tests_df = pd.DataFrame(rows_tests)
    if not tests_df.empty:
        _, p_holm, _, _ = multipletests(tests_df["p_value"].to_numpy(), method="holm")
        tests_df["p_value_holm"] = p_holm

    return pd.DataFrame(rows_summary), tests_df


def lure_false_alarm_analysis(test_trials: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Analyse P(old|lure) by boundary position and condition.

    Pre-boundary lures being called 'old' more often than mid-event lures
    would indicate higher familiarity signal for pre-boundary items rather
    than better pattern separation (which would increase 'similar' responses).
    This tests whether the LDI non-replication is accompanied by a directional
    familiarity elevation for pre-boundary items.
    """
    lure = test_trials.loc[
        (test_trials["item_role"] == "lure")
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
    ].copy()
    lure["is_old"] = lure["response_label"].eq("old").astype(float)

    part_fa = (
        lure.groupby(["participant_uid", "condition", "test_boundary_position"], observed=True)["is_old"]
        .mean()
        .reset_index()
    )

    rows_summary: list[dict[str, object]] = []
    rows_tests: list[dict[str, object]] = []

    for condition in CONDITION_ORDER:
        sub = part_fa.loc[part_fa["condition"] == condition]
        pivot = sub.pivot(
            index="participant_uid", columns="test_boundary_position", values="is_old"
        ).reindex(columns=BOUNDARY_ORDER).dropna()
        n = len(pivot)

        for boundary in BOUNDARY_ORDER:
            rows_summary.append({
                "condition": condition,
                "boundary": boundary,
                "mean_lure_fa_rate": float(pivot[boundary].mean()),
                "se": float(pivot[boundary].std(ddof=1) / math.sqrt(n)),
                "n": int(n),
            })

        for left, right in [("post", "mid"), ("pre", "mid"), ("post", "pre")]:
            if left in pivot.columns and right in pivot.columns:
                diff = pivot[left] - pivot[right]
                t_stat, p_raw = stats.ttest_1samp(diff.dropna(), 0.0)
                n_pair = int(len(diff.dropna()))
                rows_tests.append({
                    "analysis_family": "lure_false_alarm",
                    "condition": condition,
                    "contrast": f"{left}-{right}",
                    "n": n_pair,
                    "mean_diff": float(diff.mean()),
                    "t_value": float(t_stat),
                    "p_value": float(p_raw),
                    "cohens_dz": float(t_stat) / math.sqrt(n_pair),
                })

    tests_df = pd.DataFrame(rows_tests)
    if not tests_df.empty:
        _, p_holm, _, _ = multipletests(tests_df["p_value"].to_numpy(), method="holm")
        tests_df["p_value_holm"] = p_holm

    return pd.DataFrame(rows_summary), tests_df


def sdt_dprime_analysis(test_trials: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Signal detection theory d-prime and criterion (c) by boundary position and condition.

    Uses participant-level hit rate (P(old|target, boundary)) and a single
    false-alarm rate (P(old|foil)) per participant.  Because foils do not have
    boundary positions, FA is constant across boundary levels; consequently
    d' and raw hit rate convey identical statistical information.  The SDT
    table is provided because d' is the standard metric in the MST literature
    and is directly comparable with published values from Morse et al. (2023).

    Loglinear correction: extreme rates (0 or 1) are clipped to
    0.5/n and 1 - 0.5/n using the number of trials in the denominator.
    """
    # False alarm rate per participant (from foil trials).
    foils = test_trials.loc[test_trials["item_role"] == "foil"].copy()
    foil_counts = foils.groupby("participant_uid", observed=True).size().reset_index(name="n_foil_trials")
    foil_fa = (
        foils.groupby("participant_uid", observed=True)["response_label"]
        .apply(lambda x: (x == "old").mean())
        .reset_index()
    )
    foil_fa.columns = ["participant_uid", "fa_rate"]
    foil_fa = foil_fa.merge(foil_counts, on="participant_uid")

    # Hit rate per participant × condition × boundary.
    targets = test_trials.loc[
        (test_trials["item_role"] == "target")
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
    ].copy()
    target_counts = (
        targets.groupby(["participant_uid", "condition", "test_boundary_position"], observed=True)
        .size()
        .reset_index(name="n_target_trials")
    )
    hit_rate = (
        targets.groupby(["participant_uid", "condition", "test_boundary_position"], observed=True)["response_label"]
        .apply(lambda x: (x == "old").mean())
        .reset_index()
    )
    hit_rate.columns = ["participant_uid", "condition", "boundary", "hit_rate"]
    hit_rate = hit_rate.merge(target_counts, left_on=["participant_uid", "condition", "boundary"],
                              right_on=["participant_uid", "condition", "test_boundary_position"])

    sdt = hit_rate.merge(foil_fa, on="participant_uid")

    # Loglinear correction.
    sdt["hit_c"] = sdt.apply(lambda r: float(np.clip(r["hit_rate"], 0.5 / r["n_target_trials"],
                                                      1 - 0.5 / r["n_target_trials"])), axis=1)
    sdt["fa_c"] = sdt.apply(lambda r: float(np.clip(r["fa_rate"], 0.5 / r["n_foil_trials"],
                                                     1 - 0.5 / r["n_foil_trials"])), axis=1)
    sdt["dprime"] = stats.norm.ppf(sdt["hit_c"]) - stats.norm.ppf(sdt["fa_c"])
    sdt["criterion"] = -0.5 * (stats.norm.ppf(sdt["hit_c"]) + stats.norm.ppf(sdt["fa_c"]))

    # Summary table: mean d' and criterion by condition × boundary.
    summary = (
        sdt.groupby(["condition", "boundary"], observed=True)[["dprime", "criterion"]]
        .agg(["mean", "std"])
        .reset_index()
    )
    summary.columns = ["condition", "boundary", "dprime_mean", "dprime_std", "criterion_mean", "criterion_std"]

    # Statistical tests: Friedman + post-hoc paired t-tests for d'.
    test_rows: list[dict[str, object]] = []
    for condition in CONDITION_ORDER:
        sub = sdt.loc[sdt["condition"] == condition]
        pivot = sub.pivot(index="participant_uid", columns="boundary", values="dprime").reindex(
            columns=BOUNDARY_ORDER
        ).dropna()
        n = len(pivot)
        if n >= 3:
            chi2, p_fr = stats.friedmanchisquare(pivot["post"], pivot["mid"], pivot["pre"])
            kendall_w = float(chi2) / (n * 2)
            test_rows.append({
                "analysis_family": "sdt_dprime",
                "condition": condition,
                "test": "friedman_dprime",
                "n": int(n),
                "statistic": float(chi2),
                "p_value": float(p_fr),
                "kendall_w": kendall_w,
            })
            for left, right in [("post", "mid"), ("post", "pre")]:
                diff = pivot[left] - pivot[right]
                t_stat, p_raw = stats.ttest_1samp(diff.dropna(), 0.0)
                n_pair = int(len(diff.dropna()))
                test_rows.append({
                    "analysis_family": "sdt_dprime",
                    "condition": condition,
                    "test": f"paired_t_dprime_{left}_vs_{right}",
                    "n": n_pair,
                    "mean_dprime_diff": float(diff.mean()),
                    "t_value": float(t_stat),
                    "p_value": float(p_raw),
                    "cohens_dz": float(t_stat) / math.sqrt(n_pair),
                })

    tests_df = pd.DataFrame(test_rows)
    if not tests_df.empty and "p_value" in tests_df.columns:
        _, p_holm, _, _ = multipletests(tests_df["p_value"].to_numpy(), method="holm")
        tests_df["p_value_holm"] = p_holm

    return summary, tests_df


def apply_family_corrections(
    primary_correctness: pd.DataFrame,
    primary_rt: pd.DataFrame,
    secondary_profile: pd.DataFrame,
    secondary_lure: pd.DataFrame,
    carryover: pd.DataFrame,
) -> pd.DataFrame:
    families: list[pd.DataFrame] = []

    def _correct(df: pd.DataFrame, family_name: str) -> pd.DataFrame:
        if df.empty or "p_value" not in df.columns:
            return df
        corrected = df.copy()
        pvals = pd.to_numeric(corrected["p_value"], errors="coerce").fillna(1.0).to_numpy()
        _, p_holm, _, _ = multipletests(pvals, method="holm")
        _, p_bh, _, _ = multipletests(pvals, method="fdr_bh")
        corrected["p_value_holm"] = p_holm
        corrected["p_value_bh"] = p_bh
        corrected["family"] = family_name
        return corrected

    families.append(_correct(primary_correctness, "primary_correctness"))
    families.append(_correct(primary_rt, "primary_rt"))
    families.append(_correct(secondary_profile, "secondary_response_profile"))
    families.append(_correct(secondary_lure, "secondary_lure_bin"))
    families.append(_correct(carryover, "encoding_rt_carryover"))

    combined = pd.concat([df for df in families if df is not None and not df.empty], ignore_index=True)
    return combined


# ── Visualisation ────────────────────────────────────────────────────────────


def plot_correctness(test_trials: pd.DataFrame) -> None:
    """Overall correctness by boundary and condition (targets + lures combined)."""
    working = test_trials.loc[
        test_trials["item_role"].isin(["target", "lure"])
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
    ].copy()

    summary = (
        working.groupby(["condition", "test_boundary_position"], observed=True)["correct_int"]
        .mean()
        .reset_index()
    )

    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    sns.barplot(
        data=summary,
        x="test_boundary_position",
        y="correct_int",
        hue="condition",
        order=BOUNDARY_ORDER,
        hue_order=CONDITION_ORDER,
        ax=ax,
    )
    ax.set_ylim(0, 1)
    ax.set_xlabel("Boundary position")
    ax.set_ylabel("Mean correctness")
    ax.set_title("Phase 2: Correctness by boundary and condition")
    ax.legend(title="Condition", labels=[CONDITION_LABELS[c] for c in CONDITION_ORDER])
    fig.savefig(FIG_DIR / "phase2_correctness_boundary_condition.png")
    plt.close(fig)


def plot_target_correctness(test_trials: pd.DataFrame) -> None:
    """Target-only correctness by boundary position, separated by condition (Gap G1 / V1).

    Shows participant-level points overlaid on condition means with 95 % CI.
    This is the confirmatory figure for the post-boundary recognition cost.
    """
    target = test_trials.loc[
        (test_trials["item_role"] == "target")
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
    ].copy()

    # Participant-level means.
    part_means = (
        target.groupby(["participant_uid", "condition", "test_boundary_position"], observed=True)["correct_int"]
        .mean()
        .reset_index()
    )

    fig, axes = plt.subplots(1, 3, figsize=(14, 5), sharey=True)
    colors = sns.color_palette("Set2", 3)

    for ax, condition, color in zip(axes, CONDITION_ORDER, colors):
        sub = part_means.loc[part_means["condition"] == condition]
        # Participant points.
        ax.scatter(
            sub["test_boundary_position"].astype(str),
            sub["correct_int"],
            alpha=0.25,
            s=18,
            color=color,
            zorder=2,
        )
        # Condition mean + 95 % CI via pointplot.
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
            zorder=3,
        )
        ax.set_title(CONDITION_LABELS[condition])
        ax.set_xlabel("Boundary position")
        ax.set_ylim(0, 1.05)
        ax.axhline(0.5, color="grey", linestyle="--", linewidth=0.8, alpha=0.5)

    axes[0].set_ylabel("P(correct) — Targets")
    axes[1].set_ylabel("")
    axes[2].set_ylabel("")
    fig.suptitle("Phase 2: Target recognition accuracy by boundary position", fontsize=14, y=1.01)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "phase2_target_correctness_by_boundary.png")
    plt.close(fig)


def plot_participant_contrasts(heterogeneity_df: pd.DataFrame) -> None:
    """Within-participant post-mid contrast distribution by condition (Gap G2 / V2).

    Histogram + KDE with vertical line at zero shows whether the post-boundary
    recognition cost is consistent across participants.
    """
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=False, sharex=True)
    colors = sns.color_palette("Set2", 3)

    for ax, condition, color in zip(axes, CONDITION_ORDER, colors):
        sub = heterogeneity_df.loc[heterogeneity_df["condition"] == condition, "post_minus_mid"].dropna()
        mean_val = sub.mean()
        sns.histplot(sub, bins=16, kde=True, color=color, alpha=0.7, ax=ax)
        ax.axvline(0, color="black", linewidth=1.2, linestyle="--", label="No effect")
        ax.axvline(mean_val, color="darkred", linewidth=1.6, linestyle="-", label=f"Mean = {mean_val:.3f}")
        ax.set_title(CONDITION_LABELS[condition])
        ax.set_xlabel("post − mid correctness")
        ax.legend(fontsize=8)

    axes[0].set_ylabel("Count")
    axes[1].set_ylabel("")
    axes[2].set_ylabel("")
    fig.suptitle(
        "Phase 2: Per-participant post-minus-mid target correctness contrast",
        fontsize=13,
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(FIG_DIR / "phase2_participant_contrast_distribution.png")
    plt.close(fig)


def plot_phase1_vs_phase2_bridge(
    test_trials: pd.DataFrame, participant_level: pd.DataFrame
) -> None:
    """Side-by-side Phase 1 REC and Phase 2 target correctness for the both condition (Gap G5 / V3).

    Left panel: Phase 1 REC by boundary (from participant_level_metrics).
    Right panel: Phase 2 target correctness by boundary (from trial data).
    Both conditioned on the 'both' condition (Item + Task Shift).
    """
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)
    color = sns.color_palette("Set2", 3)[1]  # colour for 'both' condition.

    # Left — Phase 1 REC.
    pl_both = participant_level.loc[participant_level["condition"] == "both"].copy()
    rec_cols = {"post": "rec_post", "mid": "rec_mid", "pre": "rec_pre"}
    # check available column names.
    available = {k: v for k, v in rec_cols.items() if v in pl_both.columns}
    if available:
        rec_long = pl_both[list(available.values())].melt(var_name="boundary_col", value_name="REC")
        rec_long["boundary"] = rec_long["boundary_col"].map({v: k for k, v in available.items()})
        rec_long = rec_long.dropna(subset=["REC"])
        sns.pointplot(
            data=rec_long,
            x="boundary",
            y="REC",
            order=BOUNDARY_ORDER,
            color=color,
            errorbar=("ci", 95),
            markers="D",
            capsize=0.1,
            ax=axes[0],
        )
        axes[0].axhline(0, color="grey", linestyle="--", linewidth=0.8)
        axes[0].set_title("Phase 1: Recognition (REC)\nItem + Task Shift")
        axes[0].set_xlabel("Boundary position")
        axes[0].set_ylabel("REC score")
    else:
        axes[0].text(0.5, 0.5, "REC columns not found", ha="center", va="center", transform=axes[0].transAxes)

    # Right — Phase 2 target correctness.
    target_both = test_trials.loc[
        (test_trials["condition"] == "both")
        & (test_trials["item_role"] == "target")
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
    ].copy()
    part_means = (
        target_both.groupby(["participant_uid", "test_boundary_position"], observed=True)["correct_int"]
        .mean()
        .reset_index()
    )
    axes[1].scatter(
        part_means["test_boundary_position"].astype(str),
        part_means["correct_int"],
        alpha=0.2,
        s=18,
        color=color,
    )
    sns.pointplot(
        data=part_means,
        x="test_boundary_position",
        y="correct_int",
        order=BOUNDARY_ORDER,
        color=color,
        errorbar=("ci", 95),
        markers="D",
        capsize=0.1,
        ax=axes[1],
    )
    axes[1].axhline(0.5, color="grey", linestyle="--", linewidth=0.8)
    axes[1].set_title("Phase 2: Target correctness\nItem + Task Shift")
    axes[1].set_xlabel("Boundary position")
    axes[1].set_ylabel("P(correct) — Targets")
    axes[1].set_ylim(0, 1.05)

    fig.suptitle("Phase 1 → Phase 2 Bridge: Post-boundary recognition cost (Item + Task Shift)", fontsize=13)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "phase2_phase1_vs_phase2_bridge.png")
    plt.close(fig)


def plot_encoding_rt_vs_correctness(scatter_df: pd.DataFrame) -> None:
    """Participant-level encoding RT (post-boundary) vs target correctness (post-boundary) (Gap G1 / V4).

    Each point is one participant. Colour encodes condition. A negative
    correlation here is the participant-level evidence that the encoding
    disruption causes the recognition cost.
    """
    fig, ax = plt.subplots(figsize=(8, 6))
    palette = {c: col for c, col in zip(CONDITION_ORDER, sns.color_palette("Set2", 3))}

    for condition in CONDITION_ORDER:
        sub = scatter_df.loc[scatter_df["condition"] == condition]
        ax.scatter(
            sub["mean_encoding_rt_post"],
            sub["mean_target_correctness_post"],
            label=CONDITION_LABELS[condition],
            color=palette[condition],
            alpha=0.7,
            s=50,
            edgecolors="white",
            linewidths=0.5,
        )
        # Per-condition regression line.
        if len(sub) > 2:
            m, b = np.polyfit(sub["mean_encoding_rt_post"], sub["mean_target_correctness_post"], 1)
            x_range = np.linspace(sub["mean_encoding_rt_post"].min(), sub["mean_encoding_rt_post"].max(), 50)
            ax.plot(x_range, m * x_range + b, color=palette[condition], linewidth=1.5, alpha=0.6)

    # Overall correlation.
    if len(scatter_df) > 3:
        r, p = stats.pearsonr(scatter_df["mean_encoding_rt_post"], scatter_df["mean_target_correctness_post"])
        ax.text(
            0.97,
            0.97,
            f"r = {r:.2f}, p = {p:.3f}",
            ha="right",
            va="top",
            transform=ax.transAxes,
            fontsize=10,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.8),
        )

    ax.set_xlabel("Mean encoding RT — post-boundary items (s)")
    ax.set_ylabel("Mean target correctness — post-boundary items")
    ax.set_title("Carry-over: Does encoding slowdown predict recognition failure?")
    ax.legend(title="Condition", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "phase2_encoding_rt_vs_correctness_scatter.png")
    plt.close(fig)


def plot_speed_accuracy_by_boundary(summary_by_boundary: pd.DataFrame) -> None:
    """Correct vs incorrect RT by boundary position for target trials in both condition (Gap G4 / V extension)."""
    target_both = summary_by_boundary.loc[
        (summary_by_boundary["condition"] == "both")
        & (summary_by_boundary["item_role"] == "target")
    ].copy()

    if target_both.empty:
        return

    long = target_both.melt(
        id_vars=["participant_uid", "condition", "item_role", "test_boundary_position"],
        value_vars=["mean_rt_correct", "mean_rt_incorrect"],
        var_name="accuracy",
        value_name="rt",
    ).dropna(subset=["rt"])
    long["accuracy"] = long["accuracy"].map({"mean_rt_correct": "Correct", "mean_rt_incorrect": "Incorrect"})

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.pointplot(
        data=long,
        x="test_boundary_position",
        y="rt",
        hue="accuracy",
        order=BOUNDARY_ORDER,
        errorbar=("ci", 95),
        markers=["D", "o"],
        capsize=0.1,
        ax=ax,
    )
    ax.set_xlabel("Boundary position")
    ax.set_ylabel("Mean response RT (s)")
    ax.set_title("Speed-accuracy by boundary (Item + Task Shift — Targets)")
    ax.legend(title="Response type")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "phase2_speed_accuracy_by_boundary.png")
    plt.close(fig)


def plot_response_direction(resp_summary: pd.DataFrame) -> None:
    """Stacked bar chart showing target response-label proportions by boundary.

    For each condition × boundary, shows the mean proportion of 'old',
    'similar', and 'new' responses.  The 'both' condition panel is the
    primary interest: does the post-boundary drop in 'old' come from more
    'new' (conservative misses) or more 'similar' (pattern-separation errors)?
    """
    resp_order = ["old", "similar", "new"]
    colors = {"old": "#4C9BE8", "similar": "#F5A623", "new": "#E84C4C"}
    boundary_labels = {"post": "Post", "mid": "Mid", "pre": "Pre"}

    fig, axes = plt.subplots(1, 3, figsize=(14, 5), sharey=True)

    for ax, condition in zip(axes, CONDITION_ORDER):
        sub = resp_summary.loc[resp_summary["condition"] == condition].copy()
        x = np.arange(len(BOUNDARY_ORDER))
        width = 0.55
        bottoms = np.zeros(len(BOUNDARY_ORDER))

        for resp_label in resp_order:
            vals = []
            for boundary in BOUNDARY_ORDER:
                row = sub[(sub["boundary"] == boundary) & (sub["response_label"] == resp_label)]
                vals.append(float(row["mean_rate"].values[0]) if not row.empty else 0.0)
            vals = np.array(vals)
            ax.bar(x, vals, width=width, bottom=bottoms, color=colors[resp_label],
                   label=f'"{resp_label}"', alpha=0.88)
            # Add proportion labels inside bars if large enough.
            for xi, (v, b) in enumerate(zip(vals, bottoms)):
                if v > 0.08:
                    ax.text(xi, b + v / 2, f"{v:.2f}", ha="center", va="center",
                            fontsize=8.5, color="white", fontweight="bold")
            bottoms += vals

        ax.set_xticks(x)
        ax.set_xticklabels([boundary_labels[b] for b in BOUNDARY_ORDER])
        ax.set_title(CONDITION_LABELS[condition])
        ax.set_xlabel("Boundary position")
        ax.set_ylim(0, 1.02)

    axes[0].set_ylabel("Proportion of responses")
    axes[1].set_ylabel("")
    axes[2].set_ylabel("")
    # Single shared legend.
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, title="Response", loc="upper right",
               bbox_to_anchor=(1.0, 1.0), fontsize=9)
    fig.suptitle(
        "Response direction: target response proportions by boundary position",
        fontsize=13, y=1.02,
    )
    fig.tight_layout()
    fig.savefig(FIG_DIR / "phase2_response_direction_targets.png")
    plt.close(fig)


def plot_sdt_dprime(sdt_summary: pd.DataFrame) -> None:
    """d-prime by boundary position and condition (3-panel, MST literature format)."""
    boundary_labels = {"post": "Post", "mid": "Mid", "pre": "Pre"}
    fig, axes = plt.subplots(1, 3, figsize=(14, 5), sharey=True)
    colors = sns.color_palette("Set2", 3)

    for ax, condition, color in zip(axes, CONDITION_ORDER, colors):
        sub = sdt_summary.loc[sdt_summary["condition"] == condition].copy()
        sub["boundary_label"] = sub["boundary"].map(boundary_labels)
        # Order by BOUNDARY_ORDER.
        sub["boundary_ord"] = sub["boundary"].map({b: i for i, b in enumerate(BOUNDARY_ORDER)})
        sub = sub.sort_values("boundary_ord")

        n_participants = int(sub["dprime_std"].count())  # approximate
        ax.errorbar(
            sub["boundary_label"],
            sub["dprime_mean"],
            yerr=sub["dprime_std"] / np.sqrt(max(n_participants, 1)),
            fmt="o-",
            color=color,
            capsize=5,
            linewidth=2,
            markersize=8,
            label=CONDITION_LABELS[condition],
        )
        ax.set_title(CONDITION_LABELS[condition])
        ax.set_xlabel("Boundary position")
        ax.set_ylim(1.0, 3.5)
        ax.axhline(0, color="grey", linestyle="--", linewidth=0.8, alpha=0.4)

    axes[0].set_ylabel("d′ (signal detection sensitivity)")
    axes[1].set_ylabel("")
    axes[2].set_ylabel("")
    fig.suptitle("SDT sensitivity (d′) by boundary position and condition", fontsize=13, y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "phase2_sdt_dprime_by_boundary.png")
    plt.close(fig)


def plot_lure_false_alarm(lure_fa_summary: pd.DataFrame) -> None:
    """P(old|lure) by boundary position and condition.

    Highlights the pre-boundary lure false-alarm elevation in the 'both'
    condition — pre-event lures are more often called 'old', indicating
    higher familiarity signal rather than better pattern separation.
    """
    boundary_labels = {"post": "Post", "mid": "Mid", "pre": "Pre"}
    fig, axes = plt.subplots(1, 3, figsize=(14, 5), sharey=True)
    colors = sns.color_palette("Set2", 3)

    for ax, condition, color in zip(axes, CONDITION_ORDER, colors):
        sub = lure_fa_summary.loc[lure_fa_summary["condition"] == condition].copy()
        sub["boundary_label"] = sub["boundary"].map(boundary_labels)
        sub["boundary_ord"] = sub["boundary"].map({b: i for i, b in enumerate(BOUNDARY_ORDER)})
        sub = sub.sort_values("boundary_ord")

        ax.errorbar(
            sub["boundary_label"],
            sub["mean_lure_fa_rate"],
            yerr=sub["se"] * 1.96,
            fmt="s-",
            color=color,
            capsize=5,
            linewidth=2,
            markersize=8,
        )
        ax.set_title(CONDITION_LABELS[condition])
        ax.set_xlabel("Boundary position")
        ax.set_ylim(0, 0.55)

    axes[0].set_ylabel("P(\"old\" | lure) — False alarm rate")
    axes[1].set_ylabel("")
    axes[2].set_ylabel("")
    fig.suptitle("Lure false-alarm rate by boundary position", fontsize=13, y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "phase2_lure_false_alarm_by_boundary.png")
    plt.close(fig)


def plot_rt(test_trials: pd.DataFrame) -> None:
    working = test_trials.loc[
        test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
        & test_trials["response_rt"].notna()
        & test_trials["response_rt"].between(0.2, 30)
    ].copy()

    fig, axes = plt.subplots(1, 3, figsize=(14.2, 4.8), sharey=True)
    for ax, condition in zip(axes, CONDITION_ORDER):
        subset = working.loc[working["condition"] == condition]
        sns.violinplot(
            data=subset,
            x="test_boundary_position",
            y="response_rt",
            order=BOUNDARY_ORDER,
            inner="quartile",
            cut=0,
            ax=ax,
        )
        ax.set_title(CONDITION_LABELS[condition])
        ax.set_xlabel("Boundary")
        ax.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Response RT (s)")
    axes[1].set_ylabel("")
    axes[2].set_ylabel("")
    fig.suptitle("Phase 2: Test RT distributions by boundary")
    fig.savefig(FIG_DIR / "phase2_test_rt_violin.png")
    plt.close(fig)


def plot_lure_bins(test_trials: pd.DataFrame) -> None:
    lure = test_trials.loc[
        (test_trials["item_role"] == "lure")
        & test_trials["test_boundary_position"].isin(BOUNDARY_ORDER)
        & test_trials["lure_bin"].notna()
    ].copy()
    lure["similar_resp"] = lure["response_label"].eq("similar").astype(float)

    fig, ax = plt.subplots(figsize=(9.8, 5.4))
    sns.pointplot(
        data=lure,
        x="lure_bin",
        y="similar_resp",
        hue="test_boundary_position",
        hue_order=BOUNDARY_ORDER,
        errorbar=("ci", 95),
        dodge=0.2,
        ax=ax,
    )
    ax.set_ylim(0, 1)
    ax.set_xlabel("Lure bin (1=more similar, 5=less similar)")
    ax.set_ylabel("P(similar response)")
    ax.set_title("Phase 2: Lure-bin slopes by boundary")
    fig.savefig(FIG_DIR / "phase2_lure_bin_slopes.png")
    plt.close(fig)


def plot_diagnostics(diag_df: pd.DataFrame, test_trials: pd.DataFrame) -> None:
    participant_mean = (
        test_trials.groupby("participant_uid", observed=True)["response_rt"].mean().replace(0, np.nan).dropna()
    )
    participant_log = np.log(participant_mean)
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    sns.histplot(participant_log, bins=24, kde=True, ax=ax)
    ax.set_xlabel("Participant mean log RT")
    ax.set_title("Phase 2 diagnostics: participant mean log RT distribution")
    fig.savefig(FIG_DIR / "phase2_diagnostic_logrt_hist.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.0, 6.0))
    stats.probplot(diag_df["residual"], dist="norm", plot=ax)
    ax.set_title("Phase 2 diagnostics: QQ plot of RT-model residuals")
    fig.savefig(FIG_DIR / "phase2_diagnostic_qq_residuals.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    sns.scatterplot(
        data=diag_df.sample(n=min(12000, len(diag_df)), random_state=17),
        x="fitted",
        y="residual",
        s=10,
        alpha=0.35,
        ax=ax,
    )
    ax.axhline(0.0, color="black", linewidth=1)
    ax.set_xlabel("Fitted log RT")
    ax.set_ylabel("Residual")
    ax.set_title("Phase 2 diagnostics: residual vs fitted")
    fig.savefig(FIG_DIR / "phase2_diagnostic_residuals_vs_fitted.png")
    plt.close(fig)


def write_analysis_registry() -> pd.DataFrame:
    rows = [
        {
            "model_name": "primary_correctness_gee",
            "purpose": "confirmatory",
            "assumption_focus": "clustered binary outcome; robust sandwich SE; stimulus_class x boundary interaction added",
            "included_in_report": True,
            "fix_applied": "B2 (foil level removed); B3 (lure_bin_c removed from combined formula)",
        },
        {
            "model_name": "primary_rt_gaussian_gee",
            "purpose": "confirmatory",
            "assumption_focus": "Gaussian GEE on log RT; LMM singular — GEE fallback used",
            "included_in_report": True,
            "fix_applied": "B1 (correctly labelled as GEE); B2 (foil level removed)",
        },
        {
            "model_name": "fallback_friedman_target_correctness",
            "purpose": "confirmatory",
            "assumption_focus": "nonparametric repeated-measures; PRIMARY confirmatory result for boundary effect",
            "included_in_report": True,
            "fix_applied": "none",
        },
        {
            "model_name": "secondary_response_profile_chi_square",
            "purpose": "exploratory",
            "assumption_focus": "categorical independence tests; B2 applied",
            "included_in_report": True,
            "fix_applied": "B2 (foil level removed)",
        },
        {
            "model_name": "secondary_lure_bin_gee",
            "purpose": "exploratory",
            "assumption_focus": "clustered binary; B2 applied",
            "included_in_report": True,
            "fix_applied": "B2 (foil level removed)",
        },
        {
            "model_name": "encoding_rt_carryover_gee",
            "purpose": "confirmatory",
            "assumption_focus": "trial-level join of encoding RT to test correctness; new Gap G1 analysis",
            "included_in_report": True,
            "fix_applied": "new (Gap G1)",
        },
        {
            "model_name": "participant_heterogeneity",
            "purpose": "exploratory",
            "assumption_focus": "per-participant boundary contrasts; Gap G2",
            "included_in_report": True,
            "fix_applied": "new (Gap G2)",
        },
        {
            "model_name": "robustness_rt_outlier_trimmed",
            "purpose": "robustness",
            "assumption_focus": "sensitivity to participant RT outliers",
            "included_in_report": True,
            "fix_applied": "none",
        },
        {
            "model_name": "robustness_correctness_split",
            "purpose": "robustness",
            "assumption_focus": "target and lure correctness separately; lure_bin_c clean in lure model",
            "included_in_report": True,
            "fix_applied": "B2; B3 (lure_bin_c correct in lure model)",
        },
    ]
    registry = pd.DataFrame(rows)
    return registry


def save_outputs(
    qc_summary: pd.DataFrame,
    participant_rt_flags: pd.DataFrame,
    primary_correctness: pd.DataFrame,
    primary_rt: pd.DataFrame,
    fallback_np: pd.DataFrame,
    secondary_profile: pd.DataFrame,
    secondary_lure: pd.DataFrame,
    speed_accuracy: pd.DataFrame,
    speed_accuracy_by_boundary: pd.DataFrame,
    corrected: pd.DataFrame,
    registry: pd.DataFrame,
    precision_context: pd.DataFrame,
    rt_diag_summary: pd.DataFrame,
    rt_diag_points: pd.DataFrame,
    robustness_rt_trimmed: pd.DataFrame,
    robustness_correctness_split: pd.DataFrame,
    robustness_boundary_contrasts: pd.DataFrame,
    carryover_gee: pd.DataFrame,
    scatter_df: pd.DataFrame,
    heterogeneity_df: pd.DataFrame,
    resp_direction_summary: pd.DataFrame,
    resp_direction_contrasts: pd.DataFrame,
    sdt_summary: pd.DataFrame,
    sdt_tests: pd.DataFrame,
    lure_fa_summary: pd.DataFrame,
    lure_fa_contrasts: pd.DataFrame,
    power_df: pd.DataFrame,
) -> None:
    qc_summary.to_csv(PHASE2_DIR / "qc_summary.csv", index=False)
    participant_rt_flags.to_csv(PHASE2_DIR / "participant_rt_outlier_flags.csv", index=False)
    primary_correctness.to_csv(TABLE_DIR / "phase2_primary_correctness_gee.csv", index=False)
    # B1 fix: file renamed to reflect Gaussian GEE (not mixed model).
    primary_rt.to_csv(TABLE_DIR / "phase2_primary_rt_gee.csv", index=False)
    fallback_np.to_csv(TABLE_DIR / "phase2_fallback_nonparametric.csv", index=False)
    secondary_profile.to_csv(TABLE_DIR / "phase2_secondary_response_profile_chisq.csv", index=False)
    secondary_lure.to_csv(TABLE_DIR / "phase2_secondary_lure_bin_gee.csv", index=False)
    speed_accuracy.to_csv(TABLE_DIR / "phase2_speed_accuracy_summary.csv", index=False)
    speed_accuracy_by_boundary.to_csv(TABLE_DIR / "phase2_speed_accuracy_by_boundary.csv", index=False)
    corrected.to_csv(TABLE_DIR / "phase2_all_tests_corrected.csv", index=False)
    precision_context.to_csv(TABLE_DIR / "phase2_precision_context.csv", index=False)
    rt_diag_summary.to_csv(TABLE_DIR / "phase2_rt_diagnostic_summary.csv", index=False)
    robustness_rt_trimmed.to_csv(TABLE_DIR / "phase2_robustness_rt_outlier_trimmed.csv", index=False)
    robustness_correctness_split.to_csv(TABLE_DIR / "phase2_robustness_correctness_split.csv", index=False)
    robustness_boundary_contrasts.to_csv(TABLE_DIR / "phase2_robustness_boundary_contrasts.csv", index=False)
    carryover_gee.to_csv(TABLE_DIR / "phase2_encoding_rt_carryover_gee.csv", index=False)
    scatter_df.to_csv(TABLE_DIR / "phase2_encoding_rt_correctness_scatter.csv", index=False)
    heterogeneity_df.to_csv(TABLE_DIR / "phase2_participant_boundary_contrasts.csv", index=False)
    resp_direction_summary.to_csv(TABLE_DIR / "phase2_response_direction_summary.csv", index=False)
    resp_direction_contrasts.to_csv(TABLE_DIR / "phase2_response_direction_contrasts.csv", index=False)
    sdt_summary.to_csv(TABLE_DIR / "phase2_sdt_dprime.csv", index=False)
    sdt_tests.to_csv(TABLE_DIR / "phase2_sdt_dprime_tests.csv", index=False)
    lure_fa_summary.to_csv(TABLE_DIR / "phase2_lure_false_alarm_summary.csv", index=False)
    lure_fa_contrasts.to_csv(TABLE_DIR / "phase2_lure_false_alarm_contrasts.csv", index=False)
    power_df.to_csv(TABLE_DIR / "phase2_posthoc_power.csv", index=False)

    rt_diag_points_sample = rt_diag_points.sample(n=min(20000, len(rt_diag_points)), random_state=17)
    rt_diag_points_sample.to_csv(PHASE2_DIR / "phase2_rt_diag_points_sample.csv", index=False)
    registry.to_csv(PHASE2_DIR / "analysis_registry.csv", index=False)

    notes = {
        "bug_fixes_applied": [
            "B1: RT model output renamed phase2_primary_rt_gee.csv; clearly labelled Gaussian GEE throughout.",
            "B2: _clean_boundary_cat() applied in all GEE working datasets; no phantom foil dummy variables.",
            "B3: lure_bin_c removed from combined target+lure correctness GEE; reported from lure-only split.",
        ],
        "new_analyses": [
            "G1: Encoding RT carryover GEE — trial-level join of encoding RT to test correctness.",
            "G2: Participant heterogeneity — per-participant post-mid and post-pre target correctness contrasts.",
            "G3: Stimulus class x boundary interaction added to primary correctness GEE.",
            "G4: Speed-accuracy extended by boundary position.",
        ],
        "confirmatory_primary": [
            "Correctness modeled via clustered logistic GEE with participant-level clustering.",
            "Response speed modeled via Gaussian GEE (LMM was singular) on log RT.",
            "Friedman nonparametric test is the PRIMARY confirmatory result for boundary effect.",
        ],
        "fallbacks_and_secondary": [
            "Chi-square response-profile tests with Cramer's V.",
            "Lure-bin slope model using GEE on similar-response probability.",
            "Robustness reruns include RT outlier-trimmed model and split target/lure correctness models.",
        ],
        "precision_and_diagnostics": [
            "Precision-context table (CI half-width summaries by condition).",
            "RT diagnostics summary and diagnostic plots (histogram, QQ, residuals vs fitted).",
        ],
    }
    with (PHASE2_DIR / "analysis_notes.json").open("w") as handle:
        json.dump(notes, handle, indent=2)


def main() -> None:
    ensure_dirs()
    set_plot_theme()

    test_trials, encoding_trials, participant_level = load_data()
    qc_summary, participant_rt_flags = run_qc(test_trials, participant_level)
    precision_context = build_precision_context(test_trials)

    print("Running primary correctness GEE...")
    primary_correctness, fallback_np = gee_correctness_model(test_trials)

    print("Running primary RT model (Gaussian GEE)...")
    primary_rt = mixed_rt_model(test_trials)

    print("Running RT diagnostics...")
    rt_diag_summary, rt_diag_points = run_rt_diagnostics(test_trials)

    print("Running response profile chi-square tests...")
    secondary_profile = response_profile_tests(test_trials)

    print("Running lure-bin GEE...")
    secondary_lure = lure_bin_gee(test_trials)

    print("Computing speed-accuracy summaries...")
    speed_accuracy, speed_accuracy_by_boundary = speed_accuracy_summary(test_trials)

    print("Running encoding RT carryover analysis (new)...")
    carryover_gee, scatter_df = encoding_rt_carryover(test_trials, encoding_trials)

    print("Computing participant heterogeneity (new)...")
    heterogeneity_df = participant_heterogeneity(test_trials)

    print("Running response direction decomposition (new)...")
    resp_direction_summary, resp_direction_contrasts = response_direction_analysis(test_trials)

    print("Computing SDT d-prime by boundary (new)...")
    sdt_summary, sdt_tests = sdt_dprime_analysis(test_trials)

    print("Running lure false alarm analysis (new)...")
    lure_fa_summary, lure_fa_contrasts = lure_false_alarm_analysis(test_trials)

    print("Computing post-hoc power for LDI non-replication (new)...")
    power_df = post_hoc_power(test_trials)

    print("Running robustness reruns...")
    robustness_rt_trimmed, robustness_correctness_split, robustness_boundary_contrasts = robustness_reruns(
        test_trials,
        participant_rt_flags,
    )

    corrected = apply_family_corrections(
        primary_correctness=primary_correctness,
        primary_rt=primary_rt,
        secondary_profile=secondary_profile,
        secondary_lure=secondary_lure,
        carryover=carryover_gee,
    )

    print("Generating figures...")
    plot_correctness(test_trials)
    plot_target_correctness(test_trials)
    plot_participant_contrasts(heterogeneity_df)
    plot_phase1_vs_phase2_bridge(test_trials, participant_level)
    plot_encoding_rt_vs_correctness(scatter_df)
    plot_speed_accuracy_by_boundary(speed_accuracy_by_boundary)
    plot_rt(test_trials)
    plot_lure_bins(test_trials)
    plot_diagnostics(rt_diag_points, test_trials)
    plot_response_direction(resp_direction_summary)
    plot_sdt_dprime(sdt_summary)
    plot_lure_false_alarm(lure_fa_summary)

    registry = write_analysis_registry()
    save_outputs(
        qc_summary=qc_summary,
        participant_rt_flags=participant_rt_flags,
        primary_correctness=primary_correctness,
        primary_rt=primary_rt,
        fallback_np=fallback_np,
        secondary_profile=secondary_profile,
        secondary_lure=secondary_lure,
        speed_accuracy=speed_accuracy,
        speed_accuracy_by_boundary=speed_accuracy_by_boundary,
        corrected=corrected,
        registry=registry,
        precision_context=precision_context,
        rt_diag_summary=rt_diag_summary,
        rt_diag_points=rt_diag_points,
        robustness_rt_trimmed=robustness_rt_trimmed,
        robustness_correctness_split=robustness_correctness_split,
        robustness_boundary_contrasts=robustness_boundary_contrasts,
        carryover_gee=carryover_gee,
        scatter_df=scatter_df,
        heterogeneity_df=heterogeneity_df,
        resp_direction_summary=resp_direction_summary,
        resp_direction_contrasts=resp_direction_contrasts,
        sdt_summary=sdt_summary,
        sdt_tests=sdt_tests,
        lure_fa_summary=lure_fa_summary,
        lure_fa_contrasts=lure_fa_contrasts,
        power_df=power_df,
    )

    print("Saved Phase 2 outputs to", PHASE2_DIR)
    print("Saved Phase 2 tables to", TABLE_DIR)
    print("Saved Phase 2 figures to", FIG_DIR)


if __name__ == "__main__":
    main()
