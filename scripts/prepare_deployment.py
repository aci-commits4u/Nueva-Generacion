#!/usr/bin/env python3
"""Prepare a reviewable Vercel deployment manifest without deploying.

The repository is currently deployed through a manual MCP upload.  This guard
keeps that upload repeatable: it only emits an allowlisted file manifest after
checking the intended release branch, a clean tracked tree, the remote branch
pointer, and the green GitHub Actions run for the exact commit.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "aci-commits4u/Nueva-Generacion"
REMOTE = "origin"
TEAM_ID = "team_HBbhk99lljqf4KKzGX8d84Yk"

# Keep project IDs fixed here, rather than accepting --project-id, to prevent
# an accidental upload to an arbitrary Vercel project.
PROJECTS: dict[str, dict[str, str]] = {
    "dev": {
        "name": "intent-judge-perfected-dev",
        "id": "prj_BQgv2BqYWbrJjqW0LkPw13cVC8jc",
        "branch": "develop",
        "environment": "development",
    },
    "production": {
        "name": "intent-judge-perfected",
        "id": "prj_sQQGLWLVZ7qigP9WePx9fIH5kzWT",
        "branch": "production",
        "environment": "production",
    },
}

REQUIRED_JOBS = {"deterministic-regression", "Browser UI regression"}
ALLOWLIST_PREFIXES = ("app/", "web/", "profiles/", "demo/", "evals/")
ALLOWLIST_EXACT = {"requirements.txt", "vercel.json"}
BASE_REQUIRED_ENVIRONMENT_KEYS = [
    "APP_ENV",
    "STORE_BACKEND",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_TABLE_CONNECTION_STRING",
    "AZURE_TABLE_NAME",
    "DEMO_SIGNING_KEYS",
]
PRODUCTION_ONLY_ENVIRONMENT_KEYS = ["CRON_SECRET"]
DEVELOPMENT_ONLY_ENVIRONMENT_KEYS = ["AI_BUDGET_TABLE_NAME"]


class DeploymentGuardError(RuntimeError):
    """A release precondition was not met."""


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeploymentGuardError(f"could not run {' '.join(command[:2])}: {exc}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = detail[-1] if detail else f"exit code {result.returncode}"
        raise DeploymentGuardError(f"{' '.join(command[:2])} failed: {suffix[:400]}")
    return result


def _git(*args: str) -> str:
    return _run(["git", *args]).stdout.strip()


def _gh_json(*args: str) -> Any:
    result = _run(["gh", *args])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DeploymentGuardError("GitHub CLI returned invalid JSON") from exc


def _current_branch() -> str:
    branch = _git("branch", "--show-current")
    if not branch:
        raise DeploymentGuardError("detached HEAD is not a release branch")
    return branch


def _check_clean_tree() -> None:
    status = _run(["git", "status", "--porcelain=v1", "--untracked-files=all"]).stdout
    if status:
        paths = [line[3:] if len(line) > 3 else line for line in status.splitlines()]
        preview = ", ".join(paths[:8])
        if len(paths) > 8:
            preview += f" (+{len(paths) - 8} more)"
        raise DeploymentGuardError(f"working tree is not clean: {preview}")


def _check_remote(branch: str, commit: str) -> None:
    lines = _git("ls-remote", "--heads", REMOTE, branch).splitlines()
    expected_ref = f"refs/heads/{branch}"
    matches = [line.split() for line in lines if len(line.split()) == 2 and line.split()[1] == expected_ref]
    if not matches:
        raise DeploymentGuardError(f"origin does not contain refs/heads/{branch}")
    remote_commit = matches[0][0]
    if remote_commit != commit:
        raise DeploymentGuardError(
            f"origin/{branch} is {remote_commit[:12]}, but HEAD is {commit[:12]}"
        )


def _check_ci(branch: str, commit: str) -> dict[str, Any]:
    runs = _gh_json(
        "run",
        "list",
        "--repo",
        REPOSITORY,
        "--branch",
        branch,
        "--limit",
        "20",
        "--json",
        "databaseId,headSha,status,conclusion,workflowName,createdAt,url",
    )
    matching = [run for run in runs if run.get("headSha") == commit]
    matching.sort(key=lambda run: run.get("createdAt", ""), reverse=True)
    if not matching:
        raise DeploymentGuardError(f"no GitHub Actions run found for {branch}@{commit[:12]}")

    run = matching[0]
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise DeploymentGuardError(
            "latest GitHub Actions run for the release commit is not green "
            f"(status={run.get('status')!r}, conclusion={run.get('conclusion')!r})"
        )

    jobs_payload = _gh_json(
        "run",
        "view",
        str(run["databaseId"]),
        "--repo",
        REPOSITORY,
        "--json",
        "jobs",
    )
    jobs = jobs_payload.get("jobs", [])
    successful_jobs = {
        job.get("name") for job in jobs if job.get("status") == "completed" and job.get("conclusion") == "success"
    }
    missing = sorted(REQUIRED_JOBS - successful_jobs)
    if missing:
        raise DeploymentGuardError(f"green workflow is missing successful jobs: {', '.join(missing)}")

    return {
        "workflow": run.get("workflowName"),
        "run_id": run.get("databaseId"),
        "url": run.get("url"),
        "head_sha": commit,
        "jobs": sorted(REQUIRED_JOBS),
    }


def _is_allowlisted(path: str) -> bool:
    return path in ALLOWLIST_EXACT or path.startswith(ALLOWLIST_PREFIXES)


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _tracked_files() -> list[dict[str, Any]]:
    paths = [path for path in _run(["git", "ls-files", "-z"]).stdout.split("\0") if path]
    selected = [path for path in paths if _is_allowlisted(path)]
    if not selected:
        raise DeploymentGuardError("the deployment allowlist resolved to no tracked files")

    files: list[dict[str, Any]] = []
    for relative in selected:
        if relative.startswith(".env") or relative.startswith(".vercel/"):
            raise DeploymentGuardError(f"secret or Vercel metadata entered the manifest: {relative}")
        path = ROOT / relative
        if not path.is_file():
            raise DeploymentGuardError(f"allowlisted tracked file is missing: {relative}")
        data = path.read_bytes()
        files.append({"path": relative, "bytes": len(data), "sha1": _sha1(data)})
    return files


def _development_vercel_override() -> dict[str, Any] | None:
    source_path = ROOT / "vercel.json"
    source_data = source_path.read_bytes()
    config = json.loads(source_data)
    if "crons" not in config:
        return None
    effective = copy.deepcopy(config)
    effective.pop("crons", None)
    effective_data = (json.dumps(effective, indent=2, sort_keys=True) + "\n").encode()
    return {
        "path": "vercel.json",
        "reason": "development must not run the production quality cron",
        "source_sha1": _sha1(source_data),
        "bytes": len(effective_data),
        "sha1": _sha1(effective_data),
        "content_base64": base64.b64encode(effective_data).decode("ascii"),
    }


def _runtime_configuration(target: str, environment: str) -> tuple[dict[str, str], list[str]]:
    """Return non-secret runtime values and required key names for a project."""
    session_table = "IntentJudgeDev" if target == "dev" else "IntentJudge"
    runtime = {
        "APP_ENV": environment,
        "STORE_BACKEND": "azure",
        "AZURE_TABLE_NAME": session_table,
    }
    required = list(BASE_REQUIRED_ENVIRONMENT_KEYS)
    if target == "dev":
        # The dev project gets its own sessions, while the authoritative global
        # reservation ledger remains shared with production by table name.
        runtime["AI_BUDGET_TABLE_NAME"] = "IntentJudge"
        required.extend(DEVELOPMENT_ONLY_ENVIRONMENT_KEYS)
    else:
        required.extend(PRODUCTION_ONLY_ENVIRONMENT_KEYS)
    return runtime, required


def prepare(target: str, environment: str | None) -> dict[str, Any]:
    if target not in PROJECTS:
        raise DeploymentGuardError(f"unknown deployment target: {target}")

    project = PROJECTS[target]
    expected_environment = project["environment"]
    if target == "production":
        if _current_branch() != "production":
            raise DeploymentGuardError("production releases must run from the production branch")
        if environment != "production":
            raise DeploymentGuardError("production requires explicit --environment production")
    else:
        if _current_branch() != "develop":
            raise DeploymentGuardError("development releases must run from the develop branch")
        if environment not in (None, "development"):
            raise DeploymentGuardError("development releases require development environment")
        environment = "development"

    _check_clean_tree()
    commit = _git("rev-parse", "HEAD")
    branch = _current_branch()
    _check_remote(branch, commit)
    ci = _check_ci(branch, commit)
    files = _tracked_files()
    override = _development_vercel_override() if target == "dev" else None
    runtime_variables, required_environment_keys = _runtime_configuration(target, expected_environment)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "project": {
            "name": project["name"],
            "id": project["id"],
            "team_id": TEAM_ID,
            "target": "production",
        },
        "branch": branch,
        "commit": commit,
        "environment": expected_environment,
        "runtime_variables": runtime_variables,
        "required_environment_keys": required_environment_keys,
        "secret_binding_policy": {
            "DEMO_SIGNING_KEYS": "unique per Vercel project",
            "AZURE_TABLE_CONNECTION_STRING": "configured per project; session tables use distinct AZURE_TABLE_NAME values",
            "AI_BUDGET_TABLE_CONNECTION_STRING": "only when the shared ledger uses another storage account",
        },
        "secret_values_included": False,
        "ci": ci,
        "files": files,
        "file_overrides": [override] if override else [],
    }
    return manifest


def _emit(manifest: dict[str, Any], output: str | None) -> None:
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if output is None or output == "-":
        sys.stdout.write(rendered)
        return
    destination = Path(output).expanduser().resolve()
    if destination.is_relative_to(ROOT):
        raise DeploymentGuardError("manifest output must be outside the repository")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")
    print(f"wrote deployment manifest to {destination}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(PROJECTS), default="dev")
    parser.add_argument("--environment", choices=("development", "production"))
    parser.add_argument("--output", help="write JSON outside the repository; defaults to stdout")
    args = parser.parse_args(argv)
    try:
        _emit(prepare(args.target, args.environment), args.output)
    except DeploymentGuardError as exc:
        print(f"deployment guard failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
