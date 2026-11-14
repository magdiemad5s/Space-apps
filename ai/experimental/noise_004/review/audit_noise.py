"""Read-only descriptive audit of the original TRAIN partition; no model fitting."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from astra_shield_ml.features import CURRENT_FIELDS, BASELINE_FIELDS, BOUNDS, FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / "data/train.csv"
source_before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
d = pd.read_csv(SOURCE).sort_values(["participant_id", "mission_day"]).reset_index(drop=True)
assert d["split"].eq("train").all()

checks = {
    "rows": len(d), "columns": len(d.columns),
    "virtual_participants": int(d.participant_id.nunique()),
    "missing_cells": int(d.isna().sum().sum()),
    "nonfinite_numeric_cells": int((~np.isfinite(d.select_dtypes("number"))).sum().sum()),
    "exact_duplicate_rows": int(d.duplicated().sum()),
    "duplicate_person_day": int(d.duplicated(["participant_id", "mission_day"]).sum()),
    "duplicate_predictor_vectors": int(d.duplicated(FEATURE_COLUMNS).sum()),
    "bound_violations": {c: int((~d[c].between(*limits)).sum()) for c, limits in BOUNDS.items()},
    "baseline_person_fields_that_vary": int(d.groupby("participant_id")[BASELINE_FIELDS].nunique().gt(1).sum().sum()),
}
opportunity = d.sleep_duration_hours / (d.sleep_efficiency_pct / 100)
checks["sleep_onset_and_awakenings_exceed_opportunity"] = int((d.sleep_onset_delay_minutes + 3*d.awakenings_count > 60*(opportunity-d.sleep_duration_hours) + .1).sum())
checks["time_budget_above_24h"] = int((opportunity+d.workload_hours+d.exercise_minutes/60 > 24.01).sum())
checks["attention_ratio_mismatch"] = int((np.abs(d.attention_accuracy_pct - 100*d.attention_correct_count/d.attention_trials_count) > 1e-6).sum())
checks["attention_accuracy_off_2p5_grid"] = int((np.abs(d.attention_accuracy_pct/2.5 - np.round(d.attention_accuracy_pct/2.5)) > 1e-8).sum())
checks["fatigue_class_rule_mismatch"] = int((d.target_next_day_fatigue_class != np.where(d.target_next_day_fatigue_score < 4,"low",np.where(d.target_next_day_fatigue_score < 7,"moderate","high"))).sum())
for c in ["awakenings_count","reaction_time_lapses_count","attention_correct_count","attention_trials_count","reaction_time_trials_count"]:
    checks[f"noninteger_{c}"] = int((d[c] != np.round(d[c])).sum())
recomputed = {
    "sleep_duration_delta_from_baseline_hours": d.sleep_duration_hours-d.baseline_sleep_duration_hours,
    "heart_rate_delta_from_baseline_bpm": d.resting_heart_rate_bpm-d.baseline_resting_heart_rate_bpm,
    "hrv_delta_from_baseline_ms": d.hrv_rmssd_ms-d.baseline_hrv_rmssd_ms,
    "reaction_time_change_from_baseline_pct": 100*(d.reaction_time_median_ms/d.baseline_reaction_time_median_ms-1),
}
checks["derived_feature_max_absolute_errors"] = {c: float(np.abs(d[c]-v).max()) for c,v in recomputed.items()}
checks["derived_feature_errors_above_rounding_tolerance"] = {c: int((np.abs(d[c]-v)>5.01e-7).sum()) for c,v in recomputed.items()}
for source, derived in [("sleep_duration_hours","prior_3day_mean_sleep_hours"),("resting_heart_rate_bpm","prior_3day_mean_resting_heart_rate_bpm"),("reaction_time_median_ms","prior_3day_mean_reaction_time_ms")]:
    reconstructed=d.groupby("participant_id")[source].transform(lambda s:s.shift(1).rolling(3,min_periods=3).mean())
    eligible=reconstructed.notna()
    checks[f"{derived}_reconstructable_rows"] = int(eligible.sum())
    checks[f"{derived}_mismatch_over_rounding_tolerance"] = int((np.abs(d.loc[eligible,derived]-reconstructed[eligible])>5.01e-7).sum())
next_fatigue=d.groupby("participant_id").self_report_fatigue_score.shift(-1)
eligible=next_fatigue.notna()
checks["next_day_fatigue_linkage_checkable_rows"] = int(eligible.sum())
checks["next_day_fatigue_linkage_mismatches"] = int((np.abs(d.loc[eligible,"target_next_day_fatigue_score"]-next_fatigue[eligible])>1e-8).sum())

tail_rows=[]
flags={}
for factor in [1.5,3.0]:
    mask=pd.DataFrame(index=d.index)
    for c in CURRENT_FIELDS:
        q1,q3=d[c].quantile([.25,.75])
        low,high=q1-factor*(q3-q1),q3+factor*(q3-q1)
        mask[c]=(d[c]<low)|(d[c]>high)
        tail_rows.append({"feature":c,"iqr_multiplier":factor,"lower_descriptive_fence":float(low),"upper_descriptive_fence":float(high),"flagged_rows":int(mask[c].sum()),"injected_events_among_flagged":int(d.loc[mask[c],"target_current_physiology_event_injected"].sum()),"minimum":float(d[c].min()),"maximum":float(d[c].max()),"skewness":float(d[c].skew())})
    flag=mask.any(axis=1)
    flags[f"iqr_{factor}"]={"rows_flagged":int(flag.sum()),"fraction_rows_flagged":float(flag.mean()),"injected_event_rows_flagged":int(d.loc[flag,"target_current_physiology_event_injected"].sum()),"target_class_counts_among_flagged":d.loc[flag,"target_next_day_fatigue_class"].value_counts().to_dict(),"target_class_counts_unflagged":d.loc[~flag,"target_next_day_fatigue_class"].value_counts().to_dict(),"note":"Descriptive whole-TRAIN fences only, not proof of error and not fitted preprocessing for CV. Fold experiments must fit their own fences within each training fold."}
pd.DataFrame(tail_rows).to_csv(OUT/"descriptive_feature_tails.csv",index=False)

delta_columns = ["sleep_duration_delta_from_baseline_hours", "heart_rate_delta_from_baseline_bpm", "hrv_delta_from_baseline_ms", "reaction_time_change_from_baseline_pct"]
delta_median = d[delta_columns].median()
delta_mad = (d[delta_columns]-delta_median).abs().median()
robust_z = (d[delta_columns]-delta_median).abs()/(1.4826*delta_mad)
extreme = robust_z.gt(4.5).any(axis=1)
flags["personalized_delta_robust_z_over_4p5"] = {
    "rows_flagged": int(extreme.sum()),
    "fraction_rows_flagged": float(extreme.mean()),
    "feature_flag_counts": robust_z.gt(4.5).sum().astype(int).to_dict(),
    "medians": delta_median.to_dict(), "median_absolute_deviations": delta_mad.to_dict(),
    "injected_event_rows_flagged": int(d.loc[extreme,"target_current_physiology_event_injected"].sum()),
    "target_class_counts_among_flagged": d.loc[extreme,"target_next_day_fatigue_class"].value_counts().to_dict(),
    "target_class_counts_unflagged": d.loc[~extreme,"target_next_day_fatigue_class"].value_counts().to_dict(),
    "note": "Descriptive full-TRAIN flags only. The experiment must estimate median and MAD independently on each fitting fold. The event flag and future target were not used to calculate flags."
}

gen_bounds={"sleep_duration_hours":(3.2,9.8),"sleep_efficiency_pct":(58,99),"sleep_onset_delay_minutes":(1,90),"awakenings_count":(0,10),"sleep_midpoint_deviation_minutes":(-180,180),"resting_heart_rate_bpm":(40,125),"hrv_rmssd_ms":(8,115),"reaction_time_median_ms":(150,800),"self_report_stress_score":(0,10),"self_report_fatigue_score":(0,10),"self_report_mood_score":(0,10),"workload_hours":(3,15),"exercise_minutes":(0,110)}
boundary_counts={c:{"at_lower_generator_bound":int(d[c].eq(lo).sum()),"at_upper_generator_bound":int(d[c].eq(hi).sum())} for c,(lo,hi) in gen_bounds.items()}
labels=d.target_next_day_fatigue_score
threshold_distance=np.minimum(np.abs(labels-4),np.abs(labels-7))
current_class=np.where(d.self_report_fatigue_score<4,"low",np.where(d.self_report_fatigue_score<7,"moderate","high"))
event=d.target_current_physiology_event_injected.eq(1)
report={
    "scope":"Original synthetic TRAIN partition only; no validation/test/full CSV/raw observations were opened, no model fitting or data cleaning performed.",
    "source_train_sha256":source_before,
    "quality_and_consistency_checks":checks,
    "descriptive_tails":flags,
    "injected_current_physiology_events":{"count":int(event.sum()),"fraction":float(event.mean()),"note":"Intentional positive anomaly examples; generator adds HR 13..24 bpm and multiplies HRV by 0.45..0.72. Event flag was used only for this audit, never to choose training rows."},
    "target_variability":{"next_day_score_within_0p5_of_cutoff":int((threshold_distance<=.5).sum()),"next_day_score_within_1_of_cutoff":int((threshold_distance<=1).sum()),"current_vs_next_day_class_differences":int((current_class!=d.target_next_day_fatigue_class).sum()),"current_next_day_fatigue_pearson_r":float(d.self_report_fatigue_score.corr(labels)),"note":"Threshold-near scores and day-to-day changes are not mislabeled rows. Labels agree with shifted observed scores and their declared cutoff rules. The unknown latent fatigue is a different target and cannot replace observed self-report silently."},
    "generator_noise_specification":{"latent_fatigue_innovation_sd":.62,"fatigue_report_noise_sd":.65,"stress_innovation_sd":.8,"stress_report_noise_sd":.7,"mood_report_noise_sd":.9,"hr_noise_sd_bpm":2.2,"hrv_logscale_noise_sd":.08,"reaction_time_trial_lognormal_sigma":.12,"note":"These stochastic terms are deliberately generated and not independent estimated real sensor-error distributions. Day-to-day future schedule and physiological innovations cannot be denoised from today's measurements without changing target or introducing unavailable information."},
    "generator_boundary_counts":boundary_counts,
    "journal_structure":{"distinct_full_journals":int(d.journal_text.nunique()),"distinct_opening_sentences":int(d.journal_text.str.split('.').str[0].nunique()),"note":"Unique full text still has only 12 generated opening templates. This is limited language diversity, not duplicate sensor rows to delete."},
    "recommended_experiment":"Parent-prespecified comparison: unchanged RF versus FIT-only exclusion or weight 0.25 for extreme rows. Define extremes using any of four personal-baseline deltas with absolute robust z >4.5, median and MAD fitted within fitting fold only. Freeze rule before fits; keep all held-out observations untouched, retain person-disjoint folds, include forward-time checks, and report removed class/event composition after fitting. This respects derived feature identities because inputs are not independently clipped. The chief risk is suppressing intended HR/HRV anomaly examples, not repairing proven errors. Do not promote solely on reused validation or alter source CSV. A filtering win is evidence about this synthetic development setup, not proof that removed rows are erroneous.",
    "do_not_do":["Do not delete intentional injected anomalies from the anomaly detector's task.","Do not filter using target_current_physiology_event_injected or any future target.","Do not relabel outcomes using a predictor or delete rows simply because the model predicts them poorly.","Do not trim the evaluation distribution; all held-out rows, including tails and rare High examples, must remain.","Do not independently clip derived/baseline/current columns; that breaks their exact engineering relationships.","Do not smooth across people, use centered future windows, or claim unknown irreducible noise was removed."],
}
report["source_train_unchanged"]=hashlib.sha256(SOURCE.read_bytes()).hexdigest()==source_before
assert report["source_train_unchanged"]
(OUT/"noise_audit.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({k:report[k] for k in ["quality_and_consistency_checks","descriptive_tails","injected_current_physiology_events","target_variability","journal_structure","source_train_unchanged"]},indent=2))
