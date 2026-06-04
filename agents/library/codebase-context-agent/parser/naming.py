"""Deterministic cbc:* naming + minting (single source, shared by inventory + resolve)."""
from __future__ import annotations

import re

_IRREGULAR = {"people": "person", "children": "child", "data": "datum", "media": "medium"}


def singularize(token: str) -> str:
    if token in _IRREGULAR:
        return _IRREGULAR[token]
    if token.endswith("ies") and len(token) > 3:
        return token[:-3] + "y"
    if token.endswith(("ses", "xes", "zes", "ches", "shes")):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def normalize_name(name: str) -> str:
    """lowercase -> snake_case -> singularize(head token) -> strip non-alphanumerics."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if not s:
        return "unknown"
    tokens = [t for t in s.split("_") if t]
    tokens[-1] = singularize(tokens[-1])
    return "_".join(tokens)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"


class Minter:
    """Deterministic, collision-disambiguated cbc id minting for one run."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], str] = {}
        self._ids: set[str] = set()

    def mint(self, cbc_type: str, raw_name: str, *, normalizer="entity") -> str:
        key = (cbc_type, raw_name)
        if key in self._by_key:
            return self._by_key[key]
        if normalizer == "slug":
            seg = slugify(raw_name)
        elif normalizer == "raw":
            seg = re.sub(r"[^a-z0-9_]+", "_", raw_name.lower()).strip("_")
        else:
            seg = normalize_name(raw_name)
        base = f"cbc:{cbc_type}:{seg}"
        cand, n = base, 1
        while cand in self._ids:
            n += 1
            cand = f"{base}_{n}"
        self._ids.add(cand)
        self._by_key[key] = cand
        return cand
