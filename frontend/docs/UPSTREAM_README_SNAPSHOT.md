# Crew Health Console

A web app where an astronaut records 15 daily health measurements, sees them next to their own baseline, gets a
**next-day fatigue forecast with the model's reasons**, and learns how to measure each value and when to contact the
flight surgeon.

Built for the **NASA Space Apps Challenge 2026**, challenge *"Create Health Monitoring Software for Astronauts on Space
Missions"*. It is the front end of the team's ASTRA-SHIELD system (dashboard + backend + AI model).

![Overview screen](docs/overview.jpg)

> **Honest status.** This is a hackathon prototype. The AI model is trained on **synthetic data** only (simulated
> participants), the forecast is a *prototype severity index*, and nothing here is a medical diagnosis or validated
> astronaut-health tool. Details in [Limits](#limits-read-this).

**Stack:** Angular 22 (standalone components, signals) · Ionic 9 · TypeScript · plain SVG charts (no chart library).

---

## Contents

1. [What you can do in the app](#what-you-can-do-in-the-app)
2. [How the system fits together](#how-the-system-fits-together)
3. [Quick start: just the dashboard (demo mode)](#quick-start-just-the-dashboard-demo-mode)
4. [Run the whole system (dashboard + backend + AI model)](#run-the-whole-system-dashboard--backend--ai-model)
5. [Using the app](#using-the-app)
6. [Settings](#settings)
7. [Data contract](#data-contract)
8. [Color levels and where they come from](#color-levels-and-where-they-come-from)
9. [Project structure](#project-structure)
10. [Commands](#commands)
11. [Troubleshooting](#troubleshooting)
12. [Limits (read this)](#limits-read-this)
13. [NASA data, references and credits](#nasa-data-references-and-credits)
14. [Use of SI (AI tools)](#use-of-si-ai-tools)

---

## What you can do in the app

| Screen | What it does |
|---|---|
| **Overview** | Pick any daily record. On top, the **next-day forecast**: category, 0–100 index, the model's class probabilities and the index over past records (or the calibration progress before record 8). Below, five groups of measurements (sleep, heart, reaction & attention, self-report, workload). A strip and a dot timeline move between records. |
| **Body map** | An astronaut figure with four clickable points (sleep & alertness, mood & stress, heart, next-day fatigue). Each opens a card with the values, what that body part does, the linked NASA HRP risk and a link to the Guide. |
| **Check-in** | Add today's record: 15 measurements, prefilled from the previous record. A built-in **reaction test** (60 taps, or a 10-tap quick demo) fills the median reaction time and the lapse count. Shows calibration progress and the next cutoff. |
| **Trends** | Chart of the forecast index or any measurement, with your baseline, watch/action lines where a level exists, and a marker where forecasts start. |
| **Guide** | How the forecast works and its limits, then for each of the 15 measurements: how to take it, why it matters in space, what each color means, where the level comes from, when to escalate, and sources. |
| **Bottom panel** | **Alerts** for measurements in their watch or action range, *Why this forecast* (the three SHAP reasons), recommendations you can tick off, and calibration progress. Collapsible. |

States the app handles: **calibration** (first 7 records, no forecast), **forecast** (from record 8), **model unavailable**
(record saved, no prediction, one-click retry), **rejected record** (invalid values or wrong day), **demo mode** (no
backend).

---

## How the system fits together

```
 Crew Health Console (this repo)         http://localhost:4200
        │  HTTP: /api/v1/health, /assess, /astronauts/:id/history
        ▼
 TypeScript backend (AI team repo)       http://localhost:3000
        │  HTTP: /health, /v1/predict
        ▼
 Python model service (AI team repo)     http://127.0.0.1:8000   (Random Forest + SHAP, synthetic training data)
```

- **This repo** is only the front end. It never computes a prediction itself.
- The **backend and the model** live in the AI team's repository:
  <https://github.com/magdiemad5s/Space-apps> (folder `ai/`). It stores the daily records, builds the personal baseline
  and calls the model.
- Without the backend the app still opens and shows **demo mode** (see below).

### The daily-record rules (set by the backend)

- **15 measurements per day**, taken before a fixed daily cutoff (the app sets it: each record is exactly 24 h after the
  previous one in UTC).
- **Records 1 to 7 = calibration.** They build a fixed personal baseline. HTTP 202, **no forecast**.
- **From record 8** every record gets a **next-day forecast**: category (Low / Moderate / High), a 0–100
  `fatigue_points` index (50·P(moderate) + 100·P(high), *not* a medical percentage), a separate 0–10 score estimate and
  three SHAP reasons.
- Gaps and duplicates are rejected (HTTP 409), invalid values too (HTTP 422).
- If the model is down the record is **still saved** without a forecast, and can be retried unchanged (it does not add a day).
  Retry before saving the next day; once a newer record exists the older one can no longer be retried.

---

## Quick start: just the dashboard (demo mode)

You need **Node.js 22.22+ or 24.15+** and npm.

```bash
git clone <this repository>
cd <folder>
npm install
npm start
```

Open <http://localhost:4200>.

With no backend running, the line under the astronaut's name reads **Simulated example records (demo mode)** and the
Check-in tab shows *Data source: Simulated demo*. The app then shows the AI team's *simulated* example
records (seven calibration days and the day-eight forecast from their own example response). New records you add are kept
only in the browser tab and get no forecast: **no prediction is ever invented by the dashboard.**

---

## Run the whole system (dashboard + backend + AI model)

You need three terminals. Ports: **8000** (model), **3000** (backend), **4200** (dashboard).

### 0. Get the AI team repository

```bash
git clone https://github.com/magdiemad5s/Space-apps.git
```

### 1. Model service (Python)

Recommended: **Python 3.12** (what the AI team used). From the `Space-apps/ai` folder:

```bash
# macOS / Linux
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn astra_shield_ml.api:app --host 127.0.0.1 --port 8000
```

```powershell
# Windows PowerShell
py -3.12 -m venv .venv ; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn astra_shield_ml.api:app --host 127.0.0.1 --port 8000
```

Check it: <http://127.0.0.1:8000/health> must answer `{"status":"ready", ...}`.

**If it answers `503 Could not load the trusted local model artifact`** (seen on Windows with Python 3.14): one unused
XGBoost comparison model inside the bundle cannot be loaded there. Use the wrapper from this repo instead; it lets only that
model fail and loads the five models that are actually used (they reproduce the AI team's own example output exactly):

```powershell
$env:ASTRA_AI_DIR = "C:\path\to\Space-apps\ai"
python <path to this repo>\scripts\serve-model.py
```

**Python 3.14 note:** the pinned `requirements.txt` asks for pandas 2.2.3, which has no Python 3.14 wheel. This worked instead:

```powershell
python -m pip install --only-binary=:all: numpy==2.3.5 "pandas>=2.3.3,<2.4" scikit-learn==1.8.0 joblib==1.5.3 fastapi pydantic uvicorn httpx shap xgboost
```

### 2. Backend (Node)

From `Space-apps/ai/integration/backend_review/proposed_backend` (use the **whole folder**). Needs Node 22+.

```bash
npm ci
# macOS / Linux
AI_SERVICE_URL=http://127.0.0.1:8000 npm start
```

```powershell
# Windows PowerShell
$env:AI_SERVICE_URL = "http://127.0.0.1:8000"
npm start
```

Check it: <http://localhost:3000/api/v1/health> must show `"ai_integration_mode":"connected_to_private_model"`.

Records are stored in `history_db_v2.json` next to the backend (set `DB_FILE` to move it). Optionally load nine simulated days
so you do not wait a week for the first forecast:

```bash
node demo.mjs        # refuses to overwrite an existing DEMO_SIM_001 history
```

Start over with `curl -X DELETE http://127.0.0.1:3000/api/v1/astronauts/DEMO_SIM_001/history`.

### 3. Dashboard

From this repo:

```bash
npm install
npm start
```

Open <http://localhost:4200>. Under the astronaut's name you should see **Records from the backend**, and in the Check-in
tab *Data source: Live backend, model ready*.

---

## Using the app

1. Open **Overview**. After `node demo.mjs` you see 9 records: 7 calibration records and two with forecasts.
2. Click the points on the astronaut to read a measurement group; use *How to read this* to jump to the Guide.
3. Go to **Check-in**. Take the **reaction test** (or click *Use these results* after a quick demo) and adjust the other fields.
   *Fill example values (simulated)* helps when there is no previous record.
4. **Save daily record.** The message tells you what happened: calibration progress, forecast ready, saved without a
   prediction (retry button appears) or not saved (and why).
5. Open **Trends** to follow any measurement, and **Guide** for definitions, color levels and when to call the flight surgeon.

---

## Settings

- **Backend address:** `http://localhost:3000/api/v1` by default. In the Check-in tab, *Data source → change* lets you
  enter another one (the page reloads), or in the browser console: `localStorage.setItem('apiBase', 'https://host/api/v1')`.
- **Astronaut id:** `DEMO_SIM_001` (the id the AI team's demo loader fills). Change with
  `localStorage.setItem('astronautId', 'DEMO_SOMETHING')`. The backend only accepts new ids that follow its own rules.

---

## Data contract

The 15 measurements, with the exact backend names, units and input bounds (engineering limits, not medical limits).
Source: the AI team's `FRONTEND_MEASUREMENTS.csv`.

| Field | Unit | Allowed range |
|---|---|---|
| `sleep_duration_hours` | h | 0.1 – 16 |
| `sleep_efficiency_pct` | % | 10 – 100 |
| `sleep_onset_delay_minutes` | min | 0 – 300 |
| `awakenings_count` | whole number | 0 – 100 |
| `sleep_midpoint_deviation_minutes` | min (negative = earlier) | −720 – 720 |
| `resting_heart_rate_bpm` | bpm | 30 – 220 |
| `hrv_rmssd_ms` | ms (RMSSD) | 1 – 300 |
| `reaction_time_median_ms` | ms (median of 60 responses) | 100 – 2000 |
| `reaction_time_lapses_count` | whole number (responses ≥ 500 ms) | 0 – 60 |
| `attention_accuracy_pct` | % | 0 – 100 |
| `self_report_stress_score` | custom 0–10 | 0 – 10 |
| `self_report_fatigue_score` | custom 0–10 | 0 – 10 |
| `self_report_mood_score` | custom 0–10 (higher = better) | 0 – 10 |
| `workload_hours` | h | 0 – 24 |
| `exercise_minutes` | min | 0 – 480 |

A request also carries `astronaut_id`, `observation_timestamp_utc` and an optional `journal_text`. The app sends numbers (not
strings), no derived values and no extra fields, as the backend requires. Sleep, workload and exercise must fit in 24 hours.

---

## Color levels and where they come from

Only some measurements have a color level; the others are shown plainly but are still sent to the model. The model itself
does **not** use these levels. They are the dashboard's own guidance and are explained in the Guide.

| Measurement | Nominal | Watch | Action | Basis |
|---|---|---|---|---|
| Sleep duration | 7 h or more | 6 – 6.9 h | under 6 h | AASM/SRS adult recommendation; under 6 h on the ISS was linked to slower responses and more stress |
| Sleep efficiency | 85% or more | 75 – 84% | under 75% | Team assumption |
| Resting heart rate | under 90 bpm | 90 – 100 bpm | over 100 bpm | Over 100 bpm is tachycardia (AHA); 90 is a team assumption |
| HRV (RMSSD) | under 20% below baseline | 20 – 34% below | 35%+ below | Compared with your own baseline (after 7 records); percentages are a team assumption |
| Reaction time (median) | under 10% above baseline | 10 – 19% above | 20%+ above | Compared with your own baseline; percentages are a team assumption |
| Stress, fatigue (0–10) | under 5 | 5 – 6.9 | 7 or more | Team assumption (custom scores, not validated questionnaires) |
| Mood (0–10) | 5 or more | 3 – 4.9 | under 3 | Team assumption |

The rules live in `src/app/lib/metrics.ts`, the Guide text in `src/app/lib/guide.ts`. Keep them in sync.

---

## Project structure

```
src/
  index.html                  page shell (fonts, SI-disclosure meta tag)
  styles.css                  all styling (colors are CSS variables at the top)
  app/
    app.ts                    root component: state, layout, saving a record, retry
    app.config.ts             Ionic setup
    types.ts                  data contract (15 measurements, records, forecast)
    data/
      source.ts               the only file that talks to the backend; falls back to demo mode
      demo-data.ts            simulated example records (generated from the AI team's examples)
    lib/
      metrics.ts              measurement definitions, bounds, groups, color rules, feature names
      guide.ts                how-to-measure text, level basis, escalation, sources
      insights.ts             recommendations built from the astronaut's own measurements
      time.ts                 small time helpers
    components/               one file per component (body map, trend chart, reaction test, check-in form, ...)
scripts/serve-model.py        starts the model service when the normal command cannot load the bundle
docs/overview.jpg             screenshot used in this README
```

Components use attribute selectors on native elements (for example `<article appMetricGroup>`) so the page keeps plain,
simple HTML.

---

## Commands

| Command | What it does |
|---|---|
| `npm install` | Install dependencies |
| `npm start` | Dev server on <http://localhost:4200> with live reload |
| `npm run build` | Production build into `dist/dashboard-angular/browser` (static files, host anywhere) |

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| *Simulated example records (demo mode)* | The backend is not reachable. Start it, or use *Data source → change* in Check-in to enter its address. |
| *Data source: Live backend, model offline* | The backend runs but the model service does not (or `AI_SERVICE_URL` is not set). Records are saved without forecasts. Start the model, then use *Retry the prediction* in Check-in. |
| Model service answers `503 ... trusted local model artifact` | See the wrapper `scripts/serve-model.py` above. |
| `pip install` hangs or compiles pandas | Use Python 3.12, or the wheel-only command for Python 3.14 above. |
| *Not saved (duplicate, out-of-order or gapped record)* | The backend wants exactly one record per 24 h cutoff, in order. Reset the participant (`DELETE .../history`) for a fresh demo. |
| *Not saved: Non-overlapping sleep opportunity, duty and exercise exceed 24 hours* | Workload, exercise and sleep add up to more than a day. Correct the values. |
| Port already in use | Another copy is running. Stop it, or change the port (`ng serve --port 4300`). |

---

## Limits (read this)

- **Synthetic data.** The model was trained on 7,200 simulated daily forecasts from 120 virtual participants. NASA resources
  informed the project background; these are **not** NASA astronaut measurements.
- **Modest accuracy, reported by the AI team:** Macro-F1 about 0.53 on their held-out test, accuracy below the majority-class
  rate, and High-fatigue recall about 46%. The forecast is a demonstration.
- **The forecast is a prototype index**, not a medical percentage, and the SHAP reasons describe the model, not the causes of fatigue.
- The first 7 records are a computational calibration, not proof of a clinically healthy baseline.
- The reaction test and the self-report scores are custom demonstrations, not validated clinical instruments.
- The backend has no login and stores records in a local file. Do not expose it to the internet as is.
- Demo mode shows simulated records only.

---

## NASA data, references and credits

NASA resources used in the guidance:

- NASA Human Research Program, *5 Hazards of Human Spaceflight*: <https://www.nasa.gov/hrp/hazards/>
- NASA Human Research Program, *Risks of Human Spaceflight*: <https://www.nasa.gov/hrp/risks/>
- NASA Spinoff 2013, Reaction Self Test (the PVT-based fatigue check used on the ISS): <https://spinoff.nasa.gov/Spinoff2013/hm_1.html>
- Reaction Self Test study with 24 astronauts on 6-month ISS missions (PMC8919197): <https://pmc.ncbi.nlm.nih.gov/articles/PMC8919197/>

Other references:

- ASTRA-SHIELD AI repository (team): <https://github.com/magdiemad5s/Space-apps>
- Barger et al. 2014, *The Lancet Neurology*, sleep in astronauts (PMC4188436): <https://pmc.ncbi.nlm.nih.gov/articles/PMC4188436/>
- AASM and Sleep Research Society 2015 consensus on adult sleep duration (PMC4434546): <https://pmc.ncbi.nlm.nih.gov/articles/PMC4434546/>
- American Heart Association, Tachycardia: <https://www.heart.org/en/health-topics/arrhythmia/about-arrhythmia/tachycardia--fast-heart-rate>
- Basner et al. 2011, brief Psychomotor Vigilance Test (PMC3197786): <https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786/>
- Libraries: Angular, Ionic (MIT), RxJS (Apache-2.0), TypeScript (Apache-2.0). Font: Manrope, Google Fonts (SIL Open Font License).

Team: the dashboard is the front-end part of the team's NASA Space Apps 2026 project; the AI model and backend were
built by teammates in the repository linked above. No NASA logos, flags or mission identifiers are used; names and data are
fictional demo data.

---

## Use of SI (AI tools)

- The dashboard code, the SVG illustrations (astronaut, silhouette, watch) and the Guide text were written with SI
  assistance (Claude, by Anthropic) from the team's idea and requirements, and reviewed by the team.
- The astronaut illustration carries a visible *SI-generated illustration* label, and the page footer and the `si-disclosure`
  meta tag in `src/index.html` state the SI use.
- The model service and backend are the AI team's work; see their repository for how SI tools were used there.
