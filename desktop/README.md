# Windows application bundle

The bundle packages the **existing Angular dashboard, TypeScript backend, Python 3.12 runtime, and unchanged model**. It opens the dashboard in the default browser and keeps its local services in a console window. It does not introduce a different dashboard design or require Python, Node, npm, a GPU, or an AI API key on the tester's computer.

The deployment artifact contains the **same five selected inference models and required metadata**, with unused research baselines and comparison models omitted. The full research artifact contains an XGBoost comparison snapshot that fails to deserialize on Windows. Its original bytes remain unchanged in `ai/artifacts/bundle.joblib`; the deployment copy has a separate hash in `artifacts/inference_manifest.json`. [Equivalence checks](../integration-reports/DEPLOYMENT_MODEL_EQUIVALENCE.json) compare retained model state, predictions, and SHAP outputs. This export does not train or choose a new model.

The installer is for **Windows x64**. It is unsigned; a downloaded installer may show an unknown-publisher or SmartScreen warning. Confirm that the file came from this project's handoff and matches its published SHA-256 before running it. Follow the tester's organization policy rather than disabling security software.

## Build status and verification

The packaging source and automated Windows build are provided here. A build specification alone is not evidence that a particular executable works. Use the successful [Windows application bundle workflow](https://github.com/magdiemad5s/Space-apps/actions/workflows/windows-app.yml), its artifact, and its matching reports to identify a tested build:

- `ASTRA-SHIELD-Setup-x64.exe`: per-user installer.
- `ASTRA-SHIELD-portable-x64.zip`: the complete portable application folder.
- `SHA256SUMS.txt` and `build-manifest.json`: download checksums, versions, and model identity.
- `windows-smoke-report.json` and `installed-smoke-report.json`: checks performed against the bundled executable and the installed copy.

Native Windows build results must be checked before calling the package verified. Automated smoke checks cover application wiring and real local inference; the [friend's test checklist](../docs/FRIEND_TEST_CHECKLIST.md) covers the interactive handoff on the actual laptop. Neither is medical validation.

## Install and open

1. Download the installer and checksum from the same successful build. In PowerShell, `Get-FileHash .\ASTRA-SHIELD-Setup-x64.exe -Algorithm SHA256` displays the installer's hash.
2. Run the installer. Its default destination is `%LOCALAPPDATA%\Programs\ASTRA-SHIELD`; administrator privileges are not required. A desktop shortcut is optional.
3. Open **ASTRA-SHIELD Demo** from the Start menu. The installer also offers to open it when installation finishes.
4. Wait until the console prints **ASTRA-SHIELD is ready**. The browser opens the printed local URL, normally `http://127.0.0.1:4173`. If that port is occupied, the launcher chooses a free port.
5. Keep the console open while using the dashboard. **Ctrl+C in that console stops the app.** Closing only the browser tab does not stop the local services.

The Demo shortcut uses `--seed-demo`: it adds nine fictional observations for `DEMO_SIM_001` only if that participant has no history. Records 1–7 are calibration; records 8–9 receive forecasts from the shipped model. Relaunching preserves existing history and does not add another nine records.

The portable ZIP needs to be extracted completely. Keep `ASTRA-SHIELD.exe` beside its `_internal` folder and the other supplied files. Copying only the inner executable is insufficient. From the extracted folder, `.\ASTRA-SHIELD\ASTRA-SHIELD.exe --seed-demo` starts its presentation data; omit `--seed-demo` to start without adding examples. The installer itself is the single downloadable `.exe` that installs all of those files.

To run the installed executable without adding demonstration observations:

```powershell
& "$env:LOCALAPPDATA\Programs\ASTRA-SHIELD\ASTRA-SHIELD.exe"
```

Installation and ordinary inference require no network downloads once the complete bundle is available. All application services listen on `127.0.0.1`. This local prototype is not an authenticated public web service.

## History and diagnostics

| Item | Default Windows location |
|---|---|
| Application files | `%LOCALAPPDATA%\Programs\ASTRA-SHIELD` |
| Saved observations | `%LOCALAPPDATA%\ASTRA-SHIELD\history_db_v2.json` |
| Run diagnostics | `%LOCALAPPDATA%\ASTRA-SHIELD\logs\<UTC timestamp>-<PID>\` |

Each run records `runtime.json` and `backend.log`; startup/runtime failures can add `error.log`. The console prints the exact paths. Uninstalling the application preserves the separate history/log directory. Back it up before any intentional deletion. Use fictional data during handoff testing, and review logs/screenshots before sharing them.

Useful options:

```powershell
# Separate, disposable demonstration history; do not point at the normal store.
& "$env:LOCALAPPDATA\Programs\ASTRA-SHIELD\ASTRA-SHIELD.exe" --seed-demo --data-dir "$env:TEMP\astra-friend-demo"

# Choose an exact local browser port; fail if it is unavailable.
& "$env:LOCALAPPDATA\Programs\ASTRA-SHIELD\ASTRA-SHIELD.exe" --port 4273 --no-browser

# Exercise the actual bundled model in temporary, isolated storage, then stop.
& "$env:LOCALAPPDATA\Programs\ASTRA-SHIELD\ASTRA-SHIELD.exe" --smoke-test --report "$env:TEMP\astra-smoke-report.json"
```

Only one instance can use a data directory at a time: a second launch fails before starting services. The operating-system lock is released when the app exits; the remaining `.runtime.lock` file does not need deletion. An explicit `--data-dir` overrides the persistent store. `--smoke-test` uses an isolated temporary directory unless a data directory is explicitly supplied. `--report` requires `--smoke-test`. The smoke test submits fictional calibration observations and an eighth-day prediction, verifies actual TreeSHAP output and API status handling, then checks service shutdown. It does not train or evaluate model accuracy.

If the browser does not open, copy the printed URL. If startup fails, retain the console message and the run's log directory. If a prior browser setting points to another backend, use **Change backend address** and clear it to restore the same-origin default. Restarting does not repair invalid records or erase history.

## Build from source on Windows

The [workflow](../.github/workflows/windows-app.yml) supplies the pinned Python/Node toolchain. A manual build requires Windows x64, Python 3.12, Node 24, PowerShell, and Inno Setup 6:

```powershell
pwsh -File desktop/build_windows.ps1 -AppVersion 0.1.0
```

The script builds the production Angular assets, compiles the backend, bundles Python with PyInstaller, and produces a per-user Inno Setup installer. See the workflow and `requirements-build.txt` for the build dependencies. Build output goes under `desktop/dist/`; temporary resources go under `desktop/build/`. The workflow uploads `ASTRA-SHIELD-Windows-x64-<run_number>`, with a separate diagnostics artifact. These are generated files, not replacements for the model or source data. No training step is included.

The web frontend remains independent of this optional Windows wrapper. Linux/source-launcher instructions remain in [RUNNING.md](../docs/RUNNING.md), and the web deployment path remains in [WEB_DEPLOYMENT.md](../docs/WEB_DEPLOYMENT.md).

## Scope to preserve in the demonstration

The model was trained on synthetic data and forecasts next-day fatigue. SHAP gives model contributions, not medical causes. The five **Alert demo** presets are fictional UI examples; they do not run the full Clinical Alert V2 engine or its 14 medical acceptance cases. Attention accuracy is entered manually; a complete Flanker test is not present in the app. The quick reaction-time demo cannot fill the full model measurement fields.
