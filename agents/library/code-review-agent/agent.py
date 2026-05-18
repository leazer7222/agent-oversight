"""
code-review-agent — v1

Structured pre-push code reviewer for the Agent Oversight / ReformAI platform.
Reviews a git diff against PLATFORM_ARCHITECTURE.md principles, repo standards,
and agent standards. Produces an immutable code_review findings artifact.

Usage:
    python agents/library/code-review-agent/agent.py \\
        --commit-sha <sha> \\
        --base-sha   <sha|HEAD~1|origin/main> \\
        --branch     <branch-name>

    # Review the last commit:
    python agents/library/code-review-agent/agent.py \\
        --commit-sha HEAD --base-sha HEAD~1 --branch main

    # Review a feature branch against main:
    python agents/library/code-review-agent/agent.py \\
        --commit-sha HEAD --base-sha origin/main --branch feature/my-feature

Required env vars:
    ANTHROPIC_API_KEY
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    OVERSIGHT_URL           (default: https://agent-oversight.vercel.app)
    AGENT_OVERSIGHT_SECRET  (or OVERSIGHT_SECRET / INGEST_SECRET)

Optional env vars:
    CODE_REVIEW_MODEL       (default: claude-opus-4-5)

Exit codes:
    0  — approve / approve_with_warnings / review_required
    1  — block (recommendation is BLOCK; use in git hooks to prevent push)
"""

from __future__ import annotations

import os
import sys
import uuid
import argparse
import subprocess
import logging
from pathlib import Path

# ── Encoding fix (Windows) ────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Load .env.local from repo root ───────────────────────────────────────────
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(".env.local", usecwd=True))
except ImportError:
    pass  # python-dotenv optional; rely on env vars being set externally

# ── Resolve repo root and inject path deps ───────────────────────────────────
# agent.py lives at: <repo>/agents/library/code-review-agent/agent.py
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

sys.path.insert(0, str(REPO_ROOT / "python-sdk"))
sys.path.insert(0, str(Path(__file__).parent))

from oversight import OversightClient, categorize_error  # noqa: E402
from output import build_artifact, write_code_review      # noqa: E402

import anthropic  # noqa: E402

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Identity ──────────────────────────────────────────────────────────────────
AGENT_ID           = "a0b9c8d7-e6f5-4a4b-9c3d-2e1f0a9b8c7d"
COMPANY_ID         = "1021c018-fe0e-4ae8-a972-7487521cc3d9"
DEFINITION_VERSION = "1.0.0"
AGENT_INSTANCE     = "reformai.code-review-agent"

STANDARDS_PATHS = [
    "docs/PLATFORM_ARCHITECTURE.md",
    "docs/repo-standards.md",
    "docs/agent-standards.md",
]

# ── Cost estimation ───────────────────────────────────────────────────────────
# Approximate 2026 Claude pricing — per million tokens (input, output)
_CLAUDE_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus":   (15.00, 75.00),
    "claude-sonnet": (3.00,  15.00),
    "claude-haiku":  (0.25,   1.25),
}

def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    for key, (ir, orr) in _CLAUDE_PRICING.items():
        if key in model.lower():
            return round((tokens_in * ir + tokens_out * orr) / 1_000_000, 6)
    return round((tokens_in * 3.00 + tokens_out * 15.00) / 1_000_000, 6)


# ── Git utilities ─────────────────────────────────────────────────────────────

