"""
source_scan.py - deterministic mechanism-B extraction (NO LLM, literal values only).

Extracts what the drizzle snapshot cannot: actors (roles), routes, route-level
permission guards, and external integrations - all from LITERAL strings in the
Express/TS source. Confirmed statically parseable (P-3):

  - actors:       USER_ROLES constant values UNION every authorize('role',...) literal
                  arg UNION the seeded `roles` table presence.
  - routes:       /api/v1 base (app.ts) + literal mount prefix (routes/index.ts)
                  + literal router.<method>('<path>', ...) per *.routes.ts.
  - permissions:  authorize(...allowedRoles) literal args per route (+ requireAdmin /
                  requireUser aliases) => per-route required roles.
  - integrations: config/<name>.config.ts file stems.

Anything that is not a literal is NOT invented - it is omitted and reflected in coverage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

API_RELROOT = "apps/api/src"

# requireX aliases -> the literal roles they wrap (auth.middleware.ts)
GUARD_ALIASES = {"requireAdmin": ["admin"], "requireUser": ["user", "admin"]}

_METHOD_RE = re.compile(r"router\.(get|post|put|patch|delete|options|head)\s*\(", re.I)
_FIRST_STR_RE = re.compile(r"['\"]([^'\"]+)['\"]")
_AUTHORIZE_RE = re.compile(r"authorize\s*\(([^)]*)\)")
_STR_LIT_RE = re.compile(r"['\"]([^'\"]+)['\"]")
_IMPORT_ROUTE_RE = re.compile(r"import\s+(\w+).*?from\s+['\"]\./([\w.-]+)\.js['\"]", re.S)
_USE_PREFIX_RE = re.compile(r"router\.use\(\s*['\"]([^'\"]+)['\"]\s*,\s*(\w+)")
_USER_ROLES_RE = re.compile(r"USER_ROLES\s*=\s*\{(.*?)\}", re.S)
_SEED_ROLE_RE = re.compile(r"roleName:\s*['\"]([^'\"]+)['\"]")
_API_BASE_RE = re.compile(r"app\.use\(\s*['\"](/api[\w/]*)['\"]\s*,\s*routes")


@dataclass
class Actor:
    name: str
    source: str
    evidence: dict


@dataclass
class Route:
    method: str
    path: str               # full path incl. base + mount prefix
    handler: str
    required_roles: list[str]
    auth_required: bool
    evidence: dict


@dataclass
class Integration:
    name: str
    evidence: dict


@dataclass
class Capability:
    slug: str               # route-group slug (mount prefix)
    evidence: dict


@dataclass
class SourceScan:
    actors: list[Actor]
    routes: list[Route]
    integrations: list[Integration]
    capabilities: list[Capability]
    api_base: str
    # parse bookkeeping for coverage
    route_files_discovered: int = 0
    route_files_parsed: int = 0
    route_files_failed: list[str] = field(default_factory=list)
    user_roles_found: bool = False
    seed_roles_found: bool = False
    auth_middleware_found: bool = False


def _api_dir(repo_root: Path) -> Path:
    return repo_root / API_RELROOT


def _detect_api_base(api: Path) -> str:
    app = api / "app.ts"
    if app.is_file():
        m = _API_BASE_RE.search(app.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1)
    return "/api/v1"


def _parse_seed_roles(api: Path) -> tuple[list[str], dict | None]:
    """Canonical role set is seeded literally in scripts/seed-roles.ts (roleName: '<role>')."""
    for rel in ("scripts/seed-roles.ts", "scripts/seed.ts"):
        f = api / rel
        if f.is_file():
            vals = _SEED_ROLE_RE.findall(f.read_text(encoding="utf-8", errors="replace"))
            if vals:
                return sorted(set(vals)), {"type": "seed", "file_path": f"{API_RELROOT}/{rel}", "symbol": "rolesData"}
    return [], None


def _parse_user_roles(api: Path) -> tuple[list[str], dict | None]:
    f = api / "constants" / "index.ts"
    if not f.is_file():
        return [], None
    txt = f.read_text(encoding="utf-8", errors="replace")
    m = _USER_ROLES_RE.search(txt)
    if not m:
        return [], None
    vals = _STR_LIT_RE.findall(m.group(1))
    line = txt[: m.start()].count("\n") + 1
    return vals, {"type": "constant", "file_path": f"{API_RELROOT}/constants/index.ts", "symbol": "USER_ROLES", "line": line}


def _scan_routes(api: Path) -> tuple[list[Route], list[Capability], dict, list[str], int, int, list[str]]:
    routes_dir = api / "routes"
    index = routes_dir / "index.ts"
    prefix_by_file: dict[str, str] = {}
    capabilities: list[Capability] = []
    if index.is_file():
        itxt = index.read_text(encoding="utf-8", errors="replace")
        var_to_file = {v: f for v, f in _IMPORT_ROUTE_RE.findall(itxt)}
        for prefix, var in _USE_PREFIX_RE.findall(itxt):
            fname = var_to_file.get(var)
            if fname:
                prefix_by_file[fname] = prefix
                capabilities.append(Capability(slug=prefix.strip("/"),
                                               evidence={"type": "route_group", "file_path": f"{API_RELROOT}/routes/index.ts", "prefix": prefix}))

    routes: list[Route] = []
    role_args: list[str] = []
    discovered = parsed = 0
    failed: list[str] = []
    for rf in sorted(routes_dir.glob("*.routes.ts")):
        discovered += 1
        rel = rf.relative_to(api).as_posix()
        prefix = prefix_by_file.get(rf.name.replace(".ts", ""), "")
        try:
            txt = rf.read_text(encoding="utf-8", errors="replace")
            matches = list(_METHOD_RE.finditer(txt))
            for i, m in enumerate(matches):
                seg = txt[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(txt)]
                pm = _FIRST_STR_RE.search(seg)
                if not pm:
                    continue
                sub_path = pm.group(1)
                roles: list[str] = []
                for a in _AUTHORIZE_RE.findall(seg):
                    roles.extend(_STR_LIT_RE.findall(a))
                for alias, r in GUARD_ALIASES.items():
                    if alias in seg:
                        roles.extend(r)
                role_args.extend(roles)
                auth_required = "authenticate" in seg or bool(roles)
                line = txt[: m.start()].count("\n") + 1
                full = "/".join(p for p in [prefix.rstrip("/"), sub_path.lstrip("/")] if p) or "/"
                routes.append(Route(
                    method=m.group(1).lower(), path=full, handler="",
                    required_roles=sorted(set(roles)), auth_required=auth_required,
                    evidence={"type": "route", "file_path": f"apps/api/{rel}", "line": line}))
            parsed += 1
        except Exception:
            failed.append(f"apps/api/{rel}")
    return routes, capabilities, prefix_by_file, sorted(set(role_args)), discovered, parsed, failed


def _scan_integrations(api: Path) -> list[Integration]:
    cfg = api / "config"
    out: list[Integration] = []
    if cfg.is_dir():
        for f in sorted(cfg.glob("*.config.ts")):
            name = f.name.replace(".config.ts", "")
            if name in ("index",):
                continue
            out.append(Integration(name=name, evidence={"type": "integration_config",
                                                         "file_path": f"{API_RELROOT}/config/{f.name}"}))
    return out


def scan(repo_root: Path) -> SourceScan:
    api = _api_dir(repo_root)
    api_base = _detect_api_base(api)
    user_role_vals, ur_ev = _parse_user_roles(api)
    seed_role_vals, seed_ev = _parse_seed_roles(api)

    routes, caps, _pref, route_role_args, disc, parsed, failed = _scan_routes(api)

    # apply api base to route paths
    for r in routes:
        r.path = "/".join(p for p in [api_base.rstrip("/"), r.path.lstrip("/")] if p) or api_base

    # actors = seeded roles (canonical) UNION USER_ROLES UNION authorize() literal args
    actor_names: dict[str, dict] = {}
    for v in seed_role_vals:
        actor_names.setdefault(v, seed_ev or {"type": "seed"})
    for v in user_role_vals:
        actor_names.setdefault(v, ur_ev or {"type": "constant", "symbol": "USER_ROLES"})
    for v in route_role_args:
        actor_names.setdefault(v, {"type": "authorize_arg", "file_path": "apps/api/src/routes/*"})
    actors = [Actor(name=n, source="role", evidence=ev) for n, ev in sorted(actor_names.items())]

    auth_mw = (api / "middlewares" / "auth.middleware.ts").is_file()

    return SourceScan(
        actors=actors, routes=routes, integrations=_scan_integrations(api), capabilities=caps,
        api_base=api_base, route_files_discovered=disc, route_files_parsed=parsed,
        route_files_failed=failed, user_roles_found=bool(user_role_vals),
        seed_roles_found=bool(seed_role_vals), auth_middleware_found=auth_mw)


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".workspace/Reform-AI").resolve()
    s = scan(root)
    print(f"api_base: {s.api_base}")
    print(f"actors ({len(s.actors)}): {[a.name for a in s.actors]}")
    print(f"routes: {len(s.routes)} (files {s.route_files_parsed}/{s.route_files_discovered}, failed {len(s.route_files_failed)})")
    print(f"capabilities ({len(s.capabilities)}): {[c.slug for c in s.capabilities][:12]}...")
    print(f"integrations ({len(s.integrations)}): {[i.name for i in s.integrations]}")
    admin = [a for a in s.actors if a.name == 'admin']
    print(f"ADMIN actor present: {bool(admin)} -> {admin[0].evidence if admin else None}")
    print("sample routes:", [(r.method, r.path, r.required_roles) for r in s.routes[:4]])
