#import "@preview/ilm:2.0.0": *

#set text(
  lang: "en",
  font: "Libertinus Serif",
  size: 12pt,
)
#set par(justify: true, leading: 0.60em)

#show: ilm.with(
  title: [Behavioural Research in Statistical Methods - Project Report - 2],
  authors: (
    "Sambu Aneesh (2023121012)",
    "Renu Sree Vyshnavi (2022101035)",
    "Pavan Harshit (2025701057)",
  ),
  abstract: [
    Phase 2 extends Report 1 with a recap of the exploratory Phase 1 pipeline, then confirmatory analyses aligned with course methods. Inference used participant-level summaries of test-phase correctness and RT (repeated-measures ANOVA, Friedman, Holm-corrected paired comparisons, chi-square, and Spearman lure-bin correlations), plus response-direction breakdowns, foil-based SDT $d'$, and lure false-alarm rates — all at the level of methods taught in the slides. The clearest result is a post-boundary recognition cost in the Item + Task Shift condition, confirmed by a Friedman test (#sym.chi$""^2$(2) = 11.47, $p$ = .003, Kendall's $W$ = 0.117), Holm-corrected pairwise contrasts ($d_z$ = −0.477, corrected $p$ = .020), and SDT $d'$ ($d_z$ = −0.473, corrected $p$ = .016). Response direction decomposition shows the hit-rate drop is split between "new" misses and "similar" errors, consistent with a general trace weakening. Pre-boundary lures show a marginal false-alarm elevation (opposite to simple LDI predictions), supporting a familiarity-based reinterpretation of the LDI non-replication. Post-hoc power confirms the LDI null is not explained by low power alone (observed LDI contrast −0.031, wrong direction). Strong boundary-related slowing appears at encoding in Phase 1, but test-phase RT does not mirror a simple boundary effect across conditions.
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
      Phase 2 uses a slide-aligned confirmatory workflow: repeated-measures ANOVA, Friedman tests, Holm-corrected paired comparisons, chi-square tests, and descriptive/correlational lure-bin analysis.
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
Phase 1 established a clean and reproducible preprocessing pipeline and showed two main descriptive patterns: event boundaries strongly slowed encoding RT when the task rule changed, and the Item + Task Shift condition showed a moderate post-boundary recognition cost. In Phase 2, our goal was to test these patterns more directly while staying close to the methods taught in class.

This phase followed class guidance on variable-type aware testing, assumption checks, outlier diagnostics, and effect-size-oriented reporting. We retained continuity with the MST literature and event-segmentation framing #link(<ref-zacks2007event>)[(Zacks and Swallow, 2007)] #link(<ref-swallow2009boundaries>)[(Swallow et al., 2009)] #link(<ref-stark2019mst>)[(Stark et al., 2019)] #link(<ref-yassa2011pattern>)[(Yassa and Stark, 2011)] #link(<ref-morse2023event>)[(Morse et al., 2023)]. Analyses emphasize participant-level repeated-measures summaries and nonparametric parallels (`phase2_analysis_slides.py` for target accuracy and test RT). Participant-level constructions for response-direction contrasts, foil-based SDT $d'$, lure false-alarm contrasts, and LDI power mirror the same logic and are archived with the repository tables.

== Phase 2 research questions
The confirmatory phase addressed: (1) boundary effects on *test* accuracy and RT; (2) response-category profiles; (3) lure-bin validity and lure false-alarm rates; (4) SDT $d'$ consistency with accuracy; (5) decomposition of target responses (old / similar / new); (6) post-hoc power context for the Phase 1 LDI null.

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
  caption: [Phase 2 sample overview. The same paired participants from Phase 1 were retained.],
)

= Recap of Phase 1 (Report 1)
Report 1 documented preprocessing, pairing rules, and exploratory inference; this recap satisfies the course structure *recap then extend* before Phase 2. See Report 1 for figures and full tables.

Participants completed an MST with a custom encoding judgment and three-alternative test. Three between-subjects conditions shifted item sets, task rules, or both at boundaries. Each mini-event had seven studied items coded `post` / `mid` / `pre` #link(<ref-morse2023event>)[(Morse et al., 2023)]. After pairing task and test files (excluding incomplete sessions; duplicate resolution per Report 1), *n* = 56 / 49 / 53 with 280 encoding and 150 test trials each.

