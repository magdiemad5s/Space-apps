#!/usr/bin/env python3
"""Audit the frozen simulator by observing an unmodified deterministic replay.

Run once from any directory: python /path/to/replay/audit_replay.py
Requires the original NumPy 2.3.5 and pandas 2.2.3 environment.
Only this audit directory and its temporary child directory are written.
No training, feature selection, label changes or clinical validation occurs.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
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
DATA = HERE.parents[2] / "data"
EXPECTED_SOURCE_SHA256 = "e4a914c3fdd01bc6032ad39b2e61967c416408558e5015664286083b80ac01fa"
GENERATED_FILES = (
    "raw_observations.csv", "astra_shield_synthetic_ml.csv",
    "participant_splits.csv", "data_dictionary.csv", "task_config.json",
    "generation_metadata.json", "source_manifest.csv",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class Checks:
    def __init__(self):
        self.values = {}

    def add(self, name, passed, record_id=None):
        item = self.values.setdefault(name, {"checked": 0, "failed": 0, "examples": []})
        item["checked"] += 1
        if not bool(passed):
            item["failed"] += 1
            if record_id is not None and len(item["examples"]) < 8:
                item["examples"].append(str(record_id))


def trace_anchors(source: Path) -> dict:
    """Use unique AST statements, with an exact source hash as the first guard."""
    if digest(source) != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("Frozen generator hash differs; review this audit before running it.")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "generate"]
    if len(functions) != 1:
        raise RuntimeError("Expected exactly one generate function")
    function = functions[0]

    def assignment(target):
        candidates = [n.lineno for n in ast.walk(function) if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == target for t in n.targets)]
        if len(candidates) != 1:
            raise RuntimeError(f"Ambiguous assignment anchor: {target}")
        return candidates[0]

    append = [n.lineno for n in ast.walk(function) if isinstance(n, ast.Expr)
              and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute)
              and isinstance(n.value.func.value, ast.Name)
              and n.value.func.value.id == "records" and n.value.func.attr == "append"]
    replacement = [n.lineno for n in ast.walk(function) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                           and t.value.id == "rt_trials" for t in n.targets)]
    if len(append) != 1 or len(replacement) != 1:
        raise RuntimeError("Ambiguous response-array or record-append anchor")
    return {"day_start": assignment("calibration"), "after_initial_efficiency": assignment("latency"),
            "before_rt_replacement": replacement[0], "before_record_append": append[0]}


def worker(source: Path, temporary: Path) -> None:
    """Runs in its own process; never substitutes or wraps the generator's RNG."""
    anchors = trace_anchors(source)
    checks = Checks()
    summaries = []
    initial_states = []
    seen = set()
    pending = {}

    def trace(frame, event, arg):
        if frame.f_code.co_filename != str(source) or frame.f_code.co_name != "generate":
            return None
        if event != "line":
            return trace
        loc = frame.f_locals
        line = frame.f_lineno
        if line == anchors["day_start"]:
            pending.clear()
            pending.update({"previous_latent_stress": float(loc["stress"]),
                            "previous_latent_fatigue": float(loc["fatigue"]),
                            "previous_latent_circadian_minutes": float(loc["circadian"])})
            if int(loc["day"]) == -6:
                initial_states.append({"participant_id": loc["pid"], "split": loc["split"],
                    "hidden_hr_base_bpm": float(loc["hr_base"]),
                    "hidden_hrv_base_ms": float(loc["hrv_base"]),
                    "hidden_rt_base_ms": float(loc["rt_base"]),
                    "hidden_sleep_need_hours": float(loc["sleep_need"]), **pending})
        elif line == anchors["after_initial_efficiency"]:
            pending["initial_sleep_efficiency_pct"] = float(loc["efficiency"])
        elif line == anchors["before_rt_replacement"]:
            pending["rt_before_replacement"] = loc["rt_trials"].copy()
        elif line == anchors["before_record_append"]:
            record_id = f"{loc['pid']}_D{loc['day']:+04d}"
            # CPython can revisit a multi-line call; capture each session once.
            if record_id in seen:
                return trace
            seen.add(record_id)
            rt = np.array(loc["rt_trials"], dtype=np.float64, copy=True)
            mask = np.array(loc["lapse_mask"], dtype=bool, copy=True)
            before = pending["rt_before_replacement"]
            actual_median = float(np.median(rt))
            clipped_median = round(float(np.clip(actual_median, 150, 800)), 3)
            lapses500 = int(np.count_nonzero(rt >= 500))
            lapses355 = int(np.count_nonzero(rt >= 355))
            cap = 100 * loc["sleep"] / (loc["sleep"] + (loc["latency"] + 3 * loc["awakenings"]) / 60)
            floored_cap = float(np.floor(cap * 1000) / 1000)
            checks.add("rt_array_shape_60", rt.shape == (60,), record_id)
            checks.add("rt_array_finite_positive", np.isfinite(rt).all() and (rt > 0).all(), record_id)
            checks.add("rt_median_from_same_trials_clip_then_round3", clipped_median == loc["rt"], record_id)
            checks.add("rt_lapses_from_same_unrounded_trials_ge500", lapses500 == loc["lapses"], record_id)
            checks.add("rt_unmasked_draws_unchanged", np.array_equal(rt[~mask], before[~mask]), record_id)
            checks.add("rt_injected_draws_in_500_1100", ((rt[mask] >= 500) & (rt[mask] < 1100)).all(), record_id)
            checks.add("rt_count_is_masked_plus_natural_lapses",
                       lapses500 == int(mask.sum()) + int(np.count_nonzero(rt[~mask] >= 500)), record_id)
            checks.add("rt_log_median_parameter_equation",
                       loc["trial_median"] == loc["rt_base"] + 11*loc["fatigue"] + 3*loc["stress"] + abs(loc["circadian"])*.08,
                       record_id)
            checks.add("rt_lapse_injection_probability_equation",
                       loc["lapse_probability"] == np.clip(.005 + .0055*loc["fatigue"] + .002*loc["stress"], .005, .16), record_id)
            checks.add("attention_probability_bounds", .65 <= loc["attention_prob"] <= .995, record_id)
            checks.add("attention_correct_integer_0_40", isinstance(loc["correct"], int) and 0 <= loc["correct"] <= 40, record_id)
            checks.add("efficiency_cap_formula", cap == loc["max_efficiency"], record_id)
            checks.add("efficiency_min_with_downward_rounded_cap",
                       loc["efficiency"] == min(pending["initial_sleep_efficiency_pct"], floored_cap), record_id)
            checks.add("latent_state_bounds", 0 <= loc["stress"] <= 10 and 0 <= loc["fatigue"] <= 10 and -180 <= loc["circadian"] <= 180, record_id)
            checks.add("reported_scores_in_bounds_and_round3",
                       all(0 <= loc[k] <= 10 and round(loc[k], 3) == loc[k] for k in ["stress_report", "fatigue_report", "mood_report"]), record_id)
            checks.add("no_injected_events_during_calibration", not loc["calibration"] or loc["event"] == 0, record_id)
            row = {"record_id": record_id, "participant_id": loc["pid"], "mission_day": int(loc["day"]),
                   "split": loc["split"], "is_calibration": bool(loc["calibration"]),
                   "latent_stress": float(loc["stress"]), "latent_fatigue": float(loc["fatigue"]),
                   "latent_circadian_minutes": float(loc["circadian"]),
                   "hidden_duty_pressure": float(loc["duty_pressure"]),
                   "hidden_sleep_need_hours": float(loc["sleep_need"]),
                   **{k: v for k, v in pending.items() if k != "rt_before_replacement"},
                   "sleep_duration_hours": loc["sleep"], "sleep_onset_delay_minutes": loc["latency"],
                   "awakenings_count": loc["awakenings"], "sleep_efficiency_pct": loc["efficiency"],
                   "sleep_efficiency_cap_unrounded_pct": cap,
                   "sleep_midpoint_deviation_minutes": round(float(loc["circadian"]), 3),
                   "workload_hours": loc["workload"], "exercise_minutes": loc["exercise"],
                   "self_report_stress_score": loc["stress_report"],
                   "self_report_fatigue_score": loc["fatigue_report"], "self_report_mood_score": loc["mood_report"],
                   "target_current_physiology_event_injected": loc["event"],
                   "resting_heart_rate_bpm": loc["hr"], "hrv_rmssd_ms": loc["hrv"],
                   "rt_population_median_before_replacement_ms": float(loc["trial_median"]),
                   "rt_lapse_injection_probability": float(loc["lapse_probability"]),
                   "rt_injected_response_count": int(mask.sum()),
                   "rt_natural_unmasked_lapses_ge500_count": int(np.count_nonzero(rt[~mask] >= 500)),
                   "rt_unclipped_median_ms": actual_median, "reaction_time_median_ms": clipped_median,
                   "reaction_time_lapses_count": lapses500, "reaction_time_trials_count": int(rt.size),
                   "counterfactual_lapses_ge355_count": lapses355,
                   "rt_min_ms": float(rt.min()), "rt_max_ms": float(rt.max()),
                   "rt_array_sha256_float64_little_endian": hashlib.sha256(rt.astype("<f8", copy=False).tobytes()).hexdigest(),
                   "attention_probability": float(loc["attention_prob"]),
                   "attention_correct_count": loc["correct"], "attention_trials_count": 40,
                   "attention_accuracy_pct": round(loc["correct"] / 40 * 100, 3),
                   "target_journal_stress_class": loc["journal_level"]}
            summaries.append(row)
        return trace

    sys.settrace(trace)
    try:
        runpy.run_path(str(source), run_name="__main__")
    finally:
        sys.settrace(None)
    pd.DataFrame(summaries).to_csv(temporary / "recovered_session_summary.csv", index=False, float_format="%.17g")
    pd.DataFrame(initial_states).to_csv(temporary / "recovered_initial_states.csv", index=False, float_format="%.17g")
    write_json(temporary / "trace_checks.json", {"anchors": anchors, "checks": checks.values,
                "sessions_captured": len(summaries), "initial_states_captured": len(initial_states)})


