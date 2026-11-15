# Synthetic data guide

Every measurement, journal, and target in this folder comes from the original **ASTRA-SHIELD longitudinal simulator**. These are not measured NASA astronaut records. The separate uploaded V2/V3 dataset and real research datasets were not merged into this cohort.

## Files to use

| File | Purpose |
|---|---|
| [astra_shield_synthetic_ml.csv](astra_shield_synthetic_ml.csv) | Standalone original dataset: 7,200 rows and 46 columns; suitable for the team's data handoff |
| [data_dictionary.csv](data_dictionary.csv) | Definitions, units, timing, derivation, and provenance |
| [selected_features.csv](selected_features.csv) | The current 26-feature classifier contract and exploratory importance information |
| [task_config.json](task_config.json) | Exact feature allowlists and target names for each task |
| [train.csv](train.csv) | 5,040 rows from 84 virtual participants; model fitting and development CV |
| [validation.csv](validation.csv) | 1,080 rows from 18 other participants; already used for development comparisons |
| [test.csv](test.csv) | 1,080 rows from 18 other participants; historical frozen final-evaluation partition |
| [participant_splits.csv](participant_splits.csv) | Fixed participant assignments |
| [split_manifest.json](split_manifest.json) | Partition/source hashes |
| [generation_metadata.json](generation_metadata.json) | Simulator seed, version, and generation scope |
| [source_manifest.csv](source_manifest.csv) | Source provenance and background references |

The split is **70/15/15 by participant**. Keep all days for a person in their assigned partition. The full CSV contains targets and metadata for traceability; do not feed all 46 columns into a model or train on all partitions. Use each task's allowlist. The main classifier predicts `target_next_day_fatigue_class`, exactly 24 hours after the input cutoff.

The previous top-five importance list was an exploratory ranking, not a replacement five-input model. The current classifier retains 26 predictors; a 17-feature alternative was evaluated and not adopted. Related current/baseline/delta variables can share importance, and importance is not a standalone deletion rule.

## Quality and calibration

The prepared synthetic data passed the specified consistency checks. The training audit found no missing/non-finite cells, exact duplicates, duplicate participant/day keys, or failed documented bounds, so it required **no row deletion or value filling**. Repeated participant IDs represent daily histories, and repeated baseline values represent a fixed earlier reference.

Baselines use seven earlier calibration days. Past-three-day averages exclude the current and future observations. The four baseline columns are:

- `baseline_sleep_duration_hours`
- `baseline_resting_heart_rate_bpm`
- `baseline_hrv_rmssd_ms`
- `baseline_reaction_time_median_ms`

The generator also contains deliberate random variation and injected physiological events. The later filtering studies created temporary fitting subsets; they did **not** alter this original CSV or its partitions. See the [findings](../docs/FINDINGS.md) for the measured comparisons.

## Audit-only records and generator

[`raw_observations.csv`](raw_observations.csv) contains **8,160 synthetic audit rows**: calibration days −6 through 0, forecast-observation days 1 through 60, and an additional future-outcome day 61 for each of 120 people. It supports causal-feature checks and history fixtures. **It is not a predictor table** and includes records that would leak future information if used indiscriminately.

### Why the last forecast row has tomorrow's targets

The main CSV ends at mission day 60, but its last row's targets come from the same participant's **day 61 in the raw file**, marked `future_outcome_only`. Day 61 supplies observed synthetic outcomes for day 60; it is not another labeled forecast row because no day 62 was generated. Spreadsheet row 61 includes the header and is the first participant's mission day 60.

For `SIM_001_D+060`, columns AQ, AR, and AT contain fatigue **6.83**, median reaction time **360.631 ms**, and class **moderate**. Raw record `SIM_001_D+061` (CSV line 69) contains the matching fatigue and reaction-time observations at `2026-03-02T18:00:00Z`, exactly 24 hours later. The class follows the documented demo cutoffs. A provenance check confirmed that all 7,200 forecast rows match their next-day raw observations, including all 120 final-day rows; participant split membership also matches. This was a data-consistency check, not a new model evaluation.

Future outcomes may be used as supervised-training labels in the training partition. They must never become same-day predictors. Keep day 61 in the audit file; do not append it to the model table with invented day-62 targets.

### What the 60 reaction-time trials mean

Each synthetic session draws **60 response times** and derives its median and number of responses **≥500 ms** from that same array. The count of 60 is a fixed simulation assumption, not a learned feature. Lapse counts are comparable within this dataset because every session uses the same denominator.

The original dictionary and generator descriptions call this a "five-minute PVT-like" task. **The generator does not simulate stimulus intervals, feedback, or elapsed session duration**, so five minutes is only the original intended description, not an implemented timing guarantee. The precise current description is a **60-response PVT-like simulation with a ≥500 ms lapse threshold**, not a validated PVT or PVT-B test. Individual trial arrays are not retained in the CSV exports.

A real timed test can produce different trial counts. Its raw lapse count is not automatically interchangeable with a count out of 60, even if both use 500 ms. Agree on the actual frontend protocol before using those measurements with the model; a change to trial count, lapse threshold, or feature definition requires a corresponding data/API review and model evaluation. This clarification does not change the frozen data or model.

[`source_generator.py`](source_generator.py) preserves the generator for provenance. It writes CSVs beside itself when executed. Copy it into a new directory for a generation study; do not overwrite frozen inputs or attempt to improve scores by changing the simulator's noise or labels.

Source consistency does not establish clinical validity. The self-report scales, class cutoffs, physiology events, and cognitive task are simulator definitions. A fresh independent cohort and appropriate real measurements are needed for new generalization claims.
