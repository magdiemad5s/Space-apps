"""Reproduce the noise audit figures using TRAIN and saved experiment metrics only.

Run from the project root:
    .venv/bin/python reports/noise_004/generate_noise_plots.py
No model is fitted and no validation/test observation file is opened.
"""
from pathlib import Path
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/astra_shield_matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EXPERIMENT = ROOT / "experiments/noise_004"
AUDIT = ROOT / "experiments/noise_004_review"
plt.rcParams.update({"font.size": 11, "axes.spines.top": False,
                     "axes.spines.right": False, "savefig.dpi": 170})


def audit_figure():
    data = pd.read_csv(ROOT / "data/train.csv")
    report = json.loads((AUDIT / "noise_audit.json").read_text())
    desc = report["descriptive_tails"]["personalized_delta_robust_z_over_4p5"]
    columns = list(desc["medians"])
    med = data[columns].median()
    mad = (data[columns] - med).abs().median()
    flags = ((data[columns] - med).abs() / (1.4826 * mad)).gt(4.5).any(axis=1)
    events = data.target_current_physiology_event_injected.eq(1)
    assert int(flags.sum()) == desc["rows_flagged"] == 254
    assert int((flags & ~events).sum()) == 0
    fig, axes = plt.subplots(1, 2, figsize=(12, 7.6))
    fig.subplots_adjust(top=.79, bottom=.28, left=.08, right=.90, wspace=.29)
    fig.suptitle("ASTRA-SHIELD: unusual values are not automatically errors", y=.96,
                 fontsize=17, weight="bold")
    fig.text(.5, .90, "Original synthetic TRAIN partition: 5,040 observations from 84 virtual participants",
             ha="center", color="#444444")
    ax = axes[0]
    groups = [(~events, "No injected event", "#718096", "o", .24),
              (events & ~flags, "Injected event, unflagged", "#dd8c12", "o", .8),
              (flags, "Flagged: all injected events", "#b63346", "x", .8)]
    for mask, label, color, marker, alpha in groups:
        ax.scatter(data.loc[mask, "heart_rate_delta_from_baseline_bpm"],
                   data.loc[mask, "hrv_delta_from_baseline_ms"],
                   s=13, color=color, marker=marker, alpha=alpha,
                   label=f"{label} (n={int(mask.sum()):,})", rasterized=True)
    ax.set(title="Personal-baseline deviations", xlabel="Heart-rate change (bpm)",
           ylabel="RMSSD change (ms)")
    ax.legend(fontsize=8, loc="lower left", frameon=True)
    ax = axes[1]
    density = ax.hexbin(data.self_report_fatigue_score,
                       data.target_next_day_fatigue_score,
                       gridsize=25, mincnt=1, cmap="Blues", extent=(0, 10, 0, 10))
    ax.plot([0, 10], [0, 10], "--", lw=1, color="#5c6572", label="Same score tomorrow")
    for boundary in (4, 7):
        ax.axhline(boundary, color="#b63346", lw=1, linestyle=":")
    ax.set(xlim=(0, 10), ylim=(0, 10), xlabel="Today's self-reported fatigue (0–10)",
           ylabel="Tomorrow's self-reported fatigue (0–10)",
           title="Forecast uncertainty remains")
    ax.legend(fontsize=8, loc="upper left")
    fig.colorbar(density, ax=ax, fraction=.045, pad=.025, label="Observations per bin")
    notes = (
        "Left: a descriptive robust-z rule flags 254 rows (5.04%); all are deliberate physiological events.\n"
        "This rule does not prove recording error. CV filtering thresholds are fitted separately inside each fit fold.\n\n"
        "Right: the generator adds random fatigue/report variation. Dotted horizontal lines mark custom class cutoffs.\n"
        "1,615 next-day scores are within 0.5 of a cutoff; that does not make their labels incorrect.\n\n"
        "The audit found no missing, duplicate, out-of-bound or inconsistent derived values under its specified checks."
    )
    fig.text(.08, .19, notes, fontsize=10, va="top", linespacing=1.45)
    return fig


