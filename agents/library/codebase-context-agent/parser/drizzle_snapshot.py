"""
drizzle_snapshot.py - deterministic schema extraction (mechanism A).

Reads the drizzle-kit snapshot JSON the target repo already maintains
(apps/api/drizzle/migrations/meta/NNNN_snapshot.json) and produces a canonical,
reproducible entity/enum/relation inventory. NO LLM, NO TypeScript AST parsing.

Why the snapshot and not the .ts source: drizzle-kit emits a complete, structured
JSON representation of every table/column/enum/FK at each `drizzle-kit generate`.
It is authoritative and deterministic. The only failure mode is staleness (the
snapshot lagging the .ts source), which is handled by the completeness guard in
coverage.py, not here.

Snapshot format: drizzle v5 (top-level: id, prevId, version, dialect, tables, enums, schemas, _meta).
Each table: { name, schema, columns{}, indexes{}, foreignKeys{}, compositePrimaryKeys{}, uniqueConstraints{} }.
Each enum:  { name, values[] } (v5; older variants store a bare list).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SNAPSHOT_FORMAT = "drizzle-v5"
META_RELPATH = "apps/api/drizzle/migrations/meta"


@dataclass
class Column:
    name: str
    sql_type: str
    semantic_hint: str
    nullable: bool
    primary_key: bool
    is_enum: bool = False


@dataclass
class Relation:
    to_table: str
    kind: str            # many-to-one (FK side)
    via: str             # local column(s)


@dataclass
class Entity:
    name: str            # canonical table name (snapshot key)
    pg_table: str        # actual table name
    columns: list[Column]
    relations: list[Relation]
    pk: list[str]
    enums_used: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


@dataclass
class EnumDef:
    name: str
    values: list[str]


@dataclass
class SchemaInventory:
    snapshot_path: str
    snapshot_tag: str
    snapshot_format: str
    entities: list[Entity]
    enums: list[EnumDef]


# ---------------------------------------------------------------------------
# Snapshot discovery
# ---------------------------------------------------------------------------

def find_latest_snapshot(repo_root: Path) -> tuple[Path, str]:
    """Return (snapshot_path, tag) for the newest snapshot per _journal.json."""
    meta = repo_root / META_RELPATH
    journal_path = meta / "_journal.json"
    if not journal_path.is_file():
        raise FileNotFoundError(f"drizzle journal not found: {journal_path}")
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    entries = journal.get("entries", [])
    if not entries:
        raise ValueError("drizzle journal has no entries")
    latest = max(entries, key=lambda e: e["idx"])
    snap = meta / f"{latest['idx']:04d}_snapshot.json"
    if not snap.is_file():
        # fall back to lexically-greatest snapshot file
        snaps = sorted(meta.glob("*_snapshot.json"))
        if not snaps:
            raise FileNotFoundError(f"no *_snapshot.json under {meta}")
        snap = snaps[-1]
    return snap, latest.get("tag", snap.stem)


# ---------------------------------------------------------------------------
# Semantic-hint heuristics (deterministic; code-reality only, not Attribute nodes)
# ---------------------------------------------------------------------------

_MONEY_RE = re.compile(r"(price|amount|cost|fee|total|budget|balance|payout|salary|revenue)", re.I)
_EMAIL_RE = re.compile(r"email", re.I)
_URL_RE = re.compile(r"(url|uri|link|image|photo|avatar|thumbnail)", re.I)


def _semantic_hint(name: str, sql_type: str, is_enum: bool, is_fk: bool) -> str:
    t = (sql_type or "").lower()
    n = name.lower()
    if is_fk or n.endswith("_id"):
        return "foreign_key"
    if n == "id":
        return "identifier"
    if is_enum:
        return "enum"
    if any(k in t for k in ("timestamp", "date", "time")):
        return "timestamp"
    if "bool" in t:
        return "boolean"
    if any(k in t for k in ("numeric", "decimal", "double", "real", "money")):
        return "money" if _MONEY_RE.search(n) else "quantity"
    if any(k in t for k in ("integer", "bigint", "smallint", "serial")):
        return "money" if _MONEY_RE.search(n) else "quantity"
    if "json" in t:
        return "json"
    if _EMAIL_RE.search(n):
        return "email"
    if _URL_RE.search(n):
        return "url"
    return "text"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _enum_names(snapshot: dict) -> set[str]:
    enums = snapshot.get("enums", {})
    names: set[str] = set()
    if isinstance(enums, dict):
        for k, v in enums.items():
            names.add(v.get("name", k) if isinstance(v, dict) else k)
    return names


def _extract_enums(snapshot: dict) -> list[EnumDef]:
    out: list[EnumDef] = []
    enums = snapshot.get("enums", {})
    if isinstance(enums, dict):
        for k, v in enums.items():
            if isinstance(v, dict):
                out.append(EnumDef(name=v.get("name", k), values=list(v.get("values", []) or [])))
            elif isinstance(v, list):
                out.append(EnumDef(name=k, values=list(v)))
    return sorted(out, key=lambda e: e.name)


def _fk_local_columns(fk: dict) -> set[str]:
    cols = fk.get("columnsFrom") or fk.get("columns") or []
    return {c for c in cols}


def _extract_table(tkey: str, t: dict, enum_names: set[str], snapshot_rel: str, tag: str) -> Entity:
    pg_table = t.get("name", tkey)
    cols_raw = t.get("columns", {}) or {}
    fks_raw = t.get("foreignKeys", {}) or {}

    fk_cols: set[str] = set()
    relations: list[Relation] = []
    for _fkname, fk in fks_raw.items():
        local = _fk_local_columns(fk)
        fk_cols |= local
        to_table = fk.get("tableTo") or fk.get("tableToName") or ""
        relations.append(Relation(
            to_table=to_table, kind="many-to-one",
            via=",".join(sorted(local)) if local else ""))

    columns: list[Column] = []
    enums_used: list[str] = []
    for cname, c in cols_raw.items():
        if not isinstance(c, dict):
            continue
        sql_type = c.get("type", "")
        is_enum = sql_type in enum_names
        if is_enum and sql_type not in enums_used:
            enums_used.append(sql_type)
        is_fk = (c.get("name", cname) in fk_cols)
        columns.append(Column(
            name=c.get("name", cname), sql_type=sql_type,
            semantic_hint=_semantic_hint(c.get("name", cname), sql_type, is_enum, is_fk),
            nullable=not bool(c.get("notNull", False)),
            primary_key=bool(c.get("primaryKey", False)),
            is_enum=is_enum))

    # primary key: column-level + composite
    pk = [c.name for c in columns if c.primary_key]
    for _pkn, pkc in (t.get("compositePrimaryKeys", {}) or {}).items():
        cols = pkc.get("columns", []) if isinstance(pkc, dict) else (pkc if isinstance(pkc, list) else [])
        pk.extend(cols)

    return Entity(
        name=pg_table, pg_table=pg_table, columns=columns, relations=relations,
        pk=sorted(set(pk)), enums_used=sorted(set(enums_used)),
        evidence={"type": "drizzle_snapshot", "snapshot": snapshot_rel, "tag": tag, "table": pg_table})


def extract(repo_root: Path) -> SchemaInventory:
    snap_path, tag = find_latest_snapshot(repo_root)
    snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
    snapshot_rel = snap_path.relative_to(repo_root).as_posix()
    enum_names = _enum_names(snapshot)
    tables = snapshot.get("tables", {}) or {}
    entities = [
        _extract_table(tkey, t, enum_names, snapshot_rel, tag)
        for tkey, t in sorted(tables.items())
        if isinstance(t, dict)
    ]
    return SchemaInventory(
        snapshot_path=snapshot_rel, snapshot_tag=tag, snapshot_format=SNAPSHOT_FORMAT,
        entities=entities, enums=_extract_enums(snapshot))


# ---------------------------------------------------------------------------
# CLI proof
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".workspace/Reform-AI").resolve()
    inv = extract(root)
    print(f"snapshot: {inv.snapshot_path}  tag: {inv.snapshot_tag}  format: {inv.snapshot_format}")
    print(f"entities: {len(inv.entities)}   enums: {len(inv.enums)}")
    names = [e.pg_table for e in inv.entities]
    for probe in ("partner", "admin", "property", "inventor", "material", "habi", "role", "seller", "service_provider"):
        hits = [n for n in names if probe in n.lower()]
        print(f"  match '{probe}': {hits[:8]}")
    # determinism fingerprint
    import hashlib
    blob = json.dumps([e.pg_table for e in inv.entities], sort_keys=True)
    print("entity-set sha:", hashlib.sha256(blob.encode()).hexdigest()[:16])
