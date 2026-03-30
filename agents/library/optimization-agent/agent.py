"""
optimization_agent — scans the agent library for standards compliance and
synthesizes a prioritized improvement report via Gemini.

Usage:
    python agents/library/optimization-agent/agent.py
    python agents/library/optimization-agent/agent.py --repo-root /path/to/repo
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None

# Add python-sdk to path
_sdk_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../python-sdk"))
if _sdk_dir not in sys.path:
    sys.path.append(_sdk_dir)
from oversight import OversightClient

AGENT_ID = "1ba970fb-caba-4c4d-9e91-0f07135c1a70"

REQUIRED_FILES = {"agent.json", "README.md", "LESSONS.md"}
REQUIRED_JSON_FIELDS = {"agent_id", "name", "description", "owner", "version", "mcp_dependencies"}
PLACEHOLDER_UUID = re.compile(
    r"[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12}",
    re.IGNORECASE,
)
# UUIDs that are clearly placeholders
PLACEHOLDER_PATTERNS = [
    r"REPLACE-WITH",
    r"a1b2c3d4",
    r"00000000-0000-0000-0000-000000000000",
    r"xxxxxxxx",
]


# ── Scanner ──────────────────────────────────────────────────────────────────

def _find_agent_dirs(root: Path) -> List[Path]:
    """Return all directories that contain at least one .py file under agents/.

    Library agents live in agents/library/<name>/.
    Instance orchestrators live in agents/instances/<company>/ — we include
    these too but tag them separately so structural checks are relaxed.
    """
    agents_root = root / "agents"
    dirs = []
    for p in agents_root.rglob("*.py"):
        d = p.parent
        if d not in dirs and d != agents_root:
            if "__pycache__" not in str(d):
                dirs.append(d)
    return sorted(dirs)


def _is_orchestrator_dir(agent_dir: Path) -> bool:
    """True for agent/instances/<company>/ directories (orchestrators, not library agents)."""
    parts = agent_dir.parts
    try:
        idx = next(i for i, p in enumerate(parts) if p == "instances")
        # instances/<company>/ — depth 1 below instances
        return len(parts) - idx == 2
    except StopIteration:
        return False


def _check_structure(agent_dir: Path) -> List[Dict]:
    issues = []
    for fname in REQUIRED_FILES:
        if not (agent_dir / fname).exists():
            severity = "critical" if fname in ("agent.json", "README.md") else "warning"
            issues.append({
                "severity": severity,
                "check": "missing_file",
                "detail": f"Required file '{fname}' not found",
            })
    return issues


def _check_agent_json(agent_dir: Path) -> List[Dict]:
    issues = []
    json_path = agent_dir / "agent.json"
    if not json_path.exists():
        return issues  # already caught by structure check

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [{"severity": "critical", "check": "invalid_json", "detail": str(e)}]

    missing = REQUIRED_JSON_FIELDS - set(data.keys())
    for field in sorted(missing):
        issues.append({
            "severity": "critical",
            "check": "missing_json_field",
            "detail": f"agent.json missing required field: '{field}'",
        })

    agent_id = data.get("agent_id", "")
    for pat in PLACEHOLDER_PATTERNS:
        if pat.lower() in agent_id.lower():
            issues.append({
                "severity": "critical",
                "check": "placeholder_agent_id",
                "detail": f"agent_id appears to be a placeholder: '{agent_id}'",
            })
            break

    return issues


def _read_py_files(agent_dir: Path) -> str:
    """Concatenate all .py source in the dir (excluding __pycache__)."""
    parts = []
    for py in sorted(agent_dir.rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        try:
            parts.append(f"# FILE: {py.name}\n" + py.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "\n\n".join(parts)


def _oversight_delegated(agent_dir: Path) -> Optional[str]:
    """Return delegation reason if agent.json declares oversight_delegated=true, else None."""
    json_path = agent_dir / "agent.json"
    if not json_path.exists():
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if data.get("oversight_delegated"):
            return data.get("oversight_delegated_reason", "Oversight delegated to orchestrator.")
    except Exception:
        pass
    return None


def _check_code(agent_dir: Path, is_self: bool = False) -> List[Dict]:
    issues = []
    source = _read_py_files(agent_dir)
    if not source:
        return issues

    # Oversight integration
    delegation_reason = _oversight_delegated(agent_dir)
    if "OversightClient" not in source:
        if delegation_reason:
            issues.append({
                "severity": "info",
                "check": "oversight_delegated",
                "detail": f"No OversightClient (intentional): {delegation_reason}",
            })
        else:
            issues.append({
                "severity": "critical",
                "check": "no_oversight_client",
                "detail": "OversightClient is never imported or used — agent emits no lifecycle events",
            })
    else:
        if "run_started" not in source and "client.run(" not in source and ".run(" not in source:
            issues.append({
                "severity": "critical",
                "check": "no_run_lifecycle",
                "detail": "OversightClient is imported but run lifecycle (run_started/run_completed) appears absent",
            })

    # Token reporting after LLM calls
    has_llm = any(kw in source for kw in ("generate_content", "chat.completions", "client_oa", "client_gen"))
    has_report = "run.report(" in source and any(kw in source for kw in ("tokens_in", "tokens_out", "cost_usd"))
    if has_llm and not has_report:
        issues.append({
            "severity": "warning",
            "check": "no_token_reporting",
            "detail": "LLM calls detected but no token/cost reporting via run.report(tokens_in=...) found",
        })

    # Placeholder UUIDs in code — only flag when pattern appears as an actual value
    # (i.e. assigned to a variable or passed as an arg), not as a string in a list/check.
    # Skip self-scan to avoid false positives from the PLACEHOLDER_PATTERNS list definition.
    if not is_self:
        for pat in PLACEHOLDER_PATTERNS:
            # Match pattern when it's a string value (not inside a Python list or comment)
            if re.search(r'(?:=|\")\s*["\']?' + re.escape(pat), source):
                issues.append({
                    "severity": "warning",
                    "check": "placeholder_in_code",
                    "detail": f"Placeholder pattern '{pat}' found as a value in source — may indicate unregistered agent_id",
                })

    # Hardcoded local file paths — only flag actual path strings in non-comment lines.
    # Skip self-scan to avoid false positives from the path literals inside the checker.
    if not is_self:
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if r"C:\Users" in stripped or (r"/Users/" in stripped and "PLACEHOLDER" not in stripped):
                issues.append({
                    "severity": "warning",
                    "check": "hardcoded_path",
                    "detail": "Hardcoded local file path found — should use env var instead",
                })
                break

    # OVERSIGHT_URL default with path suffix — causes double /api/ingest
    # Look for the pattern only in actual default-value strings, not in comments or checker strings.
    if not is_self:
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "api/agents/ingest" in stripped and ("OVERSIGHT_URL" in stripped or "localhost" in stripped):
                issues.append({
                    "severity": "critical",
                    "check": "wrong_oversight_url_default",
                    "detail": (
                        "OVERSIGHT_URL default includes '/api/agents/ingest'. "
                        "OversightClient appends '/api/ingest', causing a doubled path. "
                        "Default should be the bare base URL only (e.g. 'http://localhost:3000')."
                    ),
                })
                break

    # Commented-out logic (bypassed steps)
    commented_calls = re.findall(r"#\s*\w+\.run\(", source)
    if commented_calls:
        issues.append({
            "severity": "warning",
            "check": "bypassed_step",
            "detail": f"Commented-out agent/step calls found: {commented_calls} — logic may be silently skipped",
        })

    return issues


def scan_agent(agent_dir: Path) -> Dict:
    is_orchestrator = _is_orchestrator_dir(agent_dir)
    is_self = agent_dir.name == "optimization-agent"

    if is_orchestrator:
        # Orchestrators don't need library agent files — only code checks apply
        issues = _check_code(agent_dir, is_self=is_self)
        agent_type = "orchestrator"
    else:
        issues = (
            _check_structure(agent_dir)
            + _check_agent_json(agent_dir)
            + _check_code(agent_dir, is_self=is_self)
        )
        agent_type = "library"

    critical = sum(1 for i in issues if i["severity"] == "critical")
    warning = sum(1 for i in issues if i["severity"] == "warning")
    info = sum(1 for i in issues if i["severity"] == "info")

    overall = "critical" if critical > 0 else ("warning" if warning > 0 else "ok")

    return {
        "agent": agent_dir.name,
        "agent_type": agent_type,
        "path": str(agent_dir),
        "overall": overall,
        "critical": critical,
        "warning": warning,
        "info": info,
        "issues": issues,
    }


# ── LLM Synthesis ────────────────────────────────────────────────────────────

def synthesize_recommendations(findings: List[Dict], api_key: str) -> str:
    if genai is None or not api_key:
        return "Gemini SDK or API key not available — skipping LLM synthesis."

    system = (
        "You are a senior AI systems architect reviewing an agent compliance report. "
        "Given a JSON findings report, produce a concise, prioritized list of recommendations. "
        "Group by severity. Be specific: name the agent and the exact fix needed. "
        "Format as Markdown. Keep it actionable — no filler."
    )

    client = genai.Client(api_key=api_key)
    try:
        resp = client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            contents=f"FINDINGS:\n{json.dumps(findings, indent=2)}",
            config=genai_types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.2,
                max_output_tokens=2048,
            ),
        )
        return resp.text
    except Exception as e:
        return f"LLM synthesis failed: {e}"


# ── Main ─────────────────────────────────────────────────────────────────────

class OptimizationAgent:
    def __init__(self):
        self.oversight = OversightClient(
            url=os.environ.get("OVERSIGHT_URL", "http://localhost:3000"),
            secret=os.environ.get("OVERSIGHT_SECRET"),
        )

    def run(self, repo_root: Optional[str] = None) -> Dict[str, Any]:
        root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[3]

        with self.oversight.run(agent_id=AGENT_ID, metadata={"repo_root": str(root)}) as run:
            print(f"[OptimizationAgent] Scanning repo: {root}")

            agent_dirs = _find_agent_dirs(root)
            print(f"  Found {len(agent_dirs)} agent directories.")

            findings = []
            for d in agent_dirs:
                result = scan_agent(d)
                findings.append(result)
                status = f"[{result['overall'].upper()}]"
                print(f"  {status} {result['agent']} — {result['critical']} critical, {result['warning']} warning")

            total_critical = sum(f["critical"] for f in findings)
            total_warning = sum(f["warning"] for f in findings)

            run.report(metadata={
                "agents_scanned": len(findings),
                "total_critical": total_critical,
                "total_warning": total_warning,
            })

            print(f"\n[OptimizationAgent] Synthesizing recommendations...")
            api_key = os.environ.get("GEMINI_API_KEY")
            recommendations_md = synthesize_recommendations(findings, api_key)

            report = {
                "summary": (
                    f"Scanned {len(findings)} agents — "
                    f"{total_critical} critical issues, {total_warning} warnings."
                ),
                "agents": findings,
                "recommendations": recommendations_md,
            }

            print("\n" + "=" * 60)
            print("OPTIMIZATION REPORT")
            print("=" * 60)
            print(f"Summary: {report['summary']}\n")
            for f in findings:
                if f["issues"]:
                    print(f"  [{f['overall'].upper()}] {f['agent']}")
                    for issue in f["issues"]:
                        print(f"    [{issue['severity']}] {issue['check']}: {issue['detail']}")
            print("\n--- RECOMMENDATIONS ---")
            print(recommendations_md)

            return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimization Agent — agent standards scanner")
    parser.add_argument("--repo-root", default=None, help="Path to repo root (auto-detected if omitted)")
    parser.add_argument("--output", default=None, help="Write JSON report to this file path")
    args = parser.parse_args()

    agent = OptimizationAgent()
    report = agent.run(repo_root=args.repo_root)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written to: {out_path}")
