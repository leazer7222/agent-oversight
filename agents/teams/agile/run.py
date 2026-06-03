#!/usr/bin/env python3
"""
Agile Team Orchestrator - lifecycle coordinator (clarifying stage)
Agent Agile Force

Phase 2 / Step 6: drives the Product Clarification Agent as lifecycle stage 1
(intake normalization). The orchestrator:
  1. resolves tenant + loads product grounding,
  2. builds the intake sources (text adapters),
  3. emits its OWN orchestrator run telemetry,
  4. calls PCA's run_intake() with parent_run_id = orchestrator run (one tree),
  5. routes on the Intake Assessment decision (proceed_direct | clarify | block),
  6. threads the handoff (feature_intent + concepts_to_check + clarification_artifact_id)
     to the downstream CCA/BA stages.

It makes NO LLM calls. PCA does the LLM work and writes the artifacts
(intake_assessment first; clarification_brief only when final).

Auto-chaining CCA -> BA is a later increment; this stage emits the handoff for them.

Usage:
  python agents/teams/agile/run.py --goal "your fuzzy idea"
  python agents/teams/agile/run.py --intake "prd:docs/feature.md" --product-key reformai-product
  python agents/teams/agile/run.py --pass b --answers answers.json --intake "idea:..."
"""

import argparse
import json
import os
import sys
import uuid
import importlib.util as ilu
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "python-sdk"))
from oversight import OversightClient  # noqa: E402

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)
except ImportError:
    pass
for _k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS"):
    if os.environ.get(_k, None) == "":
        os.environ.pop(_k, None)

ORCH_AGENT_ID = os.environ.get("AGILE_ORCHESTRATOR_AGENT_ID", "b2c3d4e5-f6a7-8901-bcde-f12345678901")


def _load_pca():
    spec = ilu.spec_from_file_location(
        "pca_agent", REPO_ROOT / "agents/library/product-clarification-agent/agent.py")
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pca = _load_pca()


def _orch_client() -> OversightClient:
    return OversightClient(
        url=os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app"),
        secret=(os.environ.get("AGENT_OVERSIGHT_SECRET") or os.environ.get("OVERSIGHT_SECRET")
                or os.environ.get("INGEST_SECRET") or ""))


def _emit(client: OversightClient, **kw) -> None:
    try:
        client.emit(**kw)
    except Exception as e:  # telemetry must never break the run
        print(f"[warn] orchestrator telemetry: {str(e)[:120]}", file=sys.stderr)


def _next_state(decision: str) -> str:
    return {"proceed_direct": "context_scanning",
            "clarify": "clarification_blocked",
            "block": "clarification_blocked"}.get(decision, "clarification_blocked")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Agile Team Orchestrator - clarifying stage (PCA)")
    p.add_argument("--intake", action="append", help="TYPE:SOURCE (file path or inline text); repeatable")
    p.add_argument("--goal", help="convenience: a one-line idea intake")
    p.add_argument("--product-key", default="reformai-product")
    p.add_argument("--tenant", default="ReformAI", help="company name or explicit UUID")
    p.add_argument("--workspace-id", default="reformai-product", help="grounding bundle workspace")
    p.add_argument("--model", default=os.environ.get("PCA_MODEL", "claude-sonnet-4-6"))
    p.add_argument("--pass", dest="pass_", choices=["a", "b"], default="a")
    p.add_argument("--answers", help="Pass B: JSON file of [{question, answer}, ...]")
    p.add_argument("--no-persist", action="store_true")
    args = p.parse_args()

    tenant = pca.resolve_tenant(args.tenant)
    grounding = pca.load_grounding(args.workspace_id)
    if grounding["missing"]:
        print(f"[warn] grounding missing: {', '.join(grounding['missing'])}", file=sys.stderr)
    sources, sources_text = pca.build_sources(args.intake, args.goal)
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8")) if args.answers else None
    if args.pass_ == "b" and not answers:
        raise SystemExit("--pass b requires --answers")

    orch_run_id = str(uuid.uuid4())
    client = _orch_client()
    _emit(client, agent_id=ORCH_AGENT_ID, event="run_started", run_id=orch_run_id, team_id="agile",
          metadata={"stage": "clarifying", "product_key": args.product_key,
                    "workspace_id": args.workspace_id, "intake_sources": len(sources), "pass": args.pass_})
    print(f"Orchestrator run {orch_run_id[:8]}  stage=clarifying  product={args.product_key}  "
          f"intake_sources={len(sources)}")

    try:
        result = pca.run_intake(
            sources=sources, sources_text=sources_text, product_key=args.product_key,
            tenant=tenant, workspace_id=args.workspace_id, grounding=grounding,
            model=args.model, pass_=args.pass_, answers=answers, no_persist=args.no_persist,
            parent_run_id=orch_run_id)
    except Exception as exc:
        _emit(client, agent_id=ORCH_AGENT_ID, event="run_failed", run_id=orch_run_id,
              error=f"[orchestrator_error] {exc}", metadata={"team_id": "agile", "stage": "clarifying"})
        raise

    pca._print_result(result)

    decision = result["decision"]
    handoff = result.get("handoff") or {}
    _emit(client, agent_id=ORCH_AGENT_ID, event="run_completed", run_id=orch_run_id,
          metadata={"team_id": "agile", "stage": "clarifying", "decision": decision,
                    "next_state": _next_state(decision),
                    "intake_assessment_artifact_id": result.get("assessment_id"),
                    "clarification_brief_artifact_id": result.get("brief_id"),
                    "feature_intent": handoff.get("feature_intent"),
                    "concepts_to_check": handoff.get("concepts_to_check"),
                    "pca_run_id": result["run_id"]})

    print(f"\n=== Lifecycle: clarifying -> {_next_state(decision)} ===")
    if decision == "proceed_direct":
        print("Stage 1 (clarifying) COMPLETE. Handoff ready for downstream stages:")
        print(f"  feature_intent    : {handoff.get('feature_intent','')}")
        print(f"  concepts_to_check : {', '.join(handoff.get('concepts_to_check', []))}")
        print(f"  clarification id  : {result.get('brief_id')}")
        print("  Next: CCA (context_scanning) -> BA (scoping) with --clarification-artifact-id above.")
    elif decision == "clarify":
        print("Stage 1 paused on clarification (clarification_blocked).")
        print(f"  Answer the questions, then re-run with: --pass b --answers <file>")
        print(f"  intake_assessment: {result.get('assessment_id')}")
    else:  # block
        print("Stage 1 blocked: intake too thin (clarification_blocked). Provide richer intake.")


if __name__ == "__main__":
    main()
