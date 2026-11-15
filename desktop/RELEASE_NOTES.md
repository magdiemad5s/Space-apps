Windows x64 demonstration package for the integrated Crew Health Console. The teammate's dashboard design is preserved. Python, Node, the production frontend and the five selected models are bundled; your tester does not need to install Python or Node.

1. Download **ASTRA-SHIELD-Setup-x64.exe** and install it for your Windows account.
2. Open **ASTRA-SHIELD Demo** from the Start menu. It opens the existing dashboard in your browser and adds nine fictional records only when the demo history is empty.
3. Keep its console open while using the app. Press **Ctrl+C** there to stop the services. Saved history is retained.

The installer is unsigned. Use the SHA256SUMS.txt from this release to verify your download. The portable ZIP is an alternative: extract the entire folder and keep its `_internal` directory beside the executable.

**Verified:** 80 final Linux Chromium UI checks, 48 browser/backend/model integration checks, and native Windows execution of both the portable and installed executable (19 smoke checks each). The Windows build also passed 25 frontend tests, 16 backend tests, runtime/process tests, six original-output reference comparisons, and installer/uninstaller checks. The interactive Windows laptop rehearsal remains the tester's task.

The original research artifact is preserved. The Windows deployment export retains the same five selected models and required metadata; unused research comparisons were excluded because their experimental XGBoost snapshot is not portable to Windows. No retraining occurred. A 130-case comparison checked all outputs and SHAP at 1e-12 tolerance, with Windows reference checks at the documented numerical tolerances.

This is a synthetic-data prototype. The five Alert demo presets do not implement the full Clinical Alert V2 engine or its 14 medical acceptance cases. Attention accuracy remains manually entered.

- [Tester checklist](https://github.com/magdiemad5s/Space-apps/blob/main/docs/FRIEND_TEST_CHECKLIST.md)
- [Windows instructions](https://github.com/magdiemad5s/Space-apps/blob/main/desktop/README.md)
- [Linux/source instructions](https://github.com/magdiemad5s/Space-apps/blob/main/docs/RUNNING.md)
- [Successful Windows build](https://github.com/magdiemad5s/Space-apps/actions/runs/43693862661)

Binary source commit: `26b14a678b67173e85a6621bb242b9e41f4f0014`. Build manifest, checksums and native Windows reports are attached.
