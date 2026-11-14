"""Newly authorized fixed-filter comparison on reused development validation.

The noise_004 fitting-only exclusion rule is reused without threshold search.
All models are fitted and the mask is frozen before validation.csv is loaded.
The official model, source data, API, previous experiments and final test stay
unchanged. Existing validation results are not independent confirmation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from .noise_cleaning_experiment import (
    DETECTOR_FEATURES, PERSISTENCE, make_model, measure, tail_detector,
)

SEED = 20261114
LABELS = ["low", "moderate", "high"]
CONTROL = "control_rf_full_training"
FILTERED = "filtered_rf_fit_tail_exclusion"
EVENT_COLUMN = "target_current_physiology_event_injected"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def numeric_metrics(values):
    return {key:value for key,value in values.items() if isinstance(value,(int,float))}


def bootstrap(frame,predictions,repetitions=1000):
    ids=np.asarray(sorted(frame.participant_id.unique()))
    locations={pid:np.flatnonzero(frame.participant_id.to_numpy()==pid) for pid in ids}
    y=frame.true_label.to_numpy()
    left,right=predictions[FILTERED],predictions[CONTROL]
    rng=np.random.default_rng(SEED)
    f1_changes,recall_changes=[],[]
    for _ in range(repetitions):
        chosen=np.concatenate([locations[pid] for pid in rng.choice(ids,len(ids),replace=True)])
        f1_changes.append(float(f1_score(y[chosen],left[chosen],labels=LABELS,average="macro",zero_division=0)
                               -f1_score(y[chosen],right[chosen],labels=LABELS,average="macro",zero_division=0)))
        high=y[chosen]=="high"
        recall_changes.append(float((left[chosen][high]=="high").mean()-(right[chosen][high]=="high").mean()) if high.any() else 0.)
    return {"comparison":"Filtered fitting-only RF minus unchanged RF control",
        "resampling":"1,000 paired whole-validation-participant bootstrap resamples",
        "repetitions":repetitions,"participants":len(ids),"seed":SEED,
        "macro_f1_difference":measure(y,left)["macro_f1"]-measure(y,right)["macro_f1"],
        "macro_f1_difference_percentile_95ci":np.quantile(f1_changes,[.025,.975]).tolist(),
        "high_recall_difference":measure(y,left)["high_recall"]-measure(y,right)["high_recall"],
        "high_recall_difference_percentile_95ci":np.quantile(recall_changes,[.025,.975]).tolist(),
        "fraction_f1_differences_positive":float((np.asarray(f1_changes)>0).mean()),
        "scope":"Descriptive uncertainty on REUSED synthetic development validation; not an independent fresh test or clinical evidence"}


def main(project_dir=None):
    root=Path(project_dir or Path(__file__).resolve().parents[1])
    output=root/"experiments/filter_validation_005"
    output.mkdir(parents=True,exist_ok=True)
    if (output/"plan.json").exists():
        raise RuntimeError("This fixed-filter validation experiment already exists; do not overwrite it or retune against the reused validation results.")
    started=time.perf_counter()
    training_path,config_path=root/"data/train.csv",root/"data/task_config.json"
    frozen=json.loads((root/"artifacts/frozen_manifest.json").read_text())
    train=pd.read_csv(training_path)
    cfg=json.loads(config_path.read_text())
    task=cfg["tasks"]["next_day_fatigue_classification"]
    features,target=task["predictors"],task["target"]
    assert len(train)==5040 and train.participant_id.nunique()==84
    assert train.split.eq("train").all() and train.is_synthetic.eq(1).all()
    assert train.record_id.is_unique and not train[features].isna().any().any()
    assert not any(c.startswith("target_") for c in features+DETECTOR_FEATURES)
    train_hash=sha256(training_path)
    bundle_hash=sha256(root/"artifacts/bundle.joblib")
    assert train_hash==frozen["data_sha256"]["data/train.csv"]
    assert bundle_hash==frozen["artifact_sha256"]["artifacts/bundle.joblib"]
    plan={"experiment":"filter_validation_005","frozen_before_fit_at_utc":now(),"seed":SEED,
        "authorization":"The user explicitly requested the previously fixed experimental filtering approach on the same original validation partition that yielded macro F1 0.5273. This is a new comparison; the prior noise_004 validation prohibition applied to that earlier study.",
        "scope":"Fixed-rule fitting-only filtering sensitivity comparison; reused development validation, not fresh confirmation",
        "training_source":"Original data/train.csv, all 5,040 rows and 84 virtual participants",
        "train_sha256":train_hash,"expected_validation_sha256_from_existing_frozen_manifest":frozen["data_sha256"]["data/validation.csv"],
        "official_bundle_sha256_before":bundle_hash,"task_config_sha256":sha256(config_path),
        "script_sha256":sha256(__file__),"reused_noise_rule_script_sha256":sha256(root/"astra_shield_ml/noise_cleaning_experiment.py"),
        "target":target,"rf_feature_allowlist":features,"persistence_effective_predictors":["self_report_fatigue_score"],
        "candidates":[CONTROL,FILTERED,PERSISTENCE],
        "fixed_rule":{"features":DETECTOR_FEATURES,"fit_statistics":"Medians and MADs from full TRAIN only",
            "formula":"abs(x - training median) / (1.4826 * training MAD) > 4.5 in any listed feature",
            "zero_mad":"Skip and record the feature","threshold_search":False,
            "no_detector_inputs":"Future labels, injected-event annotation and all non-listed columns are excluded",
            "flag_interpretation":"A robust tail flag does not prove a bad measurement; intentionally injected physiological events may be legitimate anomalies"},
        "rf_parameters":{"n_estimators":200,"max_depth":14,"min_samples_leaf":8,"class_weight":"balanced","random_state":SEED,"n_jobs":2},
        "fit_protocol":"Freeze the unlabeled TRAIN mask, then fit control on all TRAIN and filtered RF on retained TRAIN; fit median imputers and balanced class weights independently within their fitting subsets",
        "label_and_history_policy":"Keep the original shifted targets and all original baseline/history values; do not recompute across gaps caused by fitting-row exclusion",
        "holdout_policy":"Open validation.csv only after both RFs and persistence are fitted; retain ALL 1,080 observations from the same 18 participants",
        "comparison_policy":"No retuning, new threshold choice, winner promotion, or new validation-based gates",
        "uncertainty":"1,000 paired whole-validation-participant bootstrap resamples of filtered-minus-control macro F1 and High recall",
        "final_test_policy":"Never open test.csv, full uploaded CSVs or raw observations",
        "deployment_policy":"Save a separate development-only candidate; official service bundle and API remain unchanged"}
    write_json(output/"plan.json",plan)
    mask,scores,thresholds=tail_detector(train)
    mutated=train.copy()
    for column in mutated:
        if column not in DETECTOR_FEATURES:mutated[column]="not_available_to_detector"
    mutation_mask,mutation_scores,mutation_thresholds=tail_detector(mutated)
    assert mask.equals(mutation_mask) and np.array_equal(scores.to_numpy(),mutation_scores.to_numpy())
    assert thresholds==mutation_thresholds
    pd.DataFrame(thresholds).to_csv(output/"fixed_training_thresholds.csv",index=False)
    flagged=train.loc[mask,["record_id","participant_id","mission_day"]].copy()
    flagged["flagged_features"]=["|".join(c for c in DETECTOR_FEATURES if scores.loc[index,c]>4.5) for index in flagged.index]
    flagged["max_robust_z"]=scores.loc[mask].max(axis=1)
    flagged.to_csv(output/"flagged_training_record_ids.csv",index=False)
    mask_freeze={"frozen_at_utc":now(),"training_rows":len(train),"calculated_flags":int(mask.sum()),
        "retained_fitting_rows":int((~mask).sum()),"thresholds_sha256":sha256(output/"fixed_training_thresholds.csv"),
        "flagged_record_ids_sha256":sha256(output/"flagged_training_record_ids.csv"),
        "mask_invariant_to_target_event_and_all_other_metadata_mutation":True,
        "mask_was_fixed_before_validation_loaded":True,
        "comparison_with_previous_descriptive_audit":{"previously_reported_flags":254,"matches_previous":int(mask.sum())==254}}
    write_json(output/"training_mask_frozen.json",mask_freeze)
    # Diagnostics occur only after the mask and its file hashes have been frozen.
    composition=[]
    for variable in [target,EVENT_COLUMN]:
        for category in sorted(train[variable].unique()):
            members=train[variable].eq(category)
            count=int(members.sum());removed=int(mask[members].sum())
            composition.append({"diagnostic_variable":variable,"category":str(category),"original_train_rows":count,
                "flagged_fitting_rows":removed,"retained_fitting_rows":count-removed,
                "flagged_pct_of_category":100*removed/count,"diagnostic_only":True})
    pd.DataFrame(composition).to_csv(output/"removed_row_composition_diagnostics.csv",index=False)
    models={};fit_times={}
    for name,fitting in [(CONTROL,train),(FILTERED,train.loc[~mask]),(PERSISTENCE,train)]:
        inputs=["self_report_fatigue_score"] if name==PERSISTENCE else features
        model=make_model(name)
        before=time.perf_counter()
        model.fit(fitting[inputs],fitting[target])
        models[name]=model;fit_times[name]=time.perf_counter()-before
        print(f"{name}: fitted on {len(fitting):,} rows in {fit_times[name]:.2f} seconds",flush=True)
    joblib.dump({"estimator":models[FILTERED],"features":features,"target":target,
        "scope":"Development-only filtered-fatigue candidate; NOT the official service bundle",
        "data_origin":"synthetic","training_rows":int((~mask).sum()),"train_sha256":train_hash,
        "plan_sha256":sha256(output/"plan.json"),"mask_freeze":mask_freeze,
        "class_weight_policy":"Balanced weights are naturally recomputed from retained fitting target counts"},
        output/"filtered_candidate.joblib",compress=3)
    write_json(output/"fit_completed_before_validation.json",{"completed_at_utc":now(),"validation_csv_loaded":False,
        "fit_seconds":fit_times,"candidate_sha256":sha256(output/"filtered_candidate.joblib"),
        "training_class_counts":{str(k):int(v) for k,v in train[target].value_counts().items()},
        "retained_training_class_counts":{str(k):int(v) for k,v in train.loc[~mask,target].value_counts().items()},
        "source_targets_and_history_unchanged":True})

    # First load of validation.csv occurs after all fits and mask freezing.
    validation_path=root/"data/validation.csv"
    validation_hash=sha256(validation_path)
    assert validation_hash==plan["expected_validation_sha256_from_existing_frozen_manifest"]
    validation=pd.read_csv(validation_path)
    assert len(validation)==1080 and validation.participant_id.nunique()==18
    assert validation.split.eq("validation").all() and validation.record_id.is_unique
    assert set(train.participant_id).isdisjoint(validation.participant_id)
    assert not validation[features].isna().any().any()
    predictions={};probabilities={};metrics={}
    output_predictions=validation[["record_id","participant_id","observation_timestamp_utc","target_timestamp_utc"]].copy()
    output_predictions["true_label"]=validation[target]
    output_predictions["current_simulator_event"]=validation[EVENT_COLUMN]
    for name,model in models.items():
        inputs=["self_report_fatigue_score"] if name==PERSISTENCE else features
        prediction=np.asarray(model.predict(validation[inputs]))
        probability=np.asarray(model.predict_proba(validation[inputs]))
        predictions[name]=prediction;probabilities[name]=probability
        assert len(prediction)==1080 and np.isfinite(probability).all()
        metrics[name]=measure(validation[target],prediction)
        output_predictions[name+"__prediction"]=prediction
        for index,label in enumerate(model.classes_):
            output_predictions[name+"__model_probability_"+str(label)]=probability[:,index]
    output_predictions.to_csv(output/"validation_predictions.csv",index=False,float_format="%.12f")
    pd.DataFrame([{"candidate":name,"scope":"REUSED synthetic development validation",**numeric_metrics(value)}
                   for name,value in metrics.items()]).to_csv(output/"validation_comparison.csv",index=False)
    official=joblib.load(root/"artifacts/bundle.joblib")
    official_model=official["models"]["next_day_fatigue_classification"]
    assert official["task_config"]["tasks"]["next_day_fatigue_classification"]["predictors"]==features
    official_prediction=np.asarray(official_model.predict(validation[features]))
    official_probability=np.asarray(official_model.predict_proba(validation[features]))
    assert np.array_equal(official_prediction,predictions[CONTROL])
    probability_max_difference=float(np.max(np.abs(official_probability-probabilities[CONTROL])))
    assert np.allclose(official_probability,probabilities[CONTROL],rtol=0,atol=1e-12)
    historical_path=root/"experiments/eda_first_001/validation_predictions.csv"
    historical=pd.read_csv(historical_path)
    historical_column="full_26__random_forest_balanced"
    merged=output_predictions[["record_id","true_label",CONTROL+"__prediction"]].merge(
        historical[["record_id","target_next_day_fatigue_class",historical_column]],on="record_id",validate="one_to_one")
    assert len(merged)==1080
    assert merged.true_label.eq(merged.target_next_day_fatigue_class).all()
    assert merged[CONTROL+"__prediction"].eq(merged[historical_column]).all()
    subgroup=[]
    for event in [0,1]:
        members=validation[EVENT_COLUMN].eq(event).to_numpy()
        for name in models:
            subgroup.append({"candidate":name,"current_simulator_event":event,"validation_rows":int(members.sum()),
                "scope":"Descriptive fatigue classification on current-event subgroup; not anomaly detection",
                **numeric_metrics(measure(validation.loc[members,target],predictions[name][members]))})
    pd.DataFrame(subgroup).to_csv(output/"validation_event_subgroup_metrics.csv",index=False)
    bootstrap_frame=validation[["participant_id"]].copy();bootstrap_frame["true_label"]=validation[target]
    uncertainty=bootstrap(bootstrap_frame,predictions)
    assert sha256(training_path)==train_hash and sha256(validation_path)==validation_hash
    assert sha256(root/"artifacts/bundle.joblib")==bundle_hash
    assert sha256(__file__)==plan["script_sha256"]
    verification={"original_train_sha256_matches_frozen_manifest":True,"original_validation_sha256_matches_frozen_manifest":True,
        "official_bundle_unchanged":True,"original_training_csv_unchanged":True,"original_validation_csv_unchanged":True,
        "script_sha256_matches_frozen_plan":True,"feature_allowlist_matches_official_artifact":True,
        "mask_invariant_to_all_non_detector_columns":True,"participant_overlap_count":0,
        "all_validation_rows_retained":1080,"control_predictions_exactly_match_official":True,
        "control_model_probabilities_bitwise_equal_to_official":bool(np.array_equal(official_probability,probabilities[CONTROL])),
        "control_model_probabilities_max_abs_difference":probability_max_difference,
        "control_model_probabilities_equal_within_1e_minus12":True,
        "control_predictions_exactly_match_eda_first_001":True,
        "mask_and_all_fits_completed_before_validation_csv_loaded":True,
        "future_labels_and_history_recomputed_after_exclusion":False,"final_test_read":False,
        "raw_or_uploaded_full_data_read":False,"official_model_promoted_or_changed":False}
    write_json(output/"verification.json",verification)
    previous=json.loads((root/"experiments/noise_004/summary.json").read_text())
    previous_exclusion=previous["gates_by_treatment"]["rf_fit_tail_exclusion"]
    summary={"experiment":"filter_validation_005","completed_at_utc":now(),"elapsed_seconds":time.perf_counter()-started,
        "scope":"Newly authorized comparison on reused original synthetic development validation; not a fresh independent validation",
        "training_rows":5040,"flagged_training_rows":int(mask.sum()),"retained_candidate_fit_rows":int((~mask).sum()),
        "validation_rows":1080,"validation_participants":18,"all_validation_rows_retained":True,
        "metrics":metrics,"filtered_minus_control":{key:metrics[FILTERED][key]-metrics[CONTROL][key]
            for key in ["macro_f1","accuracy","high_precision","high_recall"]},
        "paired_participant_bootstrap":uncertainty,"verification":verification,
        "previous_noise_004_context":{"mean_groupcv_macro_f1_delta":previous_exclusion["mean_cv_macro_f1_delta"],
            "all_original_gates_passed":previous_exclusion["passes_all_gates"],
            "note":"The earlier failed engineering gate stands. Reusing validation here is not independent confirmation or permission to tune."},
        "automatic_promotion":False,"clinical_validation":False,
        "conclusion":"Report the observed change and uncertainty; retain the official demo unchanged. Tail flags correspond to possible legitimate events, not proven corruption."}
    write_json(output/"summary.json",summary)
    lines=["ASTRA-SHIELD — FIXED-FILTER COMPARISON ON REUSED VALIDATION 005","",
        "The user newly authorized this fixed filtering experiment on the same",
        "original development-validation partition that previously yielded 0.5273",
        "macro F1. These are reused synthetic development observations, not a fresh",
        "holdout or independent scientific confirmation.","",
        "The plan and script hash were frozen before fitting. The unchanged noise_004",
        "rule uses only four personalized numerical deltas, fitting medians/MAD and",
        "a fixed robust-z threshold of 4.5. No threshold search or downweighting was",
        "performed. The mask was invariant to every non-detector column, including",
        "all future targets and the injected-event annotation.","",
        f"Calculated training flags: {int(mask.sum()):,} of 5,040. Candidate fitting rows: {int((~mask).sum()):,}.",
        "The control used all 5,040 rows. The filtered candidate omitted flags only",
        "during its fit. Original shifted labels and baseline/history features were",
        "kept unchanged; no rolling window or target was reconstructed across gaps.",
        "Balanced class weights recalculated naturally inside each fitting subset.",
        "All models were fitted before validation.csv was opened. Every one of the",
        "1,080 validation records from 18 other virtual participants was scored.","",
        "OBSERVED REUSED-VALIDATION RESULTS"]
    for name,value in metrics.items():
        lines.append(f"{name}: macro F1 = {value['macro_f1']:.4f}; accuracy = {value['accuracy']:.4f}; High precision = {value['high_precision']:.4f}; High recall = {value['high_recall']:.4f}.")
    lines.extend(["",f"Filtered-minus-control macro F1 change: {summary['filtered_minus_control']['macro_f1']:+.4f}.",
        f"Paired participant-bootstrap 95% difference interval: {uncertainty['macro_f1_difference_percentile_95ci']}.",
        f"High-recall change: {summary['filtered_minus_control']['high_recall']:+.4f}; bootstrap interval: {uncertainty['high_recall_difference_percentile_95ci']}.","",
        "REPRODUCIBILITY AND LIMITS",
        "Control predictions matched the official saved RF and historical",
        "eda_first_001 predictions for all 1,080 records. Model class scores matched",
        "the official artifact within 1e-12; floating accumulation can differ at",
        "machine precision. These are uncalibrated model scores, not medical risks.",
        "Source and official model hashes are unchanged. The filtered estimator is",
        "saved separately as filtered_candidate.joblib and is not a serving bundle.",
        "The prior noise_004 cross-validation gain was small and failed its",
        "prespecified improvement gate. That result is not overturned by reusing",
        "this development partition. No validation-based retuning or new promotion",
        "gate was performed. No final-test data was read or rescored.",
        "Flagged physiology events are not automatically bad measurements. Subgroup",
        "results describe fatigue classification only; the anomaly model is unchanged.",
        "Keep the official demo unchanged; no automatic promotion occurred."])
    (output/"RESULTS.txt").write_text("\n".join(lines)+"\n")
    print(json.dumps({"flagged_training_rows":int(mask.sum()),"retained_fitting_rows":int((~mask).sum()),
        "macro_f1":{name:value["macro_f1"] for name,value in metrics.items()},
        "filtered_minus_control":summary["filtered_minus_control"],"bootstrap":uncertainty,
        "elapsed_seconds":summary["elapsed_seconds"],"official_demo_changed":False,"final_test_read":False},indent=2))
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir",type=Path)
    args=parser.parse_args()
    main(args.project_dir)
