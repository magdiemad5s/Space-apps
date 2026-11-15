# Submission UI fixes — 0.1.1

The team reviewed a browser-based medical/scientific critique and corrected the data-entry and presentation issues before handoff. The model, training CSV, feature contract and dashboard design are retained. This work adds no clinical engine or new medical measurements.

| Finding | Change |
|---|---|
| Previous readings could be saved as today's measurements | Each new Check-in starts blank. Example autofill is available only in the explicitly selected offline demo. Saved-record retries still send the exact original observation. |
| Missing model output appeared alongside reassuring advice | A neutral “No forecast-based recommendation available.” message replaces that fallback. Measurement-based concerns remain visible. |
| Saved example forecasts looked like new model output | Forecast cards and explanations distinguish “Simulated example forecast” from “Model-generated forecast.” Fixture advice says “Example advisory”; full target times are shown in UTC. |
| Uncalibrated outputs could be mistaken for clinical probabilities | The index explicitly states that it is not a clinical risk probability. Class outputs are labeled uncalibrated, with a rounding explanation. |
| Alert examples appeared beside unrelated record predictions | Alert Demo retains the original astronaut illustration, but hides the selected record's hotspots, details and bottom forecast/recommendation panel. Its five examples retain their separate fictional Low placeholder. |
| Manual attention input implied an embedded test | The field says “Externally measured attention-task accuracy.” “Not measured” clears it and explains that saving/inference requires a value. It does not substitute zero, reuse an old result or store a partial draft. |
| Reaction-task identity and operational advice needed clarity | The full task is labeled “Custom 60-response PVT-inspired reaction-time test.” Quick-mode transfer remains blocked. Fixed reassessment prescriptions were replaced with mission-procedure and human-review wording. |
| Presentation storage could contain unrelated records | Windows Demo shortcuts and the source Demo launcher select a separate demo store. Linux/portable instructions provide equivalent explicit paths. Existing normal history is preserved. Use fictional measurements and journals throughout the presentation. |

Verification passed: **30 frontend regression tests, 81 UI checks, 48 end-to-end integration checks, 28 focused submission checks, 15 compiled-dashboard checks and 10 launcher tests**. The new focused test carries a scripted 60-response result through form transfer, actual save, retrieval, model inference and three SHAP explanations. No browser JavaScript errors were recorded. See the [reports](../integration-reports/README.md).

The full Clinical Alert V2 engine and its 14 clinical acceptance cases remain deferred. The five Alert Demo examples demonstrate presentation, not rule execution. Automated reaction timing and synthetic-data forecasts do not establish human or medical validity. Windows release verification is recorded separately in the [bundle handoff](../desktop/README.md); use the matching 0.1.1 installer for these changes.
