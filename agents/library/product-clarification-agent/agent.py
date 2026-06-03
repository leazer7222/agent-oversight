"""
Product Clarification Agent
Agile Team — Agent Agile Force

Receives pre-loaded workspace context from the Team Orchestrator.
Calls an LLM to produce a Clarification Brief conforming to clarification-brief.schema.json.
Emits run telemetry via the oversight.py SDK.

The agent reads no files and calls no external tools.
All I/O is through the run() method.
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Add python-sdk to path for oversight client
_repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_repo_root / "python-sdk"))
from oversight import OversightClient, OversightError, StepTimer  # noqa: E402


@dataclass
class PCAInput:
    goal: str
    product_md: str
    domain_md: str
    story_ready_md: str
    context_bundle_id: str
    context_bundle_version: int
    workspace_id: str
    run_id: str
    context_notes: Optional[str] = None
    target_user: Optional[str] = None
    urgency: Optional[str] = None


class ProductClarificationAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.client = OversightClient(
            url=os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app"),
            secret=(
                os.environ.get("AGENT_OVERSIGHT_SECRET")
                or os.environ.get("OVERSIGHT_SECRET")
                or os.environ.get("INGEST_SECRET")
            ),
        )
        self.prompt = self._load_prompt()
        self.provider = os.environ.get("AGILE_LLM_PROVIDER", "anthropic").lower()

    def _load_prompt(self) -> str:
        prompt_path = Path(__file__).parent / "prompt.md"
        return prompt_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # LLM call — configurable provider
    # ------------------------------------------------------------------

    def _call_llm(self, user_message: str) -> tuple[str, int, int, float]:
        """Call the configured LLM. Returns (content, tokens_in, tokens_out, cost_usd)."""
        if self.provider == "anthropic":
            return self._call_anthropic(user_message)
        elif self.provider == "openai":
            return self._call_openai(user_message)
        elif self.provider == "gemini":
            return self._call_gemini(user_message)
        else:
            raise ValueError(f"Unknown AGILE_LLM_PROVIDER: {self.provider!r}. Use anthropic, openai, or gemini.")

    def _call_anthropic(self, user_message: str) -> tuple[str, int, int, float]:
        import anthropic
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        # Input: $3/M tokens  Output: $15/M tokens (claude-sonnet-4-6)
        COST_IN = 3.0 / 1_000_000
        COST_OUT = 15.0 / 1_000_000

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            system=self.prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        content = resp.content[0].text
        tok_in = resp.usage.input_tokens
        tok_out = resp.usage.output_tokens
        cost = tok_in * COST_IN + tok_out * COST_OUT
        return content, tok_in, tok_out, round(cost, 6)

    def _call_openai(self, user_message: str) -> tuple[str, int, int, float]:
        from openai import OpenAI
        model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        # gpt-4o pricing (approximate)
        COST_IN = 2.5 / 1_000_000
        COST_OUT = 10.0 / 1_000_000

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        tok_in = resp.usage.prompt_tokens if resp.usage else 0
        tok_out = resp.usage.completion_tokens if resp.usage else 0
        cost = tok_in * COST_IN + tok_out * COST_OUT
        return content, tok_in, tok_out, round(cost, 6)

    def _call_gemini(self, user_message: str) -> tuple[str, int, int, float]:
        import google.generativeai as genai
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp")
        # Gemini 2.0 Flash — free tier (cost = 0 on free)
        COST_IN = 0.0
        COST_OUT = 0.0

        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=self.prompt,
        )
        resp = model.generate_content(user_message)
        content = resp.text
        tok_in = getattr(resp.usage_metadata, "prompt_token_count", 0) or 0
        tok_out = getattr(resp.usage_metadata, "candidates_token_count", 0) or 0
        cost = tok_in * COST_IN + tok_out * COST_OUT
        return content, tok_in, tok_out, round(cost, 6)

    # ------------------------------------------------------------------
    # Context assembly
    # ------------------------------------------------------------------

    def _build_user_message(self, inp: PCAInput) -> str:
        parts = [
            "## PRODUCT.md\n\n" + inp.product_md,
            "## DOMAIN.md\n\n" + inp.domain_md,
            "## STORY-READY.md\n\n" + inp.story_ready_md,
            f"## Goal\n\n{inp.goal}",
        ]
        if inp.context_notes:
            parts.append(f"## Context Notes\n\n{inp.context_notes}")
        if inp.target_user:
            parts.append(f"## Target User (provided)\n\n{inp.target_user}")
        if inp.urgency:
            parts.append(f"## Urgency\n\n{inp.urgency}")
        parts.append(
            "## Your Task\n\n"
            "Produce a single JSON object conforming to clarification-brief.schema.json. "
            "No markdown fences, no preamble, no explanation — only the JSON object."
        )
        return "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self, inp: PCAInput) -> dict:
        """
        Execute a PCA run with the provided input.
        Returns the parsed Clarification Brief dict.
        Emits telemetry via the oversight client.
        Raises on unrecoverable error (orchestrator handles).
        """
        with self.client.run(
            agent_id=self.agent_id,
            run_id=inp.run_id,
            team_id="agile",
            context_bundle_id=inp.context_bundle_id,
            context_bundle_version=inp.context_bundle_version,
            metadata={
                "workspace_id": inp.workspace_id,
                "provider": self.provider,
                "goal_chars": len(inp.goal),
            },
        ) as ctx:
            # Step 1: context check
            with ctx.timer() as t:
                doc_chars = {
                    "product_md": len(inp.product_md),
                    "domain_md": len(inp.domain_md),
                    "story_ready_md": len(inp.story_ready_md),
                }
                staleness_flags_found = []
                for doc_name, content in [
                    ("PRODUCT.md", inp.product_md),
                    ("DOMAIN.md", inp.domain_md),
                    ("STORY-READY.md", inp.story_ready_md),
                ]:
                    if "> **STALE" in content:
                        staleness_flags_found.append(doc_name)

            ctx.step(
                "context_check",
                message=f"Docs loaded. Total chars: {sum(doc_chars.values())}. "
                        f"Staleness flags: {staleness_flags_found or 'none'}",
                duration_ms=t.ms,
                payload={
                    "doc_chars": doc_chars,
                    "staleness_flags": staleness_flags_found,
                    "context_notes_provided": inp.context_notes is not None,
                },
            )

            # Step 2: build user message
            with ctx.timer() as t:
                user_message = self._build_user_message(inp)

            ctx.step(
                "goal_analysis",
                message=f"User message assembled. Total chars: {len(user_message)}",
                duration_ms=t.ms,
                payload={"message_chars": len(user_message)},
            )

            # Step 3: LLM call
            with ctx.timer() as t:
                raw_content, tok_in, tok_out, cost = self._call_llm(user_message)

            ctx.step(
                "brief_generation",
                message=f"LLM call complete via {self.provider}. "
                        f"tokens_in={tok_in} tokens_out={tok_out} cost=${cost:.4f}",
                duration_ms=t.ms,
                tokens_in=tok_in,
                tokens_out=tok_out,
                cost_usd=cost,
                payload={"provider": self.provider, "raw_chars": len(raw_content)},
            )

            ctx.report(tokens_in=tok_in, tokens_out=tok_out, cost_usd=cost)

            # Step 4: parse JSON
            with ctx.timer() as t:
                # Strip markdown fences if the model added them despite instructions
                content = raw_content.strip()
                if content.startswith("```"):
                    lines = content.splitlines()
                    content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                brief = json.loads(content)

            # Inject metadata fields the agent cannot self-populate
            import datetime
            brief.setdefault("metadata", {})
            brief["metadata"]["agent"] = "product-clarification-agent"
            brief["metadata"]["run_id"] = inp.run_id
            brief["metadata"]["timestamp"] = datetime.datetime.utcnow().isoformat() + "Z"
            brief["metadata"]["workspace_id"] = inp.workspace_id
            brief["metadata"]["team_id"] = "agile"
            brief["metadata"]["context_bundle_id"] = inp.context_bundle_id
            brief["metadata"]["context_bundle_version"] = inp.context_bundle_version

            ctx.step(
                "quality_self_check",
                message="JSON parsed successfully. Metadata fields injected.",
                duration_ms=t.ms,
                payload={
                    "context_integrity_rating": brief.get("context_integrity", {}).get("rating", "unknown"),
                    "open_questions_count": len(brief.get("open_questions", [])),
                    "success_criteria_count": len(brief.get("success_criteria", [])),
                    "domain_terms_count": len(brief.get("domain_terms", [])),
                    "staleness_flags_count": len(brief.get("staleness_flags", [])),
                },
            )

        return brief


# ==========================================================================================
# Intake-normalization pipeline (Phase 1: text intake)
# ==========================================================================================
# PCA as the Agile front door. Transforms arbitrary text intake into a complete Clarification
# Brief + handoff. Clarification is CONDITIONAL: the intake classifier writes a logged
# intake_assessment FIRST (every run); the clarification_brief is written ONLY when final
# (proceed_direct, or after Pass B). See docs/agile-pca-integration-plan.md.

import argparse  # noqa: E402
import hashlib   # noqa: E402
import logging   # noqa: E402
import uuid      # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import requests   # noqa: E402
import anthropic  # noqa: E402
import jsonschema  # noqa: E402

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)
except ImportError:
    pass

# Claude Code injects EMPTY ANTHROPIC_* vars -> illegal 'Bearer ' header.
for _k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS"):
    if os.environ.get(_k, None) == "":
        os.environ.pop(_k, None)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
_log = logging.getLogger("pca")

REPO_ROOT          = Path(__file__).resolve().parents[3]
AGENT_INSTANCE_ID  = os.environ.get("PCA_AGENT_ID", "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
AGENT_INSTANCE     = "reformai.product-clarification-agent"
DEFINITION_VERSION = "1.0.0"
SCHEMAS            = REPO_ROOT / "docs" / "schemas"
BRIEF_SCHEMA_PATH  = SCHEMAS / "clarification-brief.schema.json"
ASSESS_SCHEMA_PATH = SCHEMAS / "intake-assessment.schema.json"
PKG_SCHEMA_PATH    = SCHEMAS / "intake-package.schema.json"

TEXT_INTAKE_TYPES = {
    "idea", "paragraph", "prd", "jira_text", "customer_feedback", "bug_enhancement", "text_workflow",
}

_PRICING = {"claude-opus": (15.00, 75.00), "claude-sonnet": (3.00, 15.00), "claude-haiku": (0.25, 1.25)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _est_cost(model: str, ti: int, to: int) -> float:
    for k, (ir, orr) in _PRICING.items():
        if k in model.lower():
            return round((ti * ir + to * orr) / 1_000_000, 6)
    return round((ti * 3.0 + to * 15.0) / 1_000_000, 6)


class _NullCtx:
    def step(self, *a, **k): pass
    def report(self, *a, **k): pass
    def timer(self): return StepTimer()


import contextlib  # noqa: E402


@contextlib.contextmanager
def _telemetry(oversight: OversightClient, **kw):
    try:
        with oversight.run(**kw) as ctx:
            yield ctx
        return
    except OversightError as e:
        _log.warning("telemetry disabled (%s) - proceeding", str(e)[:140])
        yield _NullCtx()


# -- Supabase REST helpers (mirror BA) -----------------------------------------------------

def _sb():
    url = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return url, {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def resolve_tenant(name_or_id: str) -> str:
    """Resolve company by exact name or explicit UUID. Never LIMIT 1."""
    try:
        uuid.UUID(name_or_id)
        return name_or_id
    except ValueError:
        pass
    url, h = _sb()
    r = requests.get(f"{url}/rest/v1/companies", headers=h,
                     params={"name": f"eq.{name_or_id}", "select": "id,name"}, timeout=20)
    r.raise_for_status()
    rows = r.json()
    if len(rows) != 1:
        raise RuntimeError(f"tenant '{name_or_id}' resolved to {len(rows)} companies (need exactly 1)")
    return rows[0]["id"]


def write_agent_output(output_type: str, content: dict, run_id: str, company_id: str) -> str:
    url, h = _sb()
    r = requests.post(f"{url}/rest/v1/agent_outputs",
        headers={**h, "Prefer": "return=representation"},
        json={"agent_id": AGENT_INSTANCE_ID, "run_id": run_id, "company_id": company_id,
              "output_type": output_type, "content": content}, timeout=25)
    if not r.ok:
        raise RuntimeError(f"agent_outputs write failed ({output_type}): {r.status_code} {r.text}")
    d = r.json()
    return (d[0] if isinstance(d, list) else d).get("id", "")


# -- Product grounding (stable per product; distinct from intake) --------------------------

def load_grounding(workspace_id: str) -> dict:
    """Load PRODUCT/DOMAIN/STORY-READY grounding from the workspace bundle. Tolerates absence."""
    g = {"product_md": "", "domain_md": "", "story_ready_md": "",
         "bundle_id": "agile-v1", "bundle_version": 1, "available": False, "missing": []}
    bundle_path = REPO_ROOT / f"docs/workspaces/{workspace_id}/context-bundles/agile-v1.json"
    if not bundle_path.exists():
        g["missing"].append(str(bundle_path.relative_to(REPO_ROOT)))
        return g
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    g["bundle_id"] = bundle.get("bundle_id", "agile-v1")
    g["bundle_version"] = bundle.get("version", 1)
    keys = ["product_md", "domain_md", "story_ready_md"]
    for i, doc in enumerate(bundle.get("docs", [])[:3]):
        p = REPO_ROOT / doc["path"]
        if p.exists():
            g[keys[i]] = p.read_text(encoding="utf-8")
        else:
            g["missing"].append(doc["path"])
    g["available"] = bool(g["product_md"] or g["domain_md"])
    return g


def _grounding_text(g: dict) -> str:
    if not g["available"]:
        return "(NO product grounding available - PRODUCT.md/DOMAIN.md absent. Reflect this in context_integrity.)"
    return f"## PRODUCT.md\n\n{g['product_md']}\n\n## DOMAIN.md\n\n{g['domain_md']}\n\n## STORY-READY.md\n\n{g['story_ready_md']}"


# -- Intake adapters (text) ----------------------------------------------------------------

def build_sources(intake_entries, goal) -> tuple[list[dict], str]:
    """Build canonical source records + a combined raw blob from intake entries (TYPE:SOURCE) + optional goal."""
    raw: list[tuple[str, str]] = []
    for entry in (intake_entries or []):
        if ":" not in entry:
            raise SystemExit("--intake must be TYPE:SOURCE (SOURCE = file path or inline text)")
        t, src = entry.split(":", 1)
        raw.append((t.strip(), src.strip()))
    if goal:
        raw.append(("idea", goal))
    if not raw:
        raise SystemExit("provide at least one --intake TYPE:SOURCE (or --goal)")

    sources, blobs = [], []
    for t, src in raw:
        if t not in TEXT_INTAKE_TYPES:
            raise SystemExit(f"unknown intake type '{t}'; Phase 1 supports {sorted(TEXT_INTAKE_TYPES)}")
        cand = Path(src)
        cand_rel = REPO_ROOT / src
        if cand.exists():
            text, origin = cand.read_text(encoding="utf-8"), src
        elif cand_rel.exists():
            text, origin = cand_rel.read_text(encoding="utf-8"), src
        else:
            text, origin = src, "inline"
        sources.append({
            "source_type": t, "origin_ref": origin,
            "content_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
            "adapter": f"text:{t}", "ingested_at": _now(),
        })
        blobs.append(f"## SOURCE [{t}] ({origin})\n\n{text}")
    return sources, "\n\n---\n\n".join(blobs)


def build_package(sources: list[dict], analysis: dict) -> dict:
    sig = dict(analysis.get("extracted_signals") or {})
    for k in ("explicit_goals", "actors", "workflows", "states", "entities", "stated_rules", "constraints"):
        sig.setdefault(k, [])
    return {
        "sources": sources,
        "normalized_text": analysis.get("normalized_text", ""),
        "extracted_signals": {k: list(sig[k]) for k in
            ("explicit_goals", "actors", "workflows", "states", "entities", "stated_rules", "constraints")},
        "attachments": [],
        "provenance": {"source_count": len(sources), "modalities": ["text"], "mixed": len(sources) > 1},
    }


# -- LLM calls -----------------------------------------------------------------------------

_ANALYSIS_TOOL = {
    "name": "submit_intake_analysis",
    "description": "Normalize the intake and assess whether it can satisfy the Clarification Brief contract.",
    "input_schema": {
        "type": "object",
        "required": ["normalized_text", "extracted_signals", "field_coverage", "scores", "blocking_gaps", "decision", "rationale"],
        "properties": {
            "normalized_text": {"type": "string", "description": "Unified statement of intent across all sources."},
            "extracted_signals": {"type": "object", "properties": {
                "explicit_goals": {"type": "array", "items": {"type": "string"}},
                "actors":         {"type": "array", "items": {"type": "string"}},
                "workflows":      {"type": "array", "items": {"type": "string"}},
                "states":         {"type": "array", "items": {"type": "string"}},
                "entities":       {"type": "array", "items": {"type": "string"}},
                "stated_rules":   {"type": "array", "items": {"type": "string"}},
                "constraints":    {"type": "array", "items": {"type": "string"}}}},
            "field_coverage": {"type": "array", "items": {"type": "object",
                "required": ["field", "covered", "confidence"], "properties": {
                    "field": {"type": "string"}, "covered": {"type": "boolean"},
                    "confidence": {"type": "number"}, "evidence": {"type": "string"},
                    "source_refs": {"type": "array", "items": {"type": "string"}}}}},
            "scores": {"type": "object", "required": ["fidelity", "completeness", "ambiguity", "context_confidence"],
                "properties": {"fidelity": {"type": "number"}, "completeness": {"type": "number"},
                               "ambiguity": {"type": "number"}, "context_confidence": {"type": "number"}}},
            "blocking_gaps": {"type": "array", "items": {"type": "object",
                "required": ["field", "why"], "properties": {"field": {"type": "string"}, "why": {"type": "string"}}}},
            "decision": {"type": "string", "enum": ["proceed_direct", "clarify", "block"]},
            "rationale": {"type": "string"},
        },
    },
}

_ANALYSIS_SYSTEM = """You are the intake classifier for the Product Clarification Agent - the Agile front door.
Given arbitrary product intake (one or more text sources) and the product grounding, you do TWO things:
1. Normalize the intake into one statement of intent and extract intent-level signals (actors, workflows,
   states, entities, stated rules, constraints). These are ASSERTIONS from the intake - not code reality,
   not design. Entities seed the downstream existence-check.
