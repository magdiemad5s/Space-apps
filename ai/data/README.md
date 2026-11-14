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

[`source_generator.py`](source_generator.py) preserves the generator for provenance. It writes CSVs beside itself when executed. Copy it into a new directory for a generation study; do not overwrite frozen inputs or attempt to improve scores by changing the simulator's noise or labels.

Source consistency does not establish clinical validity. The self-report scales, class cutoffs, physiology events, and cognitive task are simulator definitions. A fresh independent cohort and appropriate real measurements are needed for new generalization claims.
