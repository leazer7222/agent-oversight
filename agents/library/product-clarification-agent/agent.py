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
from oversight import OversightClient  # noqa: E402


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
