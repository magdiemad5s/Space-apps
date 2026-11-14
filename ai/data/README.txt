TRAINING DATA CONTRACT

All records are from the original ASTRA-SHIELD longitudinal synthetic demo.
The user's separately uploaded V2 CSV is not included or used in this project.

train.csv: 5,040 rows, 84 virtual participants; model fitting only.
validation.csv: 1,080 rows, 18 different participants; candidate selection only.
test.csv: 1,080 rows, 18 different participants; frozen final evaluation only.
task_config.json: exact predictor allowlists and task target names.
data_dictionary.csv: definitions, units, measurement windows and provenance.
participant_splits.csv: group assignments shared across all tasks.
split_manifest.json: file hashes and source dataset SHA-256.

raw_observations.csv: 8,160 source audit rows including seven calibration days and
one additional future-outcome day per virtual participant. NOT A TRAINING TABLE.
It deliberately contains future outcomes and simulator annotations. It is only
used to verify causal feature construction and provide enrollment/history examples.
Neither training.py nor service.py reads it.

generation_metadata.json: simulator seed, version, scope and dependency details.
source_generator.py: original uncalibrated generator, supplied for audit. If run,
it writes new CSV files beside itself; do not overwrite the frozen experiment's
data. For generation experiments, copy it to a new directory first.

The primary target is target_next_day_fatigue_class, not any uploaded V3 label.
No measured NASA or real MMASH data was merged into this synthetic cohort.
