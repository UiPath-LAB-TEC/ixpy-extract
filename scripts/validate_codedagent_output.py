#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate ixpy-extract coded-agent smoke-test output."
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to the JSON output produced by uip codedagent run.",
    )
    return parser.parse_args()


def load_output(output_path: Path) -> Any:
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"output file does not exist: {output_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"output file must contain valid JSON: {exc}") from exc


def validate_output(payload: Any) -> list[str]:
    errors: list[str] = []

    if not isinstance(payload, dict):
        return ["output root must be a JSON object."]

    document_id = payload.get("document_id")
    if not isinstance(document_id, str) or not document_id.strip():
        errors.append("document_id must be a non-empty string.")

    extraction_results = payload.get("extraction_results")
    if not isinstance(extraction_results, dict):
        errors.append("extraction_results must be a JSON object.")

    if "extraction_time_seconds" in payload:
        extraction_time_seconds = payload["extraction_time_seconds"]
        if not isinstance(extraction_time_seconds, (int, float)) or isinstance(
            extraction_time_seconds, bool
        ):
            errors.append("extraction_time_seconds must be numeric when present.")

    validation_action = payload.get("validation_action")
    if validation_action is not None and not isinstance(validation_action, dict):
        errors.append("validation_action must be null, missing, or a JSON object.")

    return errors


def main() -> int:
    args = parse_args()
    try:
        payload = load_output(args.output)
    except ValueError as exc:
        print(f"Output validation failed: {exc}", file=sys.stderr)
        return 1

    errors = validate_output(payload)
    if errors:
        print("Output validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Output validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
