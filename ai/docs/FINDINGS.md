# Findings and model decisions

The current demo retains the original **26-feature Random Forest**. The experiments are recorded separately and none replaced the serving model. All observations and outcomes discussed here are from the original uncalibrated longitudinal **synthetic** cohort.

## Pipeline and EDA chronology

The implemented flow is participant splitting, causal feature engineering, training-fitted preprocessing, candidate fitting and comparison, artifact freezing, and a separate historical test evaluation. Identifiers, targets, and future timestamps are excluded from predictor inputs.

The **initial experimental training preceded the formal standalone EDA report**. Source consistency checks and causal feature construction already existed before that fit. Later, the EDA follow-up reviewed training-only graphs, documented feature decisions, froze two feature sets and model recipes, then fitted and compared them. The report preserves this chronology rather than presenting the initial run as EDA-first.

The [six-page visual EDA](../reports/visual_eda/ASTRA_SHIELD_visual_EDA.pdf) includes distributions, class balance, correlations, and individual longitudinal patterns. The training cohort is dominated by the Moderate class, which is why accuracy alone is not an adequate selection metric. Correlations and linked baseline/current/delta features motivated a reduced-feature experiment; correlation alone did not establish that a feature should be deleted.

## Cleaning and noise

The training audit passed 41 defined checks. It found no missing or non-finite values, exact duplicates, duplicate participant/day records, or failed documented measurement bounds. No rows were deleted and no values needed filling. Repeated participant IDs and fixed baseline values are expected in longitudinal data.

The subsequent noise audit checked reconstructable baseline changes, prior means, and next-day labels. No mismatches beyond documented rounding were found where reconstruction was possible. This establishes consistency under those checks, not biological accuracy or absence of every possible defect.

The simulator deliberately adds random physiological variation and fatigue-report noise. A conservative robust rule flagged **254 of 5,040 training rows**; all 254 were intentionally injected physiological events. Those observations are not established recording errors. Labels near the custom fatigue cutoffs are also not automatically incorrect.

See the [noise audit and experiment graphs](../experimental/noise_004/visual_report/ASTRA_SHIELD_noise_review.pdf). The original data is retained; experimental filtering affected only fitting subsets. The Isolation Forest was not retrained on an artificially anomaly-free dataset.

## Experiments

Values in the table are **Macro-F1**, not accuracy percentages. Each row identifies its own evaluation population; scores across different rows are not interchangeable.

| Experiment | Evaluation | Result | Decision |
|---|---|---|---|
| [EDA and feature reduction](../experimental/eda_first_001/SUMMARY.txt) | Existing validation, 1,080 rows | RF 26 features **0.5273**; RF 17 features **0.5189** | Retain 26 features; nine predictors omitted only in the reduced candidate |
| [Bounded model comparison](../experimental/improvement_002/RESULTS.txt) | Three participant folds within 5,040 TRAIN rows | Existing RF **0.5163**; persistence **0.5140**; tested alternatives lower | Keep the RF configuration |
| [Additional history](../experimental/history_003/RESULTS.txt) | Same 4,452 eligible TRAIN rows, three participant folds | Control **0.5100**; four extra history features **0.5161** | Small gain; both forward-time checks worsened; no replacement |
| [Tail exclusion / weighting](../experimental/noise_004/RESULTS.txt) | Same 5,040 TRAIN rows, three participant folds | Control **0.5163**; exclusion **0.5199**; weight 0.25 **0.5165** | Gain uncertain and below the predefined improvement requirement |
| [Fixed filtering on validation](../experimental/filter_validation_005/RESULTS.txt) | Same existing validation, all 1,080 rows | Control **0.5273**; filtered **0.5178** | Keep the original model |

The history study's smaller cohort reflects the need for earlier history, not deletion of invalid records. In the final filtering experiment, the unchanged model fitted all 5,040 training rows; the filtered candidate fitted 4,786. It preserved the original targets and historical features and retained every validation row. High-fatigue recall fell from **37.68% to 34.06%**. The paired participant-bootstrap interval for its Macro-F1 change was **[−0.02517, +0.00548]**, so the observed decline is also uncertain.

These are reused development comparisons. The historical final test was not reopened for these experiments. The [experimental archive](../experimental/README.md) includes frozen plans, predictions, metrics, verification, and the candidate artifacts that were actually persisted.

## Baseline evidence and limitations

The original validation comparison selected Random Forest at **0.5273**, versus XGBoost at **0.4857**. Historical final-test Macro-F1 was **0.5285**, versus **0.5181** for repeating today's fatigue category. Its participant-bootstrap gain interval included zero. Historical accuracy was **61.85%**, versus **67.04%** for always choosing the majority class; the chosen objective was Macro-F1.

Historical High-fatigue precision was **41.94%** and recall **45.77%**. These results are limited and do not establish a reliable operational alerting system. See the [frozen results](../reports/RESULTS.txt) and [model card](../reports/MODEL_CARD.txt).

The data and target are the main research limitations:

- The forecast target is a custom next-day self-report, not an objective general cognitive-readiness or medical-risk label.
- NASA background sources do not validate this simulator, its class boundaries, or the seven-day calibration choice.
- Point scores are uncalibrated model indices; probability calibration and false-alarm/sensitivity tradeoffs need separate evaluation.
- SHAP explains the fatigue classifier's prediction, not causal mechanisms or the other model outputs. Correlated current/baseline/derived features can share attribution.
- Physiological anomalies are simulator injections. Journal language is generated from templates; its historical Macro-F1 was 0.3938, with High-stress recall 0.1695.
- Participant-disjoint evaluation does not establish real-human, device, site, or long-mission generalization. The complete synthetic records do not demonstrate robust handling of missing sensor days.

Future research needs appropriately labeled real longitudinal data, protocol-compatible measurements, and independent evaluation. More tuning or more records from the same simulator cannot supply that evidence. Supporting sources and methodological notes are in the [research review](../reports/RESEARCH_MODEL_IMPROVEMENT_REVIEW.txt).

## Backend changes are integration changes

The reviewed TypeScript backend now supplies the model's actual measurement contract, uses fixed seven-day calibration and past-three-day summaries, calls `/v1/predict`, returns genuine SHAP reasons, and preserves valid observations during model outages. Raw observations are available for frontend graphs.

These changes improve consistency and failure handling. They are not an increase in model accuracy, and they do not establish that the teammate's complete Angular/Ionic application has been integrated. The [status checklist](STATUS.md) tracks the remaining work.
