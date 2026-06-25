from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
from collections.abc import MutableMapping
from pathlib import Path

from uipath.platform import UiPath

UIPATH_URL_ENV = "UIPATH_URL"
UIPATH_ACCESS_TOKEN_ENV = "UIPATH_ACCESS_TOKEN"
UIPATH_UNATTENDED_USER_ACCESS_TOKEN_ENV = "UIPATH_UNATTENDED_USER_ACCESS_TOKEN"


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


def _string_value(data: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_uip_login_refresh_output(stdout: str) -> dict[str, object]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "`uip login refresh --output json` did not return valid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            "`uip login refresh --output json` returned an unexpected response."
        )

    data = payload.get("Data", payload)
    if not isinstance(data, dict):
        raise RuntimeError(
            "`uip login refresh --output json` returned an unexpected Data payload."
        )

    return data


def _tenant_base_url(data: dict[str, object]) -> str:
    base_url = _string_value(data, "BaseUrl", "UipathUrl")
    organization_name = _string_value(
        data,
        "OrganizationName",
        "UipathOrganizationName",
    )
    tenant_name = _string_value(data, "TenantName", "UipathTenantName")

    missing = [
        name
        for name, value in (
            ("BaseUrl", base_url),
            ("OrganizationName", organization_name),
            ("TenantName", tenant_name),
        )
        if value is None
    ]
    if missing:
        raise RuntimeError(
            "`uip login refresh --output json` did not return required field(s): "
            + ", ".join(missing)
        )

    assert base_url is not None
    assert organization_name is not None
    assert tenant_name is not None
    tenant_path = f"/{organization_name.strip('/')}/{tenant_name.strip('/')}"
    base_url = base_url.rstrip("/")
    if base_url.endswith(tenant_path):
        return base_url
    return f"{base_url}{tenant_path}"


def configure_sdk_env_from_uip_login(
    environ: MutableMapping[str, str] = os.environ,
) -> bool:
    if environ.get(UIPATH_URL_ENV) and (
        environ.get(UIPATH_ACCESS_TOKEN_ENV)
        or environ.get(UIPATH_UNATTENDED_USER_ACCESS_TOKEN_ENV)
    ):
        return False

    result = subprocess.run(
        ["uip", "login", "refresh", "--output", "json"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        error_detail = result.stderr.strip() or result.stdout.strip()
        message = (
            "Unable to read the active UiPath CLI session with "
            "`uip login refresh --output json`. Run `uip login ...` first."
        )
        if error_detail:
            message = f"{message} CLI error: {error_detail}"
        raise RuntimeError(message)

    data = _parse_uip_login_refresh_output(result.stdout)
    access_token = _string_value(data, "AccessToken", "access_token")
    if access_token is None:
        raise RuntimeError(
            "`uip login refresh --output json` did not return an AccessToken."
        )

    environ.setdefault(UIPATH_URL_ENV, _tenant_base_url(data))
    if not (
        environ.get(UIPATH_ACCESS_TOKEN_ENV)
        or environ.get(UIPATH_UNATTENDED_USER_ACCESS_TOKEN_ENV)
    ):
        environ[UIPATH_ACCESS_TOKEN_ENV] = access_token

    optional_env = {
        "UIPATH_ORGANIZATION_ID": _string_value(
            data,
            "OrganizationId",
            "UipathOrganizationId",
        ),
        "UIPATH_TENANT_ID": _string_value(data, "TenantId", "UipathTenantId"),
        "UIPATH_ORGANIZATION_NAME": _string_value(
            data,
            "OrganizationName",
            "UipathOrganizationName",
        ),
        "UIPATH_TENANT_NAME": _string_value(
            data,
            "TenantName",
            "UipathTenantName",
        ),
    }
    for key, value in optional_env.items():
        if value:
            environ.setdefault(key, value)

    return True


def build_input_payload(
    file_path: Path,
    attachment_id: str,
    existing_payload: dict[str, object],
    document_type: str | None,
) -> dict[str, object]:
    mime_type, _ = mimetypes.guess_type(file_path.name)
    payload = dict(existing_payload)
    payload.pop("document_file", None)
    payload["file_resource"] = {
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
    if configure_sdk_env_from_uip_login():
        print("Using active uip login session for UiPath SDK auth.")

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
    print(
        "uip codedagent run --input-file input.json "
        "--output-file codedagent-output.json"
    )


if __name__ == "__main__":
    main()
