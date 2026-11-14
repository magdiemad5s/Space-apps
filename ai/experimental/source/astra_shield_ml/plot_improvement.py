"""Plot saved training-group CV metrics; do not read observations or fit models."""
from pathlib import Path
import os
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "astra-improvement-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main():
    folder = Path(__file__).resolve().parents[1] / "experiments/improvement_002"
    frame = pd.read_csv(folder / "cv_comparison.csv")
    labels = {
        "current_rf_leaf8_depth14": "Current Random Forest",
        "current_fatigue_persistence": "Tomorrow = today's category",
        "rf_leaf16_depth10": "Random Forest: leaf 16 / depth 10",
        "rf_leaf32_depth8": "Random Forest: leaf 32 / depth 8",
        "rf_leaf48_depth6": "Random Forest: leaf 48 / depth 6",
        "balanced_logistic_C0.1": "Balanced logistic: C = 0.1",
        "balanced_logistic_C1": "Balanced logistic: C = 1",
        "majority_class": "Always predict Moderate",
    }
    colors = ["#087e8b" if c == "current_rf_leaf8_depth14" else
              "#d08a38" if c == "current_fatigue_persistence" else "#7991ac"
              for c in frame.candidate]
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.5), sharey=True)
    for ax, metric, title in zip(axes, ["mean_cv_macro_f1", "mean_cv_high_recall"],
                                  ["Macro-F1: prespecified selection metric", "High recall: descriptive tradeoff"]):
        ax.barh(range(len(frame)), frame[metric], color=colors, height=.65)
        ax.set_yticks(range(len(frame)), [labels[c] for c in frame.candidate], fontsize=10)
        ax.set_xlim(0, .78)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Mean across 3 participant folds (0 to 1)")
        ax.grid(axis="x", alpha=.2)
        ax.set_axisbelow(True)
        for i, value in enumerate(frame[metric]):
            ax.text(value + .012, i, f"{value:.3f}", va="center", fontsize=9)
    axes[0].invert_yaxis()
    fig.suptitle("ASTRA-SHIELD: no tested alternative improved the selected Macro-F1 objective", fontsize=14)
    fig.text(.5, .035, "Synthetic TRAIN data only: 84 virtual participants / 5,040 observations. All days of each person stay in one fold.", ha="center", fontsize=9)
    fig.text(.5, .01, "Fold averages are development evidence; no fresh test or clinical validation. The deployed model remains unchanged.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, .94))
    destination = folder / "cv_comparison.png"
    fig.savefig(destination, dpi=170, facecolor="white")
    plt.close(fig)
    print(destination)


if __name__ == "__main__":
    main()
