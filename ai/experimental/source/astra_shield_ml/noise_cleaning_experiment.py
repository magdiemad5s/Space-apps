"""A fixed train-only sensitivity study of fitting-set tail treatments.

Robust-tail flags are not proof of corrupted observations. Current physiology
events may be legitimate anomalies that the separate anomaly module must retain.
No validation/test partition, raw observations, or uploaded full CSV is loaded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline

from .estimators import PersistenceClassifier

SEED = 20261114
LABELS = ["low", "moderate", "high"]
CONTROL = "unchanged_rf_control"
EXCLUDE = "rf_fit_tail_exclusion"
DOWNWEIGHT = "rf_fit_tail_weight_0.25"
PERSISTENCE = "current_fatigue_persistence"
CANDIDATES = [CONTROL, EXCLUDE, DOWNWEIGHT, PERSISTENCE]
DETECTOR_FEATURES = ["sleep_duration_delta_from_baseline_hours", "heart_rate_delta_from_baseline_bpm",
                     "hrv_delta_from_baseline_ms", "reaction_time_change_from_baseline_pct"]
EVENT_COLUMN = "target_current_physiology_event_injected"


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def cohort_hash(frame):
    return hashlib.sha256("\n".join(frame.record_id.tolist()).encode()).hexdigest()


def tail_detector(fitting):
    """Return a fixed, unlabeled, fitting-only robust-z union mask."""
    values = fitting[DETECTOR_FEATURES].astype(float)
    assert np.isfinite(values).all().all()
    medians = values.median(axis=0)
    mads = (values-medians).abs().median(axis=0)
    flags = pd.Series(False, index=fitting.index)
    scores = pd.DataFrame(0., index=fitting.index, columns=DETECTOR_FEATURES)
    thresholds = []
    for feature in DETECTOR_FEATURES:
        median, mad = float(medians[feature]), float(mads[feature])
        scaled = 1.4826*mad
        if mad == 0:
            thresholds.append({"feature":feature,"median":median,"mad":mad,"scaled_mad":scaled,
                               "active":False,"skip_reason":"MAD is zero; feature is skipped", "lower_threshold":None,"upper_threshold":None})
            continue
        scores[feature] = (values[feature]-median).abs()/scaled
        flags |= scores[feature].gt(4.5)
        thresholds.append({"feature":feature,"median":median,"mad":mad,"scaled_mad":scaled,
                           "active":True,"skip_reason":"none","lower_threshold":median-4.5*scaled,"upper_threshold":median+4.5*scaled})
    return flags, scores, thresholds


def make_model(name):
    if name == PERSISTENCE:
        return PersistenceClassifier()
    return Pipeline([("imputer",SimpleImputer(strategy="median")),
        ("model",RandomForestClassifier(n_estimators=200,max_depth=14,min_samples_leaf=8,
            class_weight="balanced",random_state=SEED,n_jobs=2))])


def measure(truth,prediction):
    y,p=np.asarray(truth),np.asarray(prediction)
    report=classification_report(y,p,labels=LABELS,output_dict=True,zero_division=0)
    non_high=y!="high"
    false_high=int(((p=="high")&non_high).sum())
    return {"macro_f1":float(f1_score(y,p,labels=LABELS,average="macro",zero_division=0)),
        "high_precision":float(report["high"]["precision"]),"high_recall":float(report["high"]["recall"]),
        "accuracy":float((y==p).mean()),"false_high_count":false_high,
        "false_high_per_100_non_high":float(100*false_high/non_high.sum()) if non_high.any() else 0.,
        "classification_report":report,"confusion_matrix_labels":LABELS,
        "confusion_matrix":confusion_matrix(y,p,labels=LABELS).tolist()}


def scalars(metrics):
    return {k:v for k,v in metrics.items() if isinstance(v,(int,float))}


def paired_bootstrap(frame,predictions,treatment,repetitions=1000):
    ids=np.asarray(sorted(frame.participant_id.unique()))
    locations={pid:np.flatnonzero(frame.participant_id.to_numpy()==pid) for pid in ids}
    y=frame.true_label.to_numpy()
    left,right=predictions[treatment],predictions[CONTROL]
    rng=np.random.default_rng(SEED)
    values=[]
    for _ in range(repetitions):
        positions=np.concatenate([locations[pid] for pid in rng.choice(ids,len(ids),replace=True)])
        values.append(float(f1_score(y[positions],left[positions],labels=LABELS,average="macro",zero_division=0)
                            -f1_score(y[positions],right[positions],labels=LABELS,average="macro",zero_division=0)))
    return {"comparison":f"{treatment} minus {CONTROL}","repetitions":repetitions,"seed":SEED,
        "resampling_unit":"Whole training participant and all days together",
        "observed_pooled_oof_macro_f1_difference":measure(y,left)["macro_f1"]-measure(y,right)["macro_f1"],
        "percentile_95ci":np.quantile(values,[.025,.975]).tolist(),
        "fraction_positive":float((np.asarray(values)>0).mean()),
        "scope":"Exploratory uncertainty from reused synthetic development observations; grouped-CV predictions are correlated, not independent scientific evidence"}


def main(project_dir=None):
    root=Path(project_dir or Path(__file__).resolve().parents[1])
    output=root/"experiments/noise_004"
    output.mkdir(parents=True,exist_ok=True)
    if (output/"plan.json").exists():
        raise RuntimeError("The frozen noise_004 sensitivity study already exists; do not overwrite its plan or search the threshold after seeing results.")
    started=time.perf_counter()
    train_path,config_path=root/"data/train.csv",root/"data/task_config.json"
    folds_path=root/"experiments/improvement_002/participant_folds.csv"
    train=pd.read_csv(train_path)
    cfg=json.loads(config_path.read_text())
    features=cfg["tasks"]["next_day_fatigue_classification"]["predictors"]
    target=cfg["tasks"]["next_day_fatigue_classification"]["target"]
    folds=pd.read_csv(folds_path)
    assert len(train)==5040 and train.participant_id.nunique()==84
    assert train.split.eq("train").all() and train.is_synthetic.eq(1).all()
    assert train.record_id.is_unique and not train[features].isna().any().any()
    assert folds.participant_id.is_unique and set(folds.participant_id)==set(train.participant_id)
    assert folds.groupby("held_out_fold").size().eq(28).all()
    assert not any(c.startswith("target_") for c in features+DETECTOR_FEATURES)
    source_hash=sha256(train_path)
    model_hash=sha256(root/"artifacts/bundle.joblib")
    fold_map=dict(zip(folds.participant_id,folds.held_out_fold))
    folds.to_csv(output/"participant_folds.csv",index=False)
    plan={"experiment":"noise_004","study_type":"Train-only fitting-tail sensitivity study; not identified-noise cleaning",
        "frozen_before_fit_at_utc":timestamp(),"seed":SEED,"source":"Original synthetic data/train.csv only",
        "source_train_sha256":source_hash,"official_bundle_sha256_before":model_hash,
        "task_config_sha256":sha256(config_path),"source_folds_sha256":sha256(folds_path),
        "script_sha256":sha256(__file__),"rows":5040,"virtual_participants":84,
        "target":target,"rf_predictors":features,"persistence_effective_predictors":["self_report_fatigue_score"],
        "candidates":CANDIDATES,"rf_parameters":{"n_estimators":200,"max_depth":14,"min_samples_leaf":8,
            "class_weight":"balanced","random_state":SEED,"n_jobs":2},
        "detector":{"features":DETECTOR_FEATURES,"formula":"abs(x - fitting median) / (1.4826 * fitting MAD)",
            "tail_union_rule":"Flag fitting row if any active feature has robust z strictly greater than 4.5",
            "threshold":4.5,"zero_mad":"Skip that feature and record the reason",
            "fit_scope":"Compute medians/MAD separately inside every fitting subset, never from held-out observations",
            "forbidden_inputs":"Targets, event annotation, identities and all non-listed fields are unavailable to the detector",
            "semantics":"A tail flag is not proof of corrupted data; legitimate injected physiology events may be flagged"},
        "treatments":{"exclusion":"Remove flagged rows only from that candidate's fitting subset",
            "downweight":"Retain all fitting rows; flagged rows receive sample_weight 0.25 and all others 1",
            "unchanged":"All fitting rows, standard fixed RF recipe",
            "source":"No original rows, targets or features are removed, replaced or overwritten"},
        "preprocessing":"Fit median imputer and class weights inside each candidate's fitting subset. For downweighting, RF class weights multiply the fixed row weights. No holdout filtering or feature transformation.",
        "groupcv":"Reuse the three improvement_002 participant folds; every candidate scores all 5040 held-out observations once",
        "temporal_evaluations":[{"fit_days":[1,30],"label_cutoff_day":31,"evaluation_days":[32,45]},
                                {"fit_days":[1,45],"label_cutoff_day":46,"evaluation_days":[47,60]}],
        "comparison_gates":{"mean_groupcv_macro_f1_delta_min":.01,"all_groupfold_deltas_min":0.,
            "all_temporal_deltas_min":0.,"pooled_oof_high_precision_delta_min":-.02,"pooled_oof_high_recall_delta_min":-.02},
        "gates_scope":"Engineering investigation criteria only; a passing candidate is not automatically promoted",
        "diagnostics":"Report future class and injected-event prevalence only after masks are fixed; subgroup performance is descriptive and never used for selection",
        "uncertainty":"1000 paired whole-participant bootstrap resamples of grouped OOF predictions, each treatment versus unchanged control",
        "no_external_evaluation":"Do not open validation.csv, test.csv, raw_observations.csv or any uploaded/full CSV",
        "no_production_change":"Do not retrain the official model or Isolation Forest; do not change API, source data, earlier artifacts or reports"}
    write_json(output/"plan.json",plan)
    threshold_rows,flagged_rows,diagnostic_rows,stage_summaries=[],[],[],[]
    invariant_rows=[]

    def stage_mask(fitting,stage_id):
        mask,scores,thresholds=tail_detector(fitting)
        # Metadata/label mutation proves those fields cannot change the detector.
        mutated=fitting.copy()
        for column in mutated:
            if column not in DETECTOR_FEATURES:
                mutated[column]="not_available_to_detector"
        changed,changed_scores,changed_thresholds=tail_detector(mutated)
        assert mask.equals(changed) and np.array_equal(scores.to_numpy(),changed_scores.to_numpy())
        assert thresholds==changed_thresholds
        invariant_rows.append({"stage_id":stage_id,"mask_invariant_to_all_non_detector_columns":True,
                               "fitting_rows":len(fitting),"tail_rows":int(mask.sum())})
        for row in thresholds:threshold_rows.append({"stage_id":stage_id,**row})
        for row_index in fitting.index[mask]:
            row=fitting.loc[row_index]
            flagged_rows.append({"stage_id":stage_id,"record_id":row.record_id,"participant_id":row.participant_id,
                "mission_day":int(row.mission_day),"flagged_features":"|".join(c for c in DETECTOR_FEATURES if scores.loc[row_index,c]>4.5),
                "max_robust_z":float(scores.loc[row_index].max()),"excluded_in_exclusion_candidate":True,
                "downweight_candidate_sample_weight":.25})
        # Only now, after the unlabeled mask and thresholds are immutable, inspect
        # annotation/class columns for descriptive prevalence diagnostics.
        for variable in [target,EVENT_COLUMN]:
            for category in sorted(fitting[variable].unique()):
                member=fitting[variable].eq(category)
                count=int(member.sum());flagged=int(mask[member].sum())
                diagnostic_rows.append({"stage_id":stage_id,"diagnostic_variable":variable,"category":str(category),
                    "fitting_rows_in_category":count,"flagged_rows_in_category":flagged,
                    "flagged_pct_of_category":100*flagged/count,
                    "diagnostic_only_not_detector_input":True})
        stage_summaries.append({"stage_id":stage_id,"fitting_rows":len(fitting),"flagged_rows":int(mask.sum()),
            "flagged_pct":float(mask.mean()*100),"retained_after_exclusion":int((~mask).sum()),
            "flagged_injected_event_rows":int((mask & fitting[EVENT_COLUMN].eq(1)).sum()),
            "flagged_uninjected_rows":int((mask & fitting[EVENT_COLUMN].eq(0)).sum())})
        return mask

    def fit_score(name,fitting,holding,mask,stage_id):
        assert fitting.index.intersection(holding.index).empty
        fit_used=fitting.loc[~mask] if name==EXCLUDE else fitting
        inputs=["self_report_fatigue_score"] if name==PERSISTENCE else features
        model=make_model(name)
        before=time.perf_counter()
        if name==DOWNWEIGHT:
            weights=np.where(mask.to_numpy(),.25,1.)
            model.fit(fit_used[inputs],fit_used[target],model__sample_weight=weights)
        else:model.fit(fit_used[inputs],fit_used[target])
        prediction=np.asarray(model.predict(holding[inputs]))
        assert len(prediction)==len(holding) and not pd.isna(prediction).any()
        return prediction,{"candidate":name,"stage_id":stage_id,"fit_rows_used":len(fit_used),
            "fit_tail_rows":int(mask.sum()),"held_out_rows":len(holding),"held_out_cohort_sha256":cohort_hash(holding),
            "effective_predictor_count":len(inputs),"fit_predict_seconds":time.perf_counter()-before,
            **scalars(measure(holding[target],prediction))}

    oof=train[["record_id","participant_id","mission_day"]].copy()
    oof["held_out_fold"]=train.participant_id.map(fold_map)
    oof["true_label"]=train[target]
    # This annotation is retained for AFTER-prediction subgroup diagnostics only.
    oof["current_simulator_event"]=train[EVENT_COLUMN]
    predictions={name:np.empty(len(train),dtype=object) for name in CANDIDATES}
    group_rows=[];independence=[]
    for fold in range(3):
        holding=train[train.participant_id.map(fold_map).eq(fold)]
        fitting=train[train.participant_id.map(fold_map).ne(fold)]
        fit_ids,hold_ids=set(fitting.participant_id),set(holding.participant_id)
        assert fit_ids.isdisjoint(hold_ids) and len(fit_ids)==56 and len(hold_ids)==28 and len(holding)==1680
        stage_id=f"group_fold_{fold}"
        mask=stage_mask(fitting,stage_id)
        for name in CANDIDATES:
            pred,row=fit_score(name,fitting,holding,mask,stage_id)
            predictions[name][holding.index.to_numpy()]=pred
            group_rows.append({**row,"fold":fold,"fit_participants":56,"held_out_participants":28})
        independence.append({"fold":fold,"fitting_participants":sorted(fit_ids),
                             "held_out_participants":sorted(hold_ids),"overlap":0})
    pooled={}
    for name in CANDIDATES:
        assert not pd.isna(predictions[name]).any()
        oof[name]=predictions[name]
        pooled[name]=measure(train[target],predictions[name])
        print(name,"pooled OOF macro F1",round(pooled[name]["macro_f1"],4),flush=True)
    oof.to_csv(output/"groupcv_predictions.csv",index=False)
    group_table=pd.DataFrame(group_rows)
    assert group_table.groupby("fold").held_out_cohort_sha256.nunique().eq(1).all()
    group_table.to_csv(output/"groupcv_fold_metrics.csv",index=False)
    comparison=group_table.groupby("candidate").agg(mean_macro_f1=("macro_f1","mean"),std_macro_f1=("macro_f1","std"),
        mean_high_precision=("high_precision","mean"),mean_high_recall=("high_recall","mean"),
        mean_false_high_per_100_non_high=("false_high_per_100_non_high","mean")).reset_index()
    comparison.to_csv(output/"groupcv_comparison.csv",index=False)
    subgroup_rows=[]
    for event in [0,1]:
        members=train[EVENT_COLUMN].eq(event).to_numpy()
        for name in CANDIDATES:
            subgroup_rows.append({"candidate":name,"current_simulator_event":event,"held_out_rows":int(members.sum()),
                "scope":"Fatigue classification on event subgroup; not anomaly detection",**scalars(measure(train.loc[members,target],predictions[name][members]))})
    pd.DataFrame(subgroup_rows).to_csv(output/"oof_event_subgroup_metrics.csv",index=False)
    temporal_rows,temporal_predictions=[],[]
    for index,spec in enumerate(plan["temporal_evaluations"]):
        fitting=train[train.mission_day.between(*spec["fit_days"])]
        holding=train[train.mission_day.between(*spec["evaluation_days"])]
        available_cutoffs=train[train.mission_day.eq(spec["label_cutoff_day"])].set_index("participant_id").observation_timestamp_utc
        label_times=pd.to_datetime(fitting.target_timestamp_utc,utc=True)
        cutoffs=pd.to_datetime(fitting.participant_id.map(available_cutoffs),utc=True)
        assert (label_times<=cutoffs).all()
        assert cutoffs.max()<pd.to_datetime(holding.observation_timestamp_utc,utc=True).min()
        stage_id=f"temporal_fold_{index}"
        mask=stage_mask(fitting,stage_id)
        for name in CANDIDATES:
            pred,row=fit_score(name,fitting,holding,mask,stage_id)
            temporal_rows.append({**row,"temporal_fold":index,"fit_day_start":spec["fit_days"][0],
                "fit_day_end":spec["fit_days"][1],"label_cutoff_day":spec["label_cutoff_day"],
                "evaluation_day_start":spec["evaluation_days"][0],"evaluation_day_end":spec["evaluation_days"][1]})
            result=holding[["record_id","participant_id","mission_day"]].copy()
            result["temporal_fold"]=index;result["candidate"]=name
            result["true_label"]=holding[target];result["prediction"]=pred
            temporal_predictions.append(result)
    temporal_table=pd.DataFrame(temporal_rows)
    assert temporal_table.groupby("temporal_fold").held_out_cohort_sha256.nunique().eq(1).all()
    temporal_table.to_csv(output/"temporal_metrics.csv",index=False)
    pd.concat(temporal_predictions,ignore_index=True).to_csv(output/"temporal_predictions.csv",index=False)
    pd.DataFrame(threshold_rows).to_csv(output/"detector_thresholds.csv",index=False)
    pd.DataFrame(flagged_rows,columns=["stage_id","record_id","participant_id","mission_day","flagged_features","max_robust_z","excluded_in_exclusion_candidate","downweight_candidate_sample_weight"]).to_csv(output/"fit_tail_flags.csv",index=False)
    pd.DataFrame(diagnostic_rows).to_csv(output/"fit_flag_prevalence_diagnostics.csv",index=False)
    pd.DataFrame(stage_summaries).to_csv(output/"fit_stage_summary.csv",index=False)
    mean_scores=comparison.set_index("candidate").mean_macro_f1
    gate_results={}
    for name in [EXCLUDE,DOWNWEIGHT]:
        group_deltas=(group_table[group_table.candidate.eq(name)].set_index("fold").macro_f1
                      -group_table[group_table.candidate.eq(CONTROL)].set_index("fold").macro_f1)
        time_deltas=(temporal_table[temporal_table.candidate.eq(name)].set_index("temporal_fold").macro_f1
                     -temporal_table[temporal_table.candidate.eq(CONTROL)].set_index("temporal_fold").macro_f1)
        precision_delta=pooled[name]["high_precision"]-pooled[CONTROL]["high_precision"]
        recall_delta=pooled[name]["high_recall"]-pooled[CONTROL]["high_recall"]
        gates={"mean_cv_macro_f1_gain_at_least_0.01":bool(mean_scores[name]-mean_scores[CONTROL]>=.01),
               "all_groupfold_macro_f1_deltas_nonnegative":bool(group_deltas.ge(0).all()),
               "all_temporal_macro_f1_deltas_nonnegative":bool(time_deltas.ge(0).all()),
               "pooled_high_precision_drop_no_more_than_0.02":bool(precision_delta>=-.02),
               "pooled_high_recall_drop_no_more_than_0.02":bool(recall_delta>=-.02)}
        gate_results[name]={"mean_cv_macro_f1_delta":float(mean_scores[name]-mean_scores[CONTROL]),
            "groupfold_deltas":{str(k):float(v) for k,v in group_deltas.items()},
            "temporal_deltas":{str(k):float(v) for k,v in time_deltas.items()},
            "pooled_high_precision_delta":precision_delta,"pooled_high_recall_delta":recall_delta,
            "gates":gates,"passes_all_gates":all(gates.values())}
    uncertainty={name:paired_bootstrap(oof,predictions,name) for name in [EXCLUDE,DOWNWEIGHT]}
    assert sha256(train_path)==source_hash and sha256(root/"artifacts/bundle.joblib")==model_hash
    verification={"detector_invariant_checks":invariant_rows,"all_detector_invariants_passed":True,
        "heldout_cohort_equality_all_candidates":True,"group_separation_passed":True,
        "temporal_label_availability_passed":True,"source_train_unchanged":True,
        "official_bundle_unchanged":True,"script_sha256_matches_frozen_plan":sha256(__file__)==plan["script_sha256"],
        "validation_read":False,"final_test_read":False,"isolation_forest_retrained":False,
        "source_rows_deleted_or_rewritten":0}
    write_json(output/"execution_verification.json",verification)
    summary={"experiment":"noise_004","completed_at_utc":timestamp(),"elapsed_seconds":time.perf_counter()-started,
        "scope":"Exploratory train-only robust-tail sensitivity study on synthetic data; not proof of measured noise",
        "original_training_rows":5040,"virtual_participants":84,"all_holdout_rows_retained":True,
        "groupcv_comparison":comparison.to_dict("records"),"pooled_oof_metrics":pooled,
        "fit_stage_summaries":stage_summaries,"gates_by_treatment":gate_results,
        "paired_participant_bootstrap":uncertainty,"fold_independence":independence,
        "verification":verification,"automatic_promotion":False,"clinical_validation":False,
        "conclusion_policy":"Keep the official demo unchanged. Passing a gate could only justify a separately planned investigation; flagged physiology events are not automatically bad measurements."}
    write_json(output/"summary.json",summary)
    lines=["ASTRA-SHIELD — TRAIN-ONLY ROBUST-TAIL SENSITIVITY STUDY 004","",
        "This experiment asks whether two fitting-only tail treatments improve the",
        "fatigue classifier. It does not prove that flagged observations are noise.",
        "The detector never sees future labels or injected-event annotations.",
        "Every candidate is scored on every original held-out observation.","",
        "The original synthetic training partition contains 5,040 rows from 84",
        "virtual participants. Existing participant folds were reused. Fixed fitting",
        "medians and MAD values were computed separately in each fitting subset.",
        "A row is flagged when any of the four prespecified personalized features",
        "has absolute robust z greater than 4.5. Zero-MAD features are skipped.",
        "Flagged fitting rows are either omitted for one experimental RF or retained",
        "with weight 0.25 for another. Original data and all held-out rows remain intact.","",
        "GROUPED-CV RESULTS"]
    for _,row in comparison.iterrows():
        lines.append(f"{row.candidate}: mean macro F1 = {row.mean_macro_f1:.4f}; high precision = {row.mean_high_precision:.4f}; high recall = {row.mean_high_recall:.4f}.")
    for name,decision in gate_results.items():
        lines.extend(["",f"Treatment: {name}",
            f"Mean grouped-CV macro F1 change versus control: {decision['mean_cv_macro_f1_delta']:+.4f}.",
            f"Per-group-fold changes: {decision['groupfold_deltas']}.",
            f"Forward-time changes: {decision['temporal_deltas']}.",
            f"All prespecified engineering gates passed: {decision['passes_all_gates']}.",
            f"Paired participant-bootstrap pooled-OOF macro F1 interval: {uncertainty[name]['percentile_95ci']}."])
    lines.extend(["","FLAG DIAGNOSTICS (NOT USED TO CHOOSE THRESHOLDS OR MODELS)"])
    for stage in stage_summaries:
        lines.append(f"{stage['stage_id']}: {stage['flagged_rows']:,} of {stage['fitting_rows']:,} fitting rows flagged ({stage['flagged_pct']:.2f}%); {stage['flagged_injected_event_rows']:,} injected-event rows and {stage['flagged_uninjected_rows']:,} uninjected rows.")
    lines.extend(["","Interpret flagged injected events as potentially legitimate physiological",
        "anomalies, not automatically corrupted data. Event-subgroup metrics concern",
        "the fatigue classifier only; the separate Isolation Forest is unchanged.",
        "Bootstrap intervals describe reused synthetic development observations and",
        "correlated grouped-CV predictions, not independent clinical evidence.",
        "No validation or final-test observations were opened. No threshold was",
        "searched. No production model, API, original source row, target, or earlier",
        "report was changed. There is no automatic promotion, regardless of gates."])
    (output/"RESULTS.txt").write_text("\n".join(lines)+"\n")
    print(json.dumps({"mean_groupcv_macro_f1":mean_scores.to_dict(),"gates":gate_results,
                      "elapsed_seconds":summary["elapsed_seconds"],"official_demo_changed":False,
                      "validation_read":False,"final_test_read":False},indent=2))
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir",type=Path)
    args=parser.parse_args()
    main(args.project_dir)
