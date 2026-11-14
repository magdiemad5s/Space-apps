"""Freeze participant-disjoint partitions without selecting models on test data."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

import numpy as np
import pandas as pd

from .features import FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT.parent / "astra_shield_data/synthetic_demo")
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    source, out = args.source, args.output
    config = json.loads((source / "task_config.json").read_text())
    path = source / config["dataset"]
    frame = pd.read_csv(path)
    assert not frame.isna().any().any(), "Missing source cells"
    assert np.isfinite(frame.select_dtypes("number")).all().all()
    assert frame.record_id.is_unique
    assert frame.is_synthetic.eq(1).all() and frame.data_origin.eq("synthetic").all()
    assert frame.groupby("participant_id").split.nunique().eq(1).all()
    assert set(frame.split) == {"train", "validation", "test"}
    assert frame.groupby("participant_id").mission_day.apply(lambda s: s.sort_values().diff().dropna().eq(1).all()).all()
    cutoff = pd.to_datetime(frame.observation_timestamp_utc, utc=True)
    target = pd.to_datetime(frame.target_timestamp_utc, utc=True)
    assert (target - cutoff).eq(pd.Timedelta(hours=24)).all()
    assert config["tasks"]["next_day_fatigue_classification"]["predictors"] == FEATURE_COLUMNS
    for task in config["tasks"].values():
        assert set(task["predictors"]).issubset(frame.columns)
        assert not any(c.startswith("target_") for c in task["predictors"])
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"dataset_file": path.name, "dataset_sha256": sha256(path),
                "task_config_sha256": sha256(source / "task_config.json"),
                "data_origin": "synthetic", "seed": config["seed"],
                "partition_policy": "Frozen participant-disjoint splits; test is evaluation-only",
                "splits": {}}
    for split in ("train", "validation", "test"):
        subset = frame[frame.split.eq(split)].copy()
        dest = out / f"{split}.csv"
        if dest.exists():
            existing = pd.read_csv(dest)
            pd.testing.assert_frame_equal(existing, subset.reset_index(drop=True), check_dtype=False, rtol=1e-9, atol=1e-9)
        else:
            subset.to_csv(dest, index=False, float_format="%.6f")
        manifest["splits"][split] = {"file": dest.name, "sha256": sha256(dest), "rows": len(subset),
                                      "participants": subset.participant_id.nunique()}
    for name in ("task_config.json", "data_dictionary.csv", "participant_splits.csv"):
        shutil.copy2(source / name, out / name)
    (out / "split_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
