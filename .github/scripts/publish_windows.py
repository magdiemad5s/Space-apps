"""Verify the reviewed Windows build and publish only those exact release assets.

The workflow uses this verifier before download, before upload and before
publication. It never builds, trains, replaces assets or moves a Git tag.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
ASSETS = (
    "ASTRA-SHIELD-Setup-x64.exe", "ASTRA-SHIELD-portable-x64.zip", "SHA256SUMS.txt",
    "build-manifest.json", "windows-model-equivalence-report.json",
    "windows-smoke-report.json", "installed-smoke-report.json",
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def config():
    result = json.loads((ROOT / "desktop/release.json").read_text())
    require(result["schema_version"] == 1, "Unsupported release descriptor")
    require(result["repository"] == "magdiemad5s/Space-apps", "Unexpected repository")
    require(re.fullmatch(r"v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", result["tag"]), "Invalid release tag")
    require(re.fullmatch(r"[0-9a-f]{40}", result["source_commit"]), "Expected a full source commit")
    require(set(result["binary_sha256"]) == set(ASSETS[:2]), "Unexpected binary names")
    for digest in result["binary_sha256"].values():
        require(re.fullmatch(r"[0-9a-f]{64}", digest), "Invalid binary checksum")
    return result


def api(descriptor, endpoint, *, optional=False):
    token = os.environ["GH_TOKEN"]
    url = f"https://api.github.com/repos/{descriptor['repository']}/{endpoint}"
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if optional and error.code == 404:
            return None
        raise RuntimeError(f"GitHub API {endpoint} failed with HTTP {error.code}") from None


def output(name, value):
    require("\n" not in str(value) and "\r" not in str(value), "Invalid workflow output")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def hash_file(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_run(descriptor):
    run = api(descriptor, f"actions/runs/{descriptor['run_id']}")
    require(run["status"] == "completed" and run["conclusion"] == "success", "Windows build did not succeed")
    require(run["head_sha"] == descriptor["source_commit"], "Windows build source commit mismatch")
    require(run["head_repository"]["full_name"] == descriptor["repository"], "Unexpected build source repository")
    require(run["path"] == ".github/workflows/windows-app.yml", "Unexpected build workflow")
    artifact = api(descriptor, f"actions/artifacts/{descriptor['artifact_id']}")
    require(not artifact["expired"], "Verified build artifact has expired")
    require(artifact["name"] == descriptor["artifact_name"], "Artifact name mismatch")
    require(artifact["workflow_run"]["id"] == descriptor["run_id"], "Artifact build run mismatch")
    require(artifact["workflow_run"]["head_sha"] == descriptor["source_commit"], "Artifact source mismatch")
    require(artifact["digest"] == descriptor["artifact_digest"], "Artifact digest mismatch")
    for key in ("run_id", "artifact_name", "tag", "title", "source_commit"):
        output(key, descriptor[key])
    print("Verified successful Windows build, exact source commit and reviewed artifact identity.")


def verify_files(descriptor, directory):
    for name in ASSETS:
        require((directory / name).is_file(), f"Missing release asset: {name}")
    checksums = {}
    for line in (directory / "SHA256SUMS.txt").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        require(match is not None, "Malformed SHA256SUMS.txt")
        digest, name = match.groups()
        require(name not in checksums, "Duplicate checksum entry")
        checksums[name] = digest
    require(checksums == descriptor["binary_sha256"], "Build checksum file differs from reviewed release descriptor")
    hashes = {name: hash_file(directory / name) for name in ASSETS}
    for name, expected in descriptor["binary_sha256"].items():
        require(hashes[name] == expected, f"Downloaded binary checksum mismatch: {name}")
    manifest = json.loads((directory / "build-manifest.json").read_text(encoding="utf-8-sig"))
    require(manifest["commit"] == descriptor["source_commit"], "Build manifest source mismatch")
    for key in ("original_model_sha256", "deployment_model_sha256", "original_dataset_sha256"):
        require(manifest[key] == descriptor[key], f"Build manifest {key} mismatch")
    require(manifest["platform"] == "Windows x64", "Unexpected build platform")
    for key in ("signed", "clinical_validation", "training_performed", "runtime_install_required"):
        require(manifest[key] is False, f"Unexpected build declaration: {key}")
    required_checks = {"day 8 actual model forecast", "actual TreeSHAP three reasons",
                       "TreeSHAP reconstructs predicted class probability", "local services stopped cleanly"}
    for name in ("windows-smoke-report.json", "installed-smoke-report.json"):
        report = json.loads((directory / name).read_text(encoding="utf-8-sig"))
        require(report["passed"] is True and report["platform"] == "win32" and report["frozen"] is True, f"Native executable test failed: {name}")
        require(report["model_artifact_sha256"] == descriptor["deployment_model_sha256"], "Smoke used a different model")
        require(len(report["checks"]) >= 19 and all(item["passed"] is True for item in report["checks"]), "Incomplete or failed smoke checks")
        require(required_checks <= {item["name"] for item in report["checks"]}, "Critical smoke assertions are missing")
        require(report["forecast"] == {"label": "moderate", "points": 33.1, "shap_method": "TreeSHAP"}, "Unexpected synthetic smoke forecast")
    comparison = json.loads((directory / "windows-model-equivalence-report.json").read_text(encoding="utf-8-sig"))
    require(comparison["passed"] is True and comparison["platform"] == "win32" and comparison["case_count"] == 6, "Windows model equivalence failed")
    require(comparison["deployment_model_sha256"] == descriptor["deployment_model_sha256"], "Equivalence report model mismatch")
    require(comparison["absolute_tolerance"] <= 1e-8 and comparison["relative_tolerance"] <= 1e-7, "Equivalence tolerance is unexpectedly loose")
    print("Verified binary hashes, all native smoke assertions and original-output comparisons.")
    return hashes


def release_state(descriptor, hashes, *, require_complete=False, published=False):
    tag = urllib.parse.quote(descriptor["tag"], safe="")
    release = api(descriptor, f"releases/tags/{tag}", optional=True)
    if release is None:
        # A draft may not yet have a Git tag and can be omitted by the by-tag
        # endpoint. Authenticated listing includes drafts owned by this repo.
        matches = [item for item in api(descriptor, "releases?per_page=100")
                   if item["tag_name"] == descriptor["tag"]]
        require(len(matches) <= 1, "Multiple releases use the requested tag")
        release = matches[0] if matches else None
    # Resolve any existing tag even if a release upload was previously rolled
    # back. Never replace or retarget an existing tag.
    tag_ref = api(descriptor, f"git/ref/tags/{tag}", optional=True)
    if tag_ref:
        commit = api(descriptor, f"commits/{tag}")
        require(commit["sha"] == descriptor["source_commit"], "Existing tag points to a different commit")
    if release is None:
        require(not require_complete and not published, "Expected release is missing")
        mode, missing = "create", list(ASSETS)
    else:
        target = api(descriptor, "commits/" + urllib.parse.quote(release["target_commitish"], safe=""))
        require(target["sha"] == descriptor["source_commit"], "Existing release target differs from verified source")
        require(release["prerelease"] is True, "Refusing to change an existing non-prerelease")
        assets = {asset["name"]: asset for asset in release["assets"]}
        missing = []
        for name, expected in hashes.items():
            asset = assets.get(name)
            if asset is None:
                missing.append(name)
            else:
                require(asset["state"] == "uploaded" and asset.get("digest") == "sha256:" + expected,
                        f"Existing release asset does not match; it will not be overwritten: {name}")
        require(not (missing and (require_complete or not release["draft"])), "Published/complete release is missing verified assets")
        if published:
            require(release["draft"] is False, "Release is still a draft")
        mode = "resume" if release["draft"] else "already_published"
    output("mode", mode)
    if not require_complete:
        path = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "astra-assets-to-upload.txt"
        path.write_text("".join(name + "\n" for name in missing), encoding="utf-8")
    print(f"Release state verified: {mode}; missing assets: {len(missing)}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "files", "prepare", "uploaded", "published"))
    parser.add_argument("--directory", type=Path, default=ROOT / "release-download")
    args = parser.parse_args()
    descriptor = config()
    if args.mode == "run":
        verify_run(descriptor)
        return
    hashes = verify_files(descriptor, args.directory)
    if args.mode != "files":
        release_state(descriptor, hashes, require_complete=args.mode in {"uploaded", "published"}, published=args.mode == "published")


if __name__ == "__main__":
    main()
