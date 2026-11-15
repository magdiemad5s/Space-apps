# Windows application bundle

The bundle packages the **existing Angular dashboard, TypeScript backend, Python 3.12 runtime, and unchanged model**. It opens the dashboard in the default browser and keeps its local services in a console window. It does not introduce a different dashboard design or require Python, Node, npm, a GPU, or an AI API key on the tester's computer.

The deployment artifact contains the **same five selected inference models and required metadata**, with unused research baselines and comparison models omitted. The full research artifact contains an XGBoost comparison snapshot that fails to deserialize on Windows. Its original bytes remain unchanged in `ai/artifacts/bundle.joblib`; the deployment copy has a separate hash in `artifacts/inference_manifest.json`. [Equivalence checks](../integration-reports/DEPLOYMENT_MODEL_EQUIVALENCE.json) compare retained model state, predictions, and SHAP outputs. This export does not train or choose a new model.

The installer is for **Windows x64**. It is unsigned; a downloaded installer may show an unknown-publisher or SmartScreen warning. Confirm that the file came from this project's handoff and matches its published SHA-256 before running it. Follow the tester's organization policy rather than disabling security software.

## Build status and verification

**Version 0.1.2 passed native Windows checks in [build 6](https://github.com/magdiemad5s/Space-apps/actions/runs/43726368621)**, from commit `34f513aed953c0aaa9ca63611334e99457d52065`. Download the [installer and matching evidence](https://github.com/magdiemad5s/Space-apps/releases/tag/v0.1.2-prototype). This version embeds visible SI-generation labels directly in the astronaut and watch SVG artwork. It retains the existing measurement workflow and separate demo storage.

Both the portable and installed executables passed **19 checks each**, including actual prediction, TreeSHAP and shutdown. Six original reference responses matched on Windows. Installation/uninstallation and an installation path containing spaces were exercised. The build also passed 30 frontend and 16 backend tests. The packaged frontend was byte-identical to the production UI used for the 28 rendered-artwork checks, and both visible SVG text nodes were verified inside the portable bundle. See [verification metadata](../integration-reports/windows-build-6/verification.json). Earlier 0.1.0 and 0.1.1 releases remain available as historical evidence; use 0.1.2 for the embedded artwork labels.

The release contains:

- `ASTRA-SHIELD-Setup-x64.exe`: per-user installer.
- `ASTRA-SHIELD-portable-x64.zip`: the complete portable application folder.
- `SHA256SUMS.txt` and `build-manifest.json`: download checksums, versions, and model identity.
- `windows-smoke-report.json`, `installed-smoke-report.json`, and `windows-model-equivalence-report.json`: native runtime and numerical portability checks.

Checksums were verified after downloading the CI artifact. Automated checks cover application wiring and real local inference on a Windows runner; the [friend's test checklist](../docs/FRIEND_TEST_CHECKLIST.md) covers interactive use on the actual laptop. Windows browser interaction on that laptop is not established by the automated executable tests. Neither is medical validation.

## Install and open

1. Download the installer and checksum from the same successful build. In PowerShell, `Get-FileHash .\ASTRA-SHIELD-Setup-x64.exe -Algorithm SHA256` displays the installer's hash.
2. Run the installer. Its default destination is `%LOCALAPPDATA%\Programs\ASTRA-SHIELD`; administrator privileges are not required. A desktop shortcut is optional.
3. Open **ASTRA-SHIELD Demo** from the Start menu. The installer also offers to open it when installation finishes.
4. Wait until the console prints **ASTRA-SHIELD is ready**. The browser opens the printed local URL, normally `http://127.0.0.1:4173`. If that port is occupied, the launcher chooses a free port.
5. Keep the console open while using the dashboard. **Ctrl+C in that console stops the app.** Closing only the browser tab does not stop the local services.

The 0.1.2 Demo shortcut and post-install launch use `--seed-demo --data-dir "%LOCALAPPDATA%\ASTRA-SHIELD\demo"`. They add nine fictional observations for `DEMO_SIM_001` only if that participant has no history in this separate demo store. Records 1–7 are calibration; records 8–9 receive forecasts from the shipped model. Relaunching preserves existing demo history and does not add another nine records. Normal startup retains its original default store; earlier records are not migrated or deleted automatically.

The portable ZIP needs to be extracted completely. Keep `ASTRA-SHIELD.exe` beside its `_internal` folder and the other supplied files. Copying only the inner executable is insufficient. From the extracted folder, start its presentation with a separate store:

```powershell
.\ASTRA-SHIELD\ASTRA-SHIELD.exe --seed-demo --data-dir "$env:LOCALAPPDATA\ASTRA-SHIELD\demo"
```

The installer itself is the single downloadable `.exe` that installs all of those files.

To run the installed executable without adding demonstration observations:

```powershell
& "$env:LOCALAPPDATA\Programs\ASTRA-SHIELD\ASTRA-SHIELD.exe"
```

Installation and ordinary inference require no network downloads once the complete bundle is available. All application services listen on `127.0.0.1`. This local prototype is not an authenticated public web service.

## History and diagnostics

| Item | Default Windows location |
|---|---|
| Application files | `%LOCALAPPDATA%\Programs\ASTRA-SHIELD` |
| Normal saved observations | `%LOCALAPPDATA%\ASTRA-SHIELD\history_db_v2.json` |
| Demo shortcut observations | `%LOCALAPPDATA%\ASTRA-SHIELD\demo\history_db_v2.json` |
| Normal run diagnostics | `%LOCALAPPDATA%\ASTRA-SHIELD\logs\<UTC timestamp>-<PID>\` |
| Demo shortcut diagnostics | `%LOCALAPPDATA%\ASTRA-SHIELD\demo\logs\<UTC timestamp>-<PID>\` |

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
pwsh -File desktop/build_windows.ps1 -AppVersion 0.1.2
```

The script builds the production Angular assets, compiles the backend, bundles Python with PyInstaller, and produces a per-user Inno Setup installer. See the workflow and `requirements-build.txt` for the build dependencies. Build output goes under `desktop/dist/`; temporary resources go under `desktop/build/`. The workflow uploads `ASTRA-SHIELD-Windows-x64-<run_number>`, with a separate diagnostics artifact. These are generated files, not replacements for the model or source data. No training step is included.

The source repository includes the validated deployment artifact. To reproduce its export in the compatible original Linux Python environment, run `python desktop/export_inference_bundle.py`; this writes the deployment artifact, reference cases, and equivalence report without fitting a model. `python desktop/export_inference_bundle.py --validate-only` checks the portable artifact against its original reference outputs. The build refuses to perform its temporary installer test over an existing ASTRA installation; use the clean CI runner or `-SkipInstaller` for a portable-only local build.

The web frontend remains independent of this optional Windows wrapper. Linux/source-launcher instructions remain in [RUNNING.md](../docs/RUNNING.md), and the web deployment path remains in [WEB_DEPLOYMENT.md](../docs/WEB_DEPLOYMENT.md).

## Scope to preserve in the demonstration

Daily Check-in fields start blank. **Fill example values (simulated)** exists only in explicit offline demo mode; it does not supply ordinary backend inputs. Attention accuracy must come from an external measurement. **Not measured** clears it and blocks saving/forecasting until a valid value is supplied; incomplete drafts are not stored. A complete Flanker test is not present in the app, and the quick reaction-time demo cannot fill the full model measurement fields.

The model was trained on synthetic data and forecasts next-day fatigue. SHAP gives model contributions, not medical causes. Cards distinguish simulated examples from model-generated forecasts; missing forecasts receive neutral guidance. The five **Alert demo** presets are fictional UI examples and hide unrelated participant context. They do not run the full Clinical Alert V2 engine or its 14 medical acceptance cases. Use synthetic records in public demonstrations; do not publish real human health observations, journals, or runtime history.
