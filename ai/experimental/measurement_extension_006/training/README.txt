MEASUREMENT EXTENSION 006 — EXPERIMENTAL TRAINING ONLY

This runner uses a fresh, explicitly simulated cohort and seven new
measurement features. It does not modify the official model or API.
Questionnaire-range scores are not real or validated KSS/Samn–Perelli
responses. NASA/CSA resources provide background, not numerical data.

Stages (run from any directory with the project Python environment):
python train_experiment.py prepare-plan
  Opens only fresh data/train.csv and manifests; fixes participant folds.
  Parent then performs generation review and training-only EDA.
python train_experiment.py cv
  Requires REVIEW_BEFORE_TRAINING.json with generation_review_complete,
  training_only_eda_complete, plan_sha256 and data_manifest_sha256
  (the latter hashes data/split_manifest.json). No validation/test read.
python train_experiment.py validation
  Uses frozen selected models; scores validation once, without fitting.
python train_experiment.py test
  Requires unchanged selection and completed validation; scores fresh
  test once with participant-paired uncertainty. No model changes.

RF26 is the fixed primary control. TRAIN-only grouped CV selects an
RF extension; XGBoost26/33 is a separate matched secondary comparison.
All pipelines fit their imputer only on the fitting observations.
The selected candidate stays experimental regardless of its score.