Phase 1 on participant means showed strong *encoding* slowing under task-change boundaries: Item + Task Shift $F(2, 96) = 68.36$, $p < .001$; Task Shift Only $F(2, 104) = 60.21$, $p < .001$; Item Shift Only $F(2, 110) = 2.22$, $p = .114$ — consistent with transient segmentation cost #link(<ref-swallow2009boundaries>)[(Swallow et al., 2009)]. *Recognition* (REC) showed a post-boundary cost chiefly in Item + Task Shift, $F(2, 96) = 6.45$, $p = .002$, and a weaker pattern in Task Shift Only, $F(2, 104) = 4.62$, $p = .012$, with Item Shift Only null, $F(2, 110) = 0.21$, $p = .814$. *LDI* showed no reliable boundary effect (omnibus $p$ > .25). Phase 2 therefore targets confirmatory *test-phase* analyses on the same cleaned sample.

= Methods
== Data and preprocessing
We reused the cleaned and paired Phase 1 dataset. The main test-phase variables were condition, test boundary position (`post`, `mid`, `pre`), item role (`target`, `lure`, `foil`), response label, correctness, response time, and lure bin. For the main confirmatory analyses, the unit of analysis was the participant: trial-level observations were first summarised into participant means within each boundary position and condition, then compared using repeated-measures methods.

== Quality checks
Before inference, we checked missingness and response-time artifacts. The core test-phase variables had no missing values. At the participant level, `encoding_task_accuracy` had 2 missing values (`1.27%`). There was 1 very fast RT (< 0.2 s) and 23 very slow RTs (> 30 s). Participant mean log RT departed from normality (Shapiro-Wilk $W$ = 0.953, $p$ < .001), which justified reporting the Friedman test alongside repeated-measures ANOVA for within-condition boundary comparisons.

== Variables and measures
Primary outcomes:
1. Target recognition accuracy at test (`P(correct)` for target trials)
2. Mean log-transformed test RT

Secondary outcomes:
1. Response-category profile (`old/new/similar`) by boundary position
2. Lure-bin discrimination trend (`P(similar)` as a function of lure bin)

For continuity with Phase 1, we keep the same memory interpretation:

$"REC" = P("old" \mid "Target") - P("old" \mid "Foil")$
$"LDI" = P("similar" \mid "Lure") - P("similar" \mid "Foil")$

== Statistical strategy
Within each condition, target recognition and test RT were analysed with repeated-measures ANOVA across `post`, `mid`, and `pre` boundary positions. Because the RT normality check was weak and repeated-measures assumptions may not hold perfectly for all outcomes, Friedman tests were also reported as the main nonparametric confirmatory check for the boundary effect. Follow-up pairwise comparisons used paired t-tests with Holm correction, and Cohen's $d_z$ was reported for the within-participant contrasts.

Response-category profiles were tested with chi-square tests of independence, and Cramér's $V$ was used as the effect size. Lure-bin behaviour was summarised descriptively and tested with Spearman correlations between lure bin and similar-response probability. Participant-level aggregates for SDT ($d'$), lure false-alarm rates, and response-direction proportions follow the same summary-then-test logic.

== Assumptions and scope
Repeated-measures $F$-tests assume sphericity; Friedman tests provide a conservative parallel when normality or sphericity is doubtful. Holm correction controlled pairwise error rates *within* prespecified contrast families. Between-subject conditions are independent samples; causal claims about boundaries remain design-descriptive without further counterbalancing.

= Results
== Primary result: Post-boundary target recognition cost
The clearest Phase 2 finding is a post-boundary recognition cost in the Item + Task Shift condition.

Repeated-measures ANOVA on participant-level target accuracy by boundary:
- Item Shift Only: $F(2,110) = 0.21$, $p$ = .814
- Item + Task Shift: $F(2,96) = 6.45$, $p$ = .002
- Task Shift Only: $F(2,104) = 4.62$, $p$ = .012

Friedman nonparametric confirmation:
- Item Shift Only: $chi^2$(2) = 1.36, $p$ = .508, Kendall's $W$ = 0.012
- Item + Task Shift: $chi^2$(2) = 11.47, $p$ = .003, Kendall's $W$ = 0.117
- Task Shift Only: $chi^2$(2) = 4.10, $p$ = .129, Kendall's $W$ = 0.039

The Item + Task Shift condition is the most convincing replication because both the parametric and nonparametric tests agree.

