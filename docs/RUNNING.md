# Running ASTRA-SHIELD

The same Angular/Ionic application runs on Windows and Linux in a browser. The source launcher below starts three local processes and requires Python/Node setup. The separate **[Windows bundle](../desktop/README.md)** packages those dependencies into an installer and opens the same dashboard. No GPU, cloud AI subscription, model API key, or retraining is needed.

## Windows: running from source

1. Install **Python 3.12** from <https://www.python.org/downloads/> with the Python launcher, and **Node.js 24 LTS, version 24.15 or later**, from <https://nodejs.org/>. Include npm. Keep this entire project together in a writable folder, not inside the ZIP.
2. Double-click **`Setup-Astra.cmd`** once. It creates the root `.venv`, installs `ai/requirements.txt`, and runs `npm ci` in both Node projects. Internet access is needed for dependency installation. No training runs.
3. Double-click **`Start-Demo.cmd`** for the synthetic presentation. It starts the model, backend, and dashboard, waits for their health checks, loads nine fictional daily records if the demo participant is empty, and opens <http://127.0.0.1:4200>.
4. Keep the terminal open. **Press Ctrl+C in that terminal to stop the services.** Saved history remains on disk.

Use **`Start-Astra.cmd`** to start without adding example records. The default participant is `DEMO_SIM_001`; a fresh participant needs seven daily calibration records before the eighth record can receive a forecast. Reopening a populated demo does not erase or duplicate its history.

Equivalent commands from the project root:

```powershell
.\Setup-Astra.cmd
.\Start-Demo.cmd
```

To check prerequisites without starting servers:

```powershell
.\Start-Astra.cmd --check
```

The Windows launch scripts have been reviewed, but this workspace runs Linux. **Rehearse setup, prediction, and Ctrl+C shutdown on the actual Windows laptop before presenting.** Windows-specific driver, antivirus, Python-wheel, or process-cleanup behavior has not been exercised here. Closing the terminal abruptly is not the supported shutdown procedure.

## Linux

Use a Linux distribution compatible with the pinned packages, Python **3.12 with venv support**, and Node **24.15+ LTS**. The supplied CPU XGBoost Linux wheel requires a compatible glibc system; a current Ubuntu environment is a practical choice. Install Python/venv through your distribution or an appropriate Python installer; do not use `sudo pip`.

From the repository root:

```bash
python3.12 scripts/setup.py
./start.sh --seed-demo
```

If extracting the ZIP loses the executable bit:

```bash
bash start.sh --seed-demo
```

For an already prepared Python 3.12 environment:

```bash
python3.12 scripts/start.py --python /absolute/path/to/venv/bin/python --seed-demo
```

The dependency setup uses locked npm packages and pinned Python versions. Node 22.22.3+ is also supported; the uploaded Angular toolchain accepts Node `^22.22.3 || ^24.15.0 || >=26.0.0`. Python 3.14 is not the documented runtime for this serialized model.

## What starts

| Process | Local address | Role |
|---|---|---|
| Angular/Ionic | `http://127.0.0.1:4200` | Dashboard, forms, charts, separate demo screens |
| TypeScript/Express | `http://127.0.0.1:3000/api/v1` | Validates observations, persists history, derives baseline/history inputs |
| Python/FastAPI | `http://127.0.0.1:8000` | Loads the existing model bundle and produces forecasts/SHAP |

The browser calls **`/api/v1` on its own origin**. Angular's development proxy forwards that path to the backend. The backend calls Python's **`POST /v1/predict`**. There is no `/predict` alias and no browser-to-Python integration.

The launcher checks actual model readiness, not merely an open port. It refuses occupied ports, supervises its child processes, and stops the stack if a required process exits. It does not kill unrelated applications or clear history.

## Storage, ports, and diagnostics

