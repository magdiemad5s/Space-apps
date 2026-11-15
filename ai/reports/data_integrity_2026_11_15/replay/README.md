# Deterministic generator replay audit

**Result: PASS for the specified computational consistency checks.** All seven
files produced by the original generator reproduced byte-for-byte. This does not
establish scientific, clinical, or astronaut-use validity.

The audit copied the unmodified generator into a temporary directory and ran it
once in a fresh Python process. Python's `sys.settrace` observed existing local
variables without introducing random draws, replacing the RNG, or changing the
original generator. The original source hash and unique AST statement anchors
guard the instrumentation against accidental use with a different generator.

## Results

| Check | Result |
| --- | --- |
| Captured sessions | 8,160 raw sessions; 7,200 main forecast sessions |
| Reconstructed response times | 489,600 raw responses; 432,000 main responses |
| Responses per session | Exactly 60 |
| Median | Same-array median, clipped to 150–800 ms and rounded to three decimals, matches every exported value |
| Lapses | Same-array count of unrounded responses **≥500 ms** matches every exported value |
| Attention | Integer binomial count in 0–40; percentage equals count / 40 × 100 |
| Exported scalar fields | Every corresponding traced scalar matches the original raw record |
| Reproduced original files | **7 / 7 byte-for-byte identical** |
| Audit check groups | 51 |
| Individual assertions | 318,371 |
| Failed assertions | 0 |
| Frozen generator and data | Unchanged |

For the main 7,200 sessions, there are 18,690 responses of at least 500 ms:
17,874 were explicitly injected and 816 were naturally slow draws outside the
injection mask. Therefore the injection count must not be substituted for the
actual lapse count. No session's sample median required clipping in this replay.

As a **counterfactual diagnostic only**, counting the same arrays at 355 ms would
change the lapse count in 7,083 of the 7,200 main sessions. This does not make the
existing 500 ms counts wrong, validate PVT-B, or authorize changing the protocol.
The additional rounded-median diagnostic in `checks.json` is descriptive; it is
not an exact mathematical contradiction test near the rounding boundary.

## Files

- `audit_replay.py`: reproducible executable audit.
- `checks.json`: every check, failure count, seven original/replayed hashes,
  environment, diagnostic counts, and limitations.
- `recovered_session_summary.csv`: one row per session, with recovered latent
  states, parameters, original scalar summaries, array-derived statistics, and
  the SHA-256 of each response array's little-endian float64 bytes.
- `recovered_initial_states.csv`: the 120 virtual participants' initial hidden
  parameters and latent states.
- `generator_run_summary.json`: summary printed by the original generator.

**The recovered files are audit artifacts, not newly collected measurements or
training datasets.** Latent states and response arrays were not present in the
original exported CSV. The summaries include calibration and future-outcome days,
as well as held-out participants; do not append these fields to model inputs.
No full response-array CSV is retained; rerunning the audit reconstructs the
arrays in memory and checks their summaries and hashes.

## Rerun

Use Python 3.12 with NumPy 2.3.5 and pandas 2.2.3, matching the original generator
environment. From the repository root:

```bash
python ai/reports/data_integrity_2026_11_15/replay/audit_replay.py
```

The command rewrites only these audit outputs and a temporary child directory,
which is removed afterward. It does not regenerate files inside `ai/data`, fit a
model, select features, or evaluate prediction performance. All seven generated
files—not just the numeric dataset—are compared with their frozen counterparts.

## What this cannot establish

- The data are wholly synthetic. Matching a generator does not validate its
  physiological assumptions, fatigue categories, or clinical safety.
- Custom continuous 0–10 scores are not KSS 1–9 or Samn–Perelli 1–7 instrument
  responses. Those missing measurements cannot be recovered by rescaling.
- Actual sleep timestamps, naps, measured WASO, continuous time awake, and sleep
  within a timestamped 24-hour window were not explicitly generated or measured.
  The efficiency cap does not provide those missing events.
- The sampled hidden `sleep_need` is a simulator parameter, not a measured or
  validated personal requirement. A seven-day average is not equivalent to it.
- The response generator has no stimulus timing, elapsed test duration, or
  anticipatory-response events. A recorded absence of false starts cannot be
  inferred from the omission of such events in this simulator.
- Attention correctness is a random binomial draw, not `40 × probability`.
  The probability and observed percentage are not required to be equal.

Dataset structure, temporal feature construction, baseline provenance, and other
quality checks are covered by the parent audit directory. This sub-audit focuses
on original-source replay and response-level consistency.
