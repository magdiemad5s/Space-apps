# Project status

**Snapshot: 14 November 2026. This is an in-progress prototype, not a completed application.**

The frontend team's work may exist elsewhere; its source was not provided in this repository snapshot. The full Angular/Ionic → TypeScript → Python path still needs verification with that actual application.

## Completed for the prototype

- [x] Original synthetic dataset, definitions, participant partitions, and provenance.
- [x] Data consistency audit and visual EDA.
- [x] Causal personal-baseline and prior-history features.
- [x] Trained baseline models, recorded evaluation, and genuine fatigue TreeSHAP.
- [x] Python inference API and example payloads.
- [x] Reviewed TypeScript backend integration with calibration, history, validation, and outage recovery.
- [x] Recorded local Python/TypeScript contract and real HTTP integration checks.
- [x] Feature-reduction, model-comparison, history, and filtering experiments, preserved separately.

The original model remains the selected demo baseline. Training and experimentation do not need to block the application handoff.

## Required to complete the application demonstration

- [ ] **Backend owner:** review and merge the complete proposed backend folder into the team's working project.
- [ ] **AI/backend owners:** choose the presentation runtime, install dependencies, and run the Python service at an address reachable by the backend.
- [ ] **Frontend owner:** map the 15 measurements, participant ID, and daily cutoff to the canonical request contract.
- [ ] **Frontend owner:** implement or verify calibration, completed-prediction, invalid-input, and unavailable-service states.
- [ ] **Frontend owner:** graph raw observations, show the three SHAP reasons, and label `fatigue_points` as a prototype index rather than a medical percentage.
- [ ] **Whole team:** test the actual app from seven calibration records through the eighth-day prediction and history view.
- [ ] **Whole team:** test duplicate/invalid submissions, outage-safe observation saving, identical retry after recovery, and history persistence after restart.
- [ ] **Presentation owner:** rehearse on the actual device using the explicitly synthetic example sequence; confirm device-to-backend addressing.
- [ ] **AI/presentation owners:** explain the next-day target, participant split, pipeline chronology, Macro-F1, High recall, and synthetic-data limitations consistently.

The local verification services were stopped after testing. Committing these files does not deploy a live application.

## Separate future research

Real longitudinal measurements and labels, protocol validation, independent evaluation, calibrated probabilities, alert-cost analysis, missing-day robustness, and representative annotated journal text remain future work. These should be presented as research goals rather than completed model capabilities.
