# Experimental models and findings

These are completed **development experiments on synthetic data**. They are archived for review and reproduction; none replaced the current demo model in [`../artifacts/bundle.joblib`](../artifacts/bundle.joblib).

The application is still a prototype. Frontend integration, testing of the actual Angular/Ionic application, and the full demonstration remain pending. See the [AI README](../README.md) for current service setup and integration status.

## Results at a glance

Each comparison below uses the same evaluation rows within that experiment. Scores from different rows or evaluation methods are not interchangeable.

| Experiment | Evaluation | Main comparison, Macro-F1 | Decision |
|---|---|---|---|
| [001: EDA and feature reduction](eda_first_001/SUMMARY.txt) | Reused validation: 1,080 rows / 18 participants | 26-feature RF **0.5273**; 17-feature RF **0.5189** | Retain 26 features |
| [002: regularization and simpler models](improvement_002/RESULTS.txt) | 3 participant folds within 5,040 training rows / 84 participants | Existing RF **0.5163**; persistence **0.5140**; other tried recipes lower | Retain existing RF |
| [003: four additional history features](history_003/RESULTS.txt) | Same 4,452 eligible training rows, days 8–60; grouped and forward-time checks | Existing 26-feature RF **0.5100**; 30-feature RF **0.5161** | Gain too small; both forward-time checks worsened |
| [004: exclude or downweight extreme fitting rows](noise_004/RESULTS.txt) | Same 5,040 held-out training observations across 3 participant folds | Original **0.5163**; exclusion **0.5199**; weighting **0.5165** | Small uncertain gain; prespecified comparison requirement not met |
| [005: fixed filtering on original validation](filter_validation_005/RESULTS.txt) | Same reused validation: 1,080 rows / 18 participants | Original **0.5273**; filtered **0.5178** | Retain original model |
| [006: extra simulated measurements](measurement_extension_006/README.md) | Fresh synthetic cohort; grouped training CV, then separate validation and test | Fresh test: RF26 **0.5528**; selected RF28 **0.5495**; change 95% CI **[-0.0141, +0.0076]** | No supported improvement; retain original serving model |
| [007: High-class decision thresholds](high_threshold_007/README.md) | Reused validation only; original serving RF and experiment 006 control analyzed separately; no retraining | Original validation: argmax **0.5273** Macro-F1 / **37.7%** High recall; threshold 0.43 **0.5322** / **41.3%**, adding 5 true High and 7 false High labels | Discussion candidate only; no policy deployed; larger recall gains incurred many more false alarms |

**0.5273 is validation Macro-F1, not accuracy.** The later 0.5163 is the mean across training-participant cross-validation folds; it does not mean the official model changed. The original validation partition has already supported multiple development decisions, so experiments 001-005 are not fresh independent confirmation. None rescored the original cohort's final test set. Experiment 006 used a newly generated cohort and scored its own fresh test partition once; its scores are not directly comparable with 0.5273.

## Findings worth keeping

- The existing 26-feature Random Forest remains the demo baseline. The smaller 17-feature representation and extra history features did not justify replacement.
- The specified quality checks found no missing, duplicate or invalid prepared training rows requiring deletion. Cleaning has no mandatory deletion percentage.
- The noise audit flagged **254 of 5,040 training rows** under a conservative robust rule; all 254 were deliberately injected physiological events. Being unusual does not establish a recording error.
- Experimental filtering omitted those rows **during fitting only**, leaving 4,786 fitting rows. The original targets and historical features stayed intact, and every evaluation row remained. The final direct validation comparison fell from 0.5273 to 0.5178, with High-fatigue recall falling from 37.7% to 34.1%.
- Generated random variation and arbitrary fatigue cutoffs limit this simulator's predictability. None of these results validates astronaut health monitoring, medical risk, or operational readiness.
- Initial baseline training preceded the formal standalone EDA report. Experiment 001 followed documented graph review and feature decisions before its fresh fits. That chronology is preserved in the archive.
- Experiment 006 completed generation checks and training-only visual EDA before fitting. Two simulated questionnaire-range scores improved training CV but worsened validation and slightly worsened fresh test performance. Five sleep additions alone were nearly neutral in training CV. These simulations do not establish the usefulness of actual questionnaire or sensor measurements.
- Experiment 007 changed only the decision rule applied to frozen validation scores. It did not fit a model or rescore a test cohort. The original classifier uses multiclass argmax, not a fixed 0.5 High threshold. Threshold 0.21 reached 70.3% High recall on original validation, but precision fell to 22.8% and false High labels increased from 96 to 329; threshold selection remains exploratory.

## Visual reports

- [Noise audit and controlled comparison (PDF)](noise_004/visual_report/ASTRA_SHIELD_noise_review.pdf)
- [Fixed filtering versus the original validation result (PDF)](filter_validation_005/visual_report/ASTRA_SHIELD_filtered_validation.pdf)
- [Regularization comparison (PNG)](improvement_002/cv_comparison.png)
- [Baseline visual EDA (PDF)](../reports/visual_eda/ASTRA_SHIELD_visual_EDA.pdf)
- [Fresh measurement-extension experiment (PDF)](measurement_extension_006/reports/ASTRA_SHIELD_Experiment_006.pdf)
- [High-class threshold trade-offs and PR curves (PDF)](high_threshold_007/reports/ASTRA_SHIELD_High_Threshold_Experiment_007.pdf)