2. Assess COVERAGE of the Clarification Brief contract, field by field: problem_statement, target_user,
   proposed_scope (in/out), success_criteria, and the handoff (feature_intent + concept nouns).

Decide:
- proceed_direct: every required field is confidently derivable AND there is no blocking fork. No questions.
- clarify: one or more blocking gaps - fields you cannot fill confidently, or a fork that changes the
  data model/scope. List them in blocking_gaps.
- block: the intake is too thin to form coherent intent at all.

Be decisive: a well-formed paragraph / PRD / detailed ticket should usually be proceed_direct. Ask only for
what the intake genuinely does not resolve. Call submit_intake_analysis exactly once."""

_BRIEF_TOOL = {
    "name": "submit_clarification_brief",
    "description": "Produce the Clarification Brief contract from the normalized intake + grounding.",
    "input_schema": {
        "type": "object",
        "required": ["restated_goal", "problem_statement", "target_user", "proposed_scope",
                     "success_criteria", "open_questions", "domain_terms", "staleness_flags", "context_integrity"],
        "properties": {
            "restated_goal":     {"type": "string"},
            "problem_statement": {"type": "string", "description": "User problem, solution-independent."},
            "target_user":       {"type": "string", "description": "Reference PRODUCT.md user definitions."},
            "proposed_scope": {"type": "object", "required": ["in_scope", "out_of_scope"], "properties": {
                "in_scope": {"type": "array", "items": {"type": "string"}},
                "out_of_scope": {"type": "array", "items": {"type": "string"}}}},
            "success_criteria": {"type": "array", "items": {"type": "string"}, "description": "Observable/measurable."},
            "open_questions":   {"type": "array", "items": {"type": "string"},
                                 "description": "EMPTY when finalizing (proceed_direct/Pass B). The blocking gaps when drafting."},
            "domain_terms": {"type": "array", "items": {"type": "object",
                "required": ["term", "definition"], "properties": {"term": {"type": "string"}, "definition": {"type": "string"}}}},
            "staleness_flags": {"type": "array", "items": {"type": "string"}},
            "context_integrity": {"type": "object", "required": ["rating", "reasoning"], "properties": {
                "rating": {"type": "string", "enum": ["green", "yellow", "red"]}, "reasoning": {"type": "string"}}},
            "handoff": {"type": "object", "required": ["feature_intent", "concepts_to_check"], "properties": {
                "feature_intent": {"type": "string"},
                "concepts_to_check": {"type": "array", "items": {"type": "string"}}}},
        },
    },
}

_BRIEF_SYSTEM = """You are the Product Clarification Agent producing a Clarification Brief.
Rules: problem_statement states the user problem WITHOUT a solution ('users currently cannot X'); target_user
references PRODUCT.md user definitions; success_criteria are observable/measurable; proposed_scope must have at
least one in_scope and one out_of_scope; domain_terms match DOMAIN.md.

