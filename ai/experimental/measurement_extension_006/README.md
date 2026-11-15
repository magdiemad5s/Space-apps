# Experiment 006 — simulated measurement extensions

**Completed; keep the existing serving model.** Adding the proposed features did
not show a reliable improvement on the fresh synthetic test cohort. The selected
28-feature Random Forest scored **0.5495 Macro-F1**, versus **0.5528** for its
matched 26-feature control. The difference was **−0.0034**, with a paired
participant-bootstrap 95% interval of **[−0.0141, +0.0076]**.

This is a separate experiment using wholly synthetic measurements. The original
CSV, trained model, Python/TypeScript APIs, and previous experiments were
preserved. The new fitted artifacts remain experimental; none was promoted.

## Results

These comparisons use the **same fresh cohort**. The 26-feature control was
retrained for this experiment; it is not a new evaluation of the serving model.
Macro-F1 is not accuracy.

| Candidate | Inputs | Mean training group-CV Macro-F1 | Validation Macro-F1 | Fresh test Macro-F1 |
| --- | ---: | ---: | ---: | ---: |
| Random Forest control | 26 | 0.5252 | 0.5317 | **0.5528** |
| Random Forest + questionnaire proxies — selected extension | 28 | **0.5374** | 0.5094 | 0.5495 |
| Random Forest + sleep features | 31 | 0.5254 | — | — |
| Random Forest + all additions | 33 | 0.5317 | — | — |
| XGBoost control | 26 | 0.4935 | 0.4707 | 0.4981 |
| XGBoost + all additions | 33 | 0.4961 | 0.4744 | 0.4961 |
| Repeat today's custom fatigue category | 1 | 0.5295 | 0.5129 | 0.5421 |

Only the RF extension chosen by training-only CV was evaluated against the RF
control on holdouts. Dashes mean the candidate was not selected for holdout
evaluation. XGBoost 26/33 was a separate prespecified comparison.

The selected RF extension's validation change was −0.0223 Macro-F1. On fresh test,
High-fatigue recall was **43.66% for both RF models**; High-fatigue precision was
45.59% for the control and 44.93% for the extension. The prespecified improvement
conditions were not met. The confidence interval includes zero, so the small
negative test difference does not establish a definite harmful effect either.

Read the [results summary](training/RESULTS.txt),
[validation report](training/VALIDATION_REPORT.json), and
[test report with 2,000 paired participant resamples](training/TEST_REPORT.json).
Do not compare these scores directly with the original cohort's historical
**0.5273**; different synthetic people were generated here.

## What data and features were tested?

The standalone [main CSV](data/main.csv) has **7,200 rows × 69 columns**:
120 virtual people with 60 forecast days each. Many columns are provenance,
timing, targets, or other metadata—not model inputs. Splits are participant
disjoint: **84 training people / 18 validation / 18 test**, or
5,040 / 1,080 / 1,080 rows. Seven earlier calibration days and a day61 outcome
record per person are retained in the **8,160-row audit table**.

The baseline uses the existing 26 numeric feature definitions. Seven additions
were evaluated in frozen bundles of **26, 28, 31, and 33 inputs**:

| Added field | Meaning and limitation |
| --- | --- |
| `kss_like_sleepiness_score` | Noisy ordinal 1–9 proxy with a KSS-like range; not an administered or validated KSS response |
| `samn_perelli_like_fatigue_score` | Noisy ordinal 1–7 proxy with a Samn–Perelli-like range; not an administered or validated response |
| `main_sleep_waso_minutes` | Hypothetical wake time allocated within the main sleep episode |
| `time_since_last_sleep_hours` | Hours from the latest allocated sleep end to assessment; a nap resets it |
| `nap_sleep_minutes_last_24h` | At most one optional simulated nap, limited by the available time budget |
| `total_sleep_last_24h_hours` | Main and nap sleep within the preceding 24-hour window |
| `prior_3day_sleep_shortfall_hours` | Previous three nonoverlapping daily shortfalls against a configured 8-hour goal |

The original `self_report_fatigue_score`—column W in the original CSV—was **not
converted or rescaled into either instrument**. The target remains the next-day
custom simulated 0–10 fatigue category, using the original demo thresholds 4 and
7. New proxies use current hidden simulator state plus independent noise; hidden
state itself is excluded from model inputs.

Sleep onset, waking times and WASO are hypothetical allocations consistent with
the simulated duration, efficiency, latency, awakening count and midpoint
deviation. They are not recovered measurements. Naps have **no restorative effect
on the unchanged target-generating fatigue process**. The 8-hour goal is explicit
metadata, not measured biological need. Three-day shortfall is not validated
physiological sleep debt.

