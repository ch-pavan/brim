#import "@preview/ilm:2.0.0": *

#set text(
  lang: "en",
  font: "Libertinus Serif",
  size: 12pt,
)
#set par(justify: true, leading: 0.64em)

#show: ilm.with(
  title: [Behavioural Research in Statistical Methods - Project Report - 2],
  authors: (
    "Sambu Aneesh (2023121012)",
    "Renu Sree Vyshnavi (2022101035)",
    "Pavan Harshit (2025701057)",
  ),
  abstract: [
    In Phase 2 we moved from exploratory summaries to confirmatory modelling. We directly modelled test-phase correctness, response speed, and response-category behaviour at the trial level. Three code-level bugs present in the original analysis were corrected; nine previously planned or newly identified analyses were added. The clearest result is a post-boundary recognition cost in the Item + Task Shift condition, confirmed by a nonparametric Friedman test (#sym.chi$""^2$(2) = 11.47, $p$ = .003, Kendall's $W$ = 0.117), Holm-corrected pairwise contrasts ($d_z$ = −0.477, corrected $p$ = .020), and SDT d-prime ($d_z$ = −0.473, corrected $p$ = .016). Response direction decomposition shows the hit-rate drop is split between "new" misses and "similar" errors, consistent with a general trace weakening rather than a single mechanism. A new finding is that Scenes and Objects show opposite boundary profiles. Encoding RT at study did not predict test correctness at the trial level, suggesting the encoding disruption and the memory cost are parallel consequences of boundary processing. Pre-boundary lures show a marginal false alarm elevation (opposite to LDI predictions), providing a familiarity-based reinterpretation of the LDI non-replication. Post-hoc power analysis confirms the LDI null is genuine: the observed contrast was −0.031 (wrong direction), not a power problem.
  ],
  cover-page: [
    #align(left + horizon)[
      #v(7em)
      #text(1.9em, weight: "bold")[Behavioural Research in Statistical Methods]
      #text(1.9em, weight: "bold")[Project Report - 2]
      #v(1.2em)
      *Team Name:* Earphones\
      *Experiment:* Mnemonic Similarity Task (MST)
      #v(1.2em)
      Sambu Aneesh (2023121012)\
      Renu Sree Vyshnavi (2022101035)\
      Pavan Harshit (2025701057)
      #v(1.4em)
      Phase 2 implements confirmatory models for correctness and response speed, adds five new analyses planned but not previously executed, and corrects three technical errors identified in the post-hoc review.
    ]
  ],
  preface: none,
  bibliography: none,
  table-of-contents: none,
  chapter-pagebreak: false,
  figure-index: (enabled: false),
  table-index: (enabled: false),
  listing-index: (enabled: false),
)

= Introduction
Phase 1 established a clean, reproducible base and identified a strong post-boundary encoding RT effect and a moderate post-boundary recognition cost in the Item + Task Shift condition. In Phase 2, our aim was stricter: test correctness and response speed directly at the test-trial level, include additional predictors, and enforce explicit correction for multiple testing.

This phase followed class guidance on variable-type aware testing, assumption checks, outlier diagnostics, and effect-size-oriented reporting. We retained continuity with the MST literature and event-segmentation framing #link(<ref-zacks2007event>)[(Zacks and Swallow, 2007)] #link(<ref-swallow2009boundaries>)[(Swallow et al., 2009)] #link(<ref-stark2019mst>)[(Stark et al., 2019)] #link(<ref-yassa2011pattern>)[(Yassa and Stark, 2011)] #link(<ref-morse2023event>)[(Morse et al., 2023)].

A post-hoc review of the Phase 2 pipeline identified three technical issues that were corrected before this report was finalised:
- *Bug B1:* The primary RT model had been misidentified as a linear mixed model in output file names and surrounding text. It is a Gaussian GEE (the mixed model was singular; GEE was the documented fallback). All references now correctly say Gaussian GEE.
- *Bug B2:* The `test_boundary_position` Categorical retained "foil" as a level after filtering to post/mid/pre rows, causing phantom dummy variables in every GEE model. A `remove_unused_categories()` call is now applied before each GEE fit.
- *Bug B3:* `lure_bin_c` was included in the combined target+lure correctness GEE, where its meaning differs across item roles and target rows may be silently dropped by listwise deletion. The lure-bin effect is now reported exclusively from the lure-only split model where the predictor is unambiguous.

