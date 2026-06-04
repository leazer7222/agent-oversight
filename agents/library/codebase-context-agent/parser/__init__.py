"""Deterministic codebase parsers for the Codebase Context Agent (P1).

Mechanism A: drizzle_snapshot - entities/columns/enums/relations from the drizzle-kit
             snapshot JSON (authoritative, complete, reproducible).
Mechanism B: source_scan - actors/routes/permissions/integrations from literal values
             in TS source (added later in the P1 sequence).

The LLM is NOT used here. Parsers discover structure; semantics are labeled later.
"""
