# Friend's Windows handoff test

Use **fictional measurements only**. This checks whether the packaged app works on your computer; it does not establish medical accuracy. Record the installer SHA-256/build version, Windows version, browser/version, and any failed step. Keep screenshots and the exact error text for failures.

## Installation and first launch

- [ ] Verify the installer hash against `SHA256SUMS.txt` from the same build. Install as a normal user. Note any antivirus/SmartScreen message; do not disable security protection.
- [ ] Launch **ASTRA-SHIELD Demo** from the Start menu. Confirm it works without installing Python or Node separately.
- [ ] Confirm a console stays open and the same Crew Health dashboard opens in the browser. If the browser does not open, use the URL printed in the console.
- [ ] Confirm the UI says **Records from the backend**. The seeded `DEMO_SIM_001` records are fictional, even though their predictions use the real bundled model.
- [ ] After a successful install, stop the app, disconnect internet if practical, and launch again. Local fonts, dashboard, history, and inference should still work.

## Dashboard and measurements

- [ ] On a fresh demo store, there are nine records. Records 1–7 show calibration; records 8–9 show a forecast. Check the previous/next record controls and the displayed dates.
- [ ] Check the forecast category/index and three SHAP reasons. The forecast is for the next day; the index is not a medical risk percentage.
- [ ] Click the astronaut body-map regions, expand/collapse available panels, and inspect recommendation controls. No blank panels or broken layout should appear.
- [ ] Open **Trends**, change the measurement selector, and switch the selected record. Early calibration records must not show a future baseline.
- [ ] Open **Guide** and follow its navigation links. All tabs should remain reachable at normal size, a narrow browser window, and 200% zoom. Use Tab/Shift+Tab/Enter to reach ordinary buttons and inputs.
- [ ] In **Check-in**, clear a required field and try saving. Then try an impossible value such as negative heart rate. Neither should add a record.
- [ ] Restore the fields. Try an impossible daily budget, such as 12 hours sleep plus 16 hours work. It must be rejected without adding a record.
- [ ] Restore valid fictional values and save once. Confirm one additional record appears, a forecast is shown after calibration, and the journal text survives a reload. Prefilled values and the next daily cutoff are demonstration conveniences, not newly collected measurements.
- [ ] Open the reaction-time **quick demo**. Confirm it is labeled as a demo and cannot populate the full 60-response model fields. Switching away during an active trial should invalidate/reset the attempt as described by the app.
- [ ] Confirm attention accuracy is a manual field. Do not expect a completed interactive Flanker task in this version.

## Demo separation, failures, and restart

- [ ] Open **Alert demo** and try all five presets: No concern detected, Review, High concern, Urgent, and Insufficient data. Changing a preset must not modify the participant's history or tomorrow's actual model forecast.
- [ ] Confirm the Alert demo is labeled as illustrative. These five screens are **not** the 14 Clinical Alert V2 acceptance tests.
- [ ] Try an invalid backend address in the connection settings. The UI should explain the problem instead of accepting it silently. For a connection-failure check, use an unreachable local HTTP address, then restore the same-origin default with **Change backend address**.
- [ ] A connection failure must be visible. It must not silently replace backend records with offline examples. If you explicitly choose the offline demo, confirm it is labeled and changes stay separate from backend history.
- [ ] Press **Ctrl+C in the app console**. After shutdown, refreshing its old local URL should fail; closing only the browser tab is not shutdown.
- [ ] Relaunch the same shortcut. Confirm saved records and journal text remain, and the nine seeded records were not duplicated. Check that no previous background instance remains after stopping.
- [ ] While the app is running, launch the shortcut again. The second instance should report that the data directory is already in use; it must not start another writer or alter history.

For a clean repeat without deleting the normal history, use the separate data-directory example in [desktop/README.md](../desktop/README.md). Default stored data is `%LOCALAPPDATA%\ASTRA-SHIELD`; uninstalling preserves it.

## Send back results

Send: **build/hash, Windows/browser versions, passed/failed step, exact reproduction, expected versus actual result, and screenshot/error text**. Logs are under `%LOCALAPPDATA%\ASTRA-SHIELD\logs\<UTC timestamp>-<PID>\`; the console prints the exact directory. Share only the relevant diagnostics, after checking for anything personal. Do not send real health records or the entire history file by default.

Remaining project scope is unchanged: synthetic-data validation only, no full Clinical Alert V2 engine/14-case pass claim, no real astronaut-data validation, and no public multi-user deployment.
