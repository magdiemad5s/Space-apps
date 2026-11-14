"""Render frozen model results; no fitting, tuning or new model predictions."""
from pathlib import Path
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/astra-shield-mpl")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/astra-shield-cache")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = "next_day_fatigue_classification"


def main():
    reports = ROOT / "reports"
    results = json.loads((reports / "test_metrics.json").read_text())
    validation = json.loads((reports / "validation_metrics.json").read_text())
    training = json.loads((reports / "training_summary.json").read_text())
    selected = results["tasks"][PRIMARY]["selected_metrics"]
    cm = np.asarray(selected["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(7.5, 6))
    ax.imshow(cm, cmap="Blues")
    for (i, j), count in np.ndenumerate(cm):
        ax.text(j, i, str(count), ha="center", va="center", fontsize=14,
                color="white" if count > cm.max()/2 else "#17324d")
    names = [s.title() for s in selected["confusion_matrix_labels"]]
    ax.set(xticks=range(3), yticks=range(3), xticklabels=names, yticklabels=names,
           xlabel="Predicted next-day category", ylabel="Simulated next-day category",
           title="Fatigue classifier: frozen test participants")
    fig.text(.5, .02, "1,080 synthetic observations • 18 held-out virtual participants • Macro-F1 0.5285",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, 1))
    fig.savefig(reports / "fatigue_test_confusion_matrix.png", dpi=180)
    plt.close(fig)

    candidate = validation["tasks"][PRIMARY]["candidates"]
    baseline = validation["tasks"][PRIMARY]["baselines"]
    pairs = [("Random Forest", candidate["random_forest_balanced"]["validation_metrics"]["macro_f1"]),
             ("XGBoost", candidate["xgboost_balanced"]["validation_metrics"]["macro_f1"]),
             ("Repeat today's class", baseline["current_fatigue_persistence"]["validation_metrics"]["macro_f1"]),
             ("Majority class", baseline["majority_class"]["validation_metrics"]["macro_f1"])]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    bars = ax.bar([p[0] for p in pairs], [p[1] for p in pairs], color=["#127b8e", "#437bc0", "#a1adb8", "#c5cdd5"])
    ax.bar_label(bars, fmt="%.3f", padding=4)
    ax.set(ylim=(0, .65), ylabel="Validation Macro-F1", title="Model selection used validation participants only")
    fig.text(.5, .015, "Synthetic data; final test results did not choose the model.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .03, 1, 1))
    fig.savefig(reports / "fatigue_validation_model_comparison.png", dpi=180)
    plt.close(fig)

    # Uncertainty from saved predictions, resampling whole participants. This
    # adds no model selection or tuning and is not a new independent test cohort.
    predictions = pd.read_csv(reports / "test_predictions.csv")
    groups = {pid: frame.index.to_numpy() for pid, frame in predictions.groupby("participant_id")}
    ids = list(groups)
    raw = pd.read_csv(ROOT / "data/test.csv", usecols=["record_id", "self_report_fatigue_score"])
    p = predictions.merge(raw, on="record_id", validate="one_to_one")
    true = p[f"{PRIMARY}__y_true"].to_numpy()
    pred = p[f"{PRIMARY}__y_pred"].to_numpy()
    persistence = np.where(p.self_report_fatigue_score < 4, "low", np.where(p.self_report_fatigue_score < 7, "moderate", "high"))
    rng = np.random.default_rng(20261114)
    scores, differences = [], []
    for _ in range(500):
        sample = rng.choice(ids, size=len(ids), replace=True)
        ix = np.concatenate([groups[pid] for pid in sample])
        score = f1_score(true[ix], pred[ix], labels=["low", "moderate", "high"], average="macro", zero_division=0)
        reference = f1_score(true[ix], persistence[ix], labels=["low", "moderate", "high"], average="macro", zero_division=0)
        scores.append(float(score)); differences.append(float(score-reference))
    uncertainty = {
        "method": "500 paired bootstrap resamples of complete held-out virtual participants; fixed model and predictions",
        "scope": "Exploratory uncertainty on synthetic participant cohorts, not clinical validation",
        "macro_f1_percentile_95_interval": np.quantile(scores, [.025, .975]).tolist(),
        "macro_f1_difference_vs_persistence_percentile_95_interval": np.quantile(differences, [.025, .975]).tolist(),
        "test_participants": len(ids), "seed": 20261114,
    }
    (reports / "participant_bootstrap.json").write_text(json.dumps(uncertainty, indent=2) + "\n")
    rows = []
    for name, task in results["tasks"].items():
        for metric, value in task["selected_metrics"].items():
            if isinstance(value, (float, int)):
                rows.append({"task": name, "selected_model": task["selected_model"], "partition": "test", "metric": metric, "value": value, "data_origin": "synthetic"})
    pd.DataFrame(rows).to_csv(reports / "metrics_summary.csv", index=False)
    note = [
        "ASTRA-SHIELD — FROZEN RESULTS", "",
        f"Training/selection: {training['total_training_selection_seconds']:.2f} seconds on attached cloud CPU.",
        "Dataset: original longitudinal synthetic data, no V2/V3 records.",
        "Validation selected Random Forest (Macro-F1 0.5273) over XGBoost (0.4857).",
        "The final test cohort was not used to choose features, parameters or thresholds.", "",
        "TEST RESULTS: 1,080 records from 18 virtual participants",
        "Fatigue classification Macro-F1: 0.5285; persistence baseline: 0.5181; majority: 0.2676.",
        "Fatigue accuracy: 61.85%; majority accuracy: 67.04%. Macro-F1 was the selection objective.",
        "High fatigue: precision 41.94%, recall 45.77%. The model misses over half of simulated High cases.",
        "Fatigue score MAE: 1.0197 on a custom 0..10 score; persistence: 1.1681.",
        "Next-day reaction-time MAE: 14.0213 ms; persistence: 15.5556 ms.",
        "Injected physiological-event detection: precision 0.7097, recall 0.8148, F1 0.7586.",
        "Journal stress Macro-F1: 0.3938; High-stress recall: 0.1695. Text results are experimental.", "",
        "INTERPRETATION",
        "The primary classifier has only a small gain over repeating today's category.",
        "Bootstrap uncertainty (whole participants, 500 draws) is in participant_bootstrap.json.",
        "These are simulator results, not real astronaut/clinical evidence. No tuning followed test evaluation.",
        "SHAP explains the classifier; it does not establish causes or justify medical decisions.",
    ]
    (reports / "RESULTS.txt").write_text("\n".join(note) + "\n")
    print(json.dumps(uncertainty, indent=2))


if __name__ == "__main__":
    main()
