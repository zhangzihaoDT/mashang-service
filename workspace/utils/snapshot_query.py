"""Read-only CLI conventions for managed Service queries."""

import argparse
import json
import re
from datetime import date
from pathlib import Path

from pyarrow import ArrowException

from jobs.snapshot import SnapshotError
from utils.result_contract import build_error_contract, build_partial_contract, build_success_contract


class QueryError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise QueryError("INVALID_REQUEST", message)


def calendar_date(value: str) -> date:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise QueryError("INVALID_DATE", f"Invalid calendar date: {value!r}")


def validate_request(request: dict, required: set[str], optional: set[str]) -> None:
    if not isinstance(request, dict):
        raise QueryError("INVALID_REQUEST", "Request must be a JSON object")
    unknown = request.keys() - required - optional
    missing = required - request.keys()
    if unknown or missing:
        raise QueryError("INVALID_REQUEST", f"Unknown fields: {sorted(unknown)}; missing fields: {sorted(missing)}")
    if any(not isinstance(value, str) or not value.strip() for value in request.values()):
        raise QueryError("INVALID_REQUEST", "Request values must be non-empty strings")


def _unique_object(items):
    result = dict(items)
    if len(result) != len(items):
        raise QueryError("INVALID_REQUEST", "Duplicate JSON fields")
    return result


def run_cli(script: str, query, argv: list[str] | None = None) -> int:
    parser = _Parser(description=script, allow_abbrev=False)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--request", required=True, help="Closed business request JSON object")
    parser.add_argument("--definition-version", help="Expected definition digest supplied by the host")
    try:
        args = parser.parse_args(argv)
        try:
            request = json.loads(args.request, object_pairs_hook=_unique_object)
        except json.JSONDecodeError as exc:
            raise QueryError("INVALID_REQUEST", "Malformed request JSON") from exc
        scope, result, warnings = query(args.snapshot, request, args.definition_version)
        if warnings:
            contract = build_partial_contract(script, script, scope, result, warnings)
        else:
            contract = build_success_contract(script, script, scope, result)
    except (QueryError, SnapshotError) as exc:
        contract = build_error_contract(script, script, str(exc))
        contract["errors"][0]["code"] = exc.code
    except (ArrowException, OSError, ValueError, KeyError, TypeError) as exc:
        contract = build_error_contract(script, script, str(exc))
        contract["errors"][0]["code"] = "INVALID_INPUT_DATA"
    contract["contract_version"] = 1
    print(json.dumps(contract, ensure_ascii=False, allow_nan=False))
    return int(contract["status"] == "error")
