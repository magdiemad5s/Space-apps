# ASTRA-SHIELD · Crew Health Console

**NASA Space Apps 2026 · local application prototype · Windows bundle and Linux/web paths**

The team's Angular/Ionic dashboard is connected to the TypeScript application backend and the existing Python model service. Record 15 daily measurements, build a personal calibration history, inspect trends, and receive a **next-day fatigue forecast with three SHAP reasons**.

The selected model is unchanged. Its training data is synthetic; NASA resources informed the project, not participant measurements. Forecasts and dashboard guidance are prototype outputs, not clinical validation or permission to perform a mission-critical task.

The Windows package uses an inference-only export of the five selected models. It excludes unused research comparisons, including an XGBoost snapshot that cannot deserialize on Windows. Selected model parameters and outputs are checked against the original; the original research artifact remains intact. See [deployment equivalence evidence](integration-reports/DEPLOYMENT_MODEL_EQUIVALENCE.json).

![Crew Health Console connected to the model, using synthetic demo observations](integration-reports/dashboard-current.png)

The teammate's dashboard design and Manrope typography are retained. Manrope is bundled locally for offline use. The added Alert demo tab, explicit connection controls, and mobile tab wrapping are documented integration changes.

## Team

ASTRA-SHIELD was designed and developed by the **Supermoon** team:

- **Mahfuoz Asa'ad Kamal Izhiman** — Team owner
- **Majdi Abu Ahour**
- **Yazan Ehmaid**
- **Karam Alhams**
- **Omar Hemadneh**
- **Taleen Abualhasan**

Names follow the team's Space Apps roster. The team contributed to the project's design, development and review; the tool-use disclosures below describe assistance within that work.

## AI/SI use, data origin, and credits

**ASTRA-SHIELD is a team-designed and team-developed project.** The team supplied the project brief, health-monitoring goals, measurement requirements, frontend design, backend work, and clinical-alert proposals, and directed the integration and development decisions. SI tools helped accelerate implementation, analysis, debugging, documentation, and testing within that work.

**OpenAI ChatGPT/Codex** assisted with Python simulation code and journal templates, the ML workflow and experiments, backend/frontend integration, error fixes, test automation, Windows packaging, and documentation. Numeric observations and labels were computed by the seeded Python simulator; they are not measured astronaut records or values supplied by NASA. The deployed predictions come from the team's selected trained ML models.

