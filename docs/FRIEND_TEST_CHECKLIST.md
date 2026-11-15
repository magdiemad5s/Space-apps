# Friend's Windows handoff test

Use **fictional measurements only**. This checks whether the packaged app works on your computer; it does not establish medical accuracy. Record the installer SHA-256/build version, Windows version, browser/version, and any failed step. Keep screenshots and the exact error text for failures.

This checklist describes the **0.1.1 handoff**. The matching installer passed [native Windows checks](../integration-reports/windows-build-5/verification.json). This checklist adds interactive rehearsal on your own laptop.

## Installation and first launch

- [ ] Verify the installer hash against `SHA256SUMS.txt` from the same build. Install as a normal user. Note any antivirus/SmartScreen message; do not disable security protection.
- [ ] Launch **ASTRA-SHIELD Demo** from the Start menu. Confirm it works without installing Python or Node separately.
- [ ] Confirm the console's history path is `%LOCALAPPDATA%\ASTRA-SHIELD\demo\history_db_v2.json`. The Demo shortcut must use this separate store and leave the normal history file untouched.
- [ ] Confirm a console stays open and the same Crew Health dashboard opens in the browser. If the browser does not open, use the URL printed in the console.
- [ ] Confirm the UI says **Records from the backend**. The seeded `DEMO_SIM_001` records are fictional, even though their predictions use the real bundled model.
- [ ] After a successful install, stop the app, disconnect internet if practical, and launch again. Local fonts, dashboard, history, and inference should still work.

## Dashboard and measurements

- [ ] On a fresh demo store, there are nine records. Records 1–7 show calibration; records 8–9 show a forecast. Check the previous/next record controls and the displayed dates.
- [ ] Check the forecast category/index and three SHAP reasons. Backend results say **Model-generated forecast**; offline fixtures say **Simulated example forecast**. The forecast is for the next day; the index is not a medical risk percentage.
- [ ] Select a calibration or otherwise missing-forecast record. Its guidance should remain neutral; a missing forecast must not appear as a reassuring low-risk result.
- [ ] Click the astronaut body-map regions, expand/collapse available panels, and inspect recommendation controls. No blank panels or broken layout should appear.
- [ ] Open **Trends**, change the measurement selector, and switch the selected record. Early calibration records must not show a future baseline.
- [ ] Open **Guide** and follow its navigation links. All tabs should remain reachable at normal size, a narrow browser window, and 200% zoom. Use Tab/Shift+Tab/Enter to reach ordinary buttons and inputs.
- [ ] Open **Check-in** and confirm daily measurement fields are blank; yesterday's readings are not copied. The backend-connected form must not offer **Fill example values (simulated)**.
- [ ] Leave a required field blank and try saving. Then enter an impossible value such as negative heart rate. Neither should add a record.
- [ ] Enter fictional values, then try an impossible daily budget, such as 12 hours sleep plus 16 hours work. It must be rejected without adding a record.
- [ ] Enter a valid fictional external attention-accuracy value, then click **Not measured**. It must clear the value and prevent saving or forecasting. No incomplete draft should be stored.
- [ ] Restore valid fictional values, including external attention accuracy, and save once. Confirm one additional record appears, a forecast is shown after calibration, and the journal text survives a reload. The next daily cutoff is a demonstration convenience, not evidence that a measurement was taken at that time.
- [ ] Open the reaction-time **quick demo**. Confirm it is labeled as a demo and cannot populate the full 60-response model fields. Switching away during an active trial should invalidate/reset the attempt as described by the app.
- [ ] Confirm attention accuracy is manually entered from an external test. Do not expect a completed interactive Flanker task in this version.

## Demo separation, failures, and restart

- [ ] Open **Alert demo** and try all five presets: No concern detected, Review, High concern, Urgent, and Insufficient data. Unrelated selected-record context should be hidden. Changing a preset must not modify the participant's history or tomorrow's actual model forecast.
- [ ] Confirm the Alert demo is labeled as illustrative. These five screens are **not** the 14 Clinical Alert V2 acceptance tests.
- [ ] Try an invalid backend address in the connection settings. The UI should explain the problem instead of accepting it silently. For a connection-failure check, use an unreachable local HTTP address, then restore the same-origin default with **Change backend address**.
- [ ] A connection failure must be visible. It must not silently replace backend records with offline examples. If you explicitly choose the offline demo, confirm it is labeled and changes stay separate from backend history.
- [ ] In explicit offline demo mode, Check-in may offer **Fill example values (simulated)**. Confirm it fills fictional values there only; reconnecting to the backend must not submit them or carry them into a new daily form.
- [ ] Press **Ctrl+C in the app console**. After shutdown, refreshing its old local URL should fail; closing only the browser tab is not shutdown.
- [ ] Relaunch the same shortcut. Confirm saved records and journal text remain, and the nine seeded records were not duplicated. Check that no previous background instance remains after stopping.
- [ ] While the app is running, launch the shortcut again. The second instance should report that the data directory is already in use; it must not start another writer or alter history.

For a clean repeat without deleting existing history, use a fresh separate data directory as shown in [desktop/README.md](../desktop/README.md). The 0.1.1 Demo shortcut stores data under `%LOCALAPPDATA%\ASTRA-SHIELD\demo`; normal startup keeps `%LOCALAPPDATA%\ASTRA-SHIELD`. Uninstalling preserves both. The new demo location does not automatically migrate or delete older records.

## Send back results

Send: **build/hash, Windows/browser versions, passed/failed step, exact reproduction, expected versus actual result, and screenshot/error text**. Demo shortcut logs are under `%LOCALAPPDATA%\ASTRA-SHIELD\demo\logs\<UTC timestamp>-<PID>\`; normal startup uses the corresponding `ASTRA-SHIELD\logs` path. The console prints the exact directory. Share only relevant diagnostics after checking for anything personal. Do not publish real human health records, journals, or the history file.

Remaining project scope is unchanged: synthetic-data validation only, no full Clinical Alert V2 engine/14-case pass claim, no real astronaut-data validation, and no public multi-user deployment.