def get_diff(base_sha: str, commit_sha: str) -> tuple[str, list[str], int]:
    """
    Return (diff_text, changed_files, lines_examined).
    lines_examined counts added + removed lines (not context lines).
    """
    diff = subprocess.check_output(
        ["git", "diff", base_sha, commit_sha],
        cwd=str(REPO_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    names_raw = subprocess.check_output(
        ["git", "diff", "--name-only", base_sha, commit_sha],
        cwd=str(REPO_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip()
    changed_files = [f for f in names_raw.splitlines() if f]
    lines_examined = sum(
        1 for line in diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )
    return diff, changed_files, lines_examined


# ── Standards loader ──────────────────────────────────────────────────────────

def load_standards() -> str:
    """Read all standards documents into a single annotated string."""
    parts: list[str] = []
    for rel in STANDARDS_PATHS:
        path = REPO_ROOT / rel
        if path.exists():
            parts.append(f"=== {rel} ===\n{path.read_text(encoding='utf-8')}")
        else:
            log.warning("Standards document not found: %s", rel)
    if not parts:
        raise RuntimeError("No standards documents found — cannot proceed with review")
    return "\n\n".join(parts)


# ── LLM tool definition ───────────────────────────────────────────────────────
#
# We use Claude tool_use to get deterministic structured output.
# tool_choice forces exactly this tool to be called, eliminating JSON-parse risk.

_SUBMIT_REVIEW_TOOL: dict = {
    "name": "submit_review",
    "description": (
        "Submit the completed code review. "
        "Call this exactly once with all findings and the overall recommendation. "
        "If the diff is clean, call with an empty findings array and recommendation='approve'."
    ),
    "input_schema": {
        "type": "object",
        "required": ["findings", "recommendation", "summary", "governance_flags"],
        "properties": {
            "findings": {
                "type": "array",
                "description": "All findings. Empty array means no issues found.",
                "items": {
                    "type": "object",
                    "required": [
                        "category", "severity", "confidence", "blocking",
                        "title", "explanation", "remediation",
                    ],
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": [
                                "architecture", "observability", "governance",
                                "schema", "security", "type_safety",
                                "operational_semantics", "naming", "documentation",
                            ],
                        },
                        "severity":   {"type": "string", "enum": ["critical", "warning", "info"]},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "blocking":   {"type": "boolean"},
                        "title":       {"type": "string"},
                        "explanation": {
                            "type": "string",
                            "description": "Why this is a finding — backward-looking",
                        },
                        "remediation": {
                            "type": "string",
                            "description": "What to do about it — forward-looking",
                        },
                        "affected_files":  {"type": "array", "items": {"type": "string"}},
                        "line_references": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "file":       {"type": "string"},
                                    "start_line": {"type": "integer"},
                                    "end_line":   {"type": "integer"},
                                },
                            },
                        },
                        "principles": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "PLATFORM_ARCHITECTURE.md principle IDs, e.g. ['P5', 'P6']",
                        },
                        "standards_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific section references, e.g. ['docs/agent-standards.md#3']",
                        },
                        "lessons_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "LESSONS_LEARNED.md section references if applicable",
                        },
                        "operational_risk":      {"type": "string"},
                        "governance_implication": {"type": "string"},
                    },
                },
            },
            "recommendation": {
                "type": "string",
                "enum": ["approve", "approve_with_warnings", "review_required", "block"],
                "description": (
                    "approve=no issues; approve_with_warnings=minor issues only; "
                    "review_required=human judgment needed; block=clear violation or safety risk"
                ),
            },
            "summary": {
                "type": "string",
                "description": (
                    "One paragraph: what was reviewed, how many findings, "
                    "recommendation, and the most significant concern if any."
                ),
            },
            "governance_flags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Short labels for governance signals, e.g. ['missing_telemetry', 'schema_drift']",
            },
        },
    },
}


# ── LLM call ──────────────────────────────────────────────────────────────────