The frontend supplied by **Karam Alhams** (`Karam-Eyad` on GitHub) separately acknowledges **Claude (Anthropic)** assistance with its code, SVG artwork (astronaut, silhouette, and watch), and Guide text. That attribution is retained in the [frontend README](frontend/README.md) and [original disclosure](frontend/docs/UPSTREAM_README_SNAPSHOT.md#use-of-si-ai-tools).

The integrated app has completed **81 UI checks, 48 end-to-end integration checks, and native Windows tests of both the portable and installed executable**, including real predictions, SHAP output, and shutdown. The [verification reports](integration-reports/README.md) record the tested scope; testing and teammate feedback continue as the prototype develops. These software checks are separate from future clinical validation.

The [machine-readable provenance record](PROVENANCE.json) identifies AI-assisted code/data, artwork provenance, NASA reference roles, and remaining review items. Keep it with redistributed source or data and retain dependency licenses. AI-generated artwork needs a visible SI watermark in submission media; this README alone does not satisfy that requirement.

**For submission:** use the [guide review and suggested disclosure text](docs/SUBMISSION_DISCLOSURE.md). The uploaded guide requires a separate public demo of **up to seven slides or a video of 30 seconds or less**, plus an English submission and English linked materials (non-English video speech requires English subtitles). The Windows installer is the final software artifact, not a substitute for that submission demo. The final media, permissions, team registration and actual “Submit for Judging” action still need team review.

## Start on Windows

Download the **[Windows x64 installer (.exe)](https://github.com/magdiemad5s/Space-apps/releases/download/v0.1.1-prototype/ASTRA-SHIELD-Setup-x64.exe)** from the **[0.1.1 prototype release](https://github.com/magdiemad5s/Space-apps/releases/tag/v0.1.1-prototype)**. It includes Python, Node, and the five selected models and opens this same dashboard in your browser. The installer is unsigned.

The portable and installed executables passed native Windows checks. Follow the **[Windows instructions](desktop/README.md)** and give your tester the **[handoff checklist](docs/FRIEND_TEST_CHECKLIST.md)**; interactive rehearsal on their laptop remains necessary.

The source launcher remains available for development:

Install **Python 3.12** and **Node.js 24 LTS (24.15+)**, extract the whole project, then:

1. Double-click **[Setup-Astra.cmd](Setup-Astra.cmd)** once to install dependencies.
2. Double-click **[Start-Demo.cmd](Start-Demo.cmd)** to run the presentation with clearly synthetic history, or **[Start-Astra.cmd](Start-Astra.cmd)** to run without adding example records.
3. The dashboard opens at **<http://127.0.0.1:4200>**. Keep the terminal open; **Ctrl+C** stops the stack.

These `.cmd` files are source launchers that require setup. The optional installer is built separately under `desktop/`. The dashboard remains a web application in both cases. Rehearse the installer on the team's actual Windows laptop before presenting.

## Run on Linux

With Python 3.12/venv and Node 24.15+ installed:

```bash
python3.12 scripts/setup.py
./start.sh --seed-demo
```

Use `bash start.sh --seed-demo` if a ZIP extraction removed executable permissions. Installation needs internet; normal inference runs locally on CPU and uses no external AI API.

**[Full setup, troubleshooting, storage, and presentation instructions](docs/RUNNING.md)** · **[Web development and future hosting](docs/WEB_DEPLOYMENT.md)**

## What the teammate built and what is connected

The frontend came from **Karam Alhams's [crew-health-console](https://github.com/Karam-Eyad/crew-health-console)**, supplied as a ZIP. Its dashboard, astronaut body map, daily form, trends, guide, and reaction-time prototype are retained. [Provenance and integration decisions](docs/INTEGRATION_HANDOFF.md) distinguish that work from the integration changes.

| Area | Current scope |
|---|---|
| Overview, Check-in, Trends, Guide | Angular/Ionic application using the backend's observations and forecasts |
| Calibration | First seven consecutive daily records; no prediction during calibration |
| Day eight onward | Existing model predicts tomorrow's category/index; actual TreeSHAP reasons |
| Errors and outages | Visible failures; acknowledged observations retained; exact latest-record retry |
| Reaction task | Custom 60-response prototype; quick 10-response mode is demonstration-only |
| Attention | Manual accuracy input; separate Flanker logic exists, but no complete attention-test UI |
| Measurement warnings | Frontend's illustrative guidance; not the Clinical Alert V2 engine |
| Alert demo | Five predefined fictional current-alert scenarios, independent of participant data and model calls |
| Clinical Alert V2 | Full engine deferred; its 14 medical acceptance scenarios are **not executed** by the demo |

The current-alert demo and tomorrow's forecast are deliberately separate. A low example forecast does not remove a severe current example alert. KSS and Samn–Perelli demo values are not converted to the model's custom fatigue score or sent as extra model inputs.

## Architecture

```mermaid
flowchart LR
    START[Windows or Linux launcher] --> UI[Angular / Ionic · 4200]
    START --> API[TypeScript backend · 3000]
    START --> MODEL[Python model service · 8000]
    UI -->|same-origin /api/v1| API
    API --> HISTORY[Local daily history and fixed calibration]
    HISTORY -->|22 numeric inputs| MODEL
    MODEL -->|next-day forecast and SHAP| API
    API --> UI
```

The frontend defaults to `/api/v1`. A development proxy connects it locally; a future web host can serve the same compiled frontend and proxy that path. Python remains a private backend service. There are no Electron or Windows-only frontend dependencies.

## Demonstrate without waiting a week

`Start-Demo.cmd` or `./start.sh --seed-demo --db-file .local/demo/history_db_v2.json` loads nine **historical synthetic** observations for `DEMO_SIM_001`: seven calibration days and two model requests. The displayed predictions are computed by the actual unchanged model. Presentation launchers use separate demo storage. Existing participant history is preserved, never silently reset.

A separate, explicitly selected offline demo can display fixture examples without a backend. It is labeled as simulated, makes no new model predictions, and keeps additions only in the browser session. Connection failures do not silently switch real backend history to those fixtures.

## Project layout

```text
Setup-Astra.cmd / Start-Astra.cmd / Start-Demo.cmd
start.sh
scripts/                 Setup, supervised startup, integration checks
desktop/                 Bundled runtime, Windows installer/build, smoke tests
frontend/                Teammate's Angular/Ionic app plus integration fixes
ai/
  astra_shield_ml/        Model contract, inference and analysis code
  artifacts/             Unchanged selected model bundle
  data/                  Synthetic partitions, definitions and provenance
  integration/           TypeScript backend, client, Flanker prototype
  experimental/          Separate studies; none automatically promoted
  reports/               Evaluation, EDA and data audits
docs/                    Windows/Linux/web handoff and scope
integration-reports/     Application verification and preserved hashes
.local/                  Runtime history and logs; ignored by Git
```

## Model and research

The selected **26-feature Random Forest** has original validation **Macro-F1 0.5273** and historical test **Macro-F1 0.5285**. Macro-F1 is not accuracy. Historical High-class recall was 45.77%; results describe the simulator, not astronaut health performance. The original participant split is 70/15/15; the fatigue classifier's training partition contains 5,040 rows from 84 simulated people.

`fatigue_points` is a prototype index from classifier scores, not a medical probability. The separate regression score may disagree with the category. SHAP describes model contributions, not medical causes. The baseline, later measurement-extension study, and threshold study are documented separately; no experimental threshold or replacement model is used by this application.

- [Model setup, metrics, and input contract](ai/README.md)
- [Workflow and findings](ai/docs/FINDINGS.md)
- [Original standalone CSV](ai/data/astra_shield_synthetic_ml.csv)
- [Experimental archive](ai/experimental/README.md)
- [Frontend contract](ai/docs/FRONTEND_INTEGRATION.md)
- [Frontend details and source references](frontend/README.md)

## Verification and remaining work

The handoff includes frontend contract tests, launcher tests, and actual browser/backend/model integration checks. Results and their exact scope are recorded under [integration-reports](integration-reports/). They exercise fictional fixtures and application behavior; they do not validate medical decisions or improve the reported model accuracy.

Use the [friend's test checklist](docs/FRIEND_TEST_CHECKLIST.md) on the actual Windows laptop. Public deployment, authentication, multi-user storage, validated measurement protocols, the full clinical engine, and real human-data validation remain separate work. Nothing is published or deployed simply by running these launchers.

## NASA resources used

The submission guide permits **NASA data or a NASA resource**; it does not require us to describe simulated records as NASA data. Our use is reference-based:

| NASA resource | Use in this project |
|---|---|
| [5 Hazards of Human Spaceflight](https://www.nasa.gov/hrp/hazards/) | Human-spaceflight context for sleep, behavioral health and the dashboard's explanatory Guide. |
| [Risks of Human Spaceflight](https://www.nasa.gov/hrp/risks/) | Risk framing and references in the Guide and astronaut Body map. |
| [Ongoing HRP Research](https://www.nasa.gov/hrp/ongoing-hrp-research/) | General human-research background supplied with the challenge; no measurements imported. |
| [Standard Measures](https://www.nasa.gov/reference/standard-measures/) | Conceptual motivation for consistent, repeated personal observations, recorded in the [simulator source manifest](ai/data/source_manifest.csv). |
| [ARCHER](https://www.nasa.gov/reference/archer/) | Activity, sleep and behavioral-monitoring context recorded in that same source manifest. |
| [NASA Spinoff: Reaction Self Test](https://spinoff.nasa.gov/Spinoff2013/hm_1.html) | Motivation for the reaction-time demonstration; our 60-response task is not a validated implementation of the NASA/ISS test. |

These resources do not supply our numerical records, simulation coefficients, labels, medical cutoffs or validation. The challenge's CSA radiation and ISS science links were supplied as background resources; no CSA measurement dataset or radiation-monitoring model is used here. See [references and dependency credits](docs/SUBMISSION_DISCLOSURE.md#references-and-software-credits) for the other publications, libraries and tools. No NASA endorsement or affiliation is claimed.
