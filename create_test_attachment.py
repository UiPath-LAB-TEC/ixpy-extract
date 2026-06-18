from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path

from uipath.platform import UiPath


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if key and key not in os.environ:
            os.environ[key] = value


def build_input_payload(
    file_path: Path,
    attachment_id: str,
    existing_payload: dict[str, object],
    document_type: str | None,
) -> dict[str, object]:
    mime_type, _ = mimetypes.guess_type(file_path.name)
    payload = dict(existing_payload)
    payload["document_file"] = {
        "ID": attachment_id,
        "FullName": file_path.name,
        "MimeType": mime_type or "application/octet-stream",
        "Metadata": {},
    }
    if document_type is not None:
        payload["document_type"] = document_type
    else:
        payload.setdefault("document_type", "paystubs")
    payload.setdefault("extraction_results", {})
    return payload


def load_existing_input_payload(input_json_path: Path) -> dict[str, object]:
    if not input_json_path.exists():
        return {}

    try:
        raw_payload = json.loads(input_json_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Input JSON is not valid JSON: {input_json_path}") from exc

    if not isinstance(raw_payload, dict):
        raise ValueError(f"Input JSON root must be an object: {input_json_path}")

    return raw_payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload a local document as a UiPath attachment and refresh input.json."
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="Sample Invoice.pdf",
        help="Local file to upload. Defaults to the sample invoice PDF in this repo.",
    )
    parser.add_argument(
        "--document-type",
        default=None,
        help="Document type to include in the generated input payload. Defaults to the existing value in input.json.",
    )
    parser.add_argument(
        "--input-json",
        default="input.json",
        help="Path to the input JSON file to write. Defaults to input.json",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    load_env_file(project_root / ".env")

    file_path = (project_root / args.file).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Local file not found: {file_path}")

    input_json_path = (project_root / args.input_json).resolve()
    existing_payload = load_existing_input_payload(input_json_path)

    sdk = UiPath()
    attachment_id = sdk.attachments.upload(
        name=file_path.name,
        source_path=str(file_path),
    )

    payload = build_input_payload(
        file_path=file_path,
        attachment_id=str(attachment_id),
        existing_payload=existing_payload,
        document_type=args.document_type,
    )
    input_json_path.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"Uploaded attachment: {attachment_id}")
    print(f"Wrote input file: {input_json_path}")
    print("Next step:")
    print("uv run uipath run main.py --file input.json")


if __name__ == "__main__":
    main()
