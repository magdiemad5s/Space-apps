#!/usr/bin/env python3
"""Render saved validation threshold results. Does not load or fit any model."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
COHORTS = ("original_serving_rf26", "experiment006_rf26_control")
TITLES = {
    COHORTS[0]: "Original serving RF26 / original validation cohort",
    COHORTS[1]: "Experiment 006 RF26 / separate validation cohort",
}
NAMES = {
    "baseline_argmax": "Original argmax",
    "best_high_f1_grid": "Best High F1",
    "best_macro_f1_grid": "Best Macro-F1",
    "recall_60_grid": "Recall at least 60%",
    "recall_70_grid": "Recall at least 70%",
    "recall_80_grid": "Recall at least 80%",
    "illustrative_budget_grid": "Illustrative budget",
}


def val(row, *keys, default=None):
    for key in keys:
        if key in row:
            value = row[key]
            if isinstance(value, float) and np.isnan(value):
                return default
            return value
    return default


def candidate_name(row):
    return val(row, "candidate_name", "candidate", "candidate_rule", "rule", "name", "selection_rule")


def load_cohort(root, name):
    folder = root / "results" / ("primary" if name == COHORTS[0] else "secondary")
    summary = json.loads((folder / "summary.json").read_text())
    sweep_path = folder / "allthresholdmetrics.csv"
    pr_path = folder / "PRcurve.csv"
    shortlist = pd.read_csv(folder / "shortlist.csv").to_dict("records")
    return {"name": name, "folder": folder, "summary": summary,
            "sweep": pd.read_csv(sweep_path), "pr": pd.read_csv(pr_path),
            "shortlist": {candidate_name(row): row for row in shortlist}}


def precision(row):
    return val(row, "high_precision")


def recall(row):
    return val(row, "high_recall")


def number(row, key):
    value = val(row, key)
    return None if value is None else float(value)


def fmt(value, kind="score"):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    if kind == "percent":
        return f"{float(value)*100:.1f}%"
    if kind == "count":
        return str(int(value))
    return f"{float(value):.4f}"


def plot_cohort(cohort, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    plt.rcParams.update({"font.size": 10, "axes.spines.right": False,
                         "axes.spines.top": False})
    short = cohort["shortlist"]
    baseline = short["baseline_argmax"]
    pr = cohort["pr"]
    summary = cohort["summary"]
    n = int(val(baseline, "rows", "n", "n_rows", default=1080))
    highs = int(val(baseline, "high_support", "high_count", default=val(baseline, "high_tp", default=0)+val(baseline, "high_fn", default=0)))
    prevalence = highs/n
    ap = val(summary, "average_precision", "high_average_precision", "average_precision_high")
    if ap is None:
        ap = summary.get("precision_recall", {}).get("average_precision")
    fig, ax = plt.subplots(figsize=(9, 4.2), layout="constrained")
    ax.step(pr["recall"], pr["precision"], where="post", color="#257b94",
            label=f"High-vs-rest curve; AP = {float(ap):.4f}")
    ax.axhline(prevalence, color="#858b93", linestyle="--", linewidth=1,
               label=f"High prevalence: {prevalence:.1%}")
    ax.scatter([recall(baseline)], [precision(baseline)], color="#22252c", marker="X", s=85,
               zorder=5, label="Original multiclass argmax (not a fixed threshold)")
    used = set()
    for key, color, marker in [("illustrative_budget_grid", "#c39a29", "o"),
                               ("recall_70_grid", "#b65568", "s"),
                               ("best_high_f1_grid", "#7963ad", "^")]:
        row = short.get(key)
        if row is None or precision(row) is None or val(row, "threshold") is None:
            continue
        threshold = float(row["threshold"])
        point = (threshold, recall(row), precision(row))
        if point in used:
            continue
        used.add(point)
        ax.scatter([recall(row)], [precision(row)], c=color, marker=marker, s=62,
                   zorder=6, label=f"{NAMES[key]}: t = {threshold:.2f}")
    ax.set(xlim=(0, 1.025), ylim=(0, 1.025), xlabel="High recall", ylabel="High precision",
           title=TITLES[cohort["name"]])
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.legend(fontsize=8, loc="upper right", framealpha=.94)
    fig.savefig(out / f"{cohort['name']}_precision_recall.png", dpi=180)
    plt.close(fig)

    sweep = cohort["sweep"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.7), layout="constrained")
    for key, label, color in [("high_recall", "High recall", "#257b94"),
                              ("high_precision", "High precision", "#a76630"),
                              ("high_f1", "High F1", "#8d69aa"),
                              ("macro_f1", "Macro-F1", "#328568")]:
        axes[0].plot(sweep.threshold, sweep[key], label=label, color=color, linewidth=1.8)
    axes[0].set(xlabel="High score threshold", ylabel="Score", ylim=(0, 1.02), xlim=(0, 1))
    axes[0].legend(fontsize=8)
    fp_per_100 = sweep["high_fp"] / n * 100
    predictions_per_100 = (sweep["high_tp"] + sweep["high_fp"]) / n * 100
    axes[1].plot(sweep.threshold, fp_per_100, color="#b65568", label="False High alerts")
    axes[1].plot(sweep.threshold, predictions_per_100, color="#257b94", label="All High alerts")
    axes[1].axhline(float(baseline["high_fp"])/n*100, color="#b65568", linestyle="--", alpha=.7,
                    label="Original false High alerts")
    axes[1].set(xlabel="High score threshold", ylabel="Alerts per 100 assessments", xlim=(0, 1), ylim=(0, 101))
    axes[1].legend(fontsize=8)
    fig.suptitle("Lower thresholds capture more High cases and also create more false alarms")
    fig.savefig(out / f"{cohort['name']}_threshold_tradeoffs.png", dpi=180)
    plt.close(fig)


def confusion_for(cohort, key):
    row = cohort["shortlist"][key]
    labels = ["low", "moderate", "high"]
    if all(f"cm_{actual}_as_{predicted}" in row for actual in labels for predicted in labels):
        return np.asarray([[row[f"cm_{actual}_as_{predicted}"] for predicted in labels]
                           for actual in labels], dtype=int)
    value = val(row, "confusion_matrix")
    if isinstance(value, str):
        return np.asarray(json.loads(value), dtype=int)
    if value is not None:
        return np.asarray(value, dtype=int)
    summary = cohort["summary"]
    value = summary.get("shortlist", {}).get(key) if isinstance(summary.get("shortlist"), dict) else None
    if value and "confusion_matrix" in value:
        return np.asarray(value["confusion_matrix"], dtype=int)
    csv_path = next(cohort["folder"].glob("*confusion*.csv"))
    data = pd.read_csv(csv_path)
    name_col = next(c for c in ("candidate_name", "candidate", "candidate_rule", "rule", "name", "selection_rule") if c in data)
    data = data[data[name_col] == key]
    true_col = next(c for c in ("true_label", "actual_label", "true", "actual") if c in data)
    predicted_col = next(c for c in ("predicted_label", "prediction", "predicted") if c in data)
    count_col = next(c for c in ("count", "rows", "n") if c in data)
    return data.pivot(index=true_col, columns=predicted_col, values=count_col).reindex(
        index=["low", "moderate", "high"], columns=["low", "moderate", "high"]).to_numpy(dtype=int)


def plot_confusions(cohort, out):
    import matplotlib.pyplot as plt
    keys = ["baseline_argmax", "illustrative_budget_grid", "recall_70_grid"]
    keys = [k for k in keys if k in cohort["shortlist"] and val(cohort["shortlist"][k], "available", default=True)]
    fig, axes = plt.subplots(1, len(keys), figsize=(10, 3.3), layout="constrained")
    for ax, key in zip(np.atleast_1d(axes), keys):
        matrix = confusion_for(cohort, key)
        ax.imshow(matrix, cmap="Blues", vmin=0, vmax=710)
        for i in range(3):
            for j in range(3):
                ax.text(j, i, str(matrix[i, j]), ha="center", va="center",
                        color="white" if matrix[i, j] > 355 else "black", fontsize=10)
        threshold = val(cohort["shortlist"][key], "threshold")
        title = NAMES[key] + (f"\nt = {float(threshold):.2f}" if threshold is not None else "\nno scalar threshold")
        ax.set(xticks=range(3), yticks=range(3), xticklabels=["Low", "Moderate", "High"],
               yticklabels=["Low", "Moderate", "High"], xlabel="Predicted", ylabel="Actual synthetic label", title=title)
        ax.tick_params(labelsize=8)
    fig.savefig(out / f"{cohort['name']}_confusion_matrices.png", dpi=180)
    plt.close(fig)


def render_pdf(cohorts, out):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    from PIL import Image as PILImage

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BodySmall", fontName="Helvetica", fontSize=9, leading=12.1, spaceAfter=7))
    styles["Title"].fontSize = 19
    styles["Title"].leading = 23
    story = []
    def p(text, style="BodySmall"):
        story.append(Paragraph(text, styles[style]))
    def pic(file, width=499):
        path = out / file
        with PILImage.open(path) as im:
            w, h = im.size
        story.append(Image(str(path), width=width, height=width*h/w))
        story.append(Spacer(1, 9))
    def table(cohort):
        rows = [["Decision", "t", "Recall", "Precision", "High F1", "Macro-F1", "TP", "FN", "FP"]]
        for key in NAMES:
            if key not in cohort["shortlist"]:
                continue
            r = cohort["shortlist"][key]
            rows.append([NAMES[key], "argmax" if key == "baseline_argmax" else fmt(val(r, "threshold"))[:4],
                         fmt(recall(r), "percent"), fmt(precision(r), "percent"),
                         fmt(val(r, "high_f1")), fmt(val(r, "macro_f1")),
                         fmt(val(r, "high_tp"), "count"), fmt(val(r, "high_fn"), "count"), fmt(val(r, "high_fp"), "count")])
        t = Table(rows, colWidths=[111, 38, 54, 56, 51, 61, 41, 41, 41], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173d50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#edf3f6"), colors.white])]))
        story.append(t)
        story.append(Spacer(1, 9))

    primary, secondary = cohorts
    baseline = primary["shortlist"]["baseline_argmax"]
    budget = primary["shortlist"].get("illustrative_budget_grid")
    seventy = primary["shortlist"].get("recall_70_grid")
    p("ASTRA-SHIELD: High-threshold experiment 007", "Title")
    p("15 November 2026 | Validation-only exploration | No retraining or deployment")
    p("<b>Question:</b> Can the frozen model miss fewer High-fatigue cases by changing only its decision rule? The tables expose the trade-off. No clinical false-alarm budget has been agreed, so none of these points is labelled a safe or approved operating threshold.")
    p("<b>Primary comparison:</b> the actual original serving Random Forest, on its original validation cohort: 1,080 daily observations from 18 virtual people, including 138 High labels. Every row below uses those same observations and unchanged model probabilities.")
    table(primary)
    p("TP = detected High; FN = missed High; FP = non-High labelled High. F1 and Macro-F1 are scores, not accuracy. The baseline is the original three-class argmax, <b>not a 0.5 threshold</b>. A threshold decision uses High if P(High) &gt;= t; otherwise the higher Low/Moderate score.")
    macro = primary["shortlist"].get("best_macro_f1_grid")
    if macro and val(macro, "previous_high_cases_lost", default=0):
        p(f"A net improvement can hide individual demotions: the best-Macro-F1 point t = {float(macro['threshold']):.2f} "
          f"newly detects {int(macro['additional_high_cases_detected'])} High cases but loses "
          f"{int(macro['previous_high_cases_lost'])} previously detected High case(s). Full promotion/demotion counts are in the CSV.")
    if budget and val(budget, "threshold") is not None:
        p(f"At the illustrative-budget point t = {float(budget['threshold']):.2f}, the change relative to argmax is "
          f"<b>{int(budget['high_tp'])-int(baseline['high_tp']):+d} detected High cases and "
          f"{int(budget['high_fp'])-int(baseline['high_fp']):+d} false High alerts</b>. "
          "The budget preserves baseline precision and allows at most 0.02 lower Macro-F1; these are engineering assumptions, not medical acceptance criteria.")
    if seventy:
        p(f"The at-least-70%-recall point produces {int(seventy['high_fp'])} false High alerts versus "
          f"{int(baseline['high_fp'])} originally, or {int(seventy['high_fp'])/1080*100:.1f} versus "
          f"{int(baseline['high_fp'])/1080*100:.1f} false alerts per 100 assessments. The team must judge whether this burden is useful for its intended demo workflow.")
    pic("original_serving_rf26_confusion_matrices.png")
    story.append(PageBreak())

    p("Primary validation: ranking and threshold trade-offs", "Title")
    pic("original_serving_rf26_precision_recall.png")
    p("The precision-recall curve uses every distinct High score; the threshold sweep and shortlisted points use the frozen 0.00-1.00 grid at 0.01 increments. Average precision (AP) summarizes ranking and does not choose a deployment threshold. The argmax marker can lie off this curve because it also depends on the other class scores. The final precision=1, recall=0 endpoint is a plotting convention, not measured precision with no High predictions.")
    pic("original_serving_rf26_threshold_tradeoffs.png")
    p("Precision = detected High / all High alerts. Recall = detected High / all actual High. False-positive rate uses actual non-High as its denominator; false alerts per 100 assessments use all rows. These measures are deliberately separate in the CSVs.")
    p("<b>Limits:</b> these model scores are uncalibrated and trained on synthetic labels. Both validation sets were already used for development; choosing and reporting a threshold on the same validation observations gives an optimistic exploratory estimate. The 1,080 rows are repeated observations from 18 virtual people, not 1,080 independent participants. A new independent evaluation would be needed before promoting a decision rule.")
    story.append(PageBreak())

    p("Separate check: experiment 006 control", "Title")
    p("This is the RF26 control trained on experiment 006's fresh synthetic cohort, <b>not the original serving model and not the RF28 extension</b>. Its validation cohort contains 1,080 observations from 18 virtual people, including 135 High labels. Do not combine counts or transfer a chosen threshold between the two models.")
    table(secondary)
    pic("experiment006_rf26_control_precision_recall.png")
    p("<b>Why 43.7% appears in the earlier discussion:</b> that was the already reported experiment 006 test recall: 62 of 142 High cases detected and 80 missed. It is a different cohort from either validation table here. The original serving model's previously reported test recall was 65/142 (45.8%). These historical summaries are context only; no threshold was evaluated against test observations in this experiment.")
    p("<b>Method and files:</b> model weights, features, training data and app behavior remain unchanged. The plan and input hashes were frozen before the sweep. Complete metrics for all 101 thresholds, the exact precision-recall points, candidate confusion matrices and saved validation probabilities are under results/. All candidates are proposals for review; no threshold was deployed.")
    p("The High target is tomorrow's custom synthetic fatigue category. It is not a diagnosis or an urgent current-alert level. The planned current-alert rules remain a separate system.")

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#5d6872"))
        canvas.drawString(47, 27, "ASTRA-SHIELD | Experiment 007 | Synthetic validation results only")
        canvas.drawRightString(A4[0]-47, 27, str(doc.page))
    pdf = out / "ASTRA_SHIELD_High_Threshold_Experiment_007.pdf"
    SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=46, rightMargin=46,
                      topMargin=37, bottomMargin=44, title="ASTRA-SHIELD High Threshold Experiment 007",
                      author="ASTRA-SHIELD team").build(story, onFirstPage=footer, onLaterPages=footer)
    return pdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=HERE)
    parser.add_argument("--output", type=Path, default=HERE / "reports")
    args = parser.parse_args()
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "astra007mpl"))
    args.output.mkdir(parents=True, exist_ok=True)
    cohorts = [load_cohort(args.results_root, name) for name in COHORTS]
    for cohort in cohorts:
        plot_cohort(cohort, args.output)
        plot_confusions(cohort, args.output)
    pdf = render_pdf(cohorts, args.output)
    print(pdf)


if __name__ == "__main__":
    main()
