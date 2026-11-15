ASTRA-SHIELD **0.1.2** adds visible SI-generation labels directly inside the astronaut and smartwatch SVG illustrations. The labels remain with the rendered artwork in screenshots and SVG exports. This is a code-only artwork attribution update; no new images were generated.

The existing dashboard, measurement workflow and selected models are retained. Python, Node and the production frontend are bundled, so the tester does not need to install development tools.

1. Download **ASTRA-SHIELD-Setup-x64.exe** and install it for your Windows account. Close a running older launcher before updating.
2. Open **ASTRA-SHIELD Demo** from the Start menu. Its separate demo store contains fictional observations, and the dashboard opens in your browser.
3. Keep the console open while using the app. Press **Ctrl+C** there to stop the services. Saved history is retained.

The installer is unsigned. Verify the download against this release's **SHA256SUMS.txt**. The portable ZIP is an alternative: extract the complete folder and keep `_internal` beside the executable.

**Verification for this source:** 30 frontend regression tests, type checking and the production build passed. Twenty-eight rendered-artwork checks covered desktop/mobile widths, label readability and clipping, body-map interaction and standalone SVG exports. Native Windows execution passed 19 checks each for the portable and installed executables, six original-model reference comparisons, 16 backend tests, runtime/source-launcher tests, and installer/uninstaller checks. The packaged production JavaScript was inspected for both embedded SVG labels. The earlier broader integration reports remain available as historical evidence; they were not rerun solely for the artwork change.

No training or model re-export was performed. The original model, deployment model and training CSV hashes match the existing verified artifacts. This is a synthetic-data research prototype, not a clinically validated assessment. The five Alert Demo examples remain predefined illustrations; they do not execute the full Clinical Alert V2 engine or its 14 medical acceptance cases.

- [Windows instructions](https://github.com/magdiemad5s/Space-apps/blob/main/desktop/README.md)
- [Tester checklist](https://github.com/magdiemad5s/Space-apps/blob/main/docs/FRIEND_TEST_CHECKLIST.md)
- [Rendered artwork checks](https://github.com/magdiemad5s/Space-apps/blob/main/integration-reports/ARTWORK_WATERMARK_CHECKS.json)
- [Native Windows build 6](https://github.com/magdiemad5s/Space-apps/actions/runs/43726368621)
- [Team, tool-use and data provenance](https://github.com/magdiemad5s/Space-apps/blob/main/PROVENANCE.json)

Binary source commit: `34f513aed953c0aaa9ca63611334e99457d52065`. Build manifest, checksums and native Windows reports are attached. Earlier prototype releases remain available separately; this release does not overwrite them.
