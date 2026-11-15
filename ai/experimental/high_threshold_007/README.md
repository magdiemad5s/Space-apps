# High-class threshold experiment 007

This is an isolated, validation-only comparison of decision rules for tomorrow's
**synthetic** High fatigue category. No estimator, imputer, or calibrator is fitted.
The serving model, original datasets, application APIs and experiment 006 remain
unchanged. No threshold is deployed by this study.

## Results

Original serving-model validation, 1,080 observations including 138 High targets:

| Decision | High recall | High precision | High F1 | Macro-F1 | Missed High | False High |
|---|---:|---:|---:|---:|---:|---:|
| Existing argmax | 37.68% | 35.14% | 0.3636 | 0.5273 | 86 | 96 |
| Threshold 0.43 | 41.30% | 35.63% | 0.3826 | 0.5322 | 81 | 103 |
| Threshold 0.41 | 43.48% | 34.68% | 0.3859 | 0.5317 | 78 | 113 |
| Threshold 0.27 | 60.87% | 26.75% | 0.3717 | 0.4932 | 54 | 230 |
| Threshold 0.21 | 70.29% | 22.77% | 0.3440 | 0.4552 | 41 | 329 |
| Threshold 0.14 | 80.43% | 18.47% | 0.3004 | 0.3794 | 27 | 490 |

**0.43 is a discussion candidate, not an adopted policy.** In this validation
sample it detected five additional High cases and added seven false High labels,
with no previously detected High cases lost. Threshold 0.41 detected eight more
High cases but added seventeen false High labels. Pushing recall above 70% more
than tripled false High labels (96 to 329). These trade-offs do not show a large
recall improvement at little cost.

The maximum grid Macro-F1 was 0.5323 at threshold 0.46. It gained two previously
missed High cases but lost one previously detected High case, for a net gain of
one. That point illustrates why a slightly higher Macro-F1 need not satisfy a
stronger High-recall objective.

High average precision was **0.2888**, against prevalence 0.1278. The separate
experiment 006 RF26 control had a similar qualitative result: its illustrative
threshold 0.46 raised validation recall from 37.04% to 37.78%, while a 70% recall
target required 316 false High labels versus the original 84. It does not confirm
the primary cohort's chosen threshold because both cohorts select their own
points using their reused validation observations.

The numerical sweep took approximately 3.16 seconds; preparation and review are
additional work. Twelve hand-auditable utility tests passed. Independent review
recomputed metrics, all PR points, AP and shortlist rules, and verified 255
protected pre-existing files unchanged. No classifier or calibration fit occurred.

## Files to share

- [Three-page results and graphs PDF](reports/ASTRA_SHIELD_High_Threshold_Experiment_007.pdf)
- [Original-model shortlist CSV](results/primary/shortlist.csv)
- [All 101 original-model thresholds CSV](results/primary/allthresholdmetrics.csv)
- [Original-model precision-recall curve CSV](results/primary/PRcurve.csv)
- [Original-model confusion matrices CSV](results/primary/confusionmatrices.csv)
- [Separate experiment 006 control summary](results/secondary/summary.json)
- [Independent review](INDEPENDENT_REVIEW.json)
- [Reproduction instructions](REPRODUCIBILITY.md)

## Why two separate comparisons?

The quoted **43.7% High recall, 80 missed out of 142** belongs to experiment 006's
previously reported fresh synthetic test results. Its RF26 control detected 62
High rows, predicted Moderate for 71 and Low for 9. The RF28 extension also
detected 62, with 72 Moderate and 8 Low errors. Neither artifact is the original
serving model.

The original serving model's previously reported test recall was 65/142 = 45.8%.
These historical summaries identify the source of the request; this study does
not recompute their results or score new thresholds on either test partition.

The **primary comparison** uses the original serving RF26 and its original
validation partition: 1,080 observations from 18 virtual participants, including
138 High rows. The **secondary comparison** uses the experiment 006 RF26 control's
already saved validation probabilities: another 1,080 observations from 18 other
virtual participants, including 135 High rows. Secondary probabilities have the
12-decimal precision saved by that earlier experiment. Cohorts, models and results
are never pooled.