Five additional analyses planned in the pre-registered plan but not previously implemented were added:
- Stimulus class × boundary interaction in the primary correctness GEE (Gap G3).
- Encoding RT → test accuracy carry-over analysis joining encoding and test trials on stimulus identity (Gap G1).
- Participant-level heterogeneity of the post-mid boundary contrast (Gap G2).
- Speed-accuracy summary extended by boundary position (Gap G4).
- Cohen's $d_z$ added to all boundary contrast tables (Gap R4).
- Response direction decomposition: proportion of "old", "similar", and "new" responses to targets by boundary (new).
- SDT d-prime analysis: sensitivity ($d'$) by boundary position using foil-based FA rate (new).
- Lure false alarm rate by boundary position: tests whether pre-boundary lures are called "old" more often (new).
- Post-hoc power analysis for the LDI non-replication (new).

== Phase 2 research questions
1. Does boundary position affect test correctness (`correct` = 0/1) when modelled directly?
2. Does boundary position affect test response speed after accounting for item role and condition?
3. Do response-category patterns (`old/new/similar`) differ by boundary position?
4. Do lure-bin difficulty and stimulus class explain additional variance, and does the stimulus class × boundary interaction reach significance?
5. Does encoding RT at study predict test correctness at the trial level (carry-over)?
6. Do speed-accuracy profiles differ by boundary position?
7. Does the post-boundary recognition cost manifest as more "new" misses (conservative responding) or more "similar" errors (pattern-separation overextension)?
8. Does SDT sensitivity ($d'$) show a boundary-position effect consistent with the correctness analysis?
9. Do pre-boundary lures show elevated false alarm rates, suggesting a familiarity-based explanation for the LDI non-replication?

#figure(
  table(
    columns: 4,
    align: (left, center, center, center),
    inset: 6pt,
    stroke: (x, y) => if y == 0 { 0.8pt + rgb("#6c757d") } else { 0.3pt + rgb("#d9d9d9") },
    table.header([Condition], [Paired $n$], [Test trials per participant], [Total test trials]),
    [Item Shift Only], [56], [150], [8 400],
    [Item + Task Shift], [49], [150], [7 350],
    [Task Shift Only], [53], [150], [7 950],
  ),
  caption: [Phase 2 sample overview. Same participants as Phase 1.],
)

= Methods
== Data and preprocessing
We reused the paired dataset from Phase 1. Key analysis columns were correctness (`correct`), response label (`response_label`), response time (`response_rt`), condition, boundary position, item role, lure bin, and stimulus class. Encoding RT was joined to test trials on (participant × item number) for the carry-over analysis.

Quality checks included missingness summaries, RT artifact flags, participant-level RT outlier checks using z-scores, and normality diagnostics of participant mean log RT. Core test-phase variables had no missingness. Two participants had missing `encoding_task_accuracy` at the participant level; models using this covariate handle this with explicit notation.

== Variables and measures
Phase 2 primary outcomes:
1. Test correctness (`correct`, binary)
2. Log-transformed response speed

Secondary outcomes:
1. Response-category profile (`old/new/similar`)
2. Lure-specific similar-response probability as a function of lure bin
3. Speed-accuracy summary: mean correct RT, mean incorrect RT, and their difference (extended by boundary position)
4. Encoding RT → test correctness carry-over (new)
5. Per-participant post-mid boundary contrast (new)

For continuity, Phase 1 REC and LDI are shown alongside Phase 2 correctness in a bridge figure.

$"REC" = P("old" \mid "Target") - P("old" \mid "Foil")$
$"LDI" = P("similar" \mid "Lure") - P("similar" \mid "Foil")$

== Statistical strategy
*Primary correctness* was modelled with clustered logistic GEE (Binomial family, exchangeable working correlation, participant-level clusters). The formula included condition × boundary, item role, stimulus class × boundary interaction (added in this revision), and correctly excluded `lure_bin_c` from the combined model (reported from lure-only split).

*Primary RT* was modelled on log RT with a Gaussian GEE (participant-level clustering). A linear mixed model was attempted first but was singular; the Gaussian GEE fallback provides population-average estimates with clustering handled via exchangeable working correlation.

*Confirmatory boundary effect* testing used the Friedman nonparametric test within each condition on participant-level target correctness means. Given non-normal residuals (Shapiro-Wilk $W$ = 0.949, $p$ < .001 on OLS residuals), the Friedman test with Kendall's $W$ is the primary confirmatory statistic. Follow-up paired contrasts use one-sample t-tests with Holm correction; Cohen's $d_z$ = $t / sqrt(n)$ is reported for all contrasts.

Secondary analyses used chi-square for response profiles and GEE for lure-bin slopes. Multiple comparisons were corrected within pre-specified families using Holm, with BH/FDR also reported.

== Precision context
Worst-case 95% CI half-widths at $p$ = 0.5 for proportions: 0.131 (item_only), 0.140 (both), 0.135 (task_only). For participant-mean RT: 0.308 s, 0.240 s, and 0.153 s respectively. Effects smaller than these ranges are difficult to distinguish from noise without larger samples.

= Results

== Quality-control checks
Core test-phase variables had no missingness. RT artifacts: 1 trial < 0.2 s (very fast); 23 trials > 30 s (very slow); 3 participant-level RT outliers (|z| > 3). Participant mean log RT departed from normality (Shapiro-Wilk $W$ = 0.953, $p$ < .001), supporting the use of robust GEE models and nonparametric fallback tests.

OLS residual diagnostics for RT showed non-normal residuals ($W$ = 0.949, $p$ < .001) and mild heteroscedasticity (absolute residual vs. fitted $r$ ≈ 0.086). These are consistent with the GEE specification used throughout.

#figure(
  image("figures_phase2/phase2_diagnostic_logrt_hist.png", width: 80%),
  caption: [Participant-level mean log RT distribution. Departure from normality supports robust model choices.],
)