def audit() -> dict:
    source = DATA / "source_generator.py"
    trace_anchors(source)
    before = {name: digest(DATA / name) for name in GENERATED_FILES}
    before["source_generator.py"] = digest(source)
    environment = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}
    if (np.__version__, pd.__version__) != ("2.3.5", "2.2.3"):
        raise RuntimeError("Use NumPy2.3.5 and pandas2.2.3 to audit exact original reproduction.")
    with tempfile.TemporaryDirectory(prefix="replay_work_", dir=HERE) as temporary_name:
        temporary = Path(temporary_name)
        copied = temporary / "source_generator.py"
        shutil.copyfile(source, copied)
        process = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", str(copied), str(temporary)],
                                 cwd=temporary, capture_output=True, text=True, timeout=300)
        if process.returncode:
            raise RuntimeError("Fresh-process generator replay failed:\n" + process.stderr[-8000:])
        write_json(HERE / "generator_run_summary.json", json.loads(process.stdout))
        trace_result = json.loads((temporary / "trace_checks.json").read_text())
        checks = Checks()
        checks.values.update(trace_result["checks"])
        checks.add("captured_exactly_8160_unique_sessions", trace_result["sessions_captured"] == 8160)
        checks.add("captured_120_initial_states", trace_result["initial_states_captured"] == 120)
        matches = {}
        for name in GENERATED_FILES:
            output_hash = digest(temporary / name)
            matches[name] = {"frozen_sha256": before[name], "replayed_sha256": output_hash,
                             "byte_equal": (temporary / name).read_bytes() == (DATA / name).read_bytes()}
            checks.add("byte_exact_" + name, matches[name]["byte_equal"])
        summary = pd.read_csv(temporary / "recovered_session_summary.csv")
        raw = pd.read_csv(DATA / "raw_observations.csv")
        joined = raw.merge(summary, on="record_id", how="outer", suffixes=("_original", "_replay"), validate="one_to_one", indicator=True)
        checks.add("all_raw_rows_have_trace_summary", joined["_merge"].eq("both").all())
        shared = [c for c in raw.columns if c in summary.columns and c != "record_id"]
        for name in shared:
            a, b = joined[name + "_original"], joined[name + "_replay"]
            equal = np.isclose(a, b, rtol=0, atol=1e-12) if pd.api.types.is_numeric_dtype(a) else a.eq(b).to_numpy()
            for record_id, passed in zip(joined.record_id, equal):
                checks.add("trace_matches_original_" + name, passed, record_id)
        for row in pd.read_csv(temporary / "recovered_initial_states.csv").to_dict("records"):
            checks.add("initial_hidden_parameter_ranges",
                       52 <= row["hidden_hr_base_bpm"] < 76 and 32 <= row["hidden_hrv_base_ms"] < 76
                       and 225 <= row["hidden_rt_base_ms"] < 295 and 7.4 <= row["hidden_sleep_need_hours"] < 8.5
                       and 1.3 <= row["previous_latent_fatigue"] < 3.5 and 1.6 <= row["previous_latent_stress"] < 3.6,
                       row["participant_id"])
        after = {name: digest(DATA / name) for name in before}
        checks.add("frozen_source_and_seven_files_unchanged", before == after)
        main = summary[summary.mission_day.between(1, 60)]
        diagnostic = {}
        for label, frame in [("raw_8160_sessions", summary), ("main_7200_sessions", main)]:
            diagnostic[label] = {
                "sessions": int(len(frame)),
                "responses_recovered": int(frame.reaction_time_trials_count.sum()),
                "lapses_ge500_min": int(frame.reaction_time_lapses_count.min()),
                "lapses_ge500_max": int(frame.reaction_time_lapses_count.max()),
                "responses_ge500_total": int(frame.reaction_time_lapses_count.sum()),
                "injected_responses_total": int(frame.rt_injected_response_count.sum()),
                "natural_unmasked_lapses_ge500_total": int(frame.rt_natural_unmasked_lapses_ge500_count.sum()),
                "median_clipping_changed_sessions": int(((frame.rt_unclipped_median_ms < 150) | (frame.rt_unclipped_median_ms > 800)).sum()),
                "counterfactual_355_differs_from_original_count_sessions": int(frame.counterfactual_lapses_ge355_count.ne(frame.reaction_time_lapses_count).sum()),
                "median_ge355_and_original_500_lapses_fewer_than30_sessions": int(((frame.reaction_time_median_ms >= 355) & (frame.reaction_time_lapses_count < 30)).sum()),
                "counterfactual_note": "355ms counts are diagnostic only; the original protocol and model remain at >=500ms. No columns or targets were changed.",
            }
        for name in ["recovered_session_summary.csv", "recovered_initial_states.csv"]:
            shutil.copyfile(temporary / name, HERE / name)
        passed = all(item["failed"] == 0 for item in checks.values.values())
        result = {
            "status": "passed" if passed else "failed",
            "scope": "Deterministic source replay and internal numeric consistency only; no model fitting, selection or evaluation.",
            "method": "Original generator copied byte-for-byte into a fresh temporary directory, executed once in a fresh Python process. sys.settrace observes existing locals only; no RNG calls or replacement RNG are introduced by the audit.",
            "provenance": "Recovered session summaries and latent initial states are new audit artifacts from deterministic replay. They were not originally exported measurements and must not be added to model inputs.",
            "source_sha256": EXPECTED_SOURCE_SHA256, "environment": environment,
            "trace_anchors": trace_result["anchors"], "file_comparisons": matches,
            "check_groups": len(checks.values),
            "individual_assertions": sum(item["checked"] for item in checks.values.values()),
            "failed_assertions": sum(item["failed"] for item in checks.values.values()),
            "checks": checks.values, "diagnostics": diagnostic,
            "frozen_inputs_unchanged": before == after,
            "unverifiable_or_not_established": [
                "Replay consistency does not establish human physiology, clinical validity, NASA approval, or operational safety; all inputs/labels are synthetic.",
                "The hidden stochastic states and random response arrays are reproducible from this generator/environment, not recoverable uniquely from the original aggregate CSV alone.",
                "The generator's custom continuous0-10 fatigue/stress/mood values are not KSS1-9 or Samn-Perelli1-7 responses; neither scale can be validly backfilled or inferred from these values.",
                "Actual bedtime, sleep-onset/final-wake timestamps, naps, WASO, total sleep in a timed24-hour window and continuous time awake were not measured or explicitly generated. The efficiency cap does not establish their real values.",
                "The hidden sleep_need is a sampled simulator parameter, not a measured personal sleep requirement; calibration mean sleep is not an equivalent target. Clinical sleep-debt validity is untested.",
                "The 60-response task has no simulated stimulus intervals, elapsed session duration, anticipatory-response events or PVT false-start measurement. Its values do not validate a real timed PVT/PVT-B protocol.",
                "Attention count is a stochastic Binomial draw with40 trials, not equal to40 times its probability; its percentage need not equal the probability parameter.",
                "Counterfactual355ms counts do not change the original500ms lapse definition and cannot support silently applying a PVT-B protocol to the trained model.",
            ],
        }
        write_json(HERE / "checks.json", result)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", nargs=2, metavar=("SOURCE_COPY", "TEMP_DIRECTORY"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(Path(args.worker[0]).resolve(), Path(args.worker[1]).resolve())
    else:
        try:
            result = audit()
        except Exception as exc:
            write_json(HERE / "checks.json", {"status": "error", "error": str(exc),
                       "scope": "Audit did not complete; do not infer a pass. Frozen data/model were not modified by this script."})
            raise
        print(json.dumps({k: result[k] for k in ["status", "check_groups", "individual_assertions", "failed_assertions", "frozen_inputs_unchanged"]}, indent=2))
        sys.exit(0 if result["status"] == "passed" else 1)
