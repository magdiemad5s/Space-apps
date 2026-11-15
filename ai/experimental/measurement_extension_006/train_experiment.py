#!/usr/bin/env python3
"""Staged, isolated training for measurement_extension_006.

Preregister -> prepare-plan -> generation/EDA review -> cv -> validation -> test.
The final two stages are once-only and never fit or reselect a model. Every
observation is generated, not measured astronaut/questionnaire research data.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                             classification_report, confusion_matrix, f1_score)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline

EXPERIMENT = Path(__file__).resolve().parent
AI_ROOT = EXPERIMENT.parents[1]
sys.path.insert(0, str(AI_ROOT))
from astra_shield_ml.estimators import EncodedXGBClassifier, PersistenceClassifier

LABELS = ["low", "moderate", "high"]
MODEL_SEED = 20261114
CV_SEED = 20261115
PRIMARY_CONTROL = "rf_26_control"
RF_EXTENSIONS = ["rf_28_questionnaires", "rf_31_sleep", "rf_33_combined"]
XGB_CONTROL = "xgb_26_control"
XGB_EXTENDED = "xgb_33_combined"
PERSISTENCE = "current_custom_fatigue_persistence"
QUESTIONNAIRES = ["kss_like_sleepiness_score", "samn_perelli_like_fatigue_score"]
SLEEP = ["main_sleep_waso_minutes", "time_since_last_sleep_hours",
         "nap_sleep_minutes_last_24h", "total_sleep_last_24h_hours",
         "prior_3day_sleep_shortfall_hours"]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean_json(value.tolist())
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_json(path, value):
    path=Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(clean_json(value), indent=2, allow_nan=False)+"\n")
    temporary.replace(path)


@contextmanager
def lock_stage(training, stage):
    path=training/("."+stage+".lock")
    descriptor=os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def expected_candidates(baseline):
    return {
        PRIMARY_CONTROL: {"kind":"rf", "features":baseline},
        RF_EXTENSIONS[0]: {"kind":"rf", "features":baseline+QUESTIONNAIRES},
        RF_EXTENSIONS[1]: {"kind":"rf", "features":baseline+SLEEP},
        RF_EXTENSIONS[2]: {"kind":"rf", "features":baseline+QUESTIONNAIRES+SLEEP},
        XGB_CONTROL: {"kind":"xgb", "features":baseline},
        XGB_EXTENDED: {"kind":"xgb", "features":baseline+QUESTIONNAIRES+SLEEP},
        PERSISTENCE: {"kind":"persistence", "features":["self_report_fatigue_score"]},
    }


def preregister(experiment):
    training=experiment/"training"
    training.mkdir(parents=True, exist_ok=True)
    destination=training/"preregistration.json"
    if destination.exists():
        raise RuntimeError("Preregistration already exists; do not overwrite fixed choices.")
    config=read_json(AI_ROOT/"data/task_config.json")
    baseline=config["tasks"]["next_day_fatigue_classification"]["predictors"]
    assert len(baseline)==26
    result={
        "experiment":"measurement_extension_006", "preregistered_at_utc":utc_now(),
        "root_experiment_plan_sha256":sha256(experiment/"EXPERIMENT_PLAN.json"),
        "script_sha256":sha256(__file__),
        "original_task_config_sha256":sha256(AI_ROOT/"data/task_config.json"),
        "original_estimator_implementation_sha256":sha256(AI_ROOT/"astra_shield_ml/estimators.py"),
        "official_bundle_sha256_before":sha256(AI_ROOT/"artifacts/bundle.joblib"),
        "dataset_seed":20261115, "extension_seed":2026111501, "model_seed":MODEL_SEED,
        "cv_seed":CV_SEED, "cv":"GroupKFold(3, shuffle=True, random_state=20261115); group=participant_id",
        "baseline_features":baseline, "questionnaire_features":QUESTIONNAIRES,
        "sleep_features":SLEEP, "candidates":expected_candidates(baseline),
        "rf_parameters":{"n_estimators":200,"max_depth":14,"min_samples_leaf":8,
            "class_weight":"balanced","random_state":MODEL_SEED,"n_jobs":2},
        "xgb_parameters":{"n_estimators":200,"max_depth":4,"learning_rate":.05,
            "min_child_weight":5,"subsample":.85,"colsample_bytree":.9,"reg_lambda":5.,
            "random_state":MODEL_SEED,"n_jobs":2,"tree_method":"hist","device":"cpu",
            "objective":"multi:softprob","class_balance":"compute_sample_weight balanced on fitting targets"},
        "preprocessing":"SimpleImputer median fitted only on the current fitting fold; no added indicator columns, no scaling or calibration",
        "target":"target_next_day_fatigue_class",
        "target_rule":"Following-day custom simulated fatigue score: low<4; moderate4..below7; high>=7",
        "primary_control":PRIMARY_CONTROL,
        "selection":"Select only among the three RF extensions using TRAIN-group-CV mean macro F1 rounded to 6 decimals; ties prefer fewer features then candidate name",
        "secondary_pair":[XGB_CONTROL,XGB_EXTENDED], "reference":PERSISTENCE,
        "holdout_protocol":"Freeze all choices and train-fitted artifacts before validation; score 18 validation people once without refitting/reselection, then 18 fresh test people once",
        "test_uncertainty":"2000 paired whole-participant bootstrap resamples; sampled participants retain all days and duplicate sampled IDs are retained",
        "exploratory_test_signal_rule":{"macro_f1_gain_min":.01,"bootstrap_lower_bound_above":0.,"high_recall_loss_max":.02},
        "signal_rule_use":"Reporting only; never deployment approval or automatic promotion",
        "generation_assumptions":"New questionnaire-range fields are additional noisy views of simulated current latent states; gains can reflect those assumptions rather than real instrument benefit. Naps have no modeled restorative effect on the original target process.",
        "scope":"Fresh synthetic cohort, not real questionnaire responses or measured astronaut data; scores cannot be compared directly with the historical original-cohort 0.5273",
        "never_change":"Original data, serving artifacts, API contracts and previous reports remain unchanged",
    }
    write_json(destination,result)
    (training/"README.txt").write_text(
        "MEASUREMENT EXTENSION 006 — EXPERIMENTAL TRAINING ONLY\n\n"
        "This runner uses a fresh, explicitly simulated cohort and seven new\n"
        "measurement features. It does not modify the official model or API.\n"
        "Questionnaire-range scores are not real or validated KSS/Samn–Perelli\n"
        "responses. NASA/CSA resources provide background, not numerical data.\n\n"
        "Stages (run from any directory with the project Python environment):\n"
        "python train_experiment.py prepare-plan\n"
        "  Opens only fresh data/train.csv and manifests; fixes participant folds.\n"
        "  Parent then performs generation review and training-only EDA.\n"
        "python train_experiment.py cv\n"
        "  Requires REVIEW_BEFORE_TRAINING.json with generation_review_complete,\n"
        "  training_only_eda_complete, plan_sha256 and data_manifest_sha256\n"
        "  (the latter hashes data/split_manifest.json). No validation/test read.\n"
        "python train_experiment.py validation\n"
        "  Uses frozen selected models; scores validation once, without fitting.\n"
        "python train_experiment.py test\n"
        "  Requires unchanged selection and completed validation; scores fresh\n"
        "  test once with participant-paired uncertainty. No model changes.\n\n"
        "RF26 is the fixed primary control. TRAIN-only grouped CV selects an\n"
        "RF extension; XGBoost26/33 is a separate matched secondary comparison.\n"
        "All pipelines fit their imputer only on the fitting observations.\n"
        "The selected candidate stays experimental regardless of its score.\n")
    return {"stage":"preregistered", "path":str(destination), "sha256":sha256(destination)}


def load_preregistration(experiment):
    prereg=read_json(experiment/"training/preregistration.json")
    checks={
        "root_experiment_plan_sha256":experiment/"EXPERIMENT_PLAN.json",
        "script_sha256":Path(__file__),
        "original_task_config_sha256":AI_ROOT/"data/task_config.json",
        "original_estimator_implementation_sha256":AI_ROOT/"astra_shield_ml/estimators.py",
        "official_bundle_sha256_before":AI_ROOT/"artifacts/bundle.joblib",
    }
    for key,path in checks.items():
        if sha256(path)!=prereg[key]:
            raise RuntimeError(f"Prespecified/protected input changed: {key}")
    return prereg


def prepare_plan(experiment):
    training=experiment/"training"
    if (training/"PLAN.json").exists():
        raise RuntimeError("A prepared plan already exists; do not overwrite it.")
    prereg=load_preregistration(experiment)
    manifest=read_json(experiment/"data/feature_manifest.json")
    splits=read_json(experiment/"data/split_manifest.json")
    baseline=prereg["baseline_features"]
    assert manifest["baseline_features"]==baseline
    assert manifest["extension_features"]==QUESTIONNAIRES+SLEEP
    expected={"baseline":baseline,"questionnaires_only":baseline+QUESTIONNAIRES,
              "sleep_only":baseline+SLEEP,"combined":baseline+QUESTIONNAIRES+SLEEP}
    assert all(manifest["feature_bundles"][name]==columns for name,columns in expected.items())
    assert manifest["target"]==prereg["target"]
    assert manifest["group_column"]=="participant_id" and manifest["split_column"]=="split"
    all_features=baseline+QUESTIONNAIRES+SLEEP
    assert len(set(all_features))==33
    excluded=set(manifest["excluded_columns"])
    assert not excluded.intersection(all_features)
    assert not any(c.startswith("target_") or "latent" in c.lower() or "timestamp" in c.lower()
                   or c in {"record_id","participant_id","split","is_synthetic","data_origin"}
                   for c in all_features)
    for split,count,people in [("train",5040,84),("validation",1080,18),("test",1080,18)]:
        entry=splits["splits"][split]
        assert entry["file"]==split+".csv" and entry["rows"]==count and entry["participants"]==people
        assert isinstance(entry["sha256"],str) and len(entry["sha256"])==64
    train_path=experiment/"data/train.csv"
    assert sha256(train_path)==splits["splits"]["train"]["sha256"]
    frame=pd.read_csv(train_path)
    validate_frame(frame,"train",5040,84,all_features,prereg["target"])
    splitter=GroupKFold(n_splits=3,shuffle=True,random_state=CV_SEED)
    assignments=pd.Series(-1,index=frame.index,dtype=int)
    for fold,(fitting,holding) in enumerate(splitter.split(frame,groups=frame.participant_id)):
        assert set(frame.iloc[fitting].participant_id).isdisjoint(frame.iloc[holding].participant_id)
        assignments.iloc[holding]=fold
    folds=pd.DataFrame({"participant_id":frame.participant_id,"fold":assignments}).drop_duplicates()
    assert folds.participant_id.is_unique and folds.groupby("fold").size().eq(28).all()
    folds.sort_values("participant_id").to_csv(training/"participant_folds.csv",index=False)
    plan={"experiment":"measurement_extension_006","prepared_at_utc":utc_now(),
        "preregistration_sha256":sha256(training/"preregistration.json"),
        "root_plan_sha256":sha256(experiment/"EXPERIMENT_PLAN.json"),
        "script_sha256":sha256(__file__),"feature_manifest_sha256":sha256(experiment/"data/feature_manifest.json"),
        "split_manifest_sha256":sha256(experiment/"data/split_manifest.json"),
        "participant_folds_sha256":sha256(training/"participant_folds.csv"),
        "expected_partitions":splits["splits"],"candidates":prereg["candidates"],
        "target":prereg["target"],"primary_control":PRIMARY_CONTROL,
        "rf_extension_selection":prereg["selection"],
        "validation_or_test_observations_loaded":False,
        "training_rows":len(frame),"training_participants":frame.participant_id.nunique(),
        "training_missing_cells_by_feature":frame[all_features].isna().sum().to_dict()}
    write_json(training/"PLAN.json",plan)
    return {"stage":"prepared_without_fitting", "plan_sha256":sha256(training/"PLAN.json"),
            "split_manifest_sha256":plan["split_manifest_sha256"], "fold_people":folds.groupby("fold").size().to_dict()}


def validate_frame(frame,split,rows,people,features,target):
    assert len(frame)==rows and frame.participant_id.nunique()==people
    assert frame.split.eq(split).all() and frame.is_synthetic.eq(1).all()
    assert frame.record_id.is_unique and not frame.duplicated(["participant_id","mission_day"]).any()
    assert frame.groupby("participant_id").mission_day.apply(lambda s:sorted(s)==list(range(1,61))).all()
    assert set(frame[target].unique())==set(LABELS) and not frame[target].isna().any()
    for column in features:
        assert pd.api.types.is_numeric_dtype(frame[column]),column
        observed=frame[column].dropna()
        assert len(observed)>0 and np.isfinite(observed).all(),column
    assert (pd.to_datetime(frame.target_timestamp_utc,utc=True)-pd.to_datetime(frame.observation_timestamp_utc,utc=True)).eq(pd.Timedelta(hours=24)).all()


def load_plan(experiment):
    prereg=load_preregistration(experiment)
    training=experiment/"training"
    plan=read_json(training/"PLAN.json")
    checks={"preregistration_sha256":training/"preregistration.json",
            "root_plan_sha256":experiment/"EXPERIMENT_PLAN.json","script_sha256":Path(__file__),
            "feature_manifest_sha256":experiment/"data/feature_manifest.json",
            "split_manifest_sha256":experiment/"data/split_manifest.json",
            "participant_folds_sha256":training/"participant_folds.csv"}
    for key,path in checks.items():
        if sha256(path)!=plan[key]:
            raise RuntimeError(f"Prepared training contract changed: {key}")
    return plan,prereg


def review_guard(experiment,plan):
    review_path=experiment/"training/REVIEW_BEFORE_TRAINING.json"
    if not review_path.exists():
        raise RuntimeError("Generation and training-only EDA review record is required before fitting.")
    review=read_json(review_path)
    if not review.get("generation_review_complete") or not review.get("training_only_eda_complete"):
        raise RuntimeError("Generation review and training-only EDA must be complete before fitting.")
    if review.get("plan_sha256")!=sha256(experiment/"training/PLAN.json"):
        raise RuntimeError("Review record must identify the exact prepared training plan.")
    if review.get("data_manifest_sha256")!=plan["split_manifest_sha256"]:
        raise RuntimeError("Review record must identify data/split_manifest.json SHA-256.")
    eda_path=experiment/"reports/eda/TRAIN_ONLY_EDA.json"
    if not eda_path.exists():
        raise RuntimeError("Actual training-only EDA report is missing.")
    if "eda_report_sha256" in review and review["eda_report_sha256"]!=sha256(eda_path):
        raise RuntimeError("Training-only EDA report changed after review.")
    return sha256(review_path)


def load_partition(experiment,plan,name):
    expected=plan["expected_partitions"][name]
    path=experiment/"data"/expected["file"]
    if sha256(path)!=expected["sha256"]:
        raise RuntimeError(f"Frozen {name} data hash changed")
    frame=pd.read_csv(path)
    features=plan["candidates"][RF_EXTENSIONS[2]]["features"]
    validate_frame(frame,name,expected["rows"],expected["participants"],features,plan["target"])
    return frame


def estimator(spec):
    if spec["kind"]=="persistence":
        return PersistenceClassifier()
    model=(RandomForestClassifier(n_estimators=200,max_depth=14,min_samples_leaf=8,
            class_weight="balanced",random_state=MODEL_SEED,n_jobs=2)
           if spec["kind"]=="rf" else EncodedXGBClassifier())
    return Pipeline([("imputer",SimpleImputer(strategy="median")),("model",model)])


def metrics(truth,prediction):
    report=classification_report(truth,prediction,labels=LABELS,output_dict=True,zero_division=0)
    return {"macro_f1":float(f1_score(truth,prediction,labels=LABELS,average="macro",zero_division=0)),
        "accuracy":float(accuracy_score(truth,prediction)),
        "balanced_accuracy":float(balanced_accuracy_score(truth,prediction)),
        "high_precision":float(report["high"]["precision"]),"high_recall":float(report["high"]["recall"]),
        "classification_report":report,"confusion_matrix_labels":LABELS,
        "confusion_matrix":confusion_matrix(truth,prediction,labels=LABELS).tolist()}


def metric_scalars(value):
    return {k:v for k,v in value.items() if isinstance(v,(int,float))}


def fit_model(spec,frame,target):
    model=estimator(spec)
    x=frame[spec["features"]]
    before=time.perf_counter()
    model.fit(x,frame[target])
    audit=[]
    if isinstance(model,Pipeline):
        calculated=x.median(axis=0).to_numpy()
        learned=model.named_steps["imputer"].statistics_
        assert np.allclose(calculated,learned,equal_nan=True)
        for name,fill in zip(spec["features"],learned):
            audit.append({"feature":name,"fitting_only_median":float(fill) if np.isfinite(fill) else None,
                          "fitting_missing_cells":int(x[name].isna().sum())})
    return model,time.perf_counter()-before,audit


def run_cv(experiment):
    training=experiment/"training"
    if (training/"SELECTION_FROZEN.json").exists():
        raise RuntimeError("CV choices are already frozen; do not repeat selection.")
    plan,prereg=load_plan(experiment)
    review_sha=review_guard(experiment,plan)
    with lock_stage(training,"cv"):
        started=time.perf_counter()
        frame=load_partition(experiment,plan,"train")
        folds=pd.read_csv(training/"participant_folds.csv")
        fold_map=dict(zip(folds.participant_id,folds.fold))
        assert set(fold_map)==set(frame.participant_id)
        oof=frame[["record_id","participant_id","mission_day"]].copy()
        oof["fold"]=frame.participant_id.map(fold_map)
        oof["true_label"]=frame[plan["target"]]
        fold_metrics,imputation_audit=[],[]
        pooled={}
        for name,spec in plan["candidates"].items():
            prediction=np.empty(len(frame),dtype=object)
            for fold in range(3):
                holding=frame.participant_id.map(fold_map).eq(fold)
                fit=frame.loc[~holding]
                hold=frame.loc[holding]
                assert set(fit.participant_id).isdisjoint(hold.participant_id)
                assert fit.participant_id.nunique()==56 and hold.participant_id.nunique()==28
                model,seconds,audit=fit_model(spec,fit,plan["target"])
                predicted=np.asarray(model.predict(hold[spec["features"]]))
                assert len(predicted)==1680 and not pd.isna(predicted).any()
                prediction[holding.to_numpy()]=predicted
                score=metrics(hold[plan["target"]],predicted)
                fold_metrics.append({"candidate":name,"fold":fold,"feature_count":len(spec["features"]),
                    "fit_rows":len(fit),"held_out_rows":len(hold),"fit_people":56,"held_out_people":28,
                    "fit_seconds":seconds,**metric_scalars(score)})
                imputation_audit.extend({"candidate":name,"fold":fold,**row} for row in audit)
            assert not pd.isna(prediction).any()
            oof[name]=prediction
            pooled[name]=metrics(frame[plan["target"]],prediction)
            print(f"{name}: pooled training OOF macro F1 {pooled[name]['macro_f1']:.4f}",flush=True)
        table=pd.DataFrame(fold_metrics)
        table.to_csv(training/"cv_fold_metrics.csv",index=False)
        oof.to_csv(training/"cv_predictions.csv",index=False)
        pd.DataFrame(imputation_audit).to_csv(training/"cv_imputation_audit.csv",index=False)
        comparison=table.groupby("candidate").agg(mean_macro_f1=("macro_f1","mean"),
            std_macro_f1=("macro_f1","std"),mean_high_recall=("high_recall","mean"),
            mean_high_precision=("high_precision","mean"),feature_count=("feature_count","first")).reset_index()
        comparison["selection_f1_rounded6"]=comparison.mean_macro_f1.round(6)
        comparison.to_csv(training/"cv_comparison.csv",index=False)
        ranked=comparison[comparison.candidate.isin(RF_EXTENSIONS)].sort_values(
            ["selection_f1_rounded6","feature_count","candidate"],ascending=[False,True,True])
        selected=ranked.iloc[0].candidate
        selection={"selected_at_utc":utc_now(),"selected_rf_extension":selected,
            "primary_control":PRIMARY_CONTROL,"selection_source":"Three fixed participant folds within TRAIN only",
            "selection_rule":prereg["selection"],"selected_feature_count":int(ranked.iloc[0].feature_count),
            "validation_or_test_opened":False,"secondary_xgb_pair":[XGB_CONTROL,XGB_EXTENDED],
            "best_extension_mean_cv_macro_f1":float(ranked.iloc[0].mean_macro_f1),
            "control_mean_cv_macro_f1":float(comparison.set_index("candidate").loc[PRIMARY_CONTROL,"mean_macro_f1"])}
        write_json(training/"CV_SELECTION.json",selection)
        wanted=list(dict.fromkeys([PRIMARY_CONTROL,selected,XGB_CONTROL,XGB_EXTENDED,PERSISTENCE]))
        fitted={};full_imputation=[];fit_times={}
        for name in wanted:
            fitted[name],fit_times[name],audit=fit_model(plan["candidates"][name],frame,plan["target"])
            full_imputation.extend({"candidate":name,**row} for row in audit)
        pd.DataFrame(full_imputation).to_csv(training/"full_train_imputation_audit.csv",index=False)
        bundle={"scope":"measurement_extension_006 experimental artifact only; not a serving bundle",
            "data_origin":"fresh synthetic cohort","clinical_validation":False,
            "models":fitted,"candidate_specs":{name:plan["candidates"][name] for name in wanted},
            "selection":selection,"target":plan["target"],"training_participants":sorted(frame.participant_id.unique()),
            "metadata":{"trained_at_utc":utc_now(),"preregistration_sha256":sha256(training/"preregistration.json"),
                "prepared_plan_sha256":sha256(training/"PLAN.json"),"review_record_sha256":review_sha,
                "training_data_sha256":plan["expected_partitions"]["train"]["sha256"],
                "package_versions":{"python":platform.python_version(),"numpy":np.__version__,"pandas":pd.__version__,
                    "scikit_learn":sklearn.__version__,"joblib":joblib.__version__,"xgboost_cpu":version("xgboost-cpu")},
                "probability_scope":"Uncalibrated model class scores for a synthetic target; not medical probabilities"}}
        joblib.dump(bundle,training/"candidate_models.joblib",compress=3)
        write_json(training/"feature_contract.json",{"scope":"Experimental only; existing API still accepts its original 26-feature contract",
            "selected_candidate":selected,"target":plan["target"],"candidate_inputs":{n:s["features"] for n,s in bundle["candidate_specs"].items()},
            "missingness":"Numeric nulls use training-fitted pipeline medians; never substitute zero for missing ordinal questionnaire values",
            "identity_and_target_excluded":True})
        write_json(training/"CV_REPORT.json",{"scope":"Fresh synthetic TRAIN-only model comparison",
            "selection":selection,"mean_fold_metrics":comparison.to_dict("records"),"pooled_oof_metrics":pooled,
            "final_fit_seconds":fit_times,"elapsed_seconds":time.perf_counter()-started,
            "validation_or_test_opened":False,"promotion":False})
        frozen_paths=["candidate_models.joblib","CV_SELECTION.json","CV_REPORT.json","feature_contract.json",
                      "PLAN.json","preregistration.json","participant_folds.csv"]
        frozen={"frozen_at_utc":utc_now(),"selected_rf_extension":selected,"primary_control":PRIMARY_CONTROL,
            "training_artifact_sha256":{name:sha256(training/name) for name in frozen_paths},
            "script_sha256":sha256(__file__),"review_record_sha256":review_sha,
            "expected_partition_hashes":{name:entry["sha256"] for name,entry in plan["expected_partitions"].items()},
            "validation_or_test_opened":False,"no_reselection_after_freeze":True}
        write_json(training/"SELECTION_FROZEN.json",frozen)
        (training/"MODEL_CARD.txt").write_text(
            "MEASUREMENT EXTENSION 006 — EXPERIMENTAL ONLY\n\n"
            "The cohort and all new questionnaire-range/sleep measurements are\n"
            "simulated. No real questionnaire responses or astronaut records are\n"
            "included. New score fields are additional noisy views of current\n"
            "simulator latent states; observed gains can reflect these assumptions.\n"
            "They are not evidence of real KSS/Samn–Perelli instrument benefit.\n\n"
            "RF26 is the fixed control. Three RF extensions are compared inside\n"
            "84 TRAIN people using three participant-disjoint folds. Mean macro\n"
            "F1 rounded to six decimals selects the extension; ties prefer fewer\n"
            "features, then name. XGB26 versus XGB33 is a separate paired check.\n"
            "Every imputer is fitted on fitting observations only. Missing score\n"
            "values are not coded as zero. Identifiers, labels, internal latent\n"
            "states and future timestamps never enter predictors.\n\n"
            "All choices/artifacts are frozen before validation and fresh test.\n"
            "Both holdouts are evaluated once; neither triggers refitting or\n"
            "reselection. Participant bootstrap intervals are conditional on a\n"
            "single fixed synthetic scenario, not population clinical evidence.\n"
            "Scores must not be compared directly with the old-cohort 0.5273.\n\n"
            "The original model/API remains unchanged regardless of results.\n")
        return {"stage":"cv_complete_and_frozen","selection":selection,
                "elapsed_seconds":time.perf_counter()-started,"test_opened":False}


def load_frozen(experiment):
    plan,prereg=load_plan(experiment)
    training=experiment/"training"
    frozen=read_json(training/"SELECTION_FROZEN.json")
    for name,digest in frozen["training_artifact_sha256"].items():
        if sha256(training/name)!=digest:
            raise RuntimeError(f"Frozen artifact changed: {name}")
    if frozen["script_sha256"]!=sha256(__file__):
        raise RuntimeError("Training/evaluation script changed after selection.")
    if frozen["review_record_sha256"]!=sha256(training/"REVIEW_BEFORE_TRAINING.json"):
        raise RuntimeError("Generation/EDA review record changed.")
    return plan,prereg,frozen


def bootstrap_difference(frame,predictions,selected,control,repeats=2000):
    ids=np.asarray(sorted(frame.participant_id.unique()))
    groups={pid:np.flatnonzero(frame.participant_id.to_numpy()==pid) for pid in ids}
    y=frame.true_label.to_numpy();left=predictions[selected];right=predictions[control]
    rng=np.random.default_rng(CV_SEED)
    f1_changes,recall_changes,precision_changes=[],[],[]
    for _ in range(repeats):
        chosen=np.concatenate([groups[pid] for pid in rng.choice(ids,len(ids),replace=True)])
        yy,aa,bb=y[chosen],left[chosen],right[chosen]
        f1_changes.append(float(f1_score(yy,aa,labels=LABELS,average="macro",zero_division=0)
                               -f1_score(yy,bb,labels=LABELS,average="macro",zero_division=0)))
        is_high=yy=="high"
        recall_changes.append(float((aa[is_high]=="high").mean()-(bb[is_high]=="high").mean()) if is_high.any() else 0.)
        a_positive=aa=="high";b_positive=bb=="high"
        a_precision=float(is_high[a_positive].mean()) if a_positive.any() else 0.
        b_precision=float(is_high[b_positive].mean()) if b_positive.any() else 0.
        precision_changes.append(a_precision-b_precision)
    left_metrics,right_metrics=metrics(y,left),metrics(y,right)
    return {"comparison":selected+" minus "+control,"repetitions":repeats,"seed":CV_SEED,
        "participants":len(ids),"method":"Paired whole-participant percentile bootstrap; repeated sampled participants retain all their rows each time",
        "macro_f1_difference":left_metrics["macro_f1"]-right_metrics["macro_f1"],
        "macro_f1_difference_percentile_95ci":np.quantile(f1_changes,[.025,.975]).tolist(),
        "high_recall_difference":left_metrics["high_recall"]-right_metrics["high_recall"],
        "high_recall_difference_percentile_95ci":np.quantile(recall_changes,[.025,.975]).tolist(),
        "high_precision_difference":left_metrics["high_precision"]-right_metrics["high_precision"],
        "high_precision_difference_percentile_95ci":np.quantile(precision_changes,[.025,.975]).tolist(),
        "fraction_macro_f1_differences_positive":float((np.asarray(f1_changes)>0).mean()),
        "scope":"Uncertainty conditional on this fixed synthetic scenario; not clinical or real-instrument evidence"}


def evaluate_stage(experiment,stage):
    assert stage in {"validation","test"}
    training=experiment/"training"
    destination=training/(stage.upper()+"_REPORT.json")
    if destination.exists():
        raise RuntimeError(f"{stage} has already been evaluated once. No repeated holdout scoring or tuning.")
    plan,prereg,frozen=load_frozen(experiment)
    if stage=="test":
        gate=read_json(training/"TEST_READY_FROZEN.json")
        if sha256(training/"SELECTION_FROZEN.json")!=gate["selection_frozen_sha256"]:
            raise RuntimeError("Selected models changed after validation.")
        if sha256(training/"VALIDATION_REPORT.json")!=gate["validation_report_sha256"]:
            raise RuntimeError("Validation report changed before fresh-test evaluation.")
    with lock_stage(training,stage):
        started=time.perf_counter()
        bundle=joblib.load(training/"candidate_models.joblib")
        frame=load_partition(experiment,plan,stage)
        assert set(frame.participant_id).isdisjoint(bundle["training_participants"])
        if stage=="test":
            val_people=read_json(training/"VALIDATION_REPORT.json")["participants"]
            assert set(frame.participant_id).isdisjoint(val_people)
        out=frame[["record_id","participant_id","mission_day","observation_timestamp_utc","target_timestamp_utc"]].copy()
        out["true_label"]=frame[plan["target"]]
        predictions={};scores={}
        for name,model in bundle["models"].items():
            columns=bundle["candidate_specs"][name]["features"]
            predicted=np.asarray(model.predict(frame[columns]))
            probability=np.asarray(model.predict_proba(frame[columns]))
            assert len(predicted)==1080 and probability.shape==(1080,3)
            assert np.isfinite(probability).all()
            predictions[name]=predicted;scores[name]=metrics(frame[plan["target"]],predicted)
            out[name+"__prediction"]=predicted
            for index,label in enumerate(model.classes_):
                out[name+"__model_probability_"+str(label)]=probability[:,index]
        out.to_csv(training/(stage+"_predictions.csv"),index=False,float_format="%.12f")
        pd.DataFrame([{"candidate":name,"split":stage,"rows":len(frame),
                       **metric_scalars(value)} for name,value in scores.items()]).to_csv(
                           training/(stage+"_comparison.csv"),index=False)
        selected=bundle["selection"]["selected_rf_extension"]
        primary_delta={key:scores[selected][key]-scores[PRIMARY_CONTROL][key]
                       for key in ["macro_f1","high_recall","high_precision","accuracy","balanced_accuracy"]}
        secondary_delta={key:scores[XGB_EXTENDED][key]-scores[XGB_CONTROL][key]
                         for key in ["macro_f1","high_recall","high_precision","accuracy","balanced_accuracy"]}
        result={"experiment":"measurement_extension_006","stage":stage,"evaluated_at_utc":utc_now(),
            "scope":"Fresh explicitly simulated cohort; not real questionnaire responses, measured astronaut data or clinical validity",
            "rows":len(frame),"participant_count":frame.participant_id.nunique(),
            "participants":sorted(frame.participant_id.unique()),
            "selected_rf_extension":selected,"primary_control":PRIMARY_CONTROL,"metrics":scores,
            "primary_extension_minus_control":primary_delta,"secondary_xgb33_minus_xgb26":secondary_delta,
            "partition_sha256":plan["expected_partitions"][stage]["sha256"],
            "selection_frozen_sha256":sha256(training/"SELECTION_FROZEN.json"),
            "models_reselected_refitted_or_calibrated":False,"holdout_rows_filtered":0,
            "automatic_promotion":False,"official_bundle_unchanged":True,
            "interpretation":"Additional questionnaire-range scores are designed noisy views of current latent fatigue; gains reflect the simulation assumptions, not measured instrument benefit. Do not compare with the old cohort's 0.5273."}
        if stage=="test":
            bootstrap_frame=frame[["participant_id"]].copy();bootstrap_frame["true_label"]=frame[plan["target"]]
            interval=bootstrap_difference(bootstrap_frame,predictions,selected,PRIMARY_CONTROL,2000)
            result["paired_participant_bootstrap"]=interval
            result["exploratory_reporting_signal"]={
                "macro_f1_gain_at_least_0.01":primary_delta["macro_f1"]>=.01,
                "bootstrap_lower_bound_above_zero":interval["macro_f1_difference_percentile_95ci"][0]>0,
                "high_recall_loss_no_more_than_0.02":primary_delta["high_recall"]>=-.02,
                "reporting_only_not_promotion":True}
            result["all_reporting_conditions_met"]=all(result["exploratory_reporting_signal"][key]
                for key in ["macro_f1_gain_at_least_0.01","bootstrap_lower_bound_above_zero","high_recall_loss_no_more_than_0.02"])
            result["very_high_synthetic_score_warning"]=("Very high simulated F1 requires explicit scrutiny of latent-measurement/target coupling; no noise parameters may be tuned to improve it."
                if scores[selected]["macro_f1"]>.85 else "All scores remain conditional on chosen simulator coupling and noise assumptions.")
        load_frozen(experiment)
        result["elapsed_seconds"]=time.perf_counter()-started
        write_json(destination,result)
        if stage=="validation":
            write_json(training/"TEST_READY_FROZEN.json",{
                "frozen_at_utc":utc_now(),"selection_frozen_sha256":sha256(training/"SELECTION_FROZEN.json"),
                "validation_report_sha256":sha256(destination),"model_reselection_after_validation":False,
                "fresh_test_expected_sha256":plan["expected_partitions"]["test"]["sha256"]})
        else:
            write_results(experiment,result)
        return {"stage":stage+"_evaluated_once","selected_extension":selected,
            "macro_f1":{name:value["macro_f1"] for name,value in scores.items()},
            "primary_delta":primary_delta,"elapsed_seconds":result["elapsed_seconds"],
            "automatic_promotion":False}


def write_results(experiment,test):
    training=experiment/"training"
    val=read_json(training/"VALIDATION_REPORT.json")
    cv=read_json(training/"CV_REPORT.json")
    selected=test["selected_rf_extension"]
    interval=test["paired_participant_bootstrap"]
    lines=["MEASUREMENT EXTENSION 006 — EXPERIMENTAL SYNTHETIC RESULTS", "",
        "A fresh virtual cohort was generated using a frozen scenario and independent",
        "seeds. No real astronaut measurements or actual KSS/Samn–Perelli responses",
        "were added. NASA/CSA resources supplied background, not numerical records.", "",
        "Generation checks and training-only EDA were reviewed before fitting.",
        "Three participant-disjoint folds within 84 training people selected an RF",
        "extension. All imputation was fitted inside fitting folds. Selection and",
        "artifacts were frozen before scoring either 18-person holdout once.", "",
        f"Selected extension: {selected}.",
        f"Training-CV selection: {cv['selection']['selection_rule']}.", "",
        "PRIMARY MATCHED RF COMPARISON"]
    for stage,report in [("validation",val),("fresh synthetic test",test)]:
        control=report["metrics"][PRIMARY_CONTROL];extended=report["metrics"][selected]
        lines.append(f"{stage}: RF26 macro F1 {control['macro_f1']:.4f}; selected extension {extended['macro_f1']:.4f}; change {extended['macro_f1']-control['macro_f1']:+.4f}.")
        lines.append(f"{stage}: High recall {control['high_recall']:.4f} -> {extended['high_recall']:.4f}; High precision {control['high_precision']:.4f} -> {extended['high_precision']:.4f}.")
    lines.extend([f"Test paired participant-bootstrap 95% F1-change interval: {interval['macro_f1_difference_percentile_95ci']}.",
        f"Test reporting conditions met: {test['all_reporting_conditions_met']} (exploratory only; never promotion).", "",
        "SECONDARY MATCHED XGBOOST COMPARISON"])
    for stage,report in [("validation",val),("fresh synthetic test",test)]:
        before=report["metrics"][XGB_CONTROL]["macro_f1"];after=report["metrics"][XGB_EXTENDED]["macro_f1"]
        lines.append(f"{stage}: XGB26 {before:.4f}; XGB33 {after:.4f}; change {after-before:+.4f}.")
    lines.extend(["", "LIMITS",
        "New questionnaire-range scores are extra noisy views of simulated current",
        "latent fatigue. Their value is therefore a scenario assumption, not evidence",
        "that real questionnaires would yield the same model improvement. Derived",
        "sleep features may re-express existing inputs; new naps do not affect the",
        "original simulator's fatigue evolution. No generator noise parameter was",
        "tuned after observing scores. Fresh simulated test subjects do not provide",
        "human or clinical validation. Do not compare these scores directly with the",
        "old-cohort historical 0.5273. All model class scores remain uncalibrated.",
        "The original model, API, dataset and previous experiments remain unchanged.",
        "Experimental artifacts stay isolated; there is no automatic promotion."])
    (training/"RESULTS.txt").write_text("\n".join(lines)+"\n")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=["preregister","prepare-plan","cv","validation","test"])
    parser.add_argument("--experiment-dir",type=Path,default=EXPERIMENT)
    args=parser.parse_args()
    actions={"preregister":preregister,"prepare-plan":prepare_plan,"cv":run_cv,
             "validation":lambda path:evaluate_stage(path,"validation"),
             "test":lambda path:evaluate_stage(path,"test")}
    result=actions[args.stage](args.experiment_dir.resolve())
    print(json.dumps(clean_json(result),indent=2,allow_nan=False))


if __name__=="__main__":
    main()