Exact equations, seeds, allocation rules and exclusions are recorded in the
[frozen generation plan](draftgenerationplan.json), with a readable
[data card](data/DATA_CARD.md), executable [generator](data_generator.py), and
[strict feature manifest](data/feature_manifest.json).

## Pipeline and checks

The order was: freeze plans → generate and check the cohort → training-only EDA
and visual review → training group-CV → freeze selection and fitted artifacts →
validation once → fresh test once. There was no noise/seed search, row filtering,
holdout-based feature selection, or refitting after holdout results.

- **27 generation check groups passed**, including sleep chronology, daily
  budgets, target preservation, split separation, and causal prior-day features.
- **15 training EDA checks passed**. All 33 candidate inputs were finite and
  complete; no rows were removed or values filled during dataset preparation.
- Actual pre-fit visual review is recorded in
  [REVIEW_BEFORE_TRAINING.json](training/REVIEW_BEFORE_TRAINING.json).
  Inspect the [questionnaire plot](reports/eda/questionnaires_and_target.png),
  [sleep distributions](reports/eda/sleep_extension_distributions.png), and
  [feature correlations](reports/eda/extension_correlations.png).
- Three fixed participant folds within the 84 training people selected the RF
  extension by mean Macro-F1. Any pipeline imputer was fitted only on each fitting
  fold, then on the training cohort for the frozen artifacts.
- The complete [experiment plan](EXPERIMENT_PLAN.json),
  [training preregistration](training/preregistration.json),
  [selection freeze](training/SELECTION_FROZEN.json),
  [generation checks](data/generation_quality.json), and
  [original preservation record](ORIGINAL_PRESERVATION.json) make the sequence
  and protected artifacts reviewable.

The first generation attempt stopped on mixed fractional-second timestamp
parsing. The parser was corrected and the **same frozen seeds and formulas** were
rerun; no scientific parameter was changed. This implementation issue is recorded
in [generation_attempts.json](data/generation_attempts.json).

## Use and reproduction

The [shareable report](reports/ASTRA_SHIELD_Experiment_006.pdf) is produced by
[`render_results.py`](render_results.py). The isolated prediction helper is
[`predict_experimental.py`](predict_experimental.py); its inputs are defined by
the [experimental contract](training/feature_contract.json). It does not replace
the project's existing backend or serving model.

From this directory, with the experiment requirements installed:

```bash
python predict_experimental.py --list-features
python predict_experimental.py --demo
python predict_experimental.py --input feature_values.json
```

The demo reads a training example; the input file must contain the exact frozen
28-feature allowlist. Returned model scores and SHAP contributions are experimental
prediction explanations, not calibrated health risks or medical causes.
Commands print their results without overwriting archived reports. To save a new
demo or check report, supply `--output-dir` with a new, nonexistent directory.

See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) and the pinned
[requirements](requirements-experiment.txt). Reproduce in a separate source tree:
generation and staged training guards refuse to overwrite the historical cohort
or repeatedly evaluate holdouts. A new run requires a genuine visual EDA review
with hashes of its own artifacts before fitting.

Run `python verify_package.py` to check saved-file hashes and the 17 protected
original data/model files without loading a model. [ARTIFACT_MANIFEST.json](ARTIFACT_MANIFEST.json)
records this completed experiment; byte-identical presentation files are not
required for a new reproduction. The [independent review](reports/INDEPENDENT_REVIEW.json)
passed 220 checks, including metric and bootstrap recomputation from saved predictions.

## Interpretation limits and source use

All measurements and outcomes are synthetic. Better scores would only establish
performance under these simulation assumptions: the questionnaire proxies can
reveal hidden fatigue more directly, and many sleep additions re-express existing
inputs. This experiment does not establish real questionnaire benefit, medical
validity, calibrated risk probabilities, or astronaut readiness.

NASA and CSA material is documented in the
[resource catalog](NASA_AND_PARTNER_RESOURCES.csv) and
[verification record](NASA_RESOURCE_VERIFICATION.json) as **background only**.
Those resources supplied neither training measurements nor simulator coefficients.

The reaction task remains **60 simulated responses with a ≥500 ms lapse threshold**;
it is not a validated timed PVT/PVT-B implementation. False starts, actual sensor
recordings, caffeine/medication/symptom effects, and actual questionnaire
administration remain unimplemented here. The existing 40-trial attention count
is a generic synthetic task; it is **not a newly implemented or validated Flanker
test**. No clinical assessment PDF or frontend integration was added by this
experiment.
