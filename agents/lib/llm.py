"""
Minimal Anthropic structured-call helper shared by the prototype handlers.

One function, one job: ask the model to call ONE tool and return the parsed
tool input plus a usage/cost record. Everything the handlers care about -
determinism of the schema, cost accounting, the single-call-per-stage pattern
this repo already uses - lives here so enrich/draft/classify stay small and
testable (each accepts any callable with this signature, so tests stub it).

Design notes:
  * tool_choice is 'auto' with an explicit instruction to call the tool. The
    current model generation rejects forced tool_choice on several tiers; 'auto'
    plus strict schemas is the portable form. If the model answers in prose
    instead, we retry once and then fail the job - never fabricate a result.
  * max_tokens is generous on purpose. This repo has already been bitten by a
    truncated tool input silently emptying its last fields (LESSONS_LEARNED).
  * The api key is passed explicitly from the tenant vault. There is no
    environment fallback: the worker scrubs provider env at startup.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Tuple

# USD per million tokens (input, output). Keep in step with the claude-api
# reference; these are the only two models the prototype uses.
PRICES_PER_MTOK = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


class LLMError(Exception):
    category = "llm_error"


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = PRICES_PER_MTOK.get(model, (0.0, 0.0))
    return round((tokens_in * pin + tokens_out * pout) / 1_000_000.0, 6)


def make_client(api_key: str):
    import anthropic  # local import so tests without the SDK still import this module
    if not api_key:
        raise LLMError("no api key supplied to make_client (tenant credential missing)")
    return anthropic.Anthropic(api_key=api_key)


def call_tool(
    client: Any,
    *,
    model: str,
    system: str,
    user: str,
    tool: dict,
    max_tokens: int = 8000,
) -> Tuple[dict, dict]:
    """Returns (tool_input, usage). usage = {model, tokens_in, tokens_out, cost_usd}."""
    instruction = (
        f"{user}\n\nRespond ONLY by calling the `{tool['name']}` tool with a complete input. "
        "Do not answer in prose."
    )
    tool_def = {**tool, "strict": True} if "strict" not in tool else tool
    last_err: Optional[str] = None
    totals = {"model": model, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}

    for attempt in range(2):
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=[tool_def],
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": instruction}],
        )
        u = getattr(resp, "usage", None)
        tin = int(getattr(u, "input_tokens", 0) or 0)
        tout = int(getattr(u, "output_tokens", 0) or 0)
        totals["tokens_in"] += tin
        totals["tokens_out"] += tout
        totals["cost_usd"] = round(totals["cost_usd"] + cost_usd(model, tin, tout), 6)

        for block in resp.content:
            if getattr(block, "type", "") == "tool_use" and getattr(block, "name", "") == tool["name"]:
                inp = block.input
                if isinstance(inp, dict):
                    return inp, totals
        last_err = f"model did not call {tool['name']} (stop_reason={getattr(resp, 'stop_reason', '?')})"
        instruction = instruction + "\n\nYou must call the tool. Do not reply with text."

    raise LLMError(last_err or "no tool call returned")


LLMCallable = Callable[..., Tuple[dict, dict]]
