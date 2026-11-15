#!/usr/bin/env python3
"""Generate the separately preregistered EXP006 synthetic cohort, never train.

This experiment writes only its own data directory. Run once after freezing the
root experiment and generation plans. Existing output cohorts are not replaced.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import runpy
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
AI = HERE.parents[1]
ORIGINAL = AI / "data"
OUT = HERE / "data"
PLAN = HERE / "draftgenerationplan.json"
PLAN_SHA = "b0a3502246829bfdd933c73ae23b7c237469dc4abe7bcf43aeb71aba8f48e507"
ROOT_PLAN_SHA = "2eb2c9fb4a95c378e44b6cc9a2dcea5d84e80edf4ccfbaee7ff1be78b76b94f5"
SOURCE_SHA = "e4a914c3fdd01bc6032ad39b2e61967c416408558e5015664286083b80ac01fa"
VERSION = "astra_measurement_extension_006_v1"
QUESTIONNAIRES = ["kss_like_sleepiness_score", "samn_perelli_like_fatigue_score"]
SLEEP = ["main_sleep_waso_minutes", "time_since_last_sleep_hours", "nap_sleep_minutes_last_24h",
         "total_sleep_last_24h_hours", "prior_3day_sleep_shortfall_hours"]
TOL_HOURS = 1e-6


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def require(condition, description):
    if not bool(condition):
        raise RuntimeError(description + "; aborted without deleting or repairing any rows")


def iso(ts):
    return pd.Timestamp(ts).isoformat().replace("+00:00", "Z")


def minutes(value):
    return pd.Timedelta(minutes=float(value))


def base_worker(source, destination):
    """Observe current latent state in a fresh process; no additional base RNG use."""
    tree = ast.parse(source.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "generate")
    anchors = [n.lineno for n in ast.walk(function) if isinstance(n, ast.Expr)
               and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute)
               and isinstance(n.value.func.value, ast.Name)
               and n.value.func.value.id == "records" and n.value.func.attr == "append"]
    require(len(anchors) == 1, "Unique base-generator observation anchor required")
    states = []
    seen = set()

    def trace(frame, event, arg):
        if frame.f_code.co_filename != str(source) or frame.f_code.co_name != "generate":
            return None
        if event == "line" and frame.f_lineno == anchors[0]:
            loc = frame.f_locals
            key = f"{loc['pid']}_D{loc['day']:+04d}"
            if key not in seen:
                seen.add(key)
                states.append({"record_id": key, "audit_hidden_current_fatigue": float(loc["fatigue"]),
                               "audit_hidden_current_stress": float(loc["stress"]),
                               "audit_hidden_current_circadian_minutes": float(loc["circadian"])})
        return trace

    # Do not execute __main__, which prints all-cohort outcome frequencies.
    # Loading then calling the same functions preserves the exact base draw order.
    module = runpy.run_path(str(source), run_name="exp006_original_algorithm")
    sys.settrace(trace)
    try:
        main, raw = module["generate"]()
        module["dictionary"](main, raw)
    finally:
        sys.settrace(None)
    require(len(states) == 8160, "Expected8160 current-state observations")
    pd.DataFrame(states).to_csv(destination / "current_latent_audit.csv", index=False, float_format="%.17g")


def prepare_base(folder):
    require(sha(ORIGINAL / "source_generator.py") == SOURCE_SHA, "Original generator hash changed")
    source = (ORIGINAL / "source_generator.py").read_text()
    replacements = {
        "SEED = 20261114": "SEED = 20261115",
        "VERSION = 'astra_synthetic_v1.0'": f"VERSION = '{VERSION}'",
        "pid = f'SIM_{n:03d}'": "pid = f'EXP006_{n:03d}'",
    }
    for old, new in replacements.items():
        require(source.count(old) == 1, "Original source replacement anchor must be unique: " + old)
        source = source.replace(old, new)
    folder.mkdir()
    copied = folder / "source_generator.py"
    copied.write_text(source)
    process = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--base-worker", str(copied), str(folder)],
                             cwd=folder, text=True, capture_output=True, timeout=300)
    require(process.returncode == 0, "Fresh base generation failed: " + process.stderr[-3000:])
    require(not process.stdout.strip(), "Base process unexpectedly printed statistics")
    return pd.read_csv(folder / "astra_shield_synthetic_ml.csv"), pd.read_csv(folder / "raw_observations.csv"), pd.read_csv(folder / "current_latent_audit.csv")


def extend(raw, latent):
    rng = np.random.default_rng(2026111501)
    source = raw.merge(latent, on="record_id", validate="one_to_one", how="left")
    latent_columns = ["audit_hidden_current_fatigue", "audit_hidden_current_stress", "audit_hidden_current_circadian_minutes"]
    require(len(source) == 8160 and np.isfinite(source[latent_columns].to_numpy()).all(),
            "Every source row must have finite same-day latent audit values")
    rows, segments = [], []
    for row in source.to_dict("records"):
        key = row["record_id"]
        cutoff = pd.Timestamp(row["observation_timestamp_utc"])
        window_start = cutoff - pd.Timedelta(hours=24)
        day_midnight = cutoff.normalize()
        midpoint = day_midnight + pd.Timedelta(hours=4) + minutes(row["sleep_midpoint_deviation_minutes"])
        tst = 60 * row["sleep_duration_hours"]
        opportunity = tst / (row["sleep_efficiency_pct"] / 100)
        sol = row["sleep_onset_delay_minutes"]
        count = int(row["awakenings_count"])
        remaining_awake = opportunity - tst - sol
        require(remaining_awake >= 3 * count - 60*TOL_HOURS, key + ": insufficient awake-time budget")
        waso = 0.0 if count == 0 else 3 * count + .5 * (remaining_awake - 3 * count)
        terminal = remaining_awake - waso
        require(waso >= 0 and terminal >= -60*TOL_HOURS, key + ": invalid awake allocation")
        onset = midpoint - minutes((tst + waso) / 2)
        final_wake = midpoint + minutes((tst + waso) / 2)
        attempt = onset - minutes(sol)
        out_of_bed = final_wake + minutes(terminal)
        require(window_start <= attempt < onset < final_wake <= out_of_bed <= cutoff,
                key + ": main sleep opportunity crosses assessment window")
        free_minutes = 24*60 - opportunity - row["workload_hours"]*60 - row["exercise_minutes"]
        require(free_minutes >= -60*TOL_HOURS, key + ": negative base daily time budget")
        session_segments = []
        cursor = onset
        for index in range(count + 1):
            end = cursor + minutes(tst / (count + 1))
            session_segments.append((cursor, end, "main"))
            if index < count:
                cursor = end + minutes(waso / count)
        require(abs((session_segments[-1][1] - final_wake).total_seconds()) <= TOL_HOURS*3600,
                key + ": sleep-segment reconstruction drift")

        # Draw ordering and branch behavior are fixed before generation.
        nap_attempt = bool(rng.random() < .25)
        proposed_nap_minutes = float(rng.uniform(10, 40))
        proposed_start = max(day_midnight + pd.Timedelta(hours=14), out_of_bed + minutes(30))
        latest_end = cutoff - minutes(30)
        available_minutes = (latest_end - proposed_start).total_seconds() / 60
        nap_duration = min(proposed_nap_minutes, free_minutes, available_minutes)
        has_nap = nap_attempt and nap_duration >= 10
        nap_start = proposed_start if has_nap else None
        nap_end = proposed_start + minutes(nap_duration) if has_nap else None
        if has_nap:
            require(out_of_bed <= nap_start < nap_end <= cutoff, key + ": invalid nap chronology")
            session_segments.append((nap_start, nap_end, "nap"))
        else:
            nap_duration = 0.0
        require(opportunity + row["workload_hours"]*60 + row["exercise_minutes"] + nap_duration <= 24*60 + 60*TOL_HOURS,
                key + ": nap exceeds daily budget")
        session_segments.sort(key=lambda x: x[0])
        require(all(a[1] <= b[0] for a, b in zip(session_segments, session_segments[1:])), key + ": overlapping sleep segments")

        def overlap_hours(start, end):
            return max(0.0, (min(end, cutoff) - max(start, window_start)).total_seconds() / 3600)

        total24 = sum(overlap_hours(start, end) for start, end, _ in session_segments)
        nap24_minutes = 60*sum(overlap_hours(start, end) for start, end, kind in session_segments if kind == "nap")
        latest_sleep_end = max(end for _, end, _ in session_segments)
        time_awake = (cutoff - latest_sleep_end).total_seconds() / 3600
        require(0 <= time_awake <= 24 and 0 < total24 <= 24, key + ": invalid24h sleep summary")
        require(abs(total24 - row["sleep_duration_hours"] - nap_duration/60) <= TOL_HOURS,
                key + ": segment totals differ from allocated durations")
        current_f = row["audit_hidden_current_fatigue"]
        kss_z = .65*current_f + .45*max(0, 8-total24) + .15*max(0, time_awake-12) + rng.normal(0, 1.4)
        sp_z = current_f + rng.normal(0, 1.25)
        kss = 1 + int(np.count_nonzero(kss_z >= np.arange(1, 9)))
        sp = 1 + int(np.count_nonzero(sp_z >= np.array([1.5, 3, 4.5, 6, 7.5, 9])))
        extension = {
            "record_id": key, "kss_like_sleepiness_score": kss,
            "samn_perelli_like_fatigue_score": sp, "main_sleep_waso_minutes": waso,
            "time_since_last_sleep_hours": time_awake, "nap_sleep_minutes_last_24h": nap24_minutes,
            "total_sleep_last_24h_hours": total24,
            "sleep_goal_hours": 8.0, "planned_main_sleep_midpoint_hour_utc": 4.0,
            "main_sleep_opportunity_hours": opportunity / 60,
            "main_terminal_wake_minutes": terminal,
            "main_sleep_attempt_time_utc": iso(attempt), "sleep_onset_time_utc": iso(onset),
            "wake_time_utc": iso(final_wake), "out_of_bed_time_utc": iso(out_of_bed),
            "nap_count": int(has_nap), "nap_start_time_utc": iso(nap_start) if has_nap else None,
            "nap_end_time_utc": iso(nap_end) if has_nap else None,
            "nap_status": "one_nap_simulated" if has_nap else "no_nap_simulated",
            "measurement_extension_version": VERSION,
            "sleep_timing_origin": "hypothetical_allocation_of_simulated_aggregates",
            "questionnaire_origin": "synthetic_ordinal_proxy_not_validated_questionnaire",
            "nap_origin": "additional_synthetic_episode_no_base_target_recovery_effect",
            "audit_hidden_current_fatigue": current_f,
            "audit_hidden_current_stress": row["audit_hidden_current_stress"],
            "audit_hidden_current_circadian_minutes": row["audit_hidden_current_circadian_minutes"],
            "audit_kss_proxy_latent_z": float(kss_z), "audit_sp_proxy_latent_z": float(sp_z),
        }
        rows.append(extension)
        for index, (start, end, kind) in enumerate(session_segments, 1):
            segments.append({"record_id": key, "participant_id": row["participant_id"],
                             "mission_day": row["mission_day"], "split": row["split"],
                             "segment_index": index, "sleep_kind": kind,
                             "sleep_start_time_utc": iso(start), "sleep_end_time_utc": iso(end),
                             "sleep_duration_minutes": (end-start).total_seconds()/60,
                             "provenance": "hypothetical_simulated_sleep_interval"})
    extensions = pd.DataFrame(rows)
    audit_raw = raw.merge(extensions, on="record_id", validate="one_to_one")
    shortfall = (8 - audit_raw.total_sleep_last_24h_hours).clip(lower=0)
    audit_raw["prior_3day_sleep_shortfall_hours"] = shortfall.groupby(audit_raw.participant_id).transform(
        lambda values: values.shift(1).rolling(3, min_periods=3).sum())
    return audit_raw, pd.DataFrame(segments)


def validate(main, raw, events, base_main, baseline_features):
    checks = []

    def check(name, passed, detail):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})
        require(passed, name)

    check("main_rows_7200", len(main) == 7200, "No rows removed or invented during extension")
    check("raw_rows_8160", len(raw) == 8160, "Includes7calibration and1future-outcome day per person")
    check("base_columns_unchanged", main[base_main.columns].equals(base_main), "Every fresh original field and target unchanged by extension")
    check("unique_person_day", not raw.duplicated(["participant_id", "mission_day"]).any(), "Unique source keys")
    check("chronological_complete_schedule", raw.groupby("participant_id").mission_day.apply(lambda s: s.tolist() == list(range(-6, 62))).all(), "Complete sorted68day source schedule")
    check("fresh_identifier_namespace", raw.participant_id.str.fullmatch(r"EXP006_\d{3}").all(), "No identity reuse with originalSIMcohort")
    check("fresh_version", raw.generator_version.eq(VERSION).all(), "Explicit experiment provenance")
    check("all_model_inputs_present_finite", np.isfinite(main[baseline_features + QUESTIONNAIRES + SLEEP].to_numpy()).all(), "All33predictors finite; optional metadata nulls intentional")
    check("kss_proxy_integer_1_9", raw.kss_like_sleepiness_score.between(1, 9).all() and raw.kss_like_sleepiness_score.mod(1).eq(0).all(), "Instrument-range proxy, not clinical validity")
    check("sp_proxy_integer_1_7", raw.samn_perelli_like_fatigue_score.between(1, 7).all() and raw.samn_perelli_like_fatigue_score.mod(1).eq(0).all(), "Instrument-range proxy, not clinical validity")
    check("waso_matches_awakening_count", raw.loc[raw.awakenings_count.eq(0), "main_sleep_waso_minutes"].eq(0).all() and (raw.main_sleep_waso_minutes + 60*TOL_HOURS >= 3*raw.awakenings_count).all(), "AllocatedWASO; minimum3minutes/awakening is simulator convention")
    check("nap_count_0_or_1", raw.nap_count.isin([0, 1]).all(), "Multiple naps deferred")
    check("no_nap_has_zero_minutes", raw.loc[raw.nap_count.eq(0), "nap_sleep_minutes_last_24h"].eq(0).all(), "Explicit synthetic absence, not unmeasured values")
    check("nap_missing_timestamps_match_none", raw.nap_start_time_utc.isna().eq(raw.nap_count.eq(0)).all() and raw.nap_end_time_utc.isna().eq(raw.nap_count.eq(0)).all(), "Null timestamps intentional only for simulatedno-nap")
    check("nap_durations_10_40", raw.loc[raw.nap_count.eq(1), "nap_sleep_minutes_last_24h"].between(10-60*TOL_HOURS, 40+60*TOL_HOURS).all(), "Frozen duration policy")
    check("goal_constant_metadata", raw.sleep_goal_hours.eq(8).all(), "Goal is not hidden sleep_need or a trained feature")
    check("budget_with_nap", (raw.main_sleep_opportunity_hours + raw.workload_hours + raw.exercise_minutes/60 + raw.nap_sleep_minutes_last_24h/60 <= 24+TOL_HOURS).all(), "No allocation exceeds24h")
    lookup = raw.set_index(["participant_id", "mission_day"])
    prior = []
    for lag in [3, 2, 1]:
        index = pd.MultiIndex.from_arrays([main.participant_id, main.mission_day-lag])
        prior.append(np.maximum(0, 8-lookup.reindex(index).total_sleep_last_24h_hours.to_numpy()))
    check("prior3_independent_day_key_verification", np.allclose(main.prior_3day_sleep_shortfall_hours, np.stack(prior).sum(axis=0), rtol=0, atol=TOL_HOURS), "Previous3nonoverlapping windows only")
    next_index = pd.MultiIndex.from_arrays([main.participant_id, main.mission_day+1])
    future = lookup.reindex(next_index)
    check("target_fatigue_unchanged_future_source", np.array_equal(main.target_next_day_fatigue_score, future.self_report_fatigue_score), "Next-day original custom self-report, includingday61")
    check("target_response_unchanged_future_source", np.array_equal(main.target_next_day_reaction_time_median_ms, future.reaction_time_median_ms), "Next-day original response median")
    check("original_lapse_protocol", raw.reaction_time_trials_count.eq(60).all() and raw.reaction_time_lapses_count.between(0, 60).all(), "Original60-response/500ms convention remains")
    sums = events.groupby("record_id").sleep_duration_minutes.sum() / 60
    check("sleep_event_totals", np.allclose(raw.total_sleep_last_24h_hours, raw.record_id.map(sums), rtol=0, atol=TOL_HOURS), "Event records independently sum to totals")
    starts = pd.to_datetime(events.sleep_start_time_utc, utc=True, format="ISO8601")
    ends = pd.to_datetime(events.sleep_end_time_utc, utc=True, format="ISO8601")
    cutoffs = events.record_id.map(raw.set_index("record_id").observation_timestamp_utc)
    cutoff = pd.to_datetime(cutoffs, utc=True, format="ISO8601")
    check("events_inside_causal_window", ((starts >= cutoff-pd.Timedelta(hours=24)) & (ends <= cutoff) & (ends > starts)).all(), "No future event enters current summary")
    check("event_lengths_match_timestamps", np.allclose((ends-starts).dt.total_seconds()/60, events.sleep_duration_minutes, rtol=0, atol=60*TOL_HOURS), "Recorded duration agrees with interval")
    check("metadata_not_model_features", not any(c.startswith("audit_") or "time_utc" in c or c in {"sleep_goal_hours", "nap_count"} for c in baseline_features + QUESTIONNAIRES + SLEEP), "Allowlist excludes latent/source/clockmetadata")
    check("participant_split_counts", main[["participant_id", "split"]].drop_duplicates().split.value_counts().to_dict() == {"train":84, "validation":18, "test":18}, "Original participant-disjoint split proportions")
    check("no_person_crosses_split", raw.groupby("participant_id").split.nunique().eq(1).all(), "No person leakage")
    return checks


def data_card():
    return """# EXP006: fresh synthetic measurement-extension cohort

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
"""


def generate():
    require(sha(PLAN) == PLAN_SHA, "Generation plan differs from frozen approval")
    require(sha(HERE / "EXPERIMENT_PLAN.json") == ROOT_PLAN_SHA, "Root experiment plan differs from frozen approval")
    require((np.__version__, pd.__version__) == ("2.3.5", "2.2.3"), "Use original NumPy/pandas versions")
    require(not (OUT / "main.csv").exists(), "Output cohort already exists; no automatic overwrite")
    original_paths = [ORIGINAL / name for name in ["source_generator.py", "astra_shield_synthetic_ml.csv", "raw_observations.csv", "task_config.json", "train.csv", "validation.csv", "test.csv"]]
    original_paths.append(AI / "artifacts" / "bundle.joblib")
    before = {str(path.relative_to(AI)): sha(path) for path in original_paths}
    baseline = json.loads((ORIGINAL / "task_config.json").read_text())["tasks"]["next_day_fatigue_classification"]["predictors"]
    require(len(baseline) == 26, "Expected original26feature contract")
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="exp006_generation_", dir=OUT) as temporary_name:
        stage = Path(temporary_name)
        base, raw, latent = prepare_base(stage / "base_source")
        audit_raw, events = extend(raw, latent)
        added = [c for c in audit_raw if c not in raw and not c.startswith("audit_")]
        main = base.merge(audit_raw[["record_id", *added]], on="record_id", validate="one_to_one", how="left")
        checks = validate(main, audit_raw, events, base, baseline)
        main.to_csv(stage / "main.csv", index=False, float_format="%.12g")
        audit_raw.to_csv(stage / "raw_audit.csv", index=False, float_format="%.17g")
        events.to_csv(stage / "sleep_segments.csv", index=False, float_format="%.17g")
        split_info = {}
        for name in ["train", "validation", "test"]:
            subset = main[main.split.eq(name)].reset_index(drop=True)
            file = stage / (name + ".csv")
            subset.to_csv(file, index=False, float_format="%.12g")
            split_info[name] = {"file": file.name, "sha256": sha(file), "rows": int(len(subset)), "participants": int(subset.participant_id.nunique())}
        bundles = {"baseline": baseline, "questionnaires_only": baseline+QUESTIONNAIRES,
                   "sleep_only": baseline+SLEEP, "combined": baseline+QUESTIONNAIRES+SLEEP}
        manifest = {"version": VERSION, "baseline_features": baseline,
                    "questionnaire_features": QUESTIONNAIRES, "sleep_features": SLEEP,
                    "extension_features": QUESTIONNAIRES+SLEEP, "all_features": bundles["combined"],
                    "feature_bundles": bundles, "target": "target_next_day_fatigue_class",
                    "group_column": "participant_id", "split_column": "split",
                    "timestamp_column": "observation_timestamp_utc",
                    "class_order": ["low", "moderate", "high"],
                    "excluded_columns": [c for c in main if c not in bundles["combined"]],
                    "audit_only_columns": [c for c in audit_raw if c.startswith("audit_")],
                    "generation_plan_sha256": PLAN_SHA, "root_plan_sha256": ROOT_PLAN_SHA,
                    "interpretation": "Synthetic instrument-range proxies and hypothetical sleep allocations; not validated measurements."}
        json_write(stage / "feature_manifest.json", manifest)
        split_manifest = {"generation_seed": 20261115, "extension_seed": 2026111501,
                          "version": VERSION, "target": manifest["target"],
                          "group_column": "participant_id", "split_column": "split",
                          "splits": split_info, "holdout_policy": "Use train for EDA/CV only; stage validation/test according to frozen root experiment plan."}
        json_write(stage / "split_manifest.json", split_manifest)
        (stage / "DATA_CARD.md").write_text(data_card(), encoding="utf-8")
        after = {str(path.relative_to(AI)): sha(path) for path in original_paths}
        require(before == after, "Original data/model changed during generation")
        quality = {"status": "passed", "checks_passed": len(checks), "checks_failed": 0,
                   "checks": checks, "main_rows": len(main), "main_columns": len(main.columns),
                   "raw_rows": len(audit_raw), "raw_columns": len(audit_raw.columns),
                   "sleep_segments": len(events), "rows_deleted": 0, "values_imputed": 0,
                   "scope": "All-cohort computational/causal invariants only; no held-out outcome statistics or model performance inspected.",
                   "original_data_and_model_unchanged": True, "clinical_validation": False,
                   "base_seed": 20261115, "extension_seed": 2026111501,
                   "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
                   "generated_at_utc": datetime.now(timezone.utc).isoformat()}
        json_write(stage / "generation_quality.json", quality)
        for path in sorted(stage.iterdir()):
            target = OUT / path.name
            require(not target.exists(), "Refusing to overwrite existing experiment output: " + str(target))
            shutil.move(str(path), str(target))
    hashes = {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "hash_manifest.json"}
    json_write(OUT / "hash_manifest.json", {"files": hashes, "original_before_sha256": before,
               "original_after_sha256": after, "generator_sha256": sha(Path(__file__)),
               "generation_plan_sha256": PLAN_SHA, "root_plan_sha256": ROOT_PLAN_SHA})
    print(json.dumps({"status": "passed", "checks_passed": len(checks), "rows": len(main),
                      "features": {k: len(v) for k,v in bundles.items()}, "original_unchanged": True,
                      "manifest": str(OUT / "feature_manifest.json")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-worker", nargs=2, metavar=("SOURCE", "DESTINATION"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.base_worker:
        base_worker(Path(args.base_worker[0]).resolve(), Path(args.base_worker[1]).resolve())
    else:
        try:
            generate()
        except Exception as exc:
            OUT.mkdir(exist_ok=True)
            json_write(OUT / "generation_failure.json", {"status": "aborted", "error": str(exc),
                       "no_automatic_repair": True, "plan_sha256": PLAN_SHA})
            raise
