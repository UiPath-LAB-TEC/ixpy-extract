# UiPath Coded Agent CI/CD Design

## Goal

Build a reusable GitHub Actions workflow for multiple UiPath coded-agent repositories. Each agent lives in its own folder and GitHub repo, so the shared workflow must keep behavior centralized while letting each repo supply its own project path, input file, deploy target, tenant, organization, and output validation logic.

## Architecture

Use a central reusable workflow as the source of truth for CI/CD behavior. Each agent repo adds a small caller workflow that references the shared workflow by tag or branch.

The reusable workflow handles:

- repository checkout
- Python, `uv`, and `uip` setup
- dependency installation with `uv sync`
- optional Python tests
- non-interactive `uip login`
- coded-agent smoke execution through `uip codedagent run`
- output validation through a repo-owned script
- deploy through `uip codedagent deploy`
- artifact upload for smoke output and logs

The per-agent caller workflow supplies configuration only. It should not duplicate setup, login, smoke test, or deploy scripts.

## Reusable Workflow Inputs

- `agent_root`: path to the agent project root, default `.`
- `python_version`: Python version, default `3.12`
- `run_python_tests`: whether to run Python unit tests, default `false`
- `python_test_command`: test command to run when enabled, default `python -m unittest discover`
- `run_codedagent_smoke`: whether to run the coded-agent smoke test, default `true`
- `entrypoint`: optional entrypoint argument for `uip codedagent run`; empty means auto-discovery
- `input_file`: smoke-test input file, default `input.json`
- `run_output_validation`: whether to validate the smoke output, default `true`
- `validation_script`: validation script path, default `scripts/validate_codedagent_output.py`
- `deploy`: whether to deploy after tests pass, default `false`
- `deploy_target`: one of `my-workspace`, `tenant`, or `folder`
- `folder`: folder name when `deploy_target` is `folder`

## Secrets And Variables

Required GitHub secrets:

- `UIPATH_CLIENT_ID`
- `UIPATH_CLIENT_SECRET`

Required GitHub variables or caller inputs:

- `UIPATH_ORGANIZATION`
- `UIPATH_TENANT`

Optional GitHub variable or caller input:

- `UIPATH_AUTHORITY`, used for staging, alpha, or Automation Suite identity URLs

The workflow authenticates with a non-interactive service-principal login:

```bash
uip login \
  --client-id env.UIPATH_CLIENT_ID \
  --client-secret env.UIPATH_CLIENT_SECRET \
  --organization "$UIPATH_ORGANIZATION" \
  --tenant "$UIPATH_TENANT" \
  --output json
```

When `UIPATH_AUTHORITY` is set, the workflow appends `--authority "$UIPATH_AUTHORITY"`.

## Test Flow

The standard CI sequence is:

1. Change directory to `agent_root`.
2. Run `uv sync`.
3. If `run_python_tests` is true, run `python_test_command`.
4. Run `uip login` using the configured organization, tenant, and service-principal secrets.
5. If `run_codedagent_smoke` is true, run:

   ```bash
   uip codedagent run ${ENTRYPOINT_ARG} --input-file "$INPUT_FILE" --output-file codedagent-output.json
   ```

6. Upload `codedagent-output.json` as a GitHub Actions artifact.
7. If `run_output_validation` is true, run:

   ```bash
   python "$VALIDATION_SCRIPT" --output codedagent-output.json
   ```

Python tests are optional because not every agent repo will have unit tests. The `uip codedagent run --input-file input.json` smoke test is the default required test because it verifies the agent runs through the same CLI path used by deployment.

## Output Validation Contract

Each agent repo owns its validation script because output schemas differ by agent. The shared workflow only enforces that the script exists and exits with code `0`.

The default validation script path is:

```text
scripts/validate_codedagent_output.py
```

The script must accept:

```bash
python scripts/validate_codedagent_output.py --output codedagent-output.json
```

Validation failures should print a direct error message to stderr and exit non-zero.

For this repo, the validator should check:

- `codedagent-output.json` is valid JSON
- `document_id` is present and non-empty
- `extraction_results` is an object
- `extraction_time_seconds` is numeric when present
- `validation_action` is either null/missing or object-like when returned

## Deploy Flow

Deployment only runs when `deploy` is true and all tests and validation pass. The workflow always passes a non-interactive deploy target:

```bash
uip codedagent deploy --my-workspace
uip codedagent deploy --tenant
uip codedagent deploy --folder "$FOLDER"
```

The caller workflow should decide when deployment is enabled, typically:

- pull requests: test and validate only
- pushes to `main`: test, validate, and deploy
- `workflow_dispatch`: manually choose deploy target and folder

## Per-Repo Caller Example

```yaml
name: UiPath Coded Agent

on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  coded-agent:
    uses: UiPath-LAB-TEC/github-actions/.github/workflows/uip-codedagent-ci.yml@v1
    with:
      agent_root: .
      python_version: "3.12"
      input_file: input.json
      run_python_tests: false
      run_output_validation: true
      validation_script: scripts/validate_codedagent_output.py
      deploy: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}
      deploy_target: folder
      folder: Shared
    secrets: inherit
```

## Error Handling

- Missing `input_file` fails before login or deploy.
- Missing validation script fails when `run_output_validation` is true.
- Failed `uip login` stops the job before smoke test or deploy.
- Failed smoke test uploads available logs and output artifacts.
- Failed output validation uploads `codedagent-output.json`.
- Deploy target `folder` requires `folder`; missing folder fails before deploy.

## Scope

This design covers standalone UiPath coded-agent repositories. It does not handle monorepos, UiPath solution packaging, Maestro flow wiring, or Studio Web push/pull workflows. Those can be added as separate reusable workflows later if needed.