Mode FINAL (proceed_direct or after human answers): open_questions MUST be empty; populate handoff with
feature_intent (= the restated_goal) and concepts_to_check (the salient entity nouns).
Mode DRAFT (clarify): set open_questions to the blocking gaps as crisp questions (each >= 15 chars); OMIT handoff.
If grounding is absent, set context_integrity.rating to red and flag it. Call submit_clarification_brief once."""


def _anthropic():
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def call_analysis(model: str, sources_text: str, grounding: dict) -> tuple[dict, int, int]:
    resp = _anthropic().messages.create(
        model=model, max_tokens=4000,
        system=[{"type": "text", "text": _ANALYSIS_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        tools=[_ANALYSIS_TOOL], tool_choice={"type": "tool", "name": "submit_intake_analysis"},
        messages=[{"role": "user", "content": [
            {"type": "text", "text": f"# Product grounding\n\n{_grounding_text(grounding)}", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"# Intake\n\n{sources_text}\n\nNormalize and assess. Call submit_intake_analysis."}]}],
    )
    block = next((b for b in resp.content if b.type == "tool_use"), None)
    if block is None:
        raise RuntimeError("analysis: model did not call the tool")
    return block.input, resp.usage.input_tokens, resp.usage.output_tokens


def call_synthesis(model: str, package: dict, grounding: dict, *, mode: str,
                   blocking_gaps: list, answers: list | None) -> tuple[dict, int, int]:
    ans_text = ""
    if answers:
        ans_text = "\n\n# Human answers (incorporate these; finalize)\n" + "\n".join(
            f"- Q: {a.get('question','')}\n  A: {a.get('answer','')}" for a in answers)
    gaps_text = ""
    if mode == "draft" and blocking_gaps:
        gaps_text = "\n\n# Blocking gaps to turn into open_questions\n" + "\n".join(
            f"- {g.get('field')}: {g.get('why')}" for g in blocking_gaps)
    resp = _anthropic().messages.create(
        model=model, max_tokens=4000,
        system=[{"type": "text", "text": _BRIEF_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        tools=[_BRIEF_TOOL], tool_choice={"type": "tool", "name": "submit_clarification_brief"},
        messages=[{"role": "user", "content": [
            {"type": "text", "text": f"# Product grounding\n\n{_grounding_text(grounding)}", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"# Normalized intake package\n\n{json.dumps(package, indent=2)}"
             f"\n\nMODE: {mode.upper()}{gaps_text}{ans_text}\n\nCall submit_clarification_brief."}]}],
    )
    block = next((b for b in resp.content if b.type == "tool_use"), None)
    if block is None:
        raise RuntimeError("synthesis: model did not call the tool")
    return block.input, resp.usage.input_tokens, resp.usage.output_tokens


def finalize_brief(brief: dict, *, run_id: str, workspace_id: str, grounding: dict,
                   assessment_id: str, mode: str, blocking_gaps: list, package: dict) -> dict:
    brief.setdefault("metadata", {})
    brief["metadata"].update({
        "agent": "product-clarification-agent", "run_id": run_id, "timestamp": _now(),
        "workspace_id": workspace_id, "team_id": "agile",
        "context_bundle_id": grounding["bundle_id"], "context_bundle_version": grounding["bundle_version"]})
    if assessment_id:
        brief["metadata"]["intake_assessment_artifact_id"] = assessment_id
    # Defensive caps: schema bounds success_criteria and open_questions at 5.
    if isinstance(brief.get("success_criteria"), list):
        brief["success_criteria"] = brief["success_criteria"][:5]
    if mode == "final":
        brief["open_questions"] = []
        if not brief.get("handoff"):
            brief["handoff"] = {"feature_intent": brief.get("restated_goal", ""),
                                "concepts_to_check": package["extracted_signals"].get("entities", [])}
    else:  # draft
        brief.pop("handoff", None)
        if not brief.get("open_questions"):
            brief["open_questions"] = [f"{g.get('field')}: {g.get('why')}" for g in blocking_gaps]
        brief["open_questions"] = brief["open_questions"][:5]
    return brief


def _validate(instance: dict, schema_path: Path, label: str) -> None:
    jsonschema.validate(instance, json.loads(schema_path.read_text(encoding="utf-8")))
    _log.info("%s schema-valid", label)


def run_intake(*, sources, sources_text, product_key, tenant, workspace_id, grounding,
               model="claude-sonnet-4-6", pass_="a", answers=None, no_persist=False,
               parent_run_id=None) -> dict:
    """Core intake pipeline (no printing). Callable by the CLI (main) and the agile orchestrator.
    Writes intake_assessment first; writes clarification_brief only when final. Returns a result dict."""
    run_id = str(uuid.uuid4())
    tokens_in_hint = max((len(sources_text) + len(_grounding_text(grounding))) // 4, 300)
    oversight = OversightClient(
        url=os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app"),
        secret=(os.environ.get("AGENT_OVERSIGHT_SECRET") or os.environ.get("OVERSIGHT_SECRET")
                or os.environ.get("INGEST_SECRET") or ""))
    tkw = dict(agent_id=AGENT_INSTANCE_ID, run_id=run_id, team_id="agile", model=model,
               provider="anthropic", tokens_in_hint=tokens_in_hint, task_type_code="orchestration",
               task_complexity_bucket="simple",
               metadata={"product_key": product_key, "workspace_id": workspace_id,
                         "intake_sources": len(sources), "pass": pass_})
    if parent_run_id:
        tkw["parent_run_id"] = parent_run_id

    ti_tot = to_tot = 0
    brief = draft = None
    brief_id = assessment_id = None
    with _telemetry(oversight, **tkw) as tctx:
        with tctx.timer() as t:
            analysis, ti, to = call_analysis(model, sources_text, grounding)
        ti_tot += ti; to_tot += to
        decision = "proceed_direct" if pass_ == "b" else analysis["decision"]
        package = build_package(sources, analysis)
        try:
            _validate(package, PKG_SCHEMA_PATH, "intake_package")
        except jsonschema.ValidationError as e:
            _log.warning("intake_package not strictly valid: %s", str(e)[:140])
        tctx.step("intake_analyzed", message=f"decision={decision} "
                  f"completeness={analysis['scores'].get('completeness')} gaps={len(analysis.get('blocking_gaps', []))}",
                  duration_ms=t.ms, tokens_in=ti, tokens_out=to, payload={"decision": decision})

        if decision == "clarify":
            with tctx.timer() as t2:
                draft, ti2, to2 = call_synthesis(model, package, grounding, mode="draft",
                                                 blocking_gaps=analysis.get("blocking_gaps", []), answers=None)
            ti_tot += ti2; to_tot += to2
            draft = finalize_brief(draft, run_id=run_id, workspace_id=workspace_id, grounding=grounding,
                                   assessment_id="", mode="draft", blocking_gaps=analysis.get("blocking_gaps", []),
                                   package=package)
            tctx.step("draft_synthesized", message=f"{len(draft.get('open_questions', []))} questions", duration_ms=t2.ms)

        assessment = {
            "schema_version": "1.0", "artifact_id": str(uuid.uuid4()), "run_id": run_id,
            "product_key": product_key, "tenant_id": tenant, "generated_at": _now(),
            "generator": {"agent": AGENT_INSTANCE, "version": DEFINITION_VERSION, "model": model},
            "intake_package": package, "field_coverage": analysis["field_coverage"],
            "scores": analysis["scores"], "blocking_gaps": analysis.get("blocking_gaps", []),
            "decision": decision,
            "rationale": (analysis["rationale"] if pass_ == "a" else
                          "Finalized after human answers (Pass B). " + analysis.get("rationale", "")),
        }
        if draft is not None:
            assessment["draft_brief"] = draft
        _validate(assessment, ASSESS_SCHEMA_PATH, "intake_assessment")
        if not no_persist:
            assessment_id = write_agent_output("intake_assessment", assessment, run_id, tenant)
        tctx.step("assessment_written", message=f"intake_assessment/{assessment_id} decision={decision}")

        if decision not in ("block", "clarify"):  # proceed_direct (Pass A) or forced final (Pass B)
            with tctx.timer() as t3:
                brief, ti3, to3 = call_synthesis(model, package, grounding, mode="final",
                                                 blocking_gaps=[], answers=answers)
            ti_tot += ti3; to_tot += to3
            brief = finalize_brief(brief, run_id=run_id, workspace_id=workspace_id, grounding=grounding,
                                   assessment_id=assessment_id or "", mode="final", blocking_gaps=[], package=package)
            _validate(brief, BRIEF_SCHEMA_PATH, "clarification_brief")
            if not no_persist:
                brief_id = write_agent_output("clarification_brief", brief, run_id, tenant)
            tctx.step("brief_written", message=f"clarification_brief/{brief_id}", duration_ms=t3.ms)

        cost = _est_cost(model, ti_tot, to_tot)
        tctx.report(tokens_in=ti_tot, tokens_out=to_tot, cost_usd=cost)

    return {"run_id": run_id, "decision": decision, "assessment_id": assessment_id, "brief_id": brief_id,
            "assessment": assessment, "brief": brief, "draft": draft,
            "handoff": (brief.get("handoff") if brief else None),
            "tokens_in": ti_tot, "tokens_out": to_tot, "cost": cost}


def _print_result(result: dict) -> None:
    d = result["decision"]
    if d == "block":
        _print_block(result["assessment"], result["run_id"])
    elif d == "clarify":
        _print_clarify(result["draft"], result["assessment_id"], result["run_id"])
    else:
        _print_final(result["brief"], result["brief_id"], result["assessment_id"], result["run_id"],
                     result["cost"], result["tokens_in"], result["tokens_out"])


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Product Clarification Agent - intake normalization (Phase 1: text)")
    p.add_argument("--intake", action="append", help="TYPE:SOURCE (SOURCE = file path or inline text); repeatable")
    p.add_argument("--goal", help="convenience: a one-line idea intake")
    p.add_argument("--product-key", default="reformai-product")
    p.add_argument("--tenant", default="ReformAI", help="company name or explicit UUID")
    p.add_argument("--workspace-id", default="reformai-product", help="grounding bundle workspace")
    p.add_argument("--model", default=os.environ.get("PCA_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")))
    p.add_argument("--pass", dest="pass_", choices=["a", "b"], default="a")
    p.add_argument("--answers", help="Pass B: JSON file of [{question, answer}, ...]")
    p.add_argument("--no-persist", action="store_true")
    args = p.parse_args()

    tenant = resolve_tenant(args.tenant)
    grounding = load_grounding(args.workspace_id)
    if grounding["missing"]:
        _log.warning("grounding missing: %s", ", ".join(grounding["missing"]))
    sources, sources_text = build_sources(args.intake, args.goal)
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8")) if args.answers else None
    if args.pass_ == "b" and not answers:
        raise SystemExit("--pass b requires --answers")

    result = run_intake(sources=sources, sources_text=sources_text, product_key=args.product_key,
                        tenant=tenant, workspace_id=args.workspace_id, grounding=grounding,
                        model=args.model, pass_=args.pass_, answers=answers, no_persist=args.no_persist)
    _print_result(result)


def _print_block(assessment: dict, run_id: str) -> None:
    print(f"\n{'-'*64}\n  PCA: BLOCKED (intake too thin)\n  Rationale: {assessment['rationale']}")
    print("  Missing: " + ", ".join(g["field"] for g in assessment.get("blocking_gaps", [])))
    print(f"  Run: {run_id}\n{'-'*64}")


def _print_clarify(draft: dict, assessment_id: str, run_id: str) -> None:
    print(f"\n{'-'*64}\n  PCA: CLARIFY ({len(draft.get('open_questions', []))} blocking question(s))")
    print(f"  intake_assessment: agent_outputs/{assessment_id}")
    for i, q in enumerate(draft.get("open_questions", []), 1):
        print(f"   {i}. {q}")
    print("  Answer in the dashboard, then re-run: --pass b --answers <file>")
    print(f"  Run: {run_id}\n{'-'*64}")


def _print_final(brief: dict, brief_id: str, assessment_id: str, run_id: str, cost: float, ti: int, to: int) -> None:
    h = brief.get("handoff", {})
    print(f"\n{'-'*64}\n  PCA: FINAL Clarification Brief")
    print(f"  intake_assessment : agent_outputs/{assessment_id}")
    print(f"  clarification_brief: agent_outputs/{brief_id}")
    print(f"  feature_intent     : {h.get('feature_intent','')}")
    print(f"  concepts_to_check  : {', '.join(h.get('concepts_to_check', []))}")
    print(f"  -> CCA: --feature-intent \"{h.get('feature_intent','')}\" --concepts-to-check {' '.join(h.get('concepts_to_check', []))}")
    print(f"  -> BA : --feature-intent \"{h.get('feature_intent','')}\" --clarification-artifact-id {brief_id}")
    print(f"  Cost: ${cost:.6f}  ({ti:,} in / {to:,} out)   Run: {run_id}\n{'-'*64}")


if __name__ == "__main__":
    main()
