# Dataset integrity audit — 15 November 2026

The specified consistency checks passed for the existing synthetic cohort. The
audit did not identify corrupt rows requiring deletion or imputation. It does
not establish biological/clinical validity, device performance, or completion of
the proposed new measurements or actual Angular/Ionic application.

## Results

| Scope | Result |
|---|---|
| Main data | 7,200 rows, 46 columns, 120 virtual participants |
| Raw source | 8,160 rows including calibration and future outcomes |
| Structural, numeric, causal, split and schema checks | 144 passing groups, including eight in-memory corruption-detection controls |
| Deterministic source replay | Seven of seven generated files byte-identical |
| Trial-level reconstruction | 8,160 sessions; 489,600 response times; every median and ≥500 ms count matches its source |
| Replay checks | 51 groups, 318,371 individual assertions, zero failures |
| Existing software tests | 21 Python +16 TypeScript passed; strict typecheck passed |
| Python all-row feature comparison | 7,200 rows ×26 features, zero numerical differences |
| TypeScript all-history comparison | 840 calibration +7,200 forecast observations; 158,400 numeric comparisons, zero differences |
| Invalid requests | 158 Python and 109 TypeScript invalid-input cases correctly rejected |
| Proposed field names and aliases | 36 explicitly tested, expected unsupported; no silent model integration |
| Missing cells / duplicates in existing main columns | Zero / zero |
| Training extreme-value review | 254 flagged rows; all carry intentional injected-event annotations; zero removed |
| Data, model and existing service source | Hashes unchanged |

These are different units of evidence. Do not add check groups, assertions, rows,
and software test cases together as a single independent-test count.

## Shareable outputs

- [Arabic report, PDF](ASTRA_SHIELD_Data_Audit_AR.pdf): conclusions, all six concerns,
  graphs, measurement gaps, and reproducibility.
- [Arabic report, HTML](ASTRA_SHIELD_Data_Audit_AR.html): standalone equivalent.
- [Every core check, CSV](core_checks.csv).
- [Requested measurements and readiness, CSV](requested_measurements.csv).
- [Core summary](core_summary.json) and [corruption-detection controls](negative_controls.json).
- [Generator replay](replay/README.md), including executable script and results.
- [API/data-contract checks](api/README.md), including exact scope, scripts and logs.
- [Preservation hashes](preservation.json).

All-cohort checks read validation/test records only to check structure and source
alignment. No model fitting, feature selection, new cleaning experiment or new
predictive-performance evaluation occurred. Descriptive plots, outlier flags and
correlations use the training partition only.

## Remaining measurement gaps

The 21-entry requested inventory has two existing synthetic fields (lapse count
and workload duration) and 19 absent fields, including two optional PHQ-2/GAD-2
fields. This is not 19 mandatory defects. KSS/SP responses, actual sleep timing,
naps, measured WASO, false starts, and caffeine/medication context were not
collected in this dataset. Unknown historical values must not be turned into
measured zeros or inferred questionnaire responses.

The response generator has no timed stimulus schedule. Its 60-response ≥500 ms
definition is internally consistent; it is not validated PVT/PVT-B. The attention
task has no implemented human stimulus protocol. Journal outputs are an English
template demonstration. Sleep and physiology values were not obtained from
instruments. API flags and documentation distinguish the demo from clinical
claims, but the actual frontend display was not available to test.

Adding fields to an application is distinct from using them in a trained model.
The current strict API rejects them. A future collection contract needs explicit
definitions, missingness/provenance handling, and time windows. Model inclusion
requires compatible training data and separate evaluation; no performance gain
is guaranteed. If a questionnaire defines a target, that same target must not
also be supplied as a predictor.

## Reproduce

Use Python 3.12 and the project's dependencies; the exact generator environment
is NumPy 2.3.5 and pandas 2.2.3. See `requirements-audit.txt` and the API subfolder
README for Node/TypeScript requirements. Activate the environment, then run from
the repository root:

```bash
python ai/reports/data_integrity_2026_11_15/audit_core.py
python ai/reports/data_integrity_2026_11_15/replay/audit_replay.py
python ai/reports/data_integrity_2026_11_15/api/run_api_integrity.py
python ai/reports/data_integrity_2026_11_15/render_report.py --pdf
```

The renderer needs Playwright, Chromium and an Arabic font such as Noto Naskh
Arabic. It can create standalone HTML without launching a browser. Rendering
uses only already-completed audit results, not new tests or data generation.

Scripts write outputs only in this report directory and temporary directories.
Original generator execution occurs in an isolated temporary directory. The
recovered latent values and trial-array summaries are audit artifacts and must
not be added to model features. They include held-out people and future records.

This is a snapshot audit with a known schema/source hash, not a general-purpose
CSV validator: severe structural damage can stop execution before a full failure
table is produced. A failed script never authorizes automatic data repair.