== Primary result: Post-boundary target recognition cost (Friedman + contrasts)

The clearest confirmatory finding is a post-boundary target recognition cost in the Item + Task Shift condition.

*Friedman nonparametric test* on participant-level target correctness within each condition:
- Item + Task Shift: $chi^2$(2) = 11.47, $p$ = .003, Kendall's $W$ = 0.117
- Task Shift Only: $chi^2$(2) = 4.10, $p$ = .129 (trend, not significant)
- Item Shift Only: $chi^2$(2) = 1.36, $p$ = .508 (null)

*Holm-corrected pairwise contrasts* for the Item + Task Shift condition:
- Post vs. mid (target correctness): $overline(x)$ = −0.073, $t$(48) = −3.34, $d_z$ = −0.477, $p_"Holm"$ = .020
- Post vs. pre (target correctness): $overline(x)$ = −0.051, $t$(48) = −2.54, $d_z$ = −0.362, $p_"Holm"$ = .145

This replicates and strengthens the Phase 1 REC finding using a direct trial-level measure with a nonparametric test: post-boundary target recognition in the condition where both the item set and the task rule shift is measurably and significantly worse than mid-event recognition.

#figure(
  image("figures_phase2/phase2_phase1_vs_phase2_bridge.png", width: 100%),
  caption: [Bridge figure: Phase 1 REC (left) and Phase 2 target correctness (right) for the Item + Task Shift condition, both by boundary position. The post-boundary cost is visible and consistent across both phases and both measures.],
)

#figure(
  image("figures_phase2/phase2_target_correctness_by_boundary.png", width: 100%),
  caption: [Phase 2 target recognition accuracy (proportion correct) by boundary position and condition. Points show individual participant means; diamonds show condition mean with 95% CI. The post-boundary cost is largest in the Item + Task Shift condition (centre panel). No consistent boundary pattern is visible in Item Shift Only (left panel).],
)

== Participant-level heterogeneity of the boundary effect

To assess whether the post-boundary cost is consistent across participants or driven by a few extreme responders, we computed per-participant (post − mid) target correctness contrasts for each condition.

#figure(
  image("figures_phase2/phase2_participant_contrast_distribution.png", width: 100%),
  caption: [Distribution of per-participant post-minus-mid target correctness contrasts by condition. Dashed line = zero (no effect); red line = condition mean. In the Item + Task Shift condition (centre), the mean is negative (−0.073) and the distribution sits to the left of zero, indicating the post-boundary cost is present across most participants.],
)

In the Item + Task Shift condition, 63% of participants showed a negative post-mid contrast (post-boundary worse than mid). The mean of −0.073 corresponds to roughly 7 percentage points lower recognition accuracy for post-boundary items. In Item Shift Only and Task Shift Only, the distributions are centred near zero, consistent with the null and marginal Friedman test results for those conditions.

