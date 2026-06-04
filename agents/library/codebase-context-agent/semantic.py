"""
semantic.py - label-only LLM enrichment (step 13, C2).

The LLM LABELS the deterministic inventory: it produces domain_signals and glossary over the
EXISTING entities/actors/integrations. It may NOT invent entities, actors, routes, integrations,
or existence claims. Any cbc id it returns that is not in the deterministic inventory is dropped
(enforced post-hoc). This keeps the deterministic parser the sole source of existence truth.
"""
from __future__ import annotations

import os

for _k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS"):
    if os.environ.get(_k, None) == "":
        os.environ.pop(_k, None)

import anthropic  # noqa: E402

_PRICING = {"claude-opus": (15.0, 75.0), "claude-sonnet": (3.0, 15.0), "claude-haiku": (0.25, 1.25)}
_CONF = {"type": "string", "enum": ["high", "medium", "low"]}

_TOOL = {
    "name": "submit_semantics",
    "description": "Submit domain_signals and glossary that LABEL the given inventory. Reference only "
                   "cbc ids from the provided list. Do NOT invent entities/actors/integrations.",
    "input_schema": {
        "type": "object", "required": ["domain_signals", "glossary"],
        "properties": {
            "domain_signals": {"type": "array", "items": {"type": "object",
                "required": ["signal", "implication_hint", "confidence"], "properties": {
                    "signal": {"type": "string"},
                    "implication_hint": {"type": "string"},
                    "confidence": _CONF,
                    "entity_cbc_ids": {"type": "array", "items": {"type": "string"}}}}},
            "glossary": {"type": "array", "items": {"type": "object",
                "required": ["term"], "properties": {
                    "term": {"type": "string"},
                    "aka": {"type": "array", "items": {"type": "string"}},
                    "maps_to": {"type": "string", "description": "a cbc id from the provided list"}}}},
        },
    },
}

SYSTEM = ("You are a label-only codebase semantic pass. You are given a COMPLETE, deterministic "
          "inventory of a codebase (entities, enums, actors, integrations). Your ONLY job is to "
          "surface non-obvious domain_signals (multi-tenancy, market/region/currency/locale scoping, "
          "ownership, soft-delete, status workflows, RBAC) and a short glossary, by LABELING what is "
          "already there. You may NOT invent any entity, actor, route, or integration, and you may NOT "
          "claim anything exists or does not exist. Reference only the cbc ids provided.")


def _compact(inv) -> str:
    ents = "\n".join(f"{e['cbc_id']}  {e['name']}" for e in inv.entities)
    enums = ", ".join(en["name"] for en in inv.enums)
    actors = ", ".join(f"{a['cbc_id']}({a['name']})" for a in inv.actors)
    integ = ", ".join(f"{i['cbc_id']}({i['name']})" for i in inv.integrations)
    return (f"# Entities (cbc_id  table) - {len(inv.entities)} total\n{ents}\n\n"
            f"# Enums ({len(inv.enums)})\n{enums}\n\n# Actors\n{actors}\n\n# Integrations\n{integ}")


def label(inv, feature_intent: str, model: str = None):
    model = model or os.environ.get("CCA_MODEL", "claude-opus-4-5")
    valid_ids = {e["cbc_id"] for e in inv.entities} | {a["cbc_id"] for a in inv.actors} | {i["cbc_id"] for i in inv.integrations}
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model=model, max_tokens=8000,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        tools=[_TOOL], tool_choice={"type": "tool", "name": "submit_semantics"},
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "# Deterministic inventory (authoritative)\n\n" + _compact(inv),
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"# Feature being scoped (focus, do not narrow your sweep)\n{feature_intent}\n\n"
             "Label this inventory: produce domain_signals + glossary. Reference only the cbc ids above."}]}])
    block = next((b for b in resp.content if b.type == "tool_use"), None)
    raw = block.input if block else {"domain_signals": [], "glossary": []}

    # enforce label-only: drop any cbc id not in the deterministic inventory
    signals = []
    for s in raw.get("domain_signals", []):
        ids = [i for i in (s.get("entity_cbc_ids") or []) if i in valid_ids]
        signals.append({"signal": s["signal"], "implication_hint": s["implication_hint"],
                        "confidence": s.get("confidence", "medium"),
                        **({"entities": ids} if ids else {})})
    glossary = []
    for g in raw.get("glossary", []):
        mt = g.get("maps_to") if g.get("maps_to") in valid_ids else None
        glossary.append({"term": g["term"], **({"aka": g["aka"]} if g.get("aka") else {}),
                         **({"maps_to": mt} if mt else {})})

    ti, to = resp.usage.input_tokens, resp.usage.output_tokens
    cost = next((round((ti * ir + to * orr) / 1e6, 6) for k, (ir, orr) in _PRICING.items() if k in model.lower()), 0.0)
    return {"domain_signals": signals, "glossary": glossary, "model": model}, ti, to, cost
