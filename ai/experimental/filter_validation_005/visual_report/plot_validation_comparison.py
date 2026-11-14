"""Plot saved validation metrics; no observation files or models are loaded.

Run from the project root with --control and --filtered candidate names.
"""
from pathlib import Path
import argparse
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/astra_shield_matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", required=True)
    parser.add_argument("--filtered", required=True)
    args = parser.parse_args()
    scores = pd.read_csv(ROOT / "experiments/filter_validation_005/validation_comparison.csv").set_index("candidate")
    pair = scores.loc[[args.control, args.filtered]]
    fig, axes = plt.subplots(1, 2, figsize=(11, 6.8))
    fig.subplots_adjust(left=.09, right=.97, top=.78, bottom=.33, wspace=.35)
    fig.suptitle("Experimental filtering on the original validation split", fontsize=16, weight="bold", y=.96)
    fig.text(.5, .90, "Same 1,080 records from 18 validation participants; all observations retained",
             ha="center", fontsize=11, color="#444444")
    colors = ["#24689c", "#bd6245"]
    labels = ["Original model", "Filtered candidate"]
    for ax, metric, title in zip(axes, ["macro_f1", "high_recall"], ["Macro-F1", "Recall for High fatigue"]):
        values = pair[metric].to_numpy()
        ax.bar(np.arange(2), values, color=colors, width=.62)
        for x, value in enumerate(values):
            ax.text(x, value + .018, f"{value:.4f}", ha="center", fontsize=12)
        ax.set_xticks(np.arange(2), labels, fontsize=10)
        ax.set(ylim=(0, 1), title=title)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, alpha=.15)
    delta = float(pair.iloc[1].macro_f1 - pair.iloc[0].macro_f1)
    notes = (
        f"Macro-F1 difference: {delta:+.4f}. Read the paired participant-bootstrap interval in RESULTS.txt.\n\n"
        "The filter excludes unusual fitting rows only; it does not change validation inputs or target labels.\n"
        "Its thresholds are learned from TRAIN alone. All 26 model features and RF settings are unchanged.\n\n"
        "This validation set has been used before. The result is a development comparison, not a fresh test.\n"
        "The original dataset and official model remain intact; the candidate is saved separately."
    )
    fig.text(.09, .23, notes, fontsize=10, va="top", linespacing=1.45)
    for suffix in ("png", "pdf"):
        fig.savefig(OUT / f"ASTRA_SHIELD_filtered_validation.{suffix}", dpi=170, facecolor="white")
    plt.close(fig)
    print(f"Saved chart in {OUT}")


if __name__ == "__main__":
    main()
