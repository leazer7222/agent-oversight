"""
output.py — code_review artifact writer

Writes an immutable code_review artifact to agent_outputs.
Call this once per review run after the agent has produced its findings.

The artifact is append-only after write. Do not modify it.
Lifecycle state (acknowledged/resolved/etc.) is tracked separately — that
table is deferred from v1.

Usage:
    from agents.library.code_review_agent.output import write_code_review

    record_id = write_code_review(
        agent_id="a0b9c8d7-e6f5-4a4b-9c3d-2e1f0a9b8c7d",
        run_id=run_id,
        company_id="1021c018-fe0e-4ae8-a972-7487521cc3d9",
        artifact=artifact_dict,
    )
"""

import os
import json
import uuid
import logging
import requests
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Required top-level fields in a code_review artifact.
_REQUIRED_FIELDS = {
    "schema_version",
    "review_id",
    "subject",
    "context_applied",
    "findings",
    "severity_counts",
    "category_counts",
    "recommendation",
    "summary",
}

_VALID_RECOMMENDATIONS = {"approve", "approve_with_warnings", "review_required", "block"}

_VALID_SEVERITIES = {"critical", "warning", "info"}
_VALID_CONFIDENCES = {"high", "medium", "low"}
_VALID_CATEGORIES = {
    "architecture", "observability", "governance", "schema", "security",
    "type_safety", "operational_semantics", "naming", "documentation",
}


def _finding_problems(f: dict) -> list[str]:
    """Per-finding validity problems. Empty list means the finding is emittable."""
    probs: list[str] = []
    if f.get("severity") not in _VALID_SEVERITIES:
        probs.append(f"invalid severity '{f.get('severity')}'")
    if f.get("confidence") not in _VALID_CONFIDENCES:
        probs.append(f"invalid confidence '{f.get('confidence')}'")
    if f.get("category") not in _VALID_CATEGORIES:
        probs.append(f"invalid category '{f.get('category')}'")
    if not f.get("title"):
        probs.append("missing title")
    if not f.get("explanation"):
        probs.append("missing explanation")
    if not f.get("remediation"):
        probs.append("missing remediation")
    has_citation = bool(f.get("principles")) or bool(f.get("standards_refs")) or bool(f.get("lessons_refs"))
    if not has_citation:
        probs.append("uncited (no principles/standards_refs/lessons_refs)")
    return probs


def sanitize_findings(findings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split findings into (emittable, dropped).

    Policy (per LESSONS): an uncited or malformed finding is an opinion, not a contestable
    finding - drop it rather than aborting the whole review. Returns kept findings and a list of
    {title, reasons} for the dropped ones so the caller can log what was removed (no silent drops).
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    for f in findings:
        probs = _finding_problems(f)
        if probs:
            dropped.append({"title": f.get("title", "untitled"), "reasons": probs})
        else:
            kept.append(f)
    return kept, dropped


def validate_artifact(artifact: dict) -> list[str]:
    """Return a list of validation errors. Empty list means valid."""
    errors: list[str] = []

    missing = _REQUIRED_FIELDS - set(artifact.keys())
    if missing:
        errors.append(f"Missing required top-level fields: {sorted(missing)}")

    rec = artifact.get("recommendation")
    if rec and rec not in _VALID_RECOMMENDATIONS:
        errors.append(f"Invalid recommendation '{rec}'. Must be one of {_VALID_RECOMMENDATIONS}")

    subject = artifact.get("subject", {})
    if not subject.get("commit_sha"):
        errors.append("subject.commit_sha is required and must be non-empty")

    findings = artifact.get("findings", [])
    if not isinstance(findings, list):
        errors.append("findings must be an array")
    else:
        for i, f in enumerate(findings):
            seq = i + 1
            if not f.get("finding_id"):
                errors.append(f"Finding {seq}: finding_id is required")
            if f.get("severity") not in _VALID_SEVERITIES:
                errors.append(f"Finding {seq}: invalid severity '{f.get('severity')}'")
            if f.get("confidence") not in _VALID_CONFIDENCES:
                errors.append(f"Finding {seq}: invalid confidence '{f.get('confidence')}'")
            if f.get("category") not in _VALID_CATEGORIES:
                errors.append(f"Finding {seq}: invalid category '{f.get('category')}'")
            if not f.get("title"):
                errors.append(f"Finding {seq}: title is required")
            if not f.get("explanation"):
                errors.append(f"Finding {seq}: explanation is required")
            if not f.get("remediation"):
                errors.append(f"Finding {seq}: remediation is required")
            # Enforce that at least one source is cited
            has_citation = (
                bool(f.get("principles")) or
                bool(f.get("standards_refs")) or
                bool(f.get("lessons_refs"))
            )
            if not has_citation:
                errors.append(
                    f"Finding {seq} '{f.get('title', 'untitled')}': "
                    "must cite at least one principle or standard (principles, standards_refs, or lessons_refs)"
                )

    return errors


def write_code_review(
    agent_id: str,
    run_id: str,
    company_id: str,
    artifact: dict,
    supabase_url: Optional[str] = None,
    supabase_key: Optional[str] = None,
) -> str:
    """
    Write a code_review artifact to agent_outputs.

    Returns the UUID of the created agent_outputs row.
    Raises ValueError on validation failure.
    Raises RuntimeError on API failure.

    The artifact must conform to the output_schema defined in agent_definitions
    for 'code-review-agent'. Use validate_artifact() to check before calling.
    """
    errors = validate_artifact(artifact)
    if errors:
        raise ValueError(
            f"code_review artifact failed validation ({len(errors)} error(s)):\n" +
            "\n".join(f"  - {e}" for e in errors)
        )

    url = (
        supabase_url
        or os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
    )
    key = supabase_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
            "(or passed explicitly)"
        )

    payload = {
        "agent_id": agent_id,
        "run_id": run_id,
        "company_id": company_id,
        "output_type": "code_review",
        "content": artifact,
    }

    response = requests.post(
        f"{url}/rest/v1/agent_outputs",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        json=payload,
        timeout=15,
    )

    if not response.ok:
        raise RuntimeError(
            f"Failed to write code_review artifact: {response.status_code} {response.text}"
        )

    data = response.json()
    record = data[0] if isinstance(data, list) else data
    record_id = record.get("id", "")
    logger.info(
        "code_review artifact written: agent_outputs.id=%s run_id=%s recommendation=%s findings=%d",
        record_id,
        run_id,
        artifact.get("recommendation"),
        len(artifact.get("findings", [])),
    )
    return record_id


