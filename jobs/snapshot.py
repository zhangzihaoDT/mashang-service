"""Copy registry datasets into a versioned read-only analysis snapshot."""
from __future__ import annotations

import argparse
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
    return result


def read_snapshot_inputs(manifest: Path, datasets: list[str]) -> tuple[str, dict]:
    """Resolve query inputs from one published snapshot, without reading live data."""
    manifest = manifest.resolve(strict=True)
    snapshot = json.loads(manifest.read_text())
    version = snapshot["version"]
    if manifest.name != "snapshot.json" or version != manifest.parent.name:
        raise ValueError("Snapshot manifest does not match its version directory")
    inputs = {}
    for key in datasets:
        if key not in snapshot["datasets"]:
            raise ValueError(f"Snapshot is missing required dataset: {key}")
        info = snapshot["datasets"][key]
        path = Path(info["path"])
        if (not path.is_absolute() or path.parent != manifest.parent or path.is_symlink()
                or not path.is_file() or path.stat().st_size != info["size_bytes"]):
            raise ValueError(f"Snapshot input is invalid or changed: {key}")
        inputs[key] = info
    return version, inputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--dataset", action="append", required=True)
    parser.add_argument("--run-id", action="append", required=True)
    args = parser.parse_args()
    print(json.dumps(copy_snapshot(ROOT, args.destination, args.dataset, verified_files(ROOT, args.run_id))))


if __name__ == "__main__":
    main()