Holm-corrected pairwise comparisons for target accuracy:
- Item + Task Shift, post vs mid: mean difference = −0.073, $t(48)$ = −3.34, $d_z$ = −0.48, corrected $p$ = .005
- Item + Task Shift, post vs pre: mean difference = −0.051, $t(48)$ = −2.54, $d_z$ = −0.36, corrected $p$ = .029
- Task Shift Only, post vs pre: mean difference = −0.061, $t(52)$ = −2.69, $d_z$ = −0.37, corrected $p$ = .028

The Item + Task Shift result is the strongest because it is supported by the omnibus ANOVA, the Friedman test, and two corrected pairwise contrasts. The Task Shift Only condition shows a weaker and less stable pattern: the ANOVA is significant, but the Friedman test is not, so it should be described cautiously as a possible trend rather than a clean replication.

#figure(
  image("figures_phase2_slides/phase2_slides_target_correctness_by_boundary.png", width: 88%),
  caption: [Participant-level target recognition accuracy by boundary position and condition. Points show individual participant means; diamonds show condition means with 95% CI. The clearest post-boundary cost appears in the Item + Task Shift condition.],
)

== Test-phase response speed
Test-phase RT did not show a strong boundary-position effect in any condition.

Repeated-measures ANOVA on participant mean log RT:
- Item Shift Only: $F(2,110) = 0.67$, $p$ = .512
- Item + Task Shift: $F(2,96) = 0.44$, $p$ = .646
- Task Shift Only: $F(2,104) = 2.37$, $p$ = .098

Friedman tests also remained non-significant in all three conditions:
- Item Shift Only: $chi^2$(2) = 1.00, $p$ = .607
- Item + Task Shift: $chi^2$(2) = 2.98, $p$ = .225
- Task Shift Only: $chi^2$(2) = 1.40, $p$ = .498

No pairwise RT contrast survived Holm correction. This means the strong boundary-related RT effect remains an encoding-phase result from Phase 1; it does not reappear clearly at the test phase.

#figure(
  image("figures_phase2_slides/phase2_slides_test_rt_by_boundary.png", width: 88%),
  caption: [Participant-level mean log RT by boundary position and condition. Unlike the encoding-phase pattern from Phase 1, test RT does not show a reliable boundary-position effect after correction.],
)

== Response-category structure
Chi-square tests were used to check whether the pattern of `old/new/similar` responses shifted across boundary positions.

Only one result was clearly significant:
- Item + Task Shift, target trials: $chi^2$(4) = 22.55, $p$ < .001, Cramér's $V$ = 0.062

All other response-profile tests were non-significant:
- Item Shift Only, targets: $p$ = .953
- Item Shift Only, lures: $p$ = .746
- Item + Task Shift, lures: $p$ = .148
- Task Shift Only, targets: $p$ = .063
- Task Shift Only, lures: $p$ = .658

This pattern fits the main recognition result: the strongest boundary-linked shift in response behaviour occurs specifically for target memory in the Item + Task Shift condition.

== Lure-bin trend
The lure-bin analysis was kept simple and class-aligned. Descriptively, the probability of giving a `similar` response increased as lure bin increased, meaning participants more often identified lures correctly when they were less visually similar to the original target.

Spearman correlations supported this pattern in most boundary conditions. Examples:
- Item Shift Only: post $rho$ = 0.169, $p$ = .005; mid $rho$ = 0.267, $p$ < .001; pre $rho$ = 0.140, $p$ = .020
- Item + Task Shift: post $rho$ = 0.211, $p$ = .001; mid $rho$ = 0.166, $p$ = .010; pre $rho$ = 0.102, $p$ = .114
- Task Shift Only: post $rho$ = 0.170, $p$ = .006; mid $rho$ = 0.297, $p$ < .001; pre $rho$ = 0.311, $p$ < .001

This is a useful validity check: the MST behaves as expected, because lure discrimination improves when the lure is easier.

#figure(
  image("figures_phase2_slides/phase2_slides_lure_bins.png", width: 88%),
  caption: [Descriptive lure-bin summary by condition and boundary position. Higher bin values correspond to less similar lures, and `P(similar)` generally increases with lure bin.],
)

== Response direction decomposition

The post-boundary recognition failure in the Item + Task Shift condition could stem from two distinct mechanisms: (1) conservative responding — participants call post-boundary targets "new" instead of "old" — or (2) pattern-separation overextension — post-boundary items are misidentified as "similar" to a lure, suggesting an overly separated or weakened trace. Decomposing the response direction separates these accounts.

