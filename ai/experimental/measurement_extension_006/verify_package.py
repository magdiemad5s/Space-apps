#!/usr/bin/env python3
"""Verify the saved experiment and its protected originals without model loading."""
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "ARTIFACT_MANIFEST.json").read_text())
    failures = []
    for relative, expected in manifest["sha256"].items():
        file = root / relative
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            failures.append(relative)
    original = json.loads((root / "ORIGINAL_PRESERVATION.json").read_text())
    ai = root.parents[1]
    for relative, expected in original["sha256"].items():
        file = ai / relative
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            failures.append("original:" + relative)
    print(json.dumps({"passed": not failures, "experiment_files": len(manifest["sha256"]),
                      "protected_original_files": len(original["sha256"]), "failures": failures}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