def call_llm(
    *,
    system_prompt: str,
    standards: str,
    diff: str,
    commit_sha: str,
    base_sha: str,
    branch: str,
    model: str,
) -> tuple[dict, int, int]:
    """
    Call Claude with tool_use to get structured findings.

    Uses prompt caching on:
      - system prompt (prompt.md) — stable across all calls
      - standards documents     — stable across calls for the same repo version

    Returns (tool_input_dict, tokens_in, tokens_out).
    """
    client = anthropic.Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        tools=[_SUBMIT_REVIEW_TOOL],
        tool_choice={"type": "tool", "name": "submit_review"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        # Standards docs cached — same for all reviews of this repo
                        "type": "text",
                        "text": f"# Standards and Architecture Documents\n\n{standards}",
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        # The diff is unique per call — not cached
                        "type": "text",
                        "text": (
                            f"# Diff to Review\n\n"
                            f"**Commit:** `{commit_sha}`  \n"
                            f"**Base:**   `{base_sha}`  \n"
                            f"**Branch:** `{branch or '(not specified)'}`\n\n"
                            f"```diff\n{diff}\n```\n\n"
                            f"Review this diff against the standards above. "
                            f"Submit your findings using the `submit_review` tool. "
                            f"If the diff is clean, submit an empty findings array "
                            f"with recommendation='approve'."
                        ),
                    },
                ],
            }
        ],
    )

    tokens_in  = response.usage.input_tokens
    tokens_out = response.usage.output_tokens

    tool_block = next(
        (b for b in response.content if b.type == "tool_use" and b.name == "submit_review"),
        None,
    )
    if tool_block is None:
        raise RuntimeError(
            "Claude did not call submit_review — unexpected response: "
            + str([b.type for b in response.content])
        )

    return tool_block.input, tokens_in, tokens_out


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="code-review-agent — structured pre-push review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  Review last commit:\n"
            "    python agent.py --commit-sha HEAD --base-sha HEAD~1 --branch main\n\n"
            "  Review feature branch vs main:\n"
            "    python agent.py --commit-sha HEAD --base-sha origin/main --branch my-feature\n"
        ),
    )
    parser.add_argument("--commit-sha", required=True,  help="Commit SHA to review")
    parser.add_argument("--base-sha",   required=True,  help="Base SHA to diff against")
    parser.add_argument("--branch",     default="",     help="Branch name (informational)")
    parser.add_argument("--pr-number",  type=int, default=None, help="PR number if available")
    parser.add_argument(
        "--model",
        default=os.environ.get("CODE_REVIEW_MODEL", "claude-opus-4-5"),
        help="Claude model (default: claude-opus-4-5, override with CODE_REVIEW_MODEL env var)",
    )
    args = parser.parse_args()

    # ── OversightClient — check AGENT_OVERSIGHT_SECRET first (per LESSONS_LEARNED.md) ──
    oversight_secret = (
        os.environ.get("AGENT_OVERSIGHT_SECRET")
        or os.environ.get("OVERSIGHT_SECRET")
        or os.environ.get("INGEST_SECRET")
        or ""
    )
    oversight_url = os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app")
    oversight = OversightClient(url=oversight_url, secret=oversight_secret)

    run_id = str(uuid.uuid4())

    with oversight.run(agent_id=AGENT_ID, run_id=run_id) as ctx:

        # ── Step 1: Get diff ──────────────────────────────────────────────────
        with ctx.timer() as t:
            log.info("Fetching diff  %s → %s", args.base_sha[:12], args.commit_sha[:12])
            diff, changed_files, lines_examined = get_diff(args.base_sha, args.commit_sha)
        ctx.step(
            "diff_retrieved",
            message=f"{len(changed_files)} files changed, {lines_examined} lines examined",
            duration_ms=t.ms,
            payload={"files": len(changed_files), "lines": lines_examined},
        )

        if not diff.strip():
            log.info("Empty diff — nothing to review.")
            return

        # ── Step 2: Load standards docs ───────────────────────────────────────
        with ctx.timer() as t:
            standards = load_standards()
        ctx.step(
            "standards_loaded",
            message=f"Loaded {len(STANDARDS_PATHS)} standards documents",
            duration_ms=t.ms,
        )

        # ── Step 3: Call LLM ──────────────────────────────────────────────────
        system_prompt = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")

        log.info("Calling %s for review...", args.model)
        with ctx.timer() as t:
            llm_output, tokens_in, tokens_out = call_llm(
                system_prompt=system_prompt,
                standards=standards,
                diff=diff,
                commit_sha=args.commit_sha,
                base_sha=args.base_sha,
                branch=args.branch,
                model=args.model,
            )
        cost = _estimate_cost(args.model, tokens_in, tokens_out)
        ctx.report(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)
        ctx.step(
            "llm_complete",
            message=(
                f"{len(llm_output.get('findings', []))} findings — "
                f"recommendation: {llm_output.get('recommendation')}"
            ),
            duration_ms=t.ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
        )

        # ── Step 4: Enrich findings with stable UUIDs + sequence numbers ──────
        raw_findings: list[dict] = llm_output.get("findings", [])
        for i, finding in enumerate(raw_findings):
            finding["finding_id"] = str(uuid.uuid4())
            finding["sequence"]   = i + 1
            # Ensure all optional array/string fields are present
            for arr in ("affected_files", "line_references", "principles",
                        "standards_refs", "lessons_refs"):
                finding.setdefault(arr, [])
            for s in ("operational_risk", "governance_implication"):
                finding.setdefault(s, "")

        # ── Step 5: Build + validate + write the artifact ─────────────────────
        artifact = build_artifact(
            commit_sha=args.commit_sha,
            base_sha=args.base_sha,
            branch=args.branch,
            files_examined=changed_files,
            lines_examined=lines_examined,
            findings=raw_findings,
            summary=llm_output.get("summary", ""),
            definition_version=DEFINITION_VERSION,
            agent_instance=AGENT_INSTANCE,
            pr_number=args.pr_number,
            governance_flags=llm_output.get("governance_flags", []),
        )
        # LLM's explicit recommendation takes precedence over the algorithmic derivation
        # in build_artifact() — the LLM has full context and can judge edge cases
        artifact["recommendation"] = llm_output.get("recommendation", artifact["recommendation"])

        with ctx.timer() as t:
            record_id = write_code_review(
                agent_id=AGENT_ID,
                run_id=run_id,
                company_id=COMPANY_ID,
                artifact=artifact,
            )
        ctx.step(
            "artifact_written",
            message=f"code_review artifact written → agent_outputs row {record_id}",
            duration_ms=t.ms,
        )

        # ── Summary output ─────────────────────────────────────────────────────
        sc  = artifact["severity_counts"]
        rec = artifact["recommendation"]
        n   = len(raw_findings)

        print(f"\n{'─' * 62}")
        print(f"  Code Review Complete")
        print(f"  Commit  : {args.commit_sha[:14]}")
        print(f"  Files   : {len(changed_files)} changed  ·  {lines_examined} lines examined")
        print(f"  Findings: {n}  "
              f"({sc['critical']} critical  ·  {sc['warning']} warning  ·  {sc['info']} info)")
        print(f"  Outcome : {rec.upper()}")
        print(f"  Cost    : ${cost:.6f}  "
              f"({tokens_in:,} in  /  {tokens_out:,} out tokens)")
        print(f"  Artifact: agent_outputs/{record_id}")
        print(f"  Run     : {run_id}")
        print(f"{'─' * 62}\n")

        if rec == "block":
            log.warning(
                "Recommendation is BLOCK — review findings before pushing. "
                "See agent_outputs row %s for full details.", record_id
            )
            sys.exit(1)  # non-zero exit lets git pre-push hooks gate on this


if __name__ == "__main__":
    main()
