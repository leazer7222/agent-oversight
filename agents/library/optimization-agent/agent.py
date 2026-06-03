"""
Optimization Agent
==================
Scans the agent-oversight repo for standards compliance, organizational issues,
and structural gaps. Synthesizes a prioritized improvement report via LLM.

Standards enforced: docs/repo-standards.md
Agent ID: 1ba970fb-caba-4c4d-9e91-0f07135c1a70
"""

import os
import sys
import json
import uuid
import re
from pathlib import Path

# Force UTF-8 stdout on Windows so Unicode chars in reports don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from typing import Dict, List, Any, Optional
from datetime import datetime

# Resolve repo root relative to this file
AGENT_DIR = Path(__file__).parent
REPO_ROOT = AGENT_DIR.parent.parent.parent

# Add python-sdk to path
sdk_path = str(REPO_ROOT / "python-sdk")
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

try:
    from oversight import OversightClient
except ImportError:
    OversightClient = None

try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


AGENT_ID = "1ba970fb-caba-4c4d-9e91-0f07135c1a70"

# Required files every library agent must have
REQUIRED_FILES = ["agent.json", "agent.py", "README.md", "LESSONS.md"]

# Required fields in agent.json
REQUIRED_AGENT_JSON_FIELDS = ["agent_id", "name", "description", "owner", "version"]

# Root-level files/dirs that violate standards
ROOT_CLUTTER_PATTERNS = [
    r"^register_.*\.(js|py)$",
    r"^run_.*\.(js|py)$",
]
ROOT_CLUTTER_DIRS = ["outputs"]

# Patterns that indicate hardcoded absolute paths
HARDCODED_PATH_PATTERNS = [
    r"['\"]([A-Za-z]:[/\\]Users[/\\][^'\"]+)['\"]",
    r"['\"](/home/[^'\"]+)['\"]",
    r"['\"](/Users/[^'\"]+)['\"]",
]

OVERSIGHT_CONTRACT_IMPORT = "OversightClient"


class ComplianceReport:
    def __init__(self):
        self.violations: List[Dict] = []
        self.warnings: List[Dict] = []
        self.info: List[Dict] = []
        self.agents_scanned: List[str] = []

    def critical(self, agent: str, check: str, detail: str):
        self.violations.append({"agent": agent, "check": check, "detail": detail, "severity": "critical"})

    def warn(self, agent: str, check: str, detail: str):
        self.warnings.append({"agent": agent, "check": check, "detail": detail, "severity": "warning"})

    def note(self, agent: str, check: str, detail: str):
        self.info.append({"agent": agent, "check": check, "detail": detail, "severity": "info"})

    def all_findings(self) -> List[Dict]:
        return self.violations + self.warnings + self.info

    def summary_stats(self) -> Dict:
        return {
            "agents_scanned": len(self.agents_scanned),
            "critical": len(self.violations),
            "warnings": len(self.warnings),
            "info": len(self.info),
            "total_findings": len(self.all_findings()),
        }


