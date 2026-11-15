#!/usr/bin/env python3
"""Export unchanged selected models without platform-specific research snapshots.

Export must run in the original compatible Linux model environment. Validation
can run on Windows without opening the research bundle or any dataset. Nothing
in this script fits, tunes, selects or evaluates model accuracy.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai"))
RETAINED_KEYS = ("format_version", "models", "task_config", "metadata", "reference_values",
                 "training_feature_ranges", "model_information")
REMOVED_KEYS = ("baselines", "ablation_models", "ablation_predictors")
EXPECTED_ORIGINAL_SHA256 = "7731618ad68c0302338bcb4e869820601f8a43f735c8f7480fe19a121c500706"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def reject_xgboost_objects(value):
    """Inspect the actual retained object graph, allowing textual research metadata."""
    import numpy as np
    seen = set()
    count = 0

    def visit(item):
        nonlocal count
        if id(item) in seen:
            return
        seen.add(id(item))
        count += 1
        if type(item).__module__.split(".")[0] == "xgboost":
            raise AssertionError("XGBoost object remains in deployment artifact: " + type(item).__name__)
        if isinstance(item, dict):
            for key, value in item.items():
                visit(key)
                visit(value)
        elif isinstance(item, (tuple, list, set, frozenset)):
            for child in item:
                visit(child)
        elif isinstance(item, np.ndarray):
            if item.dtype.hasobject:
                for child in item.flat:
                    visit(child)
        elif not isinstance(item, (type, str, bytes, int, float, bool, type(None))) and hasattr(item, "__dict__"):
            visit(vars(item))

    visit(value)
    return count


def canonical_state(value):
    """Hash learned values and type/layout information, excluding unused padding."""
    import numpy as np
    from sklearn.base import BaseEstimator
    from sklearn.tree import _tree
    if isinstance(value, np.ndarray) and value.dtype.names:
        return {"structured_array": True, "shape": value.shape, "dtype_description": value.dtype.descr,
                "itemsize": value.dtype.itemsize, "field_names": value.dtype.names,
                "fields": {name: canonical_state(np.ascontiguousarray(value[name])) for name in value.dtype.names}}
    if isinstance(value, (_tree.Tree, BaseEstimator)):
        return {"class": type(value).__module__ + "." + type(value).__qualname__,
                "state": canonical_state(value.__getstate__())}
    if isinstance(value, dict):
        return {key: canonical_state(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical_state(item) for item in value]
    if isinstance(value, tuple):
        return tuple(canonical_state(item) for item in value)
    return value


def audit_tree_padding(left, right):
    """Prove raw hash changes occur only in unused C-structure padding bytes."""
    import numpy as np
    from sklearn.base import BaseEstimator
    from sklearn.tree import _tree
    counts = {"trees_compared": 0, "trees_with_padding_byte_differences": 0}

    def walk(a, b):
        if type(a) is not type(b):
            raise AssertionError("Estimator state types changed.")
        if isinstance(a, _tree.Tree):
            counts["trees_compared"] += 1
            sa, sb = a.__getstate__(), b.__getstate__()
            if sa.keys() != sb.keys():
                raise AssertionError("Tree state fields changed.")
            for name in sa:
                if name != "nodes":
                    np.testing.assert_array_equal(sa[name], sb[name])
            na, nb = sa["nodes"], sb["nodes"]
            if na.dtype != nb.dtype or na.shape != nb.shape:
                raise AssertionError("Tree node type or dimensions changed.")
            used = np.zeros(na.dtype.itemsize, dtype=bool)
            for name in na.dtype.names:
                np.testing.assert_array_equal(na[name], nb[name])
                dtype, offset = na.dtype.fields[name][:2]
                used[offset:offset + dtype.itemsize] = True
            raw_a = np.frombuffer(na.tobytes(), dtype=np.uint8).reshape(len(na), na.dtype.itemsize)
            raw_b = np.frombuffer(nb.tobytes(), dtype=np.uint8).reshape(len(nb), nb.dtype.itemsize)
            if np.any(raw_a[:, used] != raw_b[:, used]):
                raise AssertionError("A learned tree-node byte changed.")
            if np.any(raw_a[:, ~used] != raw_b[:, ~used]):
                counts["trees_with_padding_byte_differences"] += 1
        elif isinstance(a, BaseEstimator):
            walk(vars(a), vars(b))
        elif isinstance(a, dict):
            if a.keys() != b.keys():
                raise AssertionError("Estimator state keys changed.")
            for name in a:
                walk(a[name], b[name])
        elif isinstance(a, (tuple, list)):
            if len(a) != len(b):
                raise AssertionError("Estimator state lengths changed.")
            for aa, bb in zip(a, b):
                walk(aa, bb)

    walk(left, right)
    return counts


def compare_reference(expected, actual, path="root", *, atol=1e-8, rtol=1e-7):
    """Compare every field, including every SHAP contribution, across platforms."""
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if type(expected) is not type(actual) or expected != actual:
            raise AssertionError(f"Reference mismatch at {path}: {actual!r} != {expected!r}")
    elif isinstance(expected, (int, float)):
        if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isclose(expected, actual, abs_tol=atol, rel_tol=rtol):
            raise AssertionError(f"Numeric reference mismatch at {path}: {actual!r} != {expected!r}")
    elif isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise AssertionError(f"Reference keys differ at {path}")
        for name, value in expected.items():
            compare_reference(value, actual[name], path + "." + name, atol=atol, rtol=rtol)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise AssertionError(f"Reference list differs at {path}")
        for index, (left, right) in enumerate(zip(expected, actual)):
            compare_reference(left, right, f"{path}[{index}]", atol=atol, rtol=rtol)
    else:
        raise TypeError("Unsupported reference value at " + path)


def validate_deployment(artifact, reference):
    """Portable preflight: deployment + small golden reference only; no research data."""
    from astra_shield_ml.service import ModelService
    reference = json.loads(Path(reference).read_text(encoding="utf-8"))
    if sha(artifact) != reference["deployment_model_sha256"]:
        raise AssertionError("Deployment artifact hash differs from the golden reference.")
    service = ModelService(artifact)
    visited = reject_xgboost_objects(service.bundle)
    for case in reference["cases"]:
        compare_reference(case["expected"], service.predict(case["request"]), case["record_id"])
    return {"passed": True, "platform": sys.platform, "case_count": len(reference["cases"]),
            "absolute_tolerance": 1e-8, "relative_tolerance": 1e-7,
            "deployment_model_sha256": sha(artifact), "object_graph_nodes_checked": visited,
            "scope": "All five selected tasks, class probabilities and every TreeSHAP contribution; numerical portability, not accuracy"}


def export(artifact, manifest_path, reference_path, report_path):
    import joblib
    import pandas as pd
    from astra_shield_ml.features import INPUT_FIELDS, OPTIONAL_FIELDS, build_request_from_history
    from astra_shield_ml.service import ModelService, REQUIRED_TASKS

    original = ROOT / "ai/artifacts/bundle.joblib"
    original_hash = sha(original)
    if original_hash != EXPECTED_ORIGINAL_SHA256:
        raise AssertionError("Original model hash differs from the reviewed frozen artifact.")
    bundle = joblib.load(original)
    if set(bundle) != set(RETAINED_KEYS) | set(REMOVED_KEYS):
        raise AssertionError("Unexpected research-bundle keys; review before exporting.")
    selected = {key: bundle[key] for key in RETAINED_KEYS}
    if set(selected["models"]) != set(REQUIRED_TASKS):
        raise AssertionError("Exactly the five previously selected tasks must be retained.")
    graph_count = reject_xgboost_objects(selected)
    before = {key: joblib.hash(selected[key], hash_name="sha1") for key in RETAINED_KEYS}
    artifact.parent.mkdir(parents=True, exist_ok=True)
    # Reuse an existing equivalent artifact for stable file identity on repeat
    # exports. Tree-node padding can differ on allocation, with no learned-value
    # changes; the exact learned-state checks below must still pass every time.
    if not artifact.exists():
        joblib.dump(selected, artifact, compress=3, protocol=4)
    loaded = joblib.load(artifact)
    after = {key: joblib.hash(loaded[key], hash_name="sha1") for key in RETAINED_KEYS}
    canonical_before = {key: joblib.hash(canonical_state(selected[key]), hash_name="sha1") for key in RETAINED_KEYS}
    canonical_after = {key: joblib.hash(canonical_state(loaded[key]), hash_name="sha1") for key in RETAINED_KEYS}
    if canonical_before != canonical_after:
        raise AssertionError("Retained learned-state hashes changed during serialization.")
    padding_audit = audit_tree_padding(selected, loaded)
    reject_xgboost_objects(loaded)
    deployment_hash = sha(artifact)
    print(json.dumps({"deployment_model": str(artifact), "deployment_model_sha256": deployment_hash,
                      "original_model_sha256": original_hash, "retained_canonical_key_hashes_equal": True}), flush=True)

    # Stronger than a string search: unpickle in a fresh interpreter where any
    # attempted XGBoost import fails. Research metadata may mention its name.
    blocked_import = """import importlib.abc,sys,joblib