## Decision rule and selection

The existing baseline is multiclass **argmax**: choose the largest of Low,
Moderate and High probabilities. It is not equivalent to setting a fixed High
threshold of 0.5.

For each candidate threshold `t`:

```text
if P(High) >= t:
    predict High
else:
    choose the larger of P(Low) and P(Moderate)
    break an exact Low/Moderate tie in favor of Low
```

`P(High)` denotes an uncalibrated model score, not a medical risk probability.
Changing this rule changes predictions; it does not improve the underlying score
ranking or retrain the model. A threshold can both promote existing non-High
predictions and demote existing High predictions. Those counts are reported.

The frozen [plan](PLAN.json) specifies thresholds 0.00 through 1.00 in increments
of 0.01, along with these comparison points:

- Original argmax.
- Highest High-class F1 on the grid.
- Highest Macro-F1 on the grid.
- Highest High precision among thresholds reaching at least 60%, 70% or 80% recall.
- An illustrative trade-off: maximize recall while preserving baseline High
  precision and allowing at most a 0.02 Macro-F1 reduction. This is an explicit
  engineering assumption, not a clinical acceptance criterion.

Tie-breaking rules were recorded before the sweep. There is no agreed clinical
false-alarm budget, so these are proposals for discussion rather than a selected
production policy. The exact High-versus-rest precision-recall curve uses all
unique validation scores, independently of the 0.01 reporting grid.

## Reading the metrics

High recall is `TP / (TP + FN)`; High precision is `TP / (TP + FP)`; High F1 is
their harmonic mean. Macro-F1 gives the three categories equal weight. Confusion
matrices use actual rows and predicted columns ordered **Low, Moderate, High**.

False positives mean a predicted High label for a synthetic Low or Moderate
outcome. They do not establish that a medical intervention was unnecessary.

- `FP / actual non-High` is the High false-positive rate.
- `100 * FP / all observations` is false High predictions per 100 assessments.
- `100 * predicted High / all observations` is total High predictions per 100
  assessments, including true positives.

These denominators differ. Precision is undefined when no High labels are
predicted; the table leaves it empty rather than claiming perfect precision.
The conventional precision-recall plotting endpoint `(recall=0, precision=1)`
has no corresponding threshold and is identified separately in the exported
curve. Average precision (AP) describes ranking; it is not accuracy, a chosen
threshold, or a clinical sensitivity estimate.

## Limits and implementation status

Both validation partitions have already supported previous development choices.
Selecting and reporting thresholds on the same validation rows gives exploratory,
potentially optimistic estimates. The 60 daily observations per participant are
correlated; 1,080 rows do not represent 1,080 independent people. The previously
inspected test results motivated this experiment and must not be presented as a
new untouched confirmation set for its threshold choices.

A team-approved candidate would need independent evaluation on appropriate new
data. A later service change would also need a versioned decision policy and
explanations corresponding to the threshold-selected class. None of those
deployment changes is included here. The proposed current-alert engine remains
separate; it must not depend on this next-day forecast to handle current symptoms.

The original dataset, synthetic target definition, feature values and model
weights are preserved. Existing files are checked by byte hashes; hashing a file
does not use its observations for threshold selection. Historical test summaries
were consulted for provenance, but no raw test observations were parsed and no
new test predictions or threshold scores were computed.

## Method references

- [Scikit-learn: decision threshold tuning](https://scikit-learn.org/stable/modules/classification_threshold.html)
  distinguishes a fitted score model from its decision rule and cautions against
  fitting the classifier and tuning the threshold on the same observations.
- [Scikit-learn: precision-recall curve](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.precision_recall_curve.html)
  documents threshold alignment and the final endpoint without a threshold.

The supplied implementation uses pinned scikit-learn 1.8.0. Linked `stable`
documentation may show a later release; no newer API is required for this sweep.