class OptimizationAgent:
    def __init__(self):
        self.agent_id = AGENT_ID
        self.repo_root = REPO_ROOT
        self.report = ComplianceReport()

        oversight_url = os.environ.get("OVERSIGHT_URL", "http://localhost:3000")
        oversight_secret = os.environ.get("OVERSIGHT_SECRET") or os.environ.get("INGEST_SECRET")

        if OversightClient:
            self.oversight = OversightClient(url=oversight_url, secret=oversight_secret)
        else:
            self.oversight = None
            print("[WARN] OversightClient not available — telemetry disabled")

    # -------------------------------------------------------------------------
    # CHECK 1: Required files per agent
    # -------------------------------------------------------------------------
    def check_required_files(self):
        library_dir = self.repo_root / "agents" / "library"
        if not library_dir.exists():
            self.report.critical("repo", "missing_files", "agents/library/ directory does not exist")
            return

        for agent_dir in sorted(library_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name.startswith("_") or agent_dir.name.startswith("."):
                continue
            name = agent_dir.name
            self.report.agents_scanned.append(name)

            for required in REQUIRED_FILES:
                fpath = agent_dir / required
                if not fpath.exists():
                    self.report.critical(name, "missing_files", f"Missing required file: {required}")

    # -------------------------------------------------------------------------
    # CHECK 2: agent.json schema validation
    # -------------------------------------------------------------------------
    def check_agent_json_schema(self):
        library_dir = self.repo_root / "agents" / "library"
        for agent_dir in sorted(library_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue
            name = agent_dir.name
            json_path = agent_dir / "agent.json"
            if not json_path.exists():
                continue  # Already caught by check_required_files

            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                self.report.critical(name, "agent_json_schema", f"agent.json is invalid JSON: {e}")
                continue

            for field in REQUIRED_AGENT_JSON_FIELDS:
                if field not in data:
                    self.report.critical(name, "agent_json_schema", f"agent.json missing required field: '{field}'")
                elif data[field] in ("", "REPLACE-WITH-GENERATED-UUID", None):
                    self.report.critical(name, "agent_json_schema", f"agent.json field '{field}' is placeholder/empty")

            # Validate agent_id looks like a UUID
            if "agent_id" in data:
                try:
                    uuid.UUID(str(data["agent_id"]))
                except ValueError:
                    self.report.critical(name, "agent_json_schema", f"agent_id is not a valid UUID: {data['agent_id']}")

            # Validate version is semver-ish
            if "version" in data:
                if not re.match(r"^\d+\.\d+\.\d+", str(data.get("version", ""))):
                    self.report.warn(name, "agent_json_schema", f"version '{data['version']}' is not semver (expected X.Y.Z)")

            # Check model field is present (recommended)
            if "model" not in data:
                self.report.warn(name, "agent_json_schema", "agent.json missing 'model' field (recommended)")

    # -------------------------------------------------------------------------
    # CHECK 3: AGENTS.md sync
    # -------------------------------------------------------------------------
    def check_agents_md_sync(self):
        agents_md = self.repo_root / "docs" / "AGENTS.md"
        if not agents_md.exists():
            self.report.critical("repo", "agents_md_sync", "AGENTS.md does not exist at repo root")
            return

        content = agents_md.read_text(encoding="utf-8")

        library_dir = self.repo_root / "agents" / "library"
        for agent_dir in sorted(library_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue
            name = agent_dir.name
            if name not in content:
                self.report.critical(name, "agents_md_sync", f"Agent '{name}' exists on disk but is not listed in AGENTS.md")

    # -------------------------------------------------------------------------
    # CHECK 4: Runtime contract (OversightClient usage)
    # -------------------------------------------------------------------------
    def check_runtime_contract(self):
        library_dir = self.repo_root / "agents" / "library"
        for agent_dir in sorted(library_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue
            name = agent_dir.name
            py_path = agent_dir / "agent.py"
            if not py_path.exists():
                continue

            code = py_path.read_text(encoding="utf-8")

            if OVERSIGHT_CONTRACT_IMPORT not in code:
                self.report.critical(name, "runtime_contract", "agent.py does not import or use OversightClient — run lifecycle events will not be emitted")

            if "run_started" not in code and "client.run" not in code:
                self.report.warn(name, "runtime_contract", "agent.py may not emit run_started — verify OversightClient context manager is used")

    # -------------------------------------------------------------------------
    # CHECK 5: Hardcoded absolute paths
    # -------------------------------------------------------------------------
    def check_hardcoded_paths(self):
        # Check agent library files
        library_dir = self.repo_root / "agents" / "library"
        for agent_dir in sorted(library_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue
            name = agent_dir.name
            for ext in ["*.py", "*.js", "*.json"]:
                for fpath in agent_dir.glob(ext):
                    self._scan_file_for_hardcoded_paths(name, fpath)

        # Check scripts at root
        for fpath in self.repo_root.glob("*.py"):
            self._scan_file_for_hardcoded_paths("root", fpath)
        for fpath in self.repo_root.glob("*.js"):
            self._scan_file_for_hardcoded_paths("root", fpath)

        # Check instances
        instances_dir = self.repo_root / "agents" / "instances"
        if instances_dir.exists():
            for company_dir in instances_dir.iterdir():
                if not company_dir.is_dir():
                    continue
                for fpath in company_dir.glob("*.py"):
                    self._scan_file_for_hardcoded_paths(f"instances/{company_dir.name}", fpath)
                for fpath in company_dir.glob("*.js"):
                    self._scan_file_for_hardcoded_paths(f"instances/{company_dir.name}", fpath)

    def _scan_file_for_hardcoded_paths(self, context: str, fpath: Path):
        try:
            code = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return
        for pattern in HARDCODED_PATH_PATTERNS:
            matches = re.findall(pattern, code)
            for match in matches:
                self.report.warn(context, "hardcoded_paths", f"{fpath.name}: hardcoded path '{match}'")

    # -------------------------------------------------------------------------
    # CHECK 6: Root-level clutter
    # -------------------------------------------------------------------------
    def check_root_clutter(self):
        for item in self.repo_root.iterdir():
            if item.is_file():
                for pattern in ROOT_CLUTTER_PATTERNS:
                    if re.match(pattern, item.name):
                        self.report.warn("root", "root_clutter",
                            f"'{item.name}' is a script at repo root — should be moved to scripts/")
            elif item.is_dir() and item.name in ROOT_CLUTTER_DIRS:
                self.report.warn("root", "root_clutter",
                    f"'{item.name}/' directory at repo root — outputs belong in agents/instances/<company>/outputs/")

    # -------------------------------------------------------------------------
    # CHECK 7: Duplicate outputs directories
    # -------------------------------------------------------------------------
    def check_output_locations(self):
        root_outputs = self.repo_root / "outputs"
        if root_outputs.exists() and any(root_outputs.iterdir()):
            self.report.warn("root", "output_location",
                "Root-level outputs/ contains files — these should live in agents/instances/<company>/outputs/ only")

        # Check if instances have outputs dirs set up properly
        instances_dir = self.repo_root / "agents" / "instances"
        if instances_dir.exists():
            for company_dir in instances_dir.iterdir():
                if not company_dir.is_dir():
                    continue
                outputs = company_dir / "outputs"
                if not outputs.exists():
                    self.report.note(f"instances/{company_dir.name}", "output_location",
                        f"No outputs/ directory in instances/{company_dir.name}/ — create it when the first run produces output")

    # -------------------------------------------------------------------------
    # CHECK 8: Supabase registration
    # -------------------------------------------------------------------------
    def check_supabase_sync(self) -> Dict[str, Any]:
        supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
        service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

        if not supabase_url or not service_role_key:
            self.report.note("supabase", "supabase_sync", "SUPABASE credentials not set — skipping Supabase registration check")
            return {}

        try:
            import urllib.request
            headers = {
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Content-Type": "application/json",
            }
            req = urllib.request.Request(
                f"{supabase_url}/rest/v1/agents?select=name,status,last_run_at",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                registered = json.loads(resp.read().decode())
        except Exception as e:
            self.report.warn("supabase", "supabase_sync", f"Could not query Supabase agents table: {e}")
            return {}

        registered_names = {r["name"] for r in registered}

        # Check each disk agent is in Supabase
        library_dir = self.repo_root / "agents" / "library"
        for agent_dir in sorted(library_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue
            name = agent_dir.name

            # Try all company prefixes
            found = any(f"{company}.{name}" in registered_names for company in ["reformai", "afterglow", "personal"])
            if not found and name not in registered_names:
                self.report.warn(name, "supabase_sync", f"Agent '{name}' has no matching registration in Supabase agents table")

        return {"registered_in_supabase": registered}

    # -------------------------------------------------------------------------
    # CHECK 9: Doc staleness — LESSONS.md and README.md must be maintained
    # -------------------------------------------------------------------------
    def check_doc_staleness(self):
        library_dir = self.repo_root / "agents" / "library"

        # README template boilerplate phrases — if still present, it was never customized
        readme_template_phrases = [
            "REPLACE-WITH-GENERATED-UUID",
            "One sentence describing what this agent does.",
            "Agent Name",
        ]

        for agent_dir in sorted(library_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue
            name = agent_dir.name

            # Check LESSONS.md — flag if still has the default placeholder
            lessons_path = agent_dir / "LESSONS.md"
            if lessons_path.exists():
                content = lessons_path.read_text(encoding="utf-8")
                if "_(none yet)_" in content and content.count("\n") < 6:
                    self.report.warn(name, "doc_staleness",
                        "LESSONS.md still has placeholder content '_(none yet)_' — update it after each run with real lessons")

            # Check README.md — flag if it still contains template boilerplate
            readme_path = agent_dir / "README.md"
            if readme_path.exists():
                content = readme_path.read_text(encoding="utf-8")
                for phrase in readme_template_phrases:
                    if phrase in content:
                        self.report.warn(name, "doc_staleness",
                            f"README.md still contains template placeholder '{phrase}' — customize it for this agent")
                        break  # one warning per agent is enough

    # -------------------------------------------------------------------------
    # CHECK 10: Run activity — agents must actually be running
    # -------------------------------------------------------------------------
    def check_run_activity(self, supabase_data: Dict):
        registered = supabase_data.get("registered_in_supabase", [])
        if not registered:
            return  # supabase check was skipped or failed

        now = datetime.utcnow()

        for agent_record in registered:
            name = agent_record.get("name", "unknown")
            last_run_at = agent_record.get("last_run_at")
            status = agent_record.get("status", "unknown")

            if status in ("paused", "deprecated"):
                continue  # skip intentionally inactive agents

            if last_run_at is None:
                self.report.warn(name, "run_activity",
                    "Agent has NEVER emitted a run event — either it has never been triggered or it is not using OversightClient correctly")
            else:
                try:
                    # Parse ISO timestamp (handles +00:00 and Z suffixes)
                    ts_str = last_run_at.replace("+00:00", "").replace("Z", "")
                    last_run = datetime.fromisoformat(ts_str)
                    days_ago = (now - last_run).days
                    if days_ago > 14:
                        self.report.warn(name, "run_activity",
                            f"Agent last ran {days_ago} days ago — verify it is still being triggered and emitting events")
                except Exception:
                    pass  # If parsing fails, don't false-positive

    # -------------------------------------------------------------------------
    # LLM Synthesis
    # -------------------------------------------------------------------------
    def synthesize_with_llm(self, findings: List[Dict], stats: Dict) -> str:
        prompt = f"""You are an elite AI infrastructure engineer reviewing an agent oversight system.

Below are the findings from an automated compliance scan of the repo. Your job is to synthesize these into a clear, prioritized action plan for the developer.

SCAN STATS:
- Agents scanned: {stats['agents_scanned']}
- Critical violations: {stats['critical']}
- Warnings: {stats['warnings']}
- Informational notes: {stats['info']}

FINDINGS (JSON):
{json.dumps(findings, indent=2)}

Write a concise improvement report:
1. Start with a one-paragraph executive summary (what is the overall health of the repo?)
2. List CRITICAL fixes first (numbered, must-do before next agent build)
3. List WARNINGS second (should-do, reduce tech debt) — group by theme (doc staleness, run activity, hardcoded paths, etc.)
4. End with a "Repo Health Score" out of 10 and one sentence on what would move it up 2 points.

Be direct. No fluff. Treat the reader as a senior engineer."""

        # Try Gemini first
        if GEMINI_AVAILABLE:
            api_key = os.environ.get("GEMINI_API_KEY")
            if api_key:
                try:
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(temperature=0.3),
                    )
                    return response.text
                except Exception as e:
                    print(f"[WARN] Gemini failed: {e}")

        # Fallback to OpenAI
        if OPENAI_AVAILABLE:
            api_key = os.environ.get("OPENAI_API_KEY")
            if api_key:
                try:
                    client = OpenAI(api_key=api_key)
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                    )
                    return response.choices[0].message.content
                except Exception as e:
                    print(f"[WARN] OpenAI failed: {e}")

        # Fallback: plain text summary
        lines = ["## Optimization Report (No LLM — Raw Findings)\n"]
        for f in findings:
            lines.append(f"[{f['severity'].upper()}] {f['agent']} / {f['check']}: {f['detail']}")
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Save output
    # -------------------------------------------------------------------------
    def save_output(self, run_id: str, result: Dict) -> Path:
        output_dir = self.repo_root / "agents" / "instances" / "reformai" / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)

        short_id = run_id[:8]
        json_path = output_dir / f"optimization_output_{short_id}.json"
        md_path = output_dir / f"optimization_report_{short_id}.md"

        json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        md_path.write_text(result.get("report_md", ""), encoding="utf-8")

        print(f"[Output] JSON   -> {json_path}")
        print(f"[Output] Report -> {md_path}")
        return md_path

    # -------------------------------------------------------------------------
    # Main run
    # -------------------------------------------------------------------------
    def run(self) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        print(f"\n{'='*60}")
        print(f"Optimization Agent - Run {run_id[:8]}")
        print(f"Repo root: {self.repo_root}")
        print(f"{'='*60}\n")

        def _execute():
            print("[1/10] Checking required files...")
            self.check_required_files()

            print("[2/10] Validating agent.json schemas...")
            self.check_agent_json_schema()

            print("[3/10] Checking AGENTS.md sync...")
            self.check_agents_md_sync()

            print("[4/10] Checking runtime contract (OversightClient)...")
            self.check_runtime_contract()

            print("[5/10] Scanning for hardcoded paths...")
            self.check_hardcoded_paths()

            print("[6/10] Checking root-level clutter...")
            self.check_root_clutter()

            print("[7/10] Checking output locations...")
            self.check_output_locations()

            print("[8/10] Checking Supabase sync...")
            supabase_data = self.check_supabase_sync()

            print("[9/10] Checking doc staleness (LESSONS.md / README.md)...")
            self.check_doc_staleness()

            print("[10/10] Checking run activity (last_run_at)...")
            self.check_run_activity(supabase_data)

            stats = self.report.summary_stats()
            findings = self.report.all_findings()

            print(f"\n--- Scan complete ---")
            print(f"Critical: {stats['critical']} | Warnings: {stats['warnings']} | Info: {stats['info']}")
            print("\nSynthesizing report via LLM...\n")

            report_md = self.synthesize_with_llm(findings, stats)

            result = {
                "run_id": run_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "repo_root": str(self.repo_root),
                "stats": stats,
                "findings": findings,
                "supabase_data": supabase_data,
                "report_md": report_md,
            }

            self.save_output(run_id, result)

            print("\n" + "="*60)
            print(report_md)
            print("="*60 + "\n")

            return result

        if self.oversight:
            try:
                with self.oversight.run(
                    agent_id=self.agent_id,
                    metadata={"repo_root": str(self.repo_root), "run_id": run_id}
                ) as run:
                    result = _execute()
                    stats = result["stats"]
                    run.report(metadata={
                        "agents_scanned": stats["agents_scanned"],
                        "critical": stats["critical"],
                        "warnings": stats["warnings"],
                        "findings_total": stats["total_findings"],
                    })
                return result
            except Exception as e:
                print(f"[WARN] Oversight telemetry unavailable ({e}) - running in no-telemetry mode")
                return _execute()
        else:
            return _execute()


if __name__ == "__main__":
    agent = OptimizationAgent()
    agent.run()
