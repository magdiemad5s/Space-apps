ASTRA-SHIELD **0.1.1** is the Supermoon team's Windows x64 prototype of the integrated Crew Health Console. The dashboard design is retained. Python, Node, the production frontend and the same five selected models are bundled; your tester does not need to install Python or Node.

This release corrects measurement entry and the presentation of example data:

- New Check-ins start blank. Previous readings are not prefilled as today's measurements; example autofill is restricted to the explicitly selected offline demo.
- Attention is labeled **Externally measured attention-task accuracy**. Selecting **Not measured** clears it and blocks saving/inference until the required measurement is supplied. No result is invented or replaced with zero.
- Example forecasts and model-generated forecasts have distinct labels and full UTC target times. Class outputs are explicitly uncalibrated, and the displayed index is not a clinical risk probability.
- Missing forecasts receive neutral guidance. Fixed reassessment prescriptions were removed; current measurement concerns remain visible.
- The Alert Demo is separate from the selected record's forecast and recommendation panels. Windows Demo shortcuts now select a separate fictional-data store.
- The reaction task is explicitly a **custom 60-response PVT-inspired test**. Quick-mode results cannot be transferred into a Check-in.

1. Download **ASTRA-SHIELD-Setup-x64.exe** and install it for your Windows account. Close a running older launcher before installing the update.
2. Open **ASTRA-SHIELD Demo** from the Start menu. It opens the existing dashboard in your browser and adds nine fictional records only when the separate demo history is empty.
3. Keep its console open while using the app. Press **Ctrl+C** there to stop the services. Saved history is retained.

The installer is unsigned. Use this release's **SHA256SUMS.txt** to verify the download. The portable ZIP is an alternative: extract the entire folder, keep `_internal` beside the executable, and follow the explicit demo-directory command in the Windows instructions.

**Verified for this source:** 30 frontend regression tests, 81 UI checks, 48 end-to-end integration checks, 28 focused submission checks, 15 compiled-dashboard checks and 10 source-launcher tests. The focused check carries a scripted full reaction task through transfer, save, retrieval, actual model inference and three SHAP reasons. Native Windows execution passed **19 smoke checks each** for the portable and installed executable, six original-output comparisons, 16 backend tests, runtime/process tests, and installer/uninstaller checks. Reports identify platform-specific skips and test scope. Interactive rehearsal on the tester's Windows laptop remains necessary.

The original research model, deployment model and training CSV are unchanged; no retraining or model re-export occurred for 0.1.1. The deployment retains the same five selected models and required metadata. Unused research comparisons remain excluded because their experimental XGBoost snapshot is not portable to Windows. The existing 130-case equivalence check and the new native Windows reference checks document this separation.

This is a synthetic-data prototype, not a clinically validated assessment. The five Alert Demo examples do not execute the full Clinical Alert V2 engine or its 14 clinical acceptance cases. Attention remains an external/manual input; an integrated attention test has not been added.

- [Tester checklist](https://github.com/magdiemad5s/Space-apps/blob/main/docs/FRIEND_TEST_CHECKLIST.md)
- [Windows instructions](https://github.com/magdiemad5s/Space-apps/blob/main/desktop/README.md)
- [Linux/source instructions](https://github.com/magdiemad5s/Space-apps/blob/main/docs/RUNNING.md)
- [Submission fixes and verification](https://github.com/magdiemad5s/Space-apps/blob/main/docs/SUBMISSION_FIXES.md)
- [Successful Windows 0.1.1 build](https://github.com/magdiemad5s/Space-apps/actions/runs/43720287539)
- [Team, tool-use and data provenance](https://github.com/magdiemad5s/Space-apps/blob/main/PROVENANCE.json)

Binary source commit: `e1a8dc1350d1e6aeeb6c2b8d995b45ceec1b5f2d`. Build manifest, checksums and native Windows reports are attached. Version 0.1.0 remains available separately; this release does not overwrite it.