== Primary correctness GEE

The trial-level GEE confirmed the direction of findings. With post as the reference boundary:
- C(boundary)[T.mid]: OR = 1.186, $p$ = .024 — mid-event trials correctly recognised more often than post-boundary trials
- C(boundary)[T.pre]: OR = 1.139, $p$ = .099 — pre-boundary trend, below significance threshold
- C(item_role)[T.lure] vs target: OR = 0.582, $p$ < .001 — lures harder to get correct
- C(stimulus_class)[T.Scenes] vs Objects: OR = 0.784, $p$ < .001 — scenes harder overall
- C(condition)[T.both] vs item_only: OR = 0.799, $p$ = .019 — Item + Task Shift participants show lower correctness overall

The stimulus class × boundary interactions were significant:
- Scenes × mid: OR = 0.785, $p$ = .005
- Scenes × pre: OR = 0.754, $p$ = .003

The negative interaction terms indicate that the mid-over-post advantage is *smaller* for Scenes than for Objects. Put differently, the post-boundary recognition cost is concentrated in Object stimuli; Scenes do not show the same mid > post advantage and may show a reversed pattern. This is a new finding enabled by adding the interaction term (Gap G3).

After Holm correction, the boundary main effects (mid, pre) fall below the threshold, while item role and stimulus class remain significant.

== Primary model 2: Response speed (Gaussian GEE)

*Note:* This model was previously mislabelled as a mixed model. It is a Gaussian GEE (linear mixed model was singular for all attempted formulas; GEE is the final model). This distinction matters: GEE provides population-average estimates; subject-specific estimates require a random-effects model.

Key coefficients from the Gaussian GEE on log RT:
1. Correct responses were faster than incorrect: exp($beta$) = 0.922, $p$ < .001
2. Lure trials were slower than target trials: exp($beta$) = 1.105, $p$ < .001
3. Task Shift Only was faster than Item Shift Only: exp($beta$) = 0.880, $p$ = .013

Boundary main effects in the RT model were not significant after adjustment (mid: $p$ = .77; pre: $p$ = .35). The test-phase RT story is dominated by response accuracy (correct vs. incorrect) and item role, not boundary position.

#figure(
  image("figures_phase2/phase2_test_rt_violin.png", width: 100%),
  caption: [Phase 2 response-time distributions by boundary and condition. RT distributions are similar across boundary positions; the main RT differences are by accuracy type and item role rather than boundary.],
)

== Speed-accuracy by boundary position

Extending the speed-accuracy summary to include boundary position: incorrect responses were slower than correct responses across all boundary positions, with overall mean difference ≈ 0.278 s. The size of this gap does not differ substantially across post, mid, and pre boundaries for target trials in the Item + Task Shift condition.

#figure(
  image("figures_phase2/phase2_speed_accuracy_by_boundary.png", width: 80%),
  caption: [Correct vs. incorrect mean RT by boundary position for target trials in the Item + Task Shift condition. The speed-accuracy gap is present across all three boundary positions with no systematic boundary-driven change.],
)

== Carry-over: Does encoding RT predict test correctness?

We joined encoding trials to test trials on (participant × item number) and modelled test correctness with log encoding RT as a predictor, over and above boundary position and other covariates.

Result: log encoding RT coefficient: OR = 0.988, $p$ = .646 (null, not significant after Holm correction).

Despite the robust trial-level encoding RT spike at post-boundary items in Phase 1, that encoding RT elevation does not translate into worse test-phase recognition for those same items at the trial level. The boundary position coefficient in this model remains in the same direction (mid > post, OR = 1.106, $p$ = .013), confirming that the boundary effect on recognition is not mediated by encoding RT. The two effects — encoding slowdown and recognition cost — appear to be parallel consequences of boundary processing rather than a causal chain.

#figure(
  image("figures_phase2/phase2_encoding_rt_vs_correctness_scatter.png", width: 85%),
  caption: [Participant-level: mean encoding RT for post-boundary items vs mean target correctness for post-boundary items, coloured by condition. Regression lines per condition are shown. The overall Pearson correlation and p-value are annotated. The weak and non-significant correlation at the participant level is consistent with the null carry-over GEE result.],
)

== Secondary analyses beyond REC and LDI