def experiment_figure():
    # This table is produced from saved predictions by the independent verifier.
    frame = pd.read_csv(OUT / "verified_comparison.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12, 7.6))
    fig.subplots_adjust(top=.79, bottom=.32, left=.08, right=.97, wspace=.32)
    fig.suptitle("Does excluding or downweighting unusual rows help?", y=.96,
                 fontsize=17, weight="bold")
    fig.text(.5, .90, "Same Random Forest, same held-out observations; training participants only",
             ha="center", color="#444444")
    labels = {"control": "Unchanged", "exclude": "Exclude tails", "downweight": "Weight tails 0.25",
              "persistence": "Persistence"}
    colors = {"control": "#24689c", "exclude": "#bd6245", "downweight": "#249281", "persistence": "#8a8a8a"}
    group = frame[frame.evaluation.eq("group_cv")]
    order = ["control", "exclude", "downweight", "persistence"]
    means = group.groupby("variant").macro_f1.mean().reindex(order)
    ax = axes[0]
    xs = np.arange(len(order))
    ax.bar(xs, means, color=[colors[k] for k in order], alpha=.8, width=.64)
    for ix, kind in enumerate(order):
        vals = group[group.variant.eq(kind)].sort_values("fold").macro_f1.to_numpy()
        ax.scatter(ix + np.linspace(-.13, .13, len(vals)), vals, s=22, color="#182330", zorder=3)
        ax.text(ix, max(vals) + .012, f"{means[kind]:.4f}", ha="center", fontsize=10)
    ax.set_xticks(xs, [labels[k].replace(" ", "\n", 1) for k in order], fontsize=10)
    ax.set(ylim=(0, max(.63, float(group.macro_f1.max()) + .07)), ylabel="Macro-F1",
           title="Mean across 3 participant folds")
    ax.text(.02, .96, "Dots: individual folds", transform=ax.transAxes, va="top", fontsize=9)
    ax = axes[1]
    temporal = frame[frame.evaluation.eq("temporal")].pivot(index="fold", columns="variant", values="macro_f1")
    for ix, kind in enumerate(("exclude", "downweight")):
        diffs = temporal[kind] - temporal.control
        pos = np.arange(len(temporal)) + (ix - .5) * .32
        ax.bar(pos, diffs, width=.30, color=colors[kind], label=labels[kind])
        for x, value in zip(pos, diffs):
            ax.annotate(f"{value:+.4f}", (x, value), ha="center",
                        xytext=(0, 5 if value >= 0 else -13), textcoords="offset points", fontsize=9)
    ax.axhline(0, color="#333333", lw=1)
    ax.set_xticks(np.arange(len(temporal)), ["Evaluate days 32–45", "Evaluate days 47–60"], fontsize=10)
    ax.set(ylabel="Macro-F1 difference from unchanged", title="Forward-time evaluations")
    ax.margins(y=.30)
    ax.legend(fontsize=9, loc="best")
    notes = (
        "Filtering/weighting affects fitting rows only. All held-out rows, including anomalies, remain in every evaluation.\n"
        "Flag rule: any of four baseline-relative features has |robust z| > 4.5; median/MAD learned on fitting rows only.\n"
        "No target labels were altered; no validation/test partition was opened; the official model was not replaced.\n\n"
        "This is a sensitivity study on a reused synthetic development cohort, not independent or clinical validation.\n"
        "A small score increase would not establish that flagged records are errors. See RESULTS.txt for the decision."
    )
    fig.text(.08, .22, notes, fontsize=10, va="top", linespacing=1.5)
    return fig


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    figures = [("noise_audit", audit_figure())]
    if (OUT / "verified_comparison.csv").exists():
        figures.append(("noise_experiment", experiment_figure()))
    with PdfPages(OUT / "ASTRA_SHIELD_noise_review.pdf") as pdf:
        for name, fig in figures:
            fig.savefig(OUT / f"{name}.png", facecolor="white")
            pdf.savefig(fig, facecolor="white")
            plt.close(fig)
    print(f"Wrote {len(figures)} page(s) to {OUT / 'ASTRA_SHIELD_noise_review.pdf'}")
