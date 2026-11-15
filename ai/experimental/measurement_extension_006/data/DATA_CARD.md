# EXP006: fresh synthetic measurement-extension cohort

This is a separately generated experiment, **not a repaired or relabeled original
dataset**. It contains120virtual participants with60forecast days each, seven
earlier calibration days, and day61for the final next-day targets. No NASA or real
human measurements are included. Nothing establishes clinical validity.

The original numeric generator runs with fresh seed20261115, EXP006identifiers,
and an explicit version. Its fatigue/physiology/response evolution is unchanged.
An independent RNG(seed2026111501) adds the frozen extension. No model is trained
by this script, and it does not print held-out outcome statistics.

## Files and use

- `main.csv`: all7200forecast rows with base fields, extension features and metadata.
- `train.csv`, `validation.csv`, `test.csv`: participant-disjoint84/18/18person splits.
- `feature_manifest.json`: the only approved model inputs; bundles have26/28/31/33features.
- `split_manifest.json`: filenames, sizes, participant counts and hashes.
- `raw_audit.csv`:8160source rows, including calibration, future outcomes and hidden
  current-state audit fields. **Never use this as a training feature table.**
- `sleep_segments.csv`: hypothetical allocated sleep intervals, not recovered real events.
- `base_source/`: fresh original-algorithm source and its generated outputs;
  its legacy wording is superseded by the protocol clarification below.
- `generation_quality.json`: structural/causal assertions only, not performance.
- `hash_manifest.json`: file hashes and preservation of the original cohort/model.

## Meaning of the additions

KSS-like1–9 and Samn–Perelli-like1–7 scores are **uncalibrated noisy ordinal
proxies with instrument-like ranges**. They are neither actual responses nor
validated translations. They are generated using only current latent fatigue,
current sleep summaries and independent noise, not by rescaling observed0–10
fatigue or using tomorrow's label. Their apparent predictive value can result
from exposing the simulator's latent state more directly.

Main sleep timing/WASO is a **hypothetical allocation** of the existing synthetic
duration, efficiency, latency, awakening count and midpoint deviation. It is an
alternate representation of those aggregates, not newly measured information.
The explicit planned main-sleep midpoint is04:00UTC. WASO and terminal wake are
allocated using the preregistered formulas; wake intervals are equally sized.

At most one optional nap is simulated. Its Bernoulli attempt is independent of
latent fatigue/stress, and its10–40minute duration is limited by known free time.
The allocated nap interval is entirely asleep; nap latency/awakenings and multiple
naps are deferred. **Naps have no physiological recovery effect on the unchanged
base fatigue/target process.** Total24h sleep includes allocated naps, and time
awake resets after the last sleep episode. Three-day shortfall uses only the three
previous nonoverlapping daily windows against a configured8hour goal. This is not
validated biological sleep debt, and8hours is metadata rather than a predictor.

Zero nap duration means confirmed synthetic no-nap; corresponding timestamp
metadata are null. The first three raw audit days have no three-day prior history,
so that feature is null there. All approved inputs are complete in the main splits.

## Protocol and interpretation limits

Reaction times remain the original **60-response simulation with lapse>=500ms**.
It has no simulated elapsed test time, stimulus intervals, anticipatory response
events or PVT false-start measurements. Any inherited five-minute wording is an
old descriptive label, not a timing guarantee. No PVT-B355ms conversion is made.
Caffeine, medication, acute symptoms, PHQ-2/GAD-2 and other unavailable contextual
measurements are not invented.

Compare models **within this same fresh cohort**. Do not compare its score directly
with0.5273from the original cohort as an estimated feature effect. Better synthetic
performance cannot validate real questionnaires, nap effects, astronaut health or
deployment. Freeze decisions, perform training-only EDA, and keep the participant
test split sealed until the evaluation plan permits its one-shot use.

## Reproduction

Use Python3.12, NumPy2.3.5 and pandas2.2.3. The frozen generation plan is
`../draftgenerationplan.json`, and the root experiment plan is
`../EXPERIMENT_PLAN.json`. `python ../data_generator.py` intentionally refuses to
overwrite an existing cohort. Reproduce in a separate copy of the experiment tree
with the same original source available. Generator and plan hashes are recorded.
Failed chronology/budget checks abort generation; no rows are removed or silently
repaired, and no seed/parameter search is performed.