## What is saved

```text
experimental/
├── README.md
├── ARCHIVE_MANIFEST.json             # byte-level checksums and provenance
├── reproduce.py                     # fresh-workspace adapter; no test CSV supplied
├── source/astra_shield_ml/           # exact historical scripts and dependencies
├── eda_first_001/                    # decisions, four candidate models, results
│   └── development_models.joblib
├── improvement_002/                  # fixed recipe comparison, predictions, results
│   └── development_bundle.joblib
├── history_003/                      # plans, features, CV/time predictions; no saved final model
├── noise_004/                        # plans, masks, CV/time predictions; no saved final model
│   ├── review/
│   └── visual_report/
├── filter_validation_005/            # fixed-filter candidate, comparisons and checks
│   ├── filtered_candidate.joblib
│   ├── review/
│   └── visual_report/
├── measurement_extension_006/        # separate fresh synthetic cohort and models
│   ├── data/main.csv
│   ├── training/candidate_models.joblib
│   ├── predict_experimental.py
│   └── reports/
└── high_threshold_007/               # frozen-model validation decision rules
    ├── results/primary/
    ├── results/secondary/
    └── reports/
```

Only three model artifacts were persisted by the historical experiments. History 003 and noise 004 fitted models for their comparisons but did **not** save a new full-data serving model. No missing model weights have been invented. The filtered candidate is an estimator plus metadata, **not** a replacement for the five-component service bundle.

Experiment 006 has its own new model artifact, source hashes and review records. It is outside the historical five-experiment archive manifest and wrapper; use its [separate reproduction instructions](measurement_extension_006/REPRODUCIBILITY.md).

Experiment 007 has no new fitted model. Its source and validation-only analysis
also have [separate reproduction instructions](high_threshold_007/REPRODUCIBILITY.md).

Use the original source data for the official model and the anomaly-detection task. The fitting masks in this archive are diagnostic experiment records, not a new universally "cleaned" dataset.

## Reproduce without overwriting the archive

Use Python 3.12 and install the pinned AI requirements in a virtual environment as described in [`../README.md`](../README.md). The commands below run from `ai/` with that environment active.

Verify all archived files and source hashes without fitting:

```bash
python experimental/reproduce.py verify
```

Prepare a fresh scratch workspace without training:

```bash
python experimental/reproduce.py prepare history_003 --output /tmp/astra-history-preview
```

Run one experiment in a **different, new** output directory:

```bash
python experimental/reproduce.py run history_003 --output /tmp/astra-history-rerun
python experimental/reproduce.py run filter_validation_005 --output /tmp/astra-filter-rerun
```

On Windows, replace `/tmp/...` with a fresh path outside this repository's `ai/` folder, such as `C:\Temp\astra-history-rerun`. Available experiment names are the five directory names above. The wrapper refuses existing output directories and never overwrites archived plans or results.

The wrapper stages exact historical modules into a compatible workspace with the old `experiments/` layout, required train/development inputs and prior study dependencies. It **does not supply `test.csv`, raw observations, or the full dataset CSV**. Studies 001, 002 and 005 use the already-used validation partition; 003 and 004 use training observations only. The wrapper never runs the final-evaluation module or promotes a candidate.

Do not run the historical scripts directly from their relocated archive path: they intentionally retain their original `experiments/` paths and, for study 001, derive the project root from the module location. Reproduction outputs appear under the selected scratch directory's `experiments/<name>/`.

New runs receive new timestamps and serialization hashes. Compare the scientific inputs, settings, prediction records and metrics; do not expect a new timestamped plan or joblib archive to have the same byte hash. Small floating-point probability differences can occur with parallel tree accumulation even when class predictions match.

Packaging verification prepared all five workspace layouts, checked that test/raw files were absent and existing/archive output paths were rejected, and ran study 005 once through the wrapper in a fresh scratch directory. Its 254 exclusions, 4,786 fitting rows and all reported metrics matched the archived result exactly. This was a reproduction check, not additional model-selection evidence. See [PACKAGING_VERIFICATION.json](PACKAGING_VERIFICATION.json).

## Provenance and limits

Historical reports, plans, audit scripts and model files were copied byte-for-byte. Some contain legacy workspace paths or refer to the earlier `experiments/` layout. The manifest records those original locations; the wrapper restores the needed layout in a scratch directory. New README links use the repository layout.

The original EDA-first plan did not hash its source script. The archive manifest now records that source hash without pretending it was recorded before the original fit. Later experiments' frozen source hashes are checked directly against their archived scripts.

Joblib files are Python serialization; load only the trusted artifacts supplied with this project. All model scores remain prototype outputs on an uncalibrated simulator. Real longitudinal data and independent evaluation are needed for claims about real people.
