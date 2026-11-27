"""Copy registry datasets into a versioned read-only analysis snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dataset.updater.dataset_registry import DATASETS, describe
from jobs.production import JOB_DATASETS, LOG_DIR, JobLock


class SnapshotError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verified_files(root: Path, run_ids: list[str]) -> dict:
    verified = {}
    for run_id in run_ids:
        if not re.fullmatch(r"dsh-[a-f0-9]{32}", run_id):
            raise ValueError("Invalid refresh run ID")
        record = json.loads((root / LOG_DIR / "records" / f"{run_id}.json").read_text())
        if record.get("run_id") != run_id or record.get("status") not in {"success", "no_new_data"}:
            raise ValueError(f"Refresh run {run_id} did not pass verification")
        after = record["after"]
        if set(after) != set(JOB_DATASETS[record["job"]]):
            raise ValueError(f"Unexpected scope in refresh run {run_id}")
        for key, evidence in after.items():
            verified[key] = evidence
    return verified


def copy_snapshot(root: Path, destination: Path, datasets: list[str], expected: dict) -> dict:
    specs = {spec.key: spec for spec in DATASETS}
    if not datasets or len(set(datasets)) != len(datasets) or set(datasets) - specs.keys():
        raise ValueError("Unknown or duplicate dataset")
    if not destination.is_dir() or any(destination.iterdir()):
        raise ValueError("Snapshot requires an empty destination")
    copies = {}
    with JobLock(root, destination.name, "analysis-snapshot"):
        signatures = {}
        for key in datasets:
            spec = specs[key]
            source = root / spec.display_path
            before = source.stat()
            signatures[source] = (before.st_ino, before.st_size, before.st_mtime_ns)
            if key in expected:
                evidence = expected[key]
                if not evidence.get("exists") or evidence.get("file_mtime") != datetime.fromtimestamp(before.st_mtime).isoformat():
                    raise ValueError(f"{key} does not match the verified refresh（与已核验刷新记录不一致）")
                if evidence.get("size_bytes") not in (None, before.st_size):
                    raise ValueError(f"{key} size differs from the verified refresh")
            target = destination / source.name
            with source.open("rb") as stream, target.open("xb") as output:
                shutil.copyfileobj(stream, output)
            shutil.copystat(source, target)
            target.chmod(0o444)
            copies[key] = replace(spec, path=target)
        for source, signature in signatures.items():
            current = source.stat()
            if (current.st_ino, current.st_size, current.st_mtime_ns) != signature:
                raise ValueError(f"{source.name} changed during snapshot creation")

    result = {}
    for key, spec in copies.items():
        info = describe(spec)
        if not info["rows"] or (spec.date_columns and not info["data_asof"]):
            raise ValueError(f"{key} is empty, unreadable or missing a business cutoff")
        result[key] = {field: info[field] for field in (
            "rows", "size_bytes", "file_mtime", "data_asof", "data_asof_column",
        )}
        result[key]["path"] = str(spec.path.resolve())
        result[key]["sha256"] = file_sha256(spec.path)
        expected_hash = expected.get(key, {}).get("sha256")
        if expected_hash and result[key]["sha256"] != expected_hash:
            raise ValueError(f"{key} content differs from the verified refresh")
    return result


def _read_manifest(manifest: Path) -> tuple[Path, dict]:
    if manifest.is_symlink():
        raise SnapshotError("SNAPSHOT_INVALID", "Snapshot manifest must not be a symlink")
    try:
        manifest = manifest.resolve(strict=True)
    except FileNotFoundError as exc:
        raise SnapshotError("SNAPSHOT_MISSING", "Snapshot manifest is missing") from exc
    snapshot = json.loads(manifest.read_text())
    if not isinstance(snapshot, dict) or manifest.name != "snapshot.json" or snapshot.get("version") != manifest.parent.name:
        raise SnapshotError("SNAPSHOT_INVALID", "Snapshot manifest does not match its version directory")
    return manifest, snapshot


def _dataset_inputs(manifest: Path, snapshot: dict, datasets: list[str]) -> dict:
    inputs = {}
    for key in datasets:
        if key not in snapshot.get("datasets", {}):
            raise SnapshotError("SNAPSHOT_DEPENDENCY_MISSING", f"Snapshot is missing required dataset: {key}")
        info = snapshot["datasets"][key]
        path = Path(info["path"])
        if (not path.is_absolute() or path.parent != manifest.parent or path.is_symlink()
                or not path.is_file() or path.stat().st_size != info["size_bytes"]):
            raise SnapshotError("SNAPSHOT_INVALID", f"Snapshot input is invalid or changed: {key}")
        inputs[key] = info
    return inputs


def read_snapshot_inputs(manifest: Path, datasets: list[str]) -> tuple[str, dict]:
    """Read the original Ticket manifest used by the legacy queries."""
    manifest, snapshot = _read_manifest(manifest)
    return snapshot["version"], _dataset_inputs(manifest, snapshot, datasets)


def _verified_copy(root: Path, key: str, info: dict) -> Path:
    path = root / info["path"]
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved != path.absolute() or not path.is_file():
        raise SnapshotError("SNAPSHOT_INVALID", f"Snapshot requires a regular copied file: {key}")
    stat = path.stat()
    if stat.st_mode & 0o222 or stat.st_size != info["size_bytes"]:
        raise SnapshotError("SNAPSHOT_INVALID", f"Snapshot file is writable or has changed size: {key}")
    digest = info.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest) or file_sha256(path) != digest:
        raise SnapshotError("SNAPSHOT_HASH_MISMATCH", f"Snapshot SHA-256 missing or mismatched: {key}")
    return path


def read_verified_snapshot(
    manifest: Path, datasets: list[str], definitions: list[str], expected_definition_version: str | None = None,
) -> tuple[dict, dict, dict]:
    """Verify the existing copy manifest and load its pinned business definitions."""
    try:
        manifest, snapshot = _read_manifest(manifest)
        if snapshot.get("mode", "copy") != "copy" or snapshot.get("manifest_version", 1) != 1:
            raise SnapshotError("SNAPSHOT_INVALID", "Only version 1 copy manifests are supported")
        inputs = _dataset_inputs(manifest, snapshot, datasets)
        paths = {key: _verified_copy(manifest.parent, key, info) for key, info in inputs.items()}
        definition_inputs = snapshot.get("definitions", {})
        missing = set(definitions) - definition_inputs.keys()
        if missing:
            raise SnapshotError("SNAPSHOT_DEPENDENCY_MISSING", f"Snapshot is missing definitions: {sorted(missing)}")
        hashes = {}
        rules = {}
        for key, info in sorted(definition_inputs.items()):
            path = _verified_copy(manifest.parent, key, info)
            hashes[key] = info["sha256"]
            if key in definitions:
                rules[key] = json.loads(path.read_bytes())
                if not isinstance(rules[key], dict):
                    raise SnapshotError("SNAPSHOT_INVALID", f"Definition must be a JSON object: {key}")
        version = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        for expected in (expected_definition_version, snapshot.get("definition_version")):
            if expected is not None and expected != version:
                raise SnapshotError("DEFINITION_VERSION_MISMATCH", "Pinned business definition version differs")
    except SnapshotError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise SnapshotError("SNAPSHOT_INVALID", f"Malformed or unreadable copy manifest: {exc}") from exc

    scope = {
        "data_source": "verified_snapshot",
        "snapshot_version": snapshot["version"],
        "definition_version": version,
        "definition_hashes": hashes,
        "inputs": {key: {field: info.get(field) for field in (
            "sha256", "rows", "size_bytes", "data_asof", "data_asof_column", "file_mtime",
        )} for key, info in inputs.items()},
    }
    return scope, paths, rules


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--dataset", action="append", required=True)
    parser.add_argument("--run-id", action="append", required=True)
    args = parser.parse_args()
    print(json.dumps(copy_snapshot(ROOT, args.destination, args.dataset, verified_files(ROOT, args.run_id))))


if __name__ == "__main__":
    main()