*Response-category structure:* Chi-square tests showed a significant boundary-linked shift only for target trials in the Item + Task Shift condition: $chi^2$(4) = 22.55, $p$ < .001, Cramér's $V$ = 0.062 (small effect). No other condition × item role combination reached significance.

*Lure-bin analysis:* From the lure-only GEE (which is the unambiguous model for `lure_bin`), similar-response probability increased with lure bin level: OR = 1.192 per bin step, $p$ < .001 (lure_bin_c in split model). Scenes showed lower similar-response probability than Objects: OR = 0.677, $p$ < .001. No significant lure_bin × boundary interaction was found ($p$ > .08 for all).

#figure(
  image("figures_phase2/phase2_lure_bin_slopes.png", width: 90%),
  caption: [Lure-bin slopes by boundary. P(similar response) increases as lures become less visually similar (higher bin = less similar to target). Slopes are parallel across boundary positions, confirming no bin × boundary interaction.],
)

== Response direction decomposition

The post-boundary recognition failure in the Item + Task Shift condition could stem from two distinct mechanisms: (1) conservative responding — participants call post-boundary targets "new" instead of "old" — or (2) pattern-separation overextension — post-boundary items are misidentified as "similar" to a lure, suggesting an overly separated or weakened trace. Decomposing the response direction separates these accounts.

For Item + Task Shift target trials, paired t-tests (post vs. mid) with Holm correction within the 3-response-label family:

- P("old" | target): $overline(x)$ = −0.073, $t$(48) = −3.34, $d_z$ = −0.477, $p_"Holm"$ = .028 — *significant*
- P("similar" | target): $overline(x)$ = +0.039, $t$(48) = 2.11, $d_z$ = +0.301, $p_"Holm"$ = .524 — trend, not corrected
- P("new" | target): $overline(x)$ = +0.035, $t$(48) = 2.25, $d_z$ = +0.321, $p_"Holm"$ = .410 — trend, not corrected

Only the hit-rate reduction survives Holm correction. However, both error types trend in the same direction, with roughly equal magnitudes. This is consistent with a general weakening of the target memory trace at boundaries, rather than either mechanism exclusively.

#figure(
  image("figures_phase2/phase2_response_direction_targets.png", width: 100%),
  caption: [Stacked proportions of "old", "similar", and "new" responses for target trials, by boundary position and condition. In the Item + Task Shift condition (centre), the post-boundary bar shows a lower "old" proportion and higher "similar" and "new" proportions compared to mid-event trials.],
)

== SDT sensitivity (d-prime) by boundary position

Signal detection theory d-prime provides a bias-free measure of recognition sensitivity. Using per-participant foil FA rate as the constant false-alarm baseline:

- Item + Task Shift: Friedman $chi^2$(2) = 11.47, $p$ = .003, Kendall's $W$ = 0.117
- Item + Task Shift post-mid d' contrast: $overline(Delta d')$ = −0.218, $d_z$ = −0.473, $p_"Holm"$ = .016 — significant
- Item + Task Shift post-pre d' contrast: $overline(Delta d')$ = −0.188, $d_z$ = −0.355, $p_"Holm"$ = .098 — marginal
- Task Shift Only: Friedman $chi^2$(2) = 4.10, $p$ = .129 — null
- Item Shift Only: Friedman $chi^2$(2) = 1.36, $p$ = .508 — null

The d' analysis yields the same Friedman statistic as the correctness analysis, because FA rate is constant across boundary positions. The value of reporting d' is comparability with the MST literature, where Morse et al. (2023) report all boundary effects in d' units. Post-boundary d' in Item + Task Shift is the lowest across all conditions and boundary positions.

#figure(
  image("figures_phase2/phase2_sdt_dprime_by_boundary.png", width: 100%),
  caption: [SDT sensitivity (d') by boundary position and condition. Error bars are ±1 SE. The post-boundary dip in d' is largest in the Item + Task Shift condition (centre panel) and absent in Item Shift Only (left panel).],
)

== Lure false alarm rate and the LDI non-replication

Morse et al. (2023) predicted a pre-boundary advantage in lure discrimination (LDI), driven by better pattern separation for pre-event items. This did not replicate in Phase 1. Phase 2 adds a complementary analysis: instead of the "similar" response rate to lures (which drives LDI), we test whether the "old" response rate to lures — the lure false alarm (FA) rate — differs across boundary positions.

