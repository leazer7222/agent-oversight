#!/usr/bin/env python3
"""
Agile Team Orchestrator — Phase 1
Agent Agile Force / Agent Oversight Sandbox

Deterministic workflow runner for the Agile Team.
Phase 1 scope: Product Clarification Agent only.

Usage:
  python agents/teams/agile/run.py --goal "your fuzzy goal here"
  python agents/teams/agile/run.py --goal "..." --workspace-id reformai
  python agents/teams/agile/run.py --goal "..." --context-notes "extra context"

This script makes no LLM calls. It:
  1. Loads the context bundle for the requested workspace
  2. Enforces the staleness gate (refuses to run if docs exceed 48h threshold)
  3. Loads doc content + computes hashes
  4. Emits its own run_started telemetry as the orchestrator
  5. Calls the PCA with pre-loaded context
  6. Validates the Brief against clarification-brief.schema.json
  7. Saves artifacts (JSON + Markdown)
  8. Emits run_completed telemetry
  9. Prints the human-readable Brief to stdout
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

# Repo root is 3 levels up from agents/teams/agile/
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "python-sdk"))
from oversight import OversightClient  # noqa: E402

import importlib.util as _ilu

def _import_pca():
    spec = _ilu.spec_from_file_location(
        "pca_agent",
        REPO_ROOT / "agents/library/product-clarification-agent/agent.py",
    )
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_pca_mod = _import_pca()
ProductClarificationAgent = _pca_mod.ProductClarificationAgent
PCAInput = _pca_mod.PCAInput


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STALENESS_THRESHOLD_HOURS = 48  # matches context bundle spec


def load_env() -> dict:
    """Load required env vars. Exit with a clear message if any are missing."""
    from dotenv import load_dotenv, find_dotenv
    # Search from CWD upward for .env.local (handles both worktree and main repo invocation)
    env_file = find_dotenv(".env.local", usecwd=True)
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv(REPO_ROOT / ".env.local")

    required = {
        "OVERSIGHT_URL": os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app"),
        "OVERSIGHT_SECRET": (
            os.environ.get("AGENT_OVERSIGHT_SECRET")
            or os.environ.get("OVERSIGHT_SECRET")
            or os.environ.get("INGEST_SECRET")
        ),
        "PCA_AGENT_ID": os.environ.get("PCA_AGENT_ID"),
        "AGILE_ORCHESTRATOR_AGENT_ID": os.environ.get("AGILE_ORCHESTRATOR_AGENT_ID"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"ERROR: Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        print("Set these in .env.local at the repo root.", file=sys.stderr)
        sys.exit(1)
    return required


# ---------------------------------------------------------------------------
# Context bundle loading
# ---------------------------------------------------------------------------

def load_bundle(workspace_id: str) -> dict:
    bundle_path = REPO_ROOT / f"docs/workspaces/{workspace_id}/context-bundles/agile-v1.json"
    if not bundle_path.exists():
        print(f"ERROR: Context bundle not found: {bundle_path}", file=sys.stderr)
        print(f"  Create docs/workspaces/{workspace_id}/context-bundles/agile-v1.json first.", file=sys.stderr)
        sys.exit(1)
    return json.loads(bundle_path.read_text(encoding="utf-8"))


def check_staleness(bundle: dict) -> list[str]:
    """
    Staleness gate. Check each required doc:
      - Does the file exist?
      - Has it been modified within the threshold?
    Returns a list of violation descriptions. Empty = all clear.
    """
    threshold_hours = bundle.get("staleness_threshold_hours", STALENESS_THRESHOLD_HOURS)
    threshold_secs = threshold_hours * 3600
    now = datetime.datetime.utcnow().timestamp()
    violations = []

    for doc in bundle["docs"]:
        if not doc.get("required", True):
            continue
        doc_path = REPO_ROOT / doc["path"]
        if not doc_path.exists():
            violations.append(f"MISSING: {doc['path']}")
            continue
        age_secs = now - doc_path.stat().st_mtime
        if age_secs > threshold_secs:
            age_hours = age_secs / 3600
            violations.append(
                f"STALE ({age_hours:.1f}h old, threshold {threshold_hours}h): {doc['path']}"
            )
    return violations


def load_docs(bundle: dict) -> dict[str, tuple[str, str]]:
    """Load doc content and SHA-256 hash for each bundle doc. Returns {path: (content, hash)}."""
    result = {}
    for doc in bundle["docs"]:
        doc_path = REPO_ROOT / doc["path"]
        content = doc_path.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        result[doc["path"]] = (content, content_hash)
    return result


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_brief(brief: dict) -> list[str]:
    """Validate Brief against clarification-brief.schema.json. Returns list of errors."""
    try:
        import jsonschema
    except ImportError:
        print("WARNING: jsonschema not installed — skipping schema validation.", file=sys.stderr)
        print("  Install with: pip install jsonschema", file=sys.stderr)
        return []

    schema_path = REPO_ROOT / "docs/schemas/clarification-brief.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = []
    validator = jsonschema.Draft7Validator(schema)
    for err in validator.iter_errors(brief):
        errors.append(f"{'.'.join(str(p) for p in err.path) or 'root'}: {err.message}")
    return errors


# ---------------------------------------------------------------------------
# Artifact saving
# ---------------------------------------------------------------------------

def save_artifacts(brief: dict, run_id: str) -> tuple[Path, Path]:
    """Save Brief as JSON + human-readable Markdown. Returns (json_path, md_path)."""
    output_dir = REPO_ROOT / "outputs/clarification-briefs"
    output_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    short_id = run_id[:8]
    base = output_dir / f"{date_str}-{short_id}"

    json_path = base.with_suffix(".json")
    json_path.write_text(json.dumps(brief, indent=2), encoding="utf-8")

    md_path = base.with_suffix(".md")
    md_path.write_text(_brief_to_markdown(brief), encoding="utf-8")

    return json_path, md_path


def _brief_to_markdown(brief: dict) -> str:
    meta = brief.get("metadata", {})
    ci = brief.get("context_integrity", {})
    rating = ci.get("rating", "unknown")
    rating_emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(rating, "⚪")

    lines = [
        f"# Clarification Brief",
        f"",
        f"**Agent:** {meta.get('agent', 'product-clarification-agent')}  ",
        f"**Run ID:** {meta.get('run_id', '')}  ",
        f"**Timestamp:** {meta.get('timestamp', '')}  ",
        f"**Workspace:** {meta.get('workspace_id', '')}  ",
        f"**Context Bundle:** {meta.get('context_bundle_id', '')} v{meta.get('context_bundle_version', '')}  ",
        f"**Context Integrity:** {rating_emoji} {rating.capitalize()}",
        f"",
        f"---",
        f"",
        f"## 1. Restated Goal",
        f"",
        brief.get("restated_goal", ""),
        f"",
        f"## 2. Problem Statement",
        f"",
        brief.get("problem_statement", ""),
        f"",
        f"## 3. Target User",
        f"",
        brief.get("target_user", ""),
        f"",
        f"## 4. Proposed Scope",
        f"",
        f"### In Scope",
    ]
    for item in brief.get("proposed_scope", {}).get("in_scope", []):
        lines.append(f"- {item}")
    lines += ["", "### Out of Scope"]
    for item in brief.get("proposed_scope", {}).get("out_of_scope", []):
        lines.append(f"- {item}")

    lines += ["", "## 5. Success Criteria", ""]
    for i, criterion in enumerate(brief.get("success_criteria", []), 1):
        lines.append(f"{i}. {criterion}")

    lines += [
        "",
        "## 6. Open Questions",
        "",
        "> These must be answered before this Brief moves to Story Structuring.",
        "",
    ]
    for i, q in enumerate(brief.get("open_questions", []), 1):
        lines.append(f"{i}. {q}")

    domain_terms = brief.get("domain_terms", [])
    if domain_terms:
        lines += ["", "## 7. Domain Terms Referenced", "", "| Term | Definition |", "|---|---|"]
        for dt in domain_terms:
            lines.append(f"| {dt['term']} | {dt['definition']} |")

    staleness = brief.get("staleness_flags", [])
    lines += ["", "## 8. Staleness Flags", ""]
    if staleness:
        for flag in staleness:
            lines.append(f"- {flag}")
    else:
        lines.append("_No staleness flags detected._")

    lines += [
        "",
        "## 9. Context Integrity",
        "",
        f"**Rating:** {rating_emoji} {rating.capitalize()}",
        "",
        ci.get("reasoning", ""),
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Agile Team Orchestrator — Phase 1 (PCA)")
    parser.add_argument("--goal",          required=True,  help="The raw product goal (fuzzy is fine)")
    parser.add_argument("--workspace-id",  default="agent-oversight", help="Workspace to run against (default: agent-oversight)")
    parser.add_argument("--context-notes", default=None,   help="Optional supplementary context")
    parser.add_argument("--target-user",   default=None,   help="Optional named user segment")
    parser.add_argument("--urgency",       default=None,   help="Optional urgency signal")
    args = parser.parse_args()

    env = load_env()

    # 1. Load context bundle
    print(f"Loading context bundle for workspace: {args.workspace_id}")
    bundle = load_bundle(args.workspace_id)
    bundle_id = bundle["bundle_id"]
    bundle_version = bundle["version"]

    # 2. Staleness gate
    print("Checking doc freshness...")
    violations = check_staleness(bundle)
    if violations:
        print("\nERROR: Staleness gate blocked the run. Update these docs before proceeding:\n")
        for v in violations:
            print(f"  • {v}")
        print(f"\nRule: docs must be updated within {bundle.get('staleness_threshold_hours', 48)} hours of any trigger event.")
        sys.exit(1)
    print("  All docs current. OK")

    # 3. Load doc content
    docs = load_docs(bundle)
    product_md_content, _ = docs[bundle["docs"][0]["path"]]
    domain_md_content, _  = docs[bundle["docs"][1]["path"]]
    story_ready_content, _ = docs[bundle["docs"][2]["path"]]

    doc_hashes = {path: h for path, (_, h) in docs.items()}

    # 4. Generate run IDs
    orchestrator_run_id = str(uuid.uuid4())
    pca_run_id = str(uuid.uuid4())

    # 5. Emit orchestrator run_started
    orchestrator_client = OversightClient(
        url=env["OVERSIGHT_URL"],
        secret=env["OVERSIGHT_SECRET"],
    )
    orchestrator_client.emit(
        agent_id=env["AGILE_ORCHESTRATOR_AGENT_ID"],
        event="run_started",
        run_id=orchestrator_run_id,
        team_id="agile",
        context_bundle_id=bundle_id,
        context_bundle_version=bundle_version,
        metadata={
            "workspace_id": args.workspace_id,
            "doc_hashes": doc_hashes,
            "goal_chars": len(args.goal),
        },
    )

    print(f"\nOrchestrator run: {orchestrator_run_id[:8]}...")
    print(f"Context bundle:   {bundle_id} v{bundle_version}")
    print(f"Docs loaded:      {', '.join(d['path'].split('/')[-1] for d in bundle['docs'])}")

    try:
        # 6. Call PCA
        print("\nCalling Product Clarification Agent...")
        pca = ProductClarificationAgent(agent_id=env["PCA_AGENT_ID"])

        pca_input = PCAInput(
            goal=args.goal,
            product_md=product_md_content,
            domain_md=domain_md_content,
            story_ready_md=story_ready_content,
            context_bundle_id=bundle_id,
            context_bundle_version=bundle_version,
            workspace_id=args.workspace_id,
            run_id=pca_run_id,
            context_notes=args.context_notes,
            target_user=args.target_user,
            urgency=args.urgency,
        )

        brief = pca.run(pca_input)

        # 7. Schema validation
        print("Validating output against schema...")
        schema_errors = validate_brief(brief)
        if schema_errors:
            print("\nERROR: Schema validation failed:")
            for err in schema_errors:
                print(f"  • {err}")
            orchestrator_client.emit(
                agent_id=env["AGILE_ORCHESTRATOR_AGENT_ID"],
                event="run_failed",
                run_id=orchestrator_run_id,
                error=f"Schema validation failed: {'; '.join(schema_errors)}",
                metadata={"workspace_id": args.workspace_id, "team_id": "agile"},
            )
            sys.exit(1)
        print("  Schema valid. OK")

        # 8. Save artifacts
        json_path, md_path = save_artifacts(brief, pca_run_id)
        print(f"  JSON: {json_path.relative_to(REPO_ROOT)}")
        print(f"  MD:   {md_path.relative_to(REPO_ROOT)}")

        # 9. Emit orchestrator run_completed
        orchestrator_client.emit(
            agent_id=env["AGILE_ORCHESTRATOR_AGENT_ID"],
            event="run_completed",
            run_id=orchestrator_run_id,
            metadata={
                "workspace_id": args.workspace_id,
                "team_id": "agile",
                "context_bundle_id": bundle_id,
                "context_bundle_version": bundle_version,
                "pca_run_id": pca_run_id,
                "context_integrity_rating": brief.get("context_integrity", {}).get("rating"),
                "open_questions_count": len(brief.get("open_questions", [])),
                "json_artifact": str(json_path),
                "md_artifact": str(md_path),
            },
        )

        # 10. Print human-readable Brief
        print("\n" + "=" * 70)
        print(md_path.read_text(encoding="utf-8"))
        print("=" * 70)
        print(f"\nRun complete. PCA run ID: {pca_run_id[:8]}...")

    except Exception as exc:
        orchestrator_client.emit(
            agent_id=env["AGILE_ORCHESTRATOR_AGENT_ID"],
            event="run_failed",
            run_id=orchestrator_run_id,
            error=f"[orchestrator_error] {exc}",
            metadata={"workspace_id": args.workspace_id, "team_id": "agile"},
        )
        raise


if __name__ == "__main__":
    main()