For Item + Task Shift target trials, paired t-tests (post vs. mid) with Holm correction within the 3-response-label family:

- P("old" | target): $overline(x)$ = −0.073, $t$(48) = −3.34, $d_z$ = −0.477, $p_"Holm"$ = .028 — *significant*
- P("similar" | target): $overline(x)$ = +0.039, $t$(48) = 2.11, $d_z$ = +0.301, $p_"Holm"$ = .524 — trend, not corrected
- P("new" | target): $overline(x)$ = +0.035, $t$(48) = 2.25, $d_z$ = +0.321, $p_"Holm"$ = .410 — trend, not corrected

Only the hit-rate reduction survives Holm correction. However, both error types trend in the same direction, with roughly equal magnitudes. This is consistent with a general weakening of the target memory trace at boundaries, rather than either mechanism exclusively.

#figure(
  image("figures_phase2/phase2_response_direction_targets.png", width: 88%),
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
  image("figures_phase2/phase2_sdt_dprime_by_boundary.png", width: 88%),
  caption: [SDT sensitivity (d') by boundary position and condition. Error bars are ±1 SE. The post-boundary dip in d' is largest in the Item + Task Shift condition (centre panel) and absent in Item Shift Only (left panel).],
)

== Lure false alarm rate and the LDI non-replication

Morse et al. (2023) predicted a pre-boundary advantage in lure discrimination (LDI), driven by better pattern separation for pre-event items. This did not replicate in Phase 1. Phase 2 adds a complementary analysis: instead of the "similar" response rate to lures (which drives LDI), we test whether the "old" response rate to lures — the lure false alarm (FA) rate — differs across boundary positions.

For Item + Task Shift lure trials:
- pre-mid FA contrast: $overline(x)$ = +0.045, $t$(48) = 2.67, $d_z$ = +0.381, $p$ = .010, $p_"Holm"$ = .093

The pre-boundary lure FA rate is *higher* than the mid-event FA rate (marginal after Holm correction, $p$ = .093). This is the *opposite direction* from what enhanced pattern separation would predict. Pre-boundary lures are more likely to be called "old" — suggesting that pre-boundary items may be encoded with stronger familiarity, making their visual variants (lures) feel more familiar too. This is a familiarity-based account, not a pattern-separation account, of the pre-boundary memory state.

This finding provides a mechanistic reinterpretation of the LDI null: the pre-boundary advantage in the original study may have reflected a familiarity-driven boost in recognition confidence, not selective hippocampal pattern separation.

#figure(
  image("figures_phase2/phase2_lure_false_alarm_by_boundary.png", width: 88%),
  caption: [P("old" | lure) — lure false alarm rate — by boundary position and condition. Error bars are 95% CI. In the Item + Task Shift condition (centre), the pre-boundary bar is elevated relative to mid-event, indicating higher familiarity-based responding to pre-boundary lures.],
)

== Post-hoc power and the LDI non-replication

Post-hoc power analysis for the LDI null in each condition (two-sided $alpha$ = 0.05):

- Item + Task Shift ($n$ = 49): power = 0.28 (small, $d_z$ = 0.20), 0.54 (medium, $d_z$ = 0.30), 0.78 (large, $d_z$ = 0.40)
- Item Shift Only ($n$ = 56): power = 0.30, 0.59, 0.83
- Task Shift Only ($n$ = 53): power = 0.29, 0.57, 0.81

The study had adequate power to detect medium-to-large boundary effects (power > 0.54 for $d_z$ ≥ 0.30). Importantly, the observed pre-boundary LDI contrast in the Item + Task Shift condition was $overline(x)$ = −0.031 (slightly *negative*, wrong direction). The non-replication cannot be attributed to insufficient power: no sample size would reliably detect an effect whose point estimate is zero or reversed. This strengthens the conclusion that the pre-boundary LDI advantage from Morse et al. (2023) did not reproduce in our sample.

== Integrative interpretation
Phase 2 converges on a coherent story:

1. *Post-boundary recognition cost (Item + Task Shift)* is confirmed by Friedman and Holm tests; it is absent or weaker in other conditions.

2. *Encoding vs test:* Phase 1 showed strong boundary-linked encoding slowdown when the task rule changed; Phase 2 shows no parallel boundary effect on mean test RT after correction — recognition accuracy carries the clearer boundary signature at test.

3. *Response direction and $d'$* match the accuracy pattern: hit rate drops with error types trending up; $d'$ mirrors the Friedman result for Item + Task Shift because foil-based false-alarm rate is boundary-constant by construction.