For Item + Task Shift lure trials:
- pre-mid FA contrast: $overline(x)$ = +0.045, $t$(48) = 2.67, $d_z$ = +0.381, $p$ = .010, $p_"Holm"$ = .093

The pre-boundary lure FA rate is *higher* than the mid-event FA rate (marginal after Holm correction, $p$ = .093). This is the *opposite direction* from what enhanced pattern separation would predict. Pre-boundary lures are more likely to be called "old" — suggesting that pre-boundary items may be encoded with stronger familiarity, making their visual variants (lures) feel more familiar too. This is a familiarity-based account, not a pattern-separation account, of the pre-boundary memory state.

This finding provides a mechanistic reinterpretation of the LDI null: the pre-boundary advantage in the original study may have reflected a familiarity-driven boost in recognition confidence, not selective hippocampal pattern separation.

#figure(
  image("figures_phase2/phase2_lure_false_alarm_by_boundary.png", width: 100%),
  caption: [P("old" | lure) — lure false alarm rate — by boundary position and condition. Error bars are 95% CI. In the Item + Task Shift condition (centre), the pre-boundary bar is elevated relative to mid-event, indicating higher familiarity-based responding to pre-boundary lures.],
)

== Post-hoc power and the LDI non-replication

Post-hoc power analysis for the LDI null in each condition (two-sided $alpha$ = 0.05):

- Item + Task Shift ($n$ = 49): power = 0.28 (small, $d_z$ = 0.20), 0.54 (medium, $d_z$ = 0.30), 0.78 (large, $d_z$ = 0.40)
- Item Shift Only ($n$ = 56): power = 0.30, 0.59, 0.83
- Task Shift Only ($n$ = 53): power = 0.29, 0.57, 0.81

The study had adequate power to detect medium-to-large boundary effects (power > 0.54 for $d_z$ ≥ 0.30). Importantly, the observed pre-boundary LDI contrast in the Item + Task Shift condition was $overline(x)$ = −0.031 (slightly *negative*, wrong direction). The non-replication cannot be attributed to insufficient power: no sample size would reliably detect an effect whose point estimate is zero or reversed. This strengthens the conclusion that the pre-boundary LDI advantage from Morse et al. (2023) did not reproduce in our sample.

== Integrative interpretation

Phase 2 converges on a coherent story that sharpens Phase 1:

1. *The post-boundary recognition cost is real and condition-specific.* It is confirmed by the Friedman test and Holm-corrected contrasts in the Item + Task Shift condition. It is not present when only items shift (Item Shift Only) or only the task rule shifts (Task Shift Only — marginal trend only).

2. *The cost is concentrated in Objects.* The significant Scenes × boundary interaction in the primary GEE shows that the post-boundary advantage for mid-event items is specific to Objects; Scenes do not show the same pattern.

3. *Encoding RT slowdown and recognition cost are parallel effects, not a chain.* The carry-over analysis finds no trial-level relationship between encoding RT and test correctness once boundary position is controlled. Both effects are driven by the same boundary condition, but the encoding disruption does not cause the memory failure.

4. *Item role and stimulus structure are the dominant drivers of correctness.* Lure difficulty, stimulus class, and item role consistently outperform boundary position in adjusted models, underscoring that MST task structure matters more than boundary timing once other factors are controlled.

5. *The post-boundary cost reflects a general weakening, not a single error type.* Response direction decomposition shows that the hit-rate drop at post-boundary is split between more "new" misses and more "similar" errors, both trending upward (only the hit-rate decrease survives Holm correction). This is consistent with a weakened and poorly differentiated memory trace for post-boundary items.

6. *SDT d-prime confirms the correctness pattern.* Post-boundary $d'$ is lowest in the Item + Task Shift condition and the Friedman test on $d'$ gives the same result as on raw correctness, providing cross-measure consistency and direct comparability with Morse et al. (2023).

7. *Pre-boundary lures show elevated "old" responses — a familiarity, not pattern separation, account.* The marginal pre-mid lure FA elevation (opposite direction to LDI) suggests pre-boundary items are stored with higher familiarity. This reframes the LDI null: the Morse et al. pre-boundary advantage may reflect familiarity-based recognition confidence, not hippocampal pattern separation.

== Robustness analyses
Three robustness checks were conducted:

