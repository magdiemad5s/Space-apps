#!/usr/bin/env python3
"""Render frozen experiment results; never fit or score an estimator."""
from pathlib import Path
import hashlib
import json
import os
import tempfile
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
OUT = HERE / "reports"


def read(name):
    return json.loads((HERE / name).read_text())


def main():
    OUT.mkdir(exist_ok=True)
    cv = read("training/CV_REPORT.json")
    validation = read("training/VALIDATION_REPORT.json")
    test = read("training/TEST_REPORT.json")
    control = test["primary_control"]
    selected = test["selected_rf_extension"]
    interval = test["paired_participant_bootstrap"]["macro_f1_difference_percentile_95ci"]
    preservation = read("ORIGINAL_PRESERVATION.json")
    ai = HERE.parents[1]
    hashes = {name: hashlib.sha256((ai / name).read_bytes()).hexdigest() == expected
              for name, expected in preservation["sha256"].items()}
    if not all(hashes.values()):
        raise RuntimeError("Original preservation check failed: " + repr(hashes))
    (OUT / "ORIGINAL_PRESERVATION_AFTER.json").write_text(json.dumps({
        "all_unchanged": True, "files_checked": len(hashes), "checks": hashes,
        "scope": "Original data files and serving bundle compared with pre-experiment hashes"
    }, indent=2) + "\n")

    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "astra006mpl"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    names = ["rf_26_control", "rf_28_questionnaires", "rf_31_sleep", "rf_33_combined",
             "xgb_26_control", "xgb_33_combined", "current_custom_fatigue_persistence"]
    labels = ["RF: original 26", "RF: +2 questionnaire proxies", "RF: +5 sleep features",
              "RF: all 33", "XGB: original 26", "XGB: all 33", "Current-fatigue persistence"]
    values = {r["candidate"]: r["mean_macro_f1"] for r in cv["mean_fold_metrics"]}
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(9, 4.8), layout="constrained")
    ax.barh(labels, [values[n] for n in names], color=["#247d91" if n != selected else "#d2a034" for n in names])
    ax.invert_yaxis()
    ax.set(xlim=(0, .65), xlabel="Mean participant-fold Macro-F1 (3 folds)",
           title="TRAIN-only selection on fresh simulated participants")
    for i, n in enumerate(names):
        ax.text(values[n] + .008, i, f"{values[n]:.4f}", va="center")
    fig.savefig(OUT / "cv_comparison.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5), layout="constrained")
    for ax, name, title in zip(axes, [control, selected], ["RF26 control", "RF28 selected extension"]):
        cm = np.asarray(test["metrics"][name]["confusion_matrix"])
        ax.imshow(cm, cmap="Blues", vmin=0, vmax=800)
        ax.set(xticks=range(3), yticks=range(3), xticklabels=["Low", "Moderate", "High"],
               yticklabels=["Low", "Moderate", "High"], xlabel="Predicted", ylabel="Simulated target", title=title)
        for i in range(3):
            for j in range(3):
                ax.text(j, i, str(cm[i, j]), ha="center", va="center", color="white" if cm[i, j] > 400 else "black")
    fig.suptitle("Fresh test: the same 1,080 observations / 18 virtual participants")
    fig.savefig(OUT / "test_confusion_matrices.png", dpi=170)
    plt.close(fig)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BodySmall", fontName="Helvetica", fontSize=9.2, leading=12.8, spaceAfter=8))
    styles["Title"].fontSize = 20
    story = []
    def p(text, style="BodySmall"):
        story.append(Paragraph(text, styles[style]))
    def pic(name, width=495):
        from PIL import Image as PILImage
        path = OUT / name
        with PILImage.open(path) as im:
            w, h = im.size
        story.append(Image(str(path), width=width, height=width*h/w))
        story.append(Spacer(1, 10))
    def table(rows, widths):
        t = Table(rows, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173e51")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#eef4f6"), colors.white]),
            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(t)
        story.append(Spacer(1, 12))

    p("ASTRA-SHIELD: measurement experiment 006", "Title")
    p("15 November 2026 | Synthetic research prototype | Original model retained")
    p("<b>Decision: keep the current demo baseline.</b> Two extra simulated questionnaire-range scores won training cross-validation, but did not improve validation or fresh test performance. None of the experimental models was deployed.")
    rows = [["Evaluation", "RF26 control", "RF28 extension", "Change"]]
    rows.append(["TRAIN CV mean", f"{values[control]:.4f}", f"{values[selected]:.4f}", f"{values[selected]-values[control]:+.4f}"])
    for label, report in [("Validation", validation), ("Fresh test", test)]:
        a, b = report["metrics"][control]["macro_f1"], report["metrics"][selected]["macro_f1"]
        rows.append([label, f"{a:.4f}", f"{b:.4f}", f"{b-a:+.4f}"])
    table(rows, [165, 110, 110, 110])
    p(f"All table scores are <b>Macro-F1, not accuracy</b>. The test improvement interval is [{interval[0]:+.4f}, {interval[1]:+.4f}] from 2,000 paired whole-participant bootstrap resamples. It includes zero; the prespecified improvement conditions failed.")
    a, b = test["metrics"][control], test["metrics"][selected]
    p(f"Test High-class recall: {a['high_recall']:.1%} versus {b['high_recall']:.1%}. High-class precision: {a['high_precision']:.1%} versus {b['high_precision']:.1%}. These modest values describe a simulator and do not establish safe human monitoring.")
    p("<b>What was tested.</b> A fresh cohort of 120 virtual people, 60 main days each: 7,200 rows. The same people never cross train / validation / test (84 / 18 / 18 people; 5,040 / 1,080 / 1,080 rows). The outcome remains tomorrow's custom synthetic fatigue category, not a questionnaire diagnosis.")
    p("The RF26 control was retrained on this fresh cohort using the original recipe. Its scores are not directly comparable with the historical cohort's 0.5273. The live service still uses its original saved bundle.")
    p(f"<b>Compute.</b> CPU training in the managed workspace, two estimator threads. Cross-validation plus final fitting: {cv['elapsed_seconds']:.1f}s. Validation: {validation['elapsed_seconds']:.1f}s. Test plus bootstrap: {test['elapsed_seconds']:.1f}s. Data generation, EDA and review are additional work.")
    story.append(PageBreak())

    p("What the comparison showed", "Title")
    pic("cv_comparison.png")
    p("The 28-feature variant added two independent noisy views of current simulated fatigue. Adding five sleep features alone was nearly neutral in training CV; adding all seven fields did not beat the 28-feature variant. The winner was frozen before opening validation and test outcomes.")
    pic("test_confusion_matrices.png")
    p("The confusion matrices show continuing errors across all classes. Persistence (reusing today's custom fatigue category) achieved test Macro-F1 " + f"{test['metrics']['current_custom_fatigue_persistence']['macro_f1']:.4f}. " + "The secondary XGBoost comparison also did not support the additions on fresh test: " + f"{test['metrics']['xgb_26_control']['macro_f1']:.4f} to {test['metrics']['xgb_33_combined']['macro_f1']:.4f}.")
    story.append(PageBreak())

    p("Visual EDA completed before fitting", "Title")
    pic("eda/questionnaires_and_target.png")
    p("The Moderate target dominates the training set (3,290 / 5,040 rows). Both simulated ordinal scores cover their full ranges, with fewer observations at the extremes. Macro-F1 and class-specific recall were retained to expose minority-class errors.")
    pic("eda/sleep_extension_distributions.png")
    p("The zero-nap mass and two time-awake modes come from the declared simulation schedule. WASO has a zero mass when no awakenings are generated. These are design artifacts, not findings about actual astronauts. No rows were deleted and no noise settings were tuned after seeing results.")
    story.append(PageBreak())

    p("What this experiment can and cannot establish", "Title")
    pic("eda/extension_correlations.png", width=345)
    p("<b>Interpretation.</b> Main sleep and total 24-hour sleep largely repeat information; nap duration strongly changes the derived time-awake value. The extra questionnaire-range scores share the same simulated latent fatigue process as the target. Their assumed information content is not evidence that real KSS or Samn-Perelli responses will improve this model.")
    p("<b>Measurements remain hypothetical.</b> No real questionnaire responses, wearable readings, timed PVT, Flanker responses or NASA participant records were added. Nap timing was allocated consistently, but naps were not assigned a restorative effect in the unchanged target generator. NASA and CSA pages provide project context, not the simulator's coefficients or clinical approval.")
    p("<b>Checks and sequence.</b> Frozen plan and simulation assumptions; 27 generation check groups; 15 training-only EDA checks; recorded visual review; grouped training CV; frozen selection; validation once; fresh test once. All 17 recorded original data/model hashes remain unchanged. Only 18 participants inform the test interval, and it is conditional on one synthetic scenario.")
    p("<b>Use the files.</b> README.md explains reproduction. data/main.csv is the separate experimental dataset; training/feature_contract.json defines allowed inputs. training/TEST_REPORT.json contains complete class metrics, uncertainty and decisions. The separately uploaded Clinical Alert Algorithm PDF is a proposed current-alert specification and was not implemented or validated by this experiment.")
    p("<b>Resource provenance.</b> NASA HRP Hazards, Risks, Ongoing Research, Standard Measures and ARCHER; CSA radiation monitoring and ISS science context. URLs and purpose are in NASA_AND_PARTNER_RESOURCES.csv. See data/DATA_CARD.md for the exact synthetic feature definitions.")

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#576571"))
        canvas.drawString(48, 27, "ASTRA-SHIELD | Experiment 006 | Synthetic evidence; no clinical validation")
        canvas.drawRightString(A4[0]-48, 27, str(doc.page))
    pdf = OUT / "ASTRA_SHIELD_Experiment_006.pdf"
    SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=48, rightMargin=48,
                      topMargin=38, bottomMargin=45, title="ASTRA-SHIELD Experiment 006",
                      author="ASTRA-SHIELD team").build(story, onFirstPage=footer, onLaterPages=footer)
    print(pdf)


if __name__ == "__main__":
    main()