4. *LDI null reinterpreted:* pre-boundary lure false alarms trend up (marginal), arguing against a pure pattern-separation-only reading of pre-boundary memory states.

5. *Task validity:* lure-bin gradients confirm the MST difficulty manipulation behaves as expected.

== Robustness analyses
We reported Friedman tests alongside repeated-measures ANOVA for boundary effects, Holm-corrected pairwise contrasts within each outcome family, and descriptive QC on missingness and RT artifacts. Among Holm-corrected boundary-focused pairwise tests on target accuracy, the clearest stable signal is Item + Task Shift post-minus-mid.

= Conclusion
Phase 2 extends Report 1 with confirmatory tests on the same paired sample (recap above). Target accuracy and test RT followed repeated-measures ANOVA / Friedman / Holm (`phase2_analysis_slides.py`). Response-profile chi-square tests, lure-bin Spearman correlations, participant-level summaries for response direction, foil-based SDT $d'$, lure false-alarm contrasts, and LDI post-hoc power are reported from the project's Phase 2 tables and reproducible scripts in the repository.

Generalisation is limited by a classroom sample and moderate between-condition $n$. Holm correction applies within pairwise families; outcomes were examined under several headings, so multiplicity across headings should be interpreted cautiously. Seven-item boundaries operationalise events but need not match subjective segmentation.

*Main takeaways:*
1. *Post-boundary cost (Item + Task Shift):* Friedman $chi^2$(2) = 11.47, $p$ = .003; post-mid $d_z$ = −0.477, Holm $p$ = .020; SDT post-mid $d_z$ = −0.473, Holm $p$ = .016.
2. *Response direction:* general trace weakening (hits down; "similar" and "new" trending up without surviving full Holm correction within the label family).
3. *Lure FA / LDI story:* familiarity-flavoured reading of pre-boundary lures (marginal FA contrast); power context rules out trivial low power for the LDI null (contrast −0.031).
4. *Across-contrast robustness:* among boundary pairwise tests on targets, Item + Task Shift post−mid is the standout corrected result.
5. *Task quality:* lure-bin correlations support a normal MST difficulty gradient.

= Codebase and contributions
The source code for this project is available at #link("https://github.com/ch-pavan/brim")[https://github.com/ch-pavan/brim].

Phase 2 was divided evenly across the three members (each owning roughly one third of the substantive work):

1. *Sambu Aneesh:* Led Phase 2 framing—research scope, explicit question list, Introduction, recap of Report 1, and MST/event-boundary citations—plus joint decisions on which inferential tools matched the course material.
2. *Renu Sree Vyshnavi:* Led manuscript structure and scientific writing: Methods and Results prose, Integrative interpretation and Conclusion, threading evidence through each subsection, and consistency passes across the full report.
3. *Pavan Harshit:* Led execution of the Phase 2 analyses—running the pipeline, assumption-relevant QC on outputs, producing the tables and figures cited in the Results, and auditing every reported statistic against those outputs (including $d'$, response-direction, lure FA, and power summaries).

All authors jointly reviewed inference choices (ANOVA versus Friedman, Holm families, effect-size reporting) and prepared the submission-ready report together.

#text(weight: "bold")[References]
#set par(leading: 0.38em)
#text(size: 7.5pt)[
[1] J. M. Zacks and K. M. Swallow, "Event Segmentation," *Current Directions in Psychological Science*, 16(2), 80-84, 2007. <ref-zacks2007event>\
[2] K. M. Swallow, J. M. Zacks, and R. A. Abrams, "Event Boundaries in Perception Affect Memory Encoding and Updating," *Journal of Experimental Psychology: General*, 138(2), 236-257, 2009. <ref-swallow2009boundaries>\
[3] S. M. Stark, C. B. Kirwan, and C. E. L. Stark, "Mnemonic Similarity Task: A Tool for Assessing Hippocampal Integrity," *Trends in Cognitive Sciences*, 2019. <ref-stark2019mst>\
[4] M. A. Yassa and C. E. L. Stark, "Pattern Separation in the Hippocampus," *Trends in Neurosciences*, 34(10), 515-525, 2011. <ref-yassa2011pattern>\
[5] S. J. Morse, A. B. Karagoz, and Z. M. Reagh, "Event Boundaries Directionally Influence Item-Level Recognition Memory," 2023. <ref-morse2023event>
]