1. *Outlier-trimmed RT rerun:* Excluding 3 participant-level RT outliers (|z| > 3) did not change the RT story. Correct responses remained faster than incorrect, and lure trials remained slower than target trials.

2. *Split correctness models:* Modelling target and lure correctness separately confirmed key patterns. For lure trials: lure-bin slope OR = 1.192 per unit, $p$ < .001; Scenes OR = 0.677, $p$ < .001. For target trials: stimulus class effect OR = 0.635, $p$ < .001; boundary effects not significant in adjusted model.

3. *Focused boundary contrasts:* The only Holm-corrected significant boundary contrast was Item + Task Shift target post-minus-mid ($d_z$ = −0.477, corrected $p$ = .020). All other condition × role × contrast combinations had corrected $p$ > 0.10.

= Conclusion
Phase 2 achieved the confirmatory objectives, corrected three technical errors, and added nine previously planned or newly identified analyses.

Main takeaways:
1. *Post-boundary recognition cost confirmed:* Friedman $chi^2$(2) = 11.47, $p$ = .003, Kendall's $W$ = 0.117; post-mid contrast $d_z$ = −0.477, Holm $p$ = .020, Item + Task Shift condition.
2. *SDT d-prime converges:* Post-mid d' contrast $d_z$ = −0.473, Holm $p$ = .016 — providing cross-measure confirmation and MST-literature compatibility.
3. *New finding — stimulus class × boundary interaction:* The post-boundary cost is concentrated in Objects; Scenes show a different (weaker or reversed) boundary profile.
4. *Response direction: general weakening.* The post-boundary hit-rate drop is split between "new" misses and "similar" errors; neither error type alone survives Holm correction, consistent with a general trace weakening.
5. *Carry-over null:* Encoding RT at study does not predict trial-level test correctness. The encoding disruption and memory cost are parallel, not causal.
6. *Lure FA elevation — familiarity account of LDI null:* Pre-boundary lures are more often called "old" ($d_z$ = +0.381, Holm $p$ = .093 — marginal). This contradicts pattern-separation and supports a familiarity-based explanation.
7. *Post-hoc power confirms non-replication:* The study had power > 0.54 to detect medium effects ($d_z$ ≥ 0.30). The observed LDI contrast was −0.031 (wrong direction), ruling out power as an explanation for the null.
8. *Lure difficulty and stimulus class dominate correctness once modelled jointly.*
9. *Speed-accuracy coupling is consistent:* Incorrect responses are slower by ≈ 0.278 s across all boundary positions; boundary position does not shift the speed-accuracy gap.

#pagebreak()

= Codebase and contributions
The source code for this project is available at #link("https://github.com/ch-pavan/brim")[https://github.com/ch-pavan/brim].

Phase 2 was completed collaboratively:
1. *Sambu Aneesh:* Framed confirmatory questions, statistical interpretation logic, and identified the technical issues corrected in this revision.
2. *Renu Sree Vyshnavi:* Led results interpretation, quality-control narrative, and the carry-over analysis framing.
3. *Pavan Harshit:* Implemented the Phase 2 pipeline, corrected all three bugs, added five new analyses, generated figures and tables, and integrated all report assets.

#text(weight: "bold")[References]
#set par(leading: 0.38em)
#text(size: 7.5pt)[
[1] J. M. Zacks and K. M. Swallow, "Event Segmentation," *Current Directions in Psychological Science*, 16(2), 80-84, 2007. <ref-zacks2007event>\
[2] K. M. Swallow, J. M. Zacks, and R. A. Abrams, "Event Boundaries in Perception Affect Memory Encoding and Updating," *Journal of Experimental Psychology: General*, 138(2), 236-257, 2009. <ref-swallow2009boundaries>\
[3] S. M. Stark, C. B. Kirwan, and C. E. L. Stark, "Mnemonic Similarity Task: A Tool for Assessing Hippocampal Integrity," *Trends in Cognitive Sciences*, 2019. <ref-stark2019mst>\
[4] M. A. Yassa and C. E. L. Stark, "Pattern Separation in the Hippocampus," *Trends in Neurosciences*, 34(10), 515-525, 2011. <ref-yassa2011pattern>\
[5] S. J. Morse, A. B. Karagoz, and Z. M. Reagh, "Event Boundaries Directionally Influence Item-Level Recognition Memory," 2023. <ref-morse2023event>
]
