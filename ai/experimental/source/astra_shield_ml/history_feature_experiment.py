"""Prespecified train-only history experiment; the official demo stays unchanged.

No validation or test partition is opened. The same eligible observations and
participant folds are used for every candidate. Extra fields are experimental
and are not accepted by the current API's frozen feature contract.
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
CONTROL = "rf_current26_control"
AUGMENTED = "rf_current26_plus4_history"
PERSISTENCE = "current_fatigue_persistence"
NEW_FEATURES = ["history_prior3_fatigue_mean", "history_current_minus_prior3_fatigue",
                "history_prior3_sleep_shortfall_sum_hours", "history_prior7_sleep_midpoint_std_minutes"]


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def derive_history_features(frame):
    """Within each participant, shift measurements before taking rolling values.

    Shortfall is a simulator engineering proxy relative to fixed calibration
    sleep duration. It is not measured physiological sleep debt or sleep need.
    """
    out = frame.sort_values(["participant_id", "mission_day"]).copy()
    groups = out.groupby("participant_id", sort=False)
    out[NEW_FEATURES[0]] = groups.self_report_fatigue_score.transform(
        lambda s: s.shift(1).rolling(3, min_periods=3).mean()).round(6)
    out[NEW_FEATURES[1]] = (out.self_report_fatigue_score-out[NEW_FEATURES[0]]).round(6)
    shortfall = (out.baseline_sleep_duration_hours-out.sleep_duration_hours).clip(lower=0)
    out[NEW_FEATURES[2]] = shortfall.groupby(out.participant_id).transform(
        lambda s: s.shift(1).rolling(3, min_periods=3).sum()).round(6)
    out[NEW_FEATURES[3]] = groups.sleep_midpoint_deviation_minutes.transform(
        lambda s: s.shift(1).rolling(7, min_periods=7).std(ddof=0)).round(6)
    return out


def model_for(name):
    if name == PERSISTENCE:
        return PersistenceClassifier()
    return Pipeline([("imputer", SimpleImputer(strategy="median")),
                     ("model", RandomForestClassifier(n_estimators=200, max_depth=14,
                         min_samples_leaf=8, class_weight="balanced", random_state=SEED, n_jobs=2))])


def measure(truth, prediction):
    y, p = np.asarray(truth), np.asarray(prediction)
    report = classification_report(y, p, labels=LABELS, output_dict=True, zero_division=0)
    non_high = y != "high"
    false_high = int(((p == "high") & non_high).sum())
    return {"macro_f1": float(f1_score(y, p, labels=LABELS, average="macro", zero_division=0)),
            "high_precision": float(report["high"]["precision"]),
            "high_recall": float(report["high"]["recall"]),
            "accuracy": float((y == p).mean()),
            "false_high_count": false_high,
            "false_high_per_100_non_high": float(false_high / non_high.sum()*100) if non_high.any() else 0.,
            "classification_report": report,
            "confusion_matrix_labels": LABELS,
            "confusion_matrix": confusion_matrix(y, p, labels=LABELS).tolist()}


def scalar_metrics(metrics):
    return {k: v for k,v in metrics.items() if isinstance(v, (int, float))}


def participant_bootstrap(frame, predictions, left, right, repeats=1000):
    rng = np.random.default_rng(SEED)
    ids = np.asarray(sorted(frame.participant_id.unique()))
    indexes = {pid: np.flatnonzero(frame.participant_id.to_numpy() == pid) for pid in ids}
    y = frame.true_label.to_numpy()
    differences = []
    for _ in range(repeats):
        selected = np.concatenate([indexes[pid] for pid in rng.choice(ids, len(ids), replace=True)])
        differences.append(float(f1_score(y[selected], predictions[left][selected], labels=LABELS,
                                           average="macro", zero_division=0)
                                 - f1_score(y[selected], predictions[right][selected], labels=LABELS,
                                             average="macro", zero_division=0)))
    observed = measure(y, predictions[left])["macro_f1"]-measure(y, predictions[right])["macro_f1"]
    return {"comparison": f"{left} minus {right}", "repetitions": repeats, "seed": SEED,
            "unit": "whole participant, all eligible days together",
            "observed_oof_macro_f1_difference": observed,
            "percentile_95ci": np.quantile(differences, [.025, .975]).tolist(),
            "fraction_positive": float((np.asarray(differences)>0).mean()),
            "scope": "Descriptive uncertainty for correlated grouped-CV predictions from a synthetic training cohort; not a fresh or independent test"}


def main(project_dir=None):
    root = Path(project_dir or Path(__file__).resolve().parents[1])
    output = root / "experiments/history_003"
    output.mkdir(parents=True, exist_ok=True)
    if (output / "plan.json").exists():
        raise RuntimeError("The frozen history_003 plan already exists; do not overwrite or adapt this experiment after results.")
    beginning = time.perf_counter()
    train_path, config_path = root / "data/train.csv", root / "data/task_config.json"
    folds_path = root / "experiments/improvement_002/participant_folds.csv"
    train = pd.read_csv(train_path)
    cfg = json.loads(config_path.read_text())
    task = cfg["tasks"]["next_day_fatigue_classification"]
    base_features, target = task["predictors"], task["target"]
    folds = pd.read_csv(folds_path)
    assert train.split.eq("train").all() and train.is_synthetic.eq(1).all()
    assert train.record_id.is_unique and folds.participant_id.is_unique
    assert set(folds.participant_id) == set(train.participant_id)
    assert set(folds.held_out_fold) == {0, 1, 2}
    assert folds.groupby("held_out_fold").size().eq(28).all()
    assert train.groupby("participant_id").mission_day.apply(lambda s: sorted(s)==list(range(1,61))).all()
    assert train.groupby("participant_id").baseline_sleep_duration_hours.nunique().eq(1).all()
    source_hash = sha256(train_path)
    official_artifact_hash = sha256(root / "artifacts/bundle.joblib")
    fold_map = dict(zip(folds.participant_id, folds.held_out_fold))
    folds.to_csv(output / "participant_folds.csv", index=False)
    feature_definitions = {
        NEW_FEATURES[0]: "Within participant mean(self_report_fatigue_score[t-3:t-1]); shift(1), rolling(3), rounded6",
        NEW_FEATURES[1]: "Current self_report_fatigue_score[t] minus history_prior3_fatigue_mean[t]; rounded6",
        NEW_FEATURES[2]: "Sum over t-3..t-1 of max(0,fixed baseline_sleep_duration_hours - observed sleep_duration_hours); rounded6; engineering shortfall proxy, not physiological sleep debt",
        NEW_FEATURES[3]: "Population SD(ddof=0) of sleep_midpoint_deviation_minutes over t-7..t-1; shift(1), rolling(7), rounded6",
    }
    plan = {
        "experiment": "history_003", "frozen_before_fit_at_utc": stamp(), "seed": SEED,
        "source": "Original longitudinal SYNTHETIC training partition only",
        "source_train_sha256": source_hash, "task_config_sha256": sha256(config_path),
        "source_folds_sha256": sha256(folds_path), "script_sha256": sha256(__file__),
        "official_bundle_sha256_before": official_artifact_hash,
        "target": target, "control_predictors": base_features,
        "new_features": feature_definitions,
        "common_cohort": "All 84 training participants, mission days8..60 inclusive:4452 rows; earlier rows are history warmup, not invalid data removed during cleaning",
        "candidates": {CONTROL: base_features, AUGMENTED: base_features+NEW_FEATURES,
                       PERSISTENCE: ["self_report_fatigue_score"]},
        "rf_parameters": {"n_estimators":200,"max_depth":14,"min_samples_leaf":8,"class_weight":"balanced","random_state":SEED,"n_jobs":2},
        "primary_selection": "Compare augmented RF to unchanged RF by mean macroF1 across the three fixed participant folds; persistence is descriptive baseline",
        "folds": "Reuse improvement_002 participant assignments; train56 participants, holdout28, all candidates same rows",
        "preprocessing": "Median imputer fitted inside each fitting fold only; no scaling/calibration/threshold tuning",
        "temporal_evaluations": [
            {"fit_days":[8,30], "label_availability_cutoff_day":31, "evaluation_days":[32,45]},
            {"fit_days":[8,45], "label_availability_cutoff_day":46, "evaluation_days":[47,60]},
        ],
        "promotion_gate_engineering_only": {
            "mean_groupcv_macro_f1_delta_min": .01,
            "all_three_groupfold_deltas_min": 0.,
            "all_two_temporal_macro_f1_deltas_min": 0.,
            "aggregate_group_oof_high_recall_delta_min": -.02,
            "aggregate_group_oof_high_precision_delta_min": -.02,
        },
        "gate_interpretation": "Passing can only justify parent review for further development confirmation; no automatic promotion or clinical significance",
        "uncertainty": "1000 whole-participant paired bootstrap resamples of OOF predictions; descriptive, not independent external evidence",
        "validation_policy": "Do not read validation.csv in this experiment; parent review required before any prespecified reused-validation confirmation",
        "test_policy": "Never open test.csv or rescore final test; original production model/API/data/reports stay untouched",
        "invariants": ["Future observation changes cannot affect earlier history features", "Changing target labels cannot alter features", "Prefix derivation agrees with full-history derivation", "No target metadata in any predictor list", "Same rows/folds for all candidates", "Every fitting label available before temporal evaluation begins"],
    }
    write_json(output / "plan.json", plan)
    enriched = derive_history_features(train)
    eligible = enriched[enriched.mission_day.between(8,60)].copy().reset_index(drop=True)
    assert len(eligible)==4452 and eligible.participant_id.nunique()==84
    assert np.isfinite(eligible[base_features+NEW_FEATURES]).all().all()
    assert not any(c.startswith("target_") for c in base_features+NEW_FEATURES)
    # Assertions below check feature causality without inspecting outcomes.
    mutated = train.copy()
    future = mutated.mission_day.ge(40)
    mutated.loc[future,"self_report_fatigue_score"] = 10.
    mutated.loc[future,"sleep_duration_hours"] = .1
    mutated.loc[future,"sleep_midpoint_deviation_minutes"] = 720.
    mutated_enriched = derive_history_features(mutated)
    before = enriched.mission_day.lt(40)
    assert np.allclose(enriched.loc[before,NEW_FEATURES], mutated_enriched.loc[before,NEW_FEATURES], equal_nan=True)
    target_mutation = train.copy()
    for column in [c for c in target_mutation if c.startswith("target_")]:
        target_mutation[column] = "unused_target_mutation"
    assert np.allclose(enriched[NEW_FEATURES], derive_history_features(target_mutation)[NEW_FEATURES], equal_nan=True)
    prefix = derive_history_features(train[train.mission_day.le(30)])
    assert np.allclose(enriched.loc[enriched.mission_day.le(30),NEW_FEATURES], prefix[NEW_FEATURES], equal_nan=True)
    # Check one explicit rolling window against a direct earlier-record calculation.
    for _, group in enriched.groupby("participant_id"):
        prior = group[group.mission_day.between(5,7)]
        day8 = group[group.mission_day.eq(8)].iloc[0]
        assert np.isclose(day8[NEW_FEATURES[0]], prior.self_report_fatigue_score.mean(), atol=1e-6)
        expected = (prior.baseline_sleep_duration_hours-prior.sleep_duration_hours).clip(lower=0).sum()
        assert np.isclose(day8[NEW_FEATURES[2]], expected, atol=1e-6)
    invariant_report = {"source_train_only":True, "future_mutation_safe":True,
        "target_mutation_safe":True,"prefix_safe":True,"all_new_features_finite_on_common_cohort":True,
        "new_feature_warmup_rows_excluded_per_participant":7,
        "source_rows_deleted_or_rewritten":0,"source_dataset_modified":False}
    write_json(output / "feature_invariants.json", invariant_report)
    eligible[["record_id","participant_id","mission_day"]+NEW_FEATURES].to_csv(output/"experimental_history_features.csv",index=False)
    candidates = {CONTROL:base_features,AUGMENTED:base_features+NEW_FEATURES,PERSISTENCE:base_features}
    oof = eligible[["record_id","participant_id","mission_day"]].copy()
    oof["held_out_fold"] = eligible.participant_id.map(fold_map)
    oof["true_label"] = eligible[target]
    fold_rows, predictions, pooled_metrics = [], {}, {}
    independence = []
    for name, predictors in candidates.items():
        predicted = np.empty(len(eligible),dtype=object)
        for fold in range(3):
            held = eligible.participant_id.map(fold_map).eq(fold)
            fitting = ~held
            fit_ids, held_ids = set(eligible.loc[fitting,"participant_id"]),set(eligible.loc[held,"participant_id"])
            assert fit_ids.isdisjoint(held_ids) and len(fit_ids)==56 and len(held_ids)==28
            assert int(held.sum())==1484
            model = model_for(name)
            before_fit = time.perf_counter()
            model.fit(eligible.loc[fitting,predictors],eligible.loc[fitting,target])
            pred = model.predict(eligible.loc[held,predictors])
            elapsed = time.perf_counter()-before_fit
            predicted[held.to_numpy()] = pred
            metrics = measure(eligible.loc[held,target],pred)
            fold_rows.append({"candidate":name,"fold":fold,"fit_predict_seconds":elapsed,
                              "fit_rows":int(fitting.sum()),"held_out_rows":int(held.sum()),
                              "predictor_count":len(predictors),**scalar_metrics(metrics)})
            if name==CONTROL:
                independence.append({"fold":fold,"fit_participants":sorted(fit_ids),"held_out_participants":sorted(held_ids),"overlap_count":0})
        assert not pd.isna(predicted).any()
        predictions[name]=predicted
        oof[name]=predicted
        pooled_metrics[name]=measure(eligible[target],predicted)
        print(name,"pooledOOFmacroF1",round(pooled_metrics[name]["macro_f1"],4),flush=True)
    oof.to_csv(output/"groupcv_predictions.csv",index=False)
    fold_table=pd.DataFrame(fold_rows)
    fold_table.to_csv(output/"groupcv_fold_metrics.csv",index=False)
    cv_summary=fold_table.groupby("candidate").agg(mean_macro_f1=("macro_f1","mean"),
        std_macro_f1=("macro_f1","std"),mean_high_recall=("high_recall","mean"),mean_high_precision=("high_precision","mean"),
        mean_false_high_per_100_non_high=("false_high_per_100_non_high","mean")).reset_index()
    cv_summary.to_csv(output/"groupcv_comparison.csv",index=False)
    temporal_rows, temporal_predictions=[],[]
    for index, spec in enumerate(plan["temporal_evaluations"]):
        fit=eligible.mission_day.between(*spec["fit_days"])
        holding=eligible.mission_day.between(*spec["evaluation_days"])
        cutoff_day=spec["label_availability_cutoff_day"]
        cutoffs=train[train.mission_day.eq(cutoff_day)].set_index("participant_id").observation_timestamp_utc
        label_times=pd.to_datetime(eligible.loc[fit,"target_timestamp_utc"],utc=True)
        available=pd.to_datetime(eligible.loc[fit,"participant_id"].map(cutoffs),utc=True)
        assert (label_times<=available).all()
        assert available.max()<pd.to_datetime(eligible.loc[holding,"observation_timestamp_utc"],utc=True).min()
        assert eligible.loc[fit,"record_id"].isin(eligible.loc[holding,"record_id"]).sum()==0
        for name,predictors in candidates.items():
            model=model_for(name)
            before_fit=time.perf_counter()
            model.fit(eligible.loc[fit,predictors],eligible.loc[fit,target])
            pred=model.predict(eligible.loc[holding,predictors])
            metrics=measure(eligible.loc[holding,target],pred)
            temporal_rows.append({"candidate":name,"temporal_fold":index,
                "fit_day_start":spec["fit_days"][0],"fit_day_end":spec["fit_days"][1],
                "fit_label_cutoff_day":cutoff_day,"eval_day_start":spec["evaluation_days"][0],
                "eval_day_end":spec["evaluation_days"][1],"fit_rows":int(fit.sum()),"eval_rows":int(holding.sum()),
                "fit_predict_seconds":time.perf_counter()-before_fit,**scalar_metrics(metrics)})
            part=eligible.loc[holding,["record_id","participant_id","mission_day"]].copy()
            part["candidate"]=name;part["temporal_fold"]=index
            part["true_label"]=eligible.loc[holding,target];part["prediction"]=pred
            temporal_predictions.append(part)
    temporal_table=pd.DataFrame(temporal_rows)
    temporal_table.to_csv(output/"temporal_metrics.csv",index=False)
    pd.concat(temporal_predictions,ignore_index=True).to_csv(output/"temporal_predictions.csv",index=False)
    means=cv_summary.set_index("candidate").mean_macro_f1
    group_deltas=(fold_table[fold_table.candidate.eq(AUGMENTED)].set_index("fold").macro_f1
                  -fold_table[fold_table.candidate.eq(CONTROL)].set_index("fold").macro_f1)
    temporal_deltas=(temporal_table[temporal_table.candidate.eq(AUGMENTED)].set_index("temporal_fold").macro_f1
                     -temporal_table[temporal_table.candidate.eq(CONTROL)].set_index("temporal_fold").macro_f1)
    precision_delta=pooled_metrics[AUGMENTED]["high_precision"]-pooled_metrics[CONTROL]["high_precision"]
    recall_delta=pooled_metrics[AUGMENTED]["high_recall"]-pooled_metrics[CONTROL]["high_recall"]
    gates={"mean_cv_macro_f1_gain_at_least_0.01":bool(means[AUGMENTED]-means[CONTROL]>=.01),
           "all_groupfold_macro_f1_deltas_nonnegative":bool(group_deltas.ge(0).all()),
           "all_temporal_macro_f1_deltas_nonnegative":bool(temporal_deltas.ge(0).all()),
           "oof_high_recall_drop_no_more_than_0.02":bool(recall_delta>=-.02),
           "oof_high_precision_drop_no_more_than_0.02":bool(precision_delta>=-.02)}
    uncertainty={"augmented_minus_control":participant_bootstrap(oof,predictions,AUGMENTED,CONTROL),
                 "augmented_minus_persistence":participant_bootstrap(oof,predictions,AUGMENTED,PERSISTENCE)}
    assert sha256(train_path)==source_hash
    assert sha256(root/"artifacts/bundle.joblib")==official_artifact_hash
    summary={"experiment":"history_003","completed_at_utc":stamp(),"elapsed_seconds":time.perf_counter()-beginning,
        "scope":"Exploratory synthetic TRAIN-only comparison; no validation/finaltest read, no deployment promotion",
        "eligible_rows":len(eligible),"virtual_participants":eligible.participant_id.nunique(),"eligible_days":[8,60],
        "cohort_warning":"Scores apply to4452commonrows and are not directly comparable with previous5040row experiment scores",
        "groupcv_comparison":cv_summary.to_dict("records"),"pooled_oof_metrics":pooled_metrics,
        "groupfold_macro_f1_deltas_augmented_minus_control":{str(k):float(v) for k,v in group_deltas.items()},
        "temporal_macro_f1_deltas_augmented_minus_control":{str(k):float(v) for k,v in temporal_deltas.items()},
        "oof_high_precision_delta":precision_delta,"oof_high_recall_delta":recall_delta,
        "prespecified_gate_results":gates,"passes_all_engineering_comparison_gates":all(gates.values()),
        "paired_participant_bootstrap":uncertainty,"fold_independence":independence,
        "feature_invariants":invariant_report,"validation_read":False,"final_test_read":False,
        "official_bundle_unchanged":True,"source_train_unchanged":True,"clinical_validation":False,
        "next_action":"Parent review only; retain official demo unchanged regardless of gate result; any validation confirmation needs a separate frozen step"}
    write_json(output/"summary.json",summary)
    lines=["ASTRA-SHIELD — HISTORY FEATURE EXPERIMENT 003","",
        "Original synthetic TRAINING participants only. No validation or final-test",
        "partition was opened. The official saved model/API/backend/dataset are unchanged.",
        "A frozen plan and existing participant folds were saved before model fitting.","",
        "COMMON COHORT",
        "84 virtual participants x53days(days8..60)=4452 observations. Days1..7 were",
        "retained as causal history warmup; these are not invalid rows removed during",
        "cleaning. All candidates use exactly the same4452observations and folds.",
        "Do not directly compare these metrics with earlier5040row experiment scores.","",
        "ADDED FEATURES"]
    for name,definition in feature_definitions.items():lines.append(f"{name}: {definition}")
    lines.extend(["","RESULTS"])
    for _,row in cv_summary.iterrows():
        lines.append(f"{row.candidate}: mean grouped-CV macro F1={row.mean_macro_f1:.4f}; mean high recall={row.mean_high_recall:.4f}; mean high precision={row.mean_high_precision:.4f}.")
    lines.append(f"Mean CV macro F1 augmented-control delta={means[AUGMENTED]-means[CONTROL]:+.4f}.")
    lines.append(f"Per-groupfold deltas={group_deltas.to_dict()}.")
    lines.append(f"Forward-time deltas={temporal_deltas.to_dict()}.")
    for name,value in gates.items():lines.append(f"Gate {name}: {value}.")
    for name,value in uncertainty.items():
        lines.append(f"{name}: pooledOOFmacroF1delta={value['observed_oof_macro_f1_difference']:+.4f}, participant-bootstrap95%interval={value['percentile_95ci']}.")
    lines.extend(["",f"All prespecified engineering comparison gates passed: {all(gates.values())}.",
        "These are exploratory engineering criteria, not medical thresholds or an",
        "independent scientific validation. Bootstrap intervals describe correlated",
        "OOF predictions from the same synthetic development cohort.",
        "No model was promoted, no threshold/calibration was tuned, and no new official",
        "bundle was written. Keep the baseline demo until parent review; even a gate",
        "pass only justifies a separately frozen development-confirmation step."])
    (output/"RESULTS.txt").write_text("\n".join(lines)+"\n")
    print(json.dumps({"mean_groupcv_macro_f1":means.to_dict(),"group_deltas":group_deltas.to_dict(),
        "temporal_deltas":temporal_deltas.to_dict(),"passes_all_gates":all(gates.values()),
        "elapsed_seconds":summary["elapsed_seconds"],"validation_read":False,"final_test_read":False},indent=2))
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir",type=Path)
    args=parser.parse_args()
    main(args.project_dir)
