"""Produce a training-only visual EDA handout with actual graphs and decisions.

No validation/test observations or model predictions are loaded by this script.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "astra-visual-eda-mpl"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "astra-visual-eda-cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/visual_eda"
NAVY = colors.HexColor("#17324d")
TEAL = colors.HexColor("#087e8b")
GRAY = colors.HexColor("#4b5b6c")
LIGHT = colors.HexColor("#edf4f7")
FONT_ROOT = Path(matplotlib.get_data_path()) / "fonts/ttf"
pdfmetrics.registerFont(TTFont("ASsans", str(FONT_ROOT / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("ASsans-Bold", str(FONT_ROOT / "DejaVuSans-Bold.ttf")))
W, H = landscape(A4)
M = 40


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def draw_paragraph(c, text, x, y, width=W-2*M, size=10, leading=14, color=GRAY):
    c.setFont("ASsans", size)
    c.setFillColor(color)
    words = text.split()
    line = ""
    lines = []
    for word in words:
        proposed = (line + " " + word).strip()
        if c.stringWidth(proposed, "ASsans", size) > width and line:
            lines.append(line)
            line = word
        else:
            line = proposed
    if line:
        lines.append(line)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def start_page(c, page, title, subtitle):
    c.setFillColor(NAVY)
    c.rect(0, H-85, W, 85, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("ASsans-Bold", 22)
    c.drawString(M, H-36, title)
    c.setFont("ASsans", 10)
    c.drawString(M, H-60, subtitle)
    c.setFillColor(GRAY)
    c.setFont("ASsans", 8)
    c.drawString(M, 19, "ASTRA-SHIELD | Original longitudinal synthetic dataset | Training observations only")
    c.drawRightString(W-M, 19, f"{page} / 6")
    return H-112


def image_fit(c, path, x, y, width, height):
    with PILImage.open(path) as im:
        iw, ih = im.size
    scale = min(width/iw, height/ih)
    dw, dh = iw*scale, ih*scale
    c.drawImage(ImageReader(str(path)), x+(width-dw)/2, y+(height-dh)/2, dw, dh, preserveAspectRatio=True)


def box(c, x, top, width, height, title, body):
    c.setFillColor(LIGHT)
    c.roundRect(x, top-height, width, height, 7, fill=1, stroke=0)
    c.setFillColor(TEAL)
    c.setFont("ASsans-Bold", 12)
    c.drawString(x+12, top-22, title)
    draw_paragraph(c, body, x+12, top-42, width-24, 9.5, 13)


def longitudinal_plot(frame):
    selected = sorted(frame.participant_id.unique())[:3]
    fig, axes = plt.subplots(2, 3, figsize=(14.5, 7.2), sharex=True, sharey="row")
    for col, pid in enumerate(selected):
        part = frame.loc[frame.participant_id.eq(pid) & frame.mission_day.le(30)].sort_values("mission_day")
        axes[0, col].plot(part.mission_day, part.sleep_duration_hours, color="#087e8b", lw=1.8, marker="o", markersize=3, label="Latest sleep")
        axes[0, col].axhline(part.baseline_sleep_duration_hours.iloc[0], color="#566b7f", ls="--", lw=1.2, label="Fixed earlier calibration mean")
        axes[1, col].plot(part.mission_day, part.self_report_fatigue_score, color="#c2663c", lw=1.8, marker="o", markersize=3, label="Current custom fatigue")
        prior = part.self_report_fatigue_score.shift(1).rolling(3).mean()
        axes[1, col].plot(part.mission_day, prior, color="#566b7f", ls="--", lw=1.2, label="Previous 3 days (descriptive)")
        axes[0, col].set_title(pid, fontsize=12, weight="bold")
        axes[0, col].set_ylim(3, 10)
        axes[1, col].set_ylim(0, 10)
        axes[1, col].set_xlabel("Simulation mission day")
        for row in range(2):
            axes[row, col].grid(alpha=.2)
            axes[row, col].set_xlim(1, 30)
            axes[row, col].spines[["top", "right"]].set_visible(False)
    axes[0, 0].set_ylabel("Sleep duration (hours)")
    axes[1, 0].set_ylabel("Current fatigue (custom 0-10)")
    axes[0, 0].legend(fontsize=8, loc="lower left")
    axes[1, 0].legend(fontsize=8, loc="lower left")
    fig.suptitle("Daily patterns within virtual participants", fontsize=17, weight="bold", y=.99)
    fig.text(.5, .012, "First three training IDs in lexical order; days 1-30. No selection by outcomes. These are simulation patterns, not clinical observations.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .95))
    destination = OUT / "training_longitudinal_patterns.png"
    fig.savefig(destination, dpi=180, facecolor="white")
    plt.close(fig)
    return selected, destination


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    train_path = ROOT / "data/train.csv"
    frame = pd.read_csv(train_path)
    assert frame.split.eq("train").all() and frame.is_synthetic.eq(1).all()
    assert len(frame)==5040 and frame.participant_id.nunique()==84
    audit = json.loads((ROOT / "reports/eda/data_quality_summary.json").read_text())
    assert audit["train_sha256"]==sha256(train_path)
    assert audit["all_checks_passed"]
    decisions = json.loads((ROOT / "experimental/eda_first_001/FEATURE_DECISIONS.json").read_text())
    selected_ids, trend = longitudinal_plot(frame)
    pdf = OUT / "ASTRA_SHIELD_visual_EDA.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(W,H))
    c.setTitle("ASTRA-SHIELD: Visual Exploratory Data Analysis")
    c.setAuthor("ASTRA-SHIELD project data review")

    y=start_page(c,1,"Visual exploratory data analysis","The graphs, what they show, and the decisions they support")
    box(c,M,y,235,108,"5,040 training records","84 virtual participants x 60 daily observations. The separate 3,000-row V2 upload is not used in this report.")
    box(c,M+253,y,235,108,"41 quality checks passed","Zero missing/non-finite cells, exact duplicate rows, duplicate participant-day keys or failed engineering input/time-budget checks.")
    box(c,M+506,y,235,108,"26 model predictors","20 other source columns are excluded from the primary model, with individual reasons. Metadata remains available for auditing.")
    y-=138
    c.setFont("ASsans-Bold",15);c.setFillColor(NAVY);c.drawString(M,y,"Cleaning does not have a required deletion percentage")
    y=draw_paragraph(c,"A dataset is not required to shrink from 3,000 records to fewer than 2,000. Remove a record only when a documented problem justifies that action. Missing values may be handled without removing rows; redundant variables may be excluded as columns. No rows required deletion in this already prepared synthetic training partition.",M,y-23,size=11,leading=16)
    y=draw_paragraph(c,"Repeated participant IDs on different days are intentional longitudinal observations. Removing them would destroy the histories needed for personal baselines and trends. Rare physiological values also need investigation before removal: some simulator tails are deliberate test scenarios.",M,y-17,size=11,leading=16)
    y=draw_paragraph(c,"Scope: only data/train.csv is read for these visuals. No validation/test observations or model predictions are used. Passing engineering consistency checks does not establish clinical validity or prove that generated distributions reproduce astronaut physiology.",M,y-17,size=10,leading=14)
    c.setFont("ASsans",7);c.drawString(M,43,"Training source SHA-256: "+sha256(train_path));c.showPage()

    y=start_page(c,2,"1. Category balance","The dominant category makes raw accuracy an incomplete model-selection measure")
    image_fit(c,ROOT/"reports/eda/training_class_distribution.png",M,170,W-2*M,H-290)
    y=draw_paragraph(c,"Observed: Low 1,079 (21.41%); Moderate 3,411 (67.68%); High 550 (10.91%). Predicting Moderate for every training record would already give 67.68% accuracy.",M,142,size=11,leading=15)
    draw_paragraph(c,"Decision: compare candidates using Macro-F1 and report each category's precision/recall. Use training-only class weights, preserve participant partitions and compare with majority/persistence baselines. These labels come from custom simulator score thresholds, not medical risk cutoffs.",M,y-12,size=10.5,leading=15);c.showPage()

    y=start_page(c,3,"2. Measurement distributions","Examine ranges, skew and tails before changing or discarding measurements")
    image_fit(c,ROOT/"reports/eda/training_feature_distributions.png",M,140,W-2*M,H-250)
    y=draw_paragraph(c,"The plotted sleep, HR, RMSSD, reaction-time and self-report distributions show bounded simulator variation. HR has a visible right tail. A non-Gaussian distribution is not automatically a data error; tree models do not require normally distributed inputs.",M,116,size=10.5,leading=14)
    draw_paragraph(c,"Decision: retain rows passing documented checks. Do not clip tails just to make plots smoother. Preserve units and explicit measurement definitions. These shapes characterize the simulator, not a measured astronaut population.",M,y-10,size=10.5,leading=14);c.showPage()

    y=start_page(c,4,"3. Predictor correlations","Correlation identifies representation overlap; it does not prove medical relevance")
    image_fit(c,ROOT/"reports/eda/numeric_correlation_heatmap.png",M,145,W-2*M,H-250)
    y=draw_paragraph(c,"Two pairs have |Pearson r| >= 0.85: sleep duration vs sleep change from baseline (r=0.920), and fixed HR baseline vs prior-three-day HR mean (r=0.893). Several correlated blocks are intentional current/baseline/history features.",M,117,size=10.5,leading=14)
    draw_paragraph(c,"Decision: prespecify a reduced personalized feature representation as a comparison, while retaining the full 26-feature candidate. Do not assume correlation proves irrelevance. Correlated features can share SHAP/permutation attribution.",M,y-10,size=10.5,leading=14);c.showPage()

    y=start_page(c,5,"4. Longitudinal patterns","Look within participants; repeated observations are not independent new people")
    image_fit(c,trend,M,135,W-2*M,H-245)
    y=draw_paragraph(c,"These are the first three training IDs in lexical order, not participants chosen for a striking pattern: "+", ".join(selected_ids)+". Solid lines are current observations. Dashed lines show an earlier fixed sleep baseline or a descriptive previous-three-day fatigue mean.",M,113,size=10.5,leading=14)
    draw_paragraph(c,"Decision: use earlier calibration and past-only summaries, preserve participant-group splits, and distinguish observed day-to-day variation from a forecast. This small deterministic display does not establish an overall mission trend or a causal sleep-fatigue relationship.",M,y-10,size=10.5,leading=14);c.showPage()

    y=start_page(c,6,"5. Feature and pipeline decisions","Record the decisions before the next candidate fitting step")
    full=decisions["feature_sets"]["full_26"]; reduced=decisions["feature_sets"]["personalized_reduced"]
    removed=[f for f in full if f not in reduced]
    box(c,M,y,354,126,"Candidate A: 26 predictors","Retain the existing current measurements, fixed baselines, baseline changes and past-only means. Useful history is preserved; correlated representations are acknowledged.")
    box(c,M+375,y,354,126,"Candidate B: 17 predictors","Retain absolute sleep, its calibration/history, behavior, work context, HR/RMSSD changes and relative reaction-time change. This is a prespecified sensitivity hypothesis.")
    y-=154
    c.setFont("ASsans-Bold",12);c.setFillColor(NAVY);c.drawString(M,y,"Nine columns excluded only from the reduced candidate")
    left=removed[:5];right=removed[5:]
    for col,fields in enumerate([left,right]):
        yy=y-24
        for field in fields:
            c.setFont("ASsans",8.8);c.setFillColor(GRAY);c.drawString(M+col*375,yy,field);yy-=17
    y-=129
    y=draw_paragraph(c,"The relative features already exist and were verified as causal: fixed means use seven earlier calibration days, and history means use t-3, t-2 and t-1. Reduced predictor count does not eliminate the earlier baseline measurements needed to calculate those changes.",M,y,size=10.5,leading=14)
    y=draw_paragraph(c,"Next comparison: freeze this review and the exact feature lists, then fit Random Forest and XGBoost on training data and select using validation Macro-F1. The previous test cohort remains historical evidence, not a fresh unseen test for a revision. The completed follow-up records are in experimental/eda_first_001/.",M,y-11,size=10.5,leading=14)
    draw_paragraph(c,"Chronology is documented honestly: the first baseline run preceded the standalone EDA report; the follow-up graph review and feature-decision record preceded its new fits. This PDF makes the actual visuals easy to review and does not rewrite that history.",M,y-11,size=10,leading=14)
    c.save()
    manifest={"pdf":str(pdf.relative_to(ROOT)),"pdf_sha256":sha256(pdf),"pages":6,"observation_files_read":["data/train.csv"],"train_rows":len(frame),"training_virtual_participants":frame.participant_id.nunique(),"train_sha256":sha256(train_path),"trend_selection":{"rule":"first three training IDs in lexical order; days 1-30","participants":selected_ids,"current_measurements_only":True},"no_validation_or_test_observations_loaded":True,"clinical_validation":False}
    (OUT/"visual_report_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps(manifest,indent=2))


if __name__=="__main__":
    main()