class BlockXGB(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'xgboost' or fullname.startswith('xgboost.'):
            raise ImportError('XGBoost deliberately unavailable during deployment proof')
sys.meta_path.insert(0, BlockXGB())
bundle = joblib.load(sys.argv[1])
assert len(bundle['models']) == 5
assert not any(name == 'xgboost' or name.startswith('xgboost.') for name in sys.modules)
print('deployment unpickles without XGBoost')
"""
    proof = subprocess.run([sys.executable, "-c", blocked_import, str(artifact)], cwd=ROOT,
                           text=True, capture_output=True, timeout=60, check=True)

    # Only this training CSV is read. Stratification is a coverage check, not
    # accuracy evaluation, threshold selection or model selection.
    train_path = ROOT / "ai/data/train.csv"
    train = pd.read_csv(train_path)
    if set(train["split"]) != {"train"}:
        raise AssertionError("Equivalence sample must contain training observations only.")
    grouped = train.groupby("target_next_day_fatigue_class", sort=True)
    sample = pd.concat([group.sample(n=43 if i < 2 else 42, random_state=20261115)
                        for i, (_, group) in enumerate(grouped)]).sort_values("record_id")
    if len(sample) != 128 or sample["record_id"].duplicated().any():
        raise AssertionError("Expected 128 unique training samples.")
    source_service, deployment_service = ModelService(original), ModelService(artifact)
    cases = []
    for row in sample.to_dict("records"):
        request = {key: row[key] for key in list(INPUT_FIELDS) + sorted(OPTIONAL_FIELDS) if key in row}
        request["awakenings_count"] = int(request["awakenings_count"])
        request["reaction_time_lapses_count"] = int(request["reaction_time_lapses_count"])
        cases.append((row["record_id"], request, "train"))
    fixture_path = ROOT / "ai/integration/backend_review/proposed_backend/examples/synthetic_daily_sequence.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    canonical = [{**{key: value for key, value in row.items() if key != "astronaut_id"},
                  "participant_id": row["astronaut_id"]} for row in fixture]
    for index in (7, 8):
        request = build_request_from_history(canonical[index], canonical[:7], canonical[:index])
        cases.append(("synthetic_fixture_day_" + str(index + 1), request, "synthetic_fixture"))

    labels, journal_labels, outliers = Counter(), Counter(), Counter()
    golden = []
    golden_labels = Counter()
    exact_count = 0
    for record_id, request, origin in cases:
        expected = source_service.predict(request)
        actual = deployment_service.predict(request)
        if actual == expected:
            exact_count += 1
        compare_reference(expected, actual, record_id, atol=1e-12, rtol=1e-12)
        labels[expected["label"]] += 1
        journal_labels[str(expected["current_observation"]["journal"]["stress_class"])] += 1
        outliers[str(expected["current_observation"]["physiology"]["outlier_flag"])] += 1
        if origin == "train" and golden_labels[expected["label"]] < 2:
            golden.append({"record_id": record_id, "request": request, "expected": expected})
            golden_labels[expected["label"]] += 1
    if set(labels) != {"low", "moderate", "high"} or len(golden) != 6:
        raise AssertionError("Equivalence cases must cover all three predicted fatigue classes.")
    if sha(original) != original_hash:
        raise AssertionError("Original model artifact changed.")
    write_json(reference_path, {"schema_version": 1, "source_partition": "train",
        "original_model_sha256": original_hash, "deployment_model_sha256": deployment_hash,
        "comparison": {"absolute_tolerance": 1e-8, "relative_tolerance": 1e-7}, "cases": golden})
    manifest = {"schema_version": 1, "purpose": "Portable inference-only export; no retraining or model changes",
        "original_model_sha256": original_hash, "deployment_model_sha256": deployment_hash,
        "retained_keys": list(RETAINED_KEYS), "removed_research_keys": list(REMOVED_KEYS),
        "retained_key_canonical_joblib_sha1": canonical_before, "canonical_key_hashes_equal": canonical_before == canonical_after,
        "raw_serialized_key_hashes_equal": before == after,
        "raw_hash_difference_explanation": "RandomForest/IsolationForest C tree-node padding bytes at offsets 57..63 are unused and can change on allocation; every named node field, node value, shape, dtype, depth and node count is checked exactly. All remaining estimator state is included in canonical hashes.",
        "selected_tasks": list(REQUIRED_TASKS), "inference_reference_sha256": sha(reference_path),
        "xgboost_objects_present": False, "xgboost_import_blocked_load_passed": True,
        "original_model_unchanged": True, "model_training_performed": False}
    write_json(manifest_path, manifest)
    report = {"passed": True, "platform": sys.platform, "scope": "Deployment serialization equivalence, not model accuracy",
        **manifest, "train_csv_sha256": sha(train_path), "sample_count": len(cases),
        "raw_before_joblib_sha1": before, "raw_after_joblib_sha1": after,
        "canonical_after_joblib_sha1": canonical_after, "tree_padding_audit": padding_audit,
        "training_sample_count": 128, "fixture_sample_count": 2, "heldout_files_read": [],
        "training_record_ids": sample["record_id"].tolist(),
        "full_response_exact_match_count": exact_count, "full_response_tolerance_match_count": len(cases),
        "local_numeric_absolute_tolerance": 1e-12, "local_numeric_relative_tolerance": 1e-12,
        "numeric_tolerance_reason": "Parallel RandomForest probability reductions may differ at floating-point rounding precision despite identical learned state.",
        "fatigue_class_counts": dict(labels),
        "journal_class_counts": dict(journal_labels), "physiology_outlier_counts": dict(outliers),
        "all_five_tasks_equal": True, "all_class_probabilities_equal": True,
        "all_treeshap_values_equal": True, "object_graph_nodes_checked": graph_count,
        "fresh_process_xgboost_block_test": proof.stdout.strip(),
        "export_script_sha256": sha(__file__), "reference_validation": validate_deployment(artifact, reference_path)}
    write_json(report_path, report)
    print(json.dumps({"passed": True, "comparison_cases": len(cases), "reference_cases": len(golden),
                      "deployment_model_sha256": deployment_hash, "report": str(report_path)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=ROOT / "desktop/artifacts/inference_bundle.joblib")
    parser.add_argument("--manifest", type=Path, default=ROOT / "desktop/artifacts/inference_manifest.json")
    parser.add_argument("--reference", type=Path, default=ROOT / "desktop/artifacts/inference_reference.json")
    parser.add_argument("--report", type=Path, default=ROOT / "integration-reports/DEPLOYMENT_MODEL_EQUIVALENCE.json")
    parser.add_argument("--validate-only", action="store_true", help="Load deployment and golden references only; portable Windows preflight")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps(validate_deployment(args.artifact, args.reference), indent=2))
    else:
        export(args.artifact, args.manifest, args.reference, args.report)


if __name__ == "__main__":
    main()