- History: `.local/history_db_v2.json` by default. This is the prototype's local, single-process JSON store.
- Logs: `.local/logs/<UTC timestamp>-<process id>/model.log`, `backend.log`, `frontend.log`, and optionally `demo-seed.log`.
- Environment: `.venv/`; Node dependencies are installed in each project's `node_modules/`.
- `.local`, environments, logs, and dependencies are excluded from Git and the source handoff.

Example alternate ports and isolated history:

```bash
python3.12 scripts/start.py --model-port 8100 --backend-port 3100 --frontend-port 4300 --db-file .local/another-demo.json --seed-demo --no-browser
```

Use the configured `.venv` interpreter on Windows, or pass `--python` when using an existing environment. `--demo-id DEMO_OTHER` seeds another explicitly synthetic participant. Select that same participant in the browser with `localStorage.setItem('astronautId', 'DEMO_OTHER')` and reload. A custom seed ID does not silently change browser settings.

## Presentation walkthrough

1. Run `Start-Demo.cmd` or `./start.sh --seed-demo`.
2. Confirm **Records from the backend**. The participant's `DEMO_` name and fixture documentation identify the fictional observations; live computation does not turn them into real astronaut data.
3. Inspect records 1–7: calibration, no forecast. Inspect records 8–9: actual model category, index, target time, and SHAP reasons.
4. Open Check-in and inspect the next daily cutoff. This demonstration advances a fixed daily sequence; do not misrepresent an automatically assigned future cutoff or copied values as measurements just taken.
5. Submit valid example measurements. Invalid sleep/time-budget combinations are rejected without saving.
6. Open Trends and Guide. A reaction-time quick demo is demonstration-only; it cannot populate the 60-response model fields.
7. The separate **Alert demo** uses predefined fictional current-alert states. It does not assess the selected participant or run the Clinical Alert V2 engine.

Prefilled values are copies for editing, not sensor measurements. Attention accuracy is entered manually; no complete attention-test UI is included. Our separate Flanker scoring prototype remains under `ai/integration/flanker_prototype`.

## Troubleshooting

| Problem | What to do |
|---|---|
| Setup cannot find Python or Node | Install the versions above, then reopen the terminal and run setup again. |
| Model returns a loading error | Read `model.log`; use Python 3.12 and the pinned requirements. Do not suppress XGBoost/joblib errors or substitute another model. |
| Port already in use | Stop your own old launcher with Ctrl+C, or choose three different ports. The script deliberately refuses to kill another process. |
| Backend/history unavailable | The UI shows an error and a retry choice. It does not silently replace actual history with demo fixtures. |
| Explicit offline demo selected | Return to the backend using the UI control. Offline examples are separate and are not saved to the backend. |
| Old browser settings use the wrong server | Use Change backend address and leave it empty for the same-origin default, or remove `apiBase` from local storage and reload. |
| Model outage saved a record | Restore service and retry the **latest identical observation**. Reload preserves its journal for the retry. Do not add another day first. |
| Duplicate, gap, or out-of-order record | The backend requires exact consecutive 24-hour cutoffs. Check the existing history; use a new demo participant rather than deleting history casually. |
| Demo seed stops partway | Read `demo-seed.log`. Partial history is preserved; the launcher does not overwrite or silently finish an existing participant. Use a fresh demo ID after fixing the error. |
| npm cache is unwritable | Set `npm_config_cache` to a writable local directory before setup. No system-wide npm installation is needed. |
| Frontend opens but forecasts are absent | Confirm both health checks below and check whether the participant is still calibrating. A model connection is not a substitute for valid history. |

Health checks:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:3000/api/v1/health
http://127.0.0.1:4200/api/v1/health
```

The last URL exercises the browser's API proxy. A ready model reports `status: ready`, `data_origin: synthetic`, and `clinical_validation: false`.

## Keep the web path

The Windows launcher is optional. The frontend has no Electron or Windows-only dependency. See [WEB_DEPLOYMENT.md](WEB_DEPLOYMENT.md) for independent development, static builds, and a future reverse-proxy deployment.