def build_artifact(
    commit_sha: str,
    base_sha: str,
    branch: str,
    files_examined: list[str],
    lines_examined: int,
    findings: list[dict],
    summary: str,
    definition_version: str = "1.0.0",
    agent_instance: str = "reformai.code-review-agent",
    standards_refs: Optional[list[str]] = None,
    review_mode: str = "pre-push",
    tenant: str = "reformai",
    project: str = "agent-oversight",
    pr_number: Optional[int] = None,
    governance_flags: Optional[list[str]] = None,
) -> dict:
    """
    Construct a well-formed code_review artifact dict.

    This is a convenience builder — callers may also construct the dict directly
    as long as it passes validate_artifact().
    """
    if standards_refs is None:
        standards_refs = [
            "docs/PLATFORM_ARCHITECTURE.md",
            "docs/repo-standards.md",
            "docs/agent-standards.md",
        ]

    # Drop uncited / malformed findings rather than aborting the whole review.
    # A single bad finding must not crash the artifact write (it previously did).
    findings, dropped = sanitize_findings(findings)
    gov_flags = list(governance_flags or [])
    if dropped:
        for d in dropped:
            logger.warning("Dropped finding '%s': %s", d["title"], "; ".join(d["reasons"]))
        gov_flags.append(
            f"{len(dropped)} finding(s) dropped before write (uncited or malformed); see run logs"
        )

    severity_counts = {"critical": 0, "warning": 0, "info": 0}
    category_counts: dict[str, int] = {}

    for f in findings:
        sev = f.get("severity", "")
        if sev in severity_counts:
            severity_counts[sev] += 1
        cat = f.get("category", "")
        if cat:
            category_counts[cat] = category_counts.get(cat, 0) + 1

    # Derive recommendation from findings
    blocking_findings = [f for f in findings if f.get("blocking")]
    if blocking_findings:
        # Any blocking finding with high confidence and critical severity → block
        hard_blocks = [
            f for f in blocking_findings
            if f.get("severity") == "critical" and f.get("confidence") == "high"
        ]
        recommendation = "block" if hard_blocks else "review_required"
    elif severity_counts["critical"] > 0:
        recommendation = "review_required"
    elif severity_counts["warning"] > 0:
        recommendation = "approve_with_warnings"
    else:
        recommendation = "approve"

    return {
        "schema_version": "1.0",
        "review_id": str(uuid.uuid4()),
        "subject": {
            "type": "pr" if pr_number is not None else "diff",
            "commit_sha": commit_sha,
            "base_sha": base_sha,
            "branch": branch,
            "pr_number": pr_number,
            "files_examined": files_examined,
            "lines_examined": lines_examined,
        },
        "context_applied": {
            "definition_version": definition_version,
            "agent_instance": agent_instance,
            "standards_refs": standards_refs,
            "review_mode": review_mode,
            "tenant": tenant,
            "project": project,
        },
        "findings": findings,
        "severity_counts": severity_counts,
        "category_counts": category_counts,
        "recommendation": recommendation,
        "governance_flags": gov_flags,
        "summary": summary,
    }
