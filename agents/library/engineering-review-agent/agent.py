import os
import sys
import json
import io
import base64
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import docx2txt
except ImportError:
    docx2txt = None

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    HAS_GDRIVE = True
except ImportError:
    HAS_GDRIVE = False

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Add python-sdk to path
import_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../python-sdk"))
if import_dir not in sys.path:
    sys.path.append(import_dir)
from oversight import OversightClient

EXCLUDED_DIRS = {
    "node_modules", ".git", "dist", "build", "__pycache__",
    ".next", ".vercel", "coverage", ".cache", "vendor"
}
EXCLUDED_EXTENSIONS = {".lock", ".map", ".min.js", ".min.css", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf"}


class EngineeringReviewAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.client = OversightClient(
            url=os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app/api/ingest"),
            secret=os.environ.get("OVERSIGHT_SECRET")
        )
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self._drive_service = None

    # ── GitHub ──────────────────────────────────────────────────────────────

    def _github_request(self, url: str) -> Any:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "engineering-review-agent"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _fetch_tree(self, repo: str, scope: str = "") -> List[Dict]:
        """Return list of {path, url} for all text files in repo[/scope]."""
        # Get default branch
        meta = self._github_request(f"https://api.github.com/repos/{repo}")
        branch = meta.get("default_branch", "main")

        # Get full tree
        tree_data = self._github_request(
            f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
        )
        files = []
        for item in tree_data.get("tree", []):
            if item.get("type") != "blob":
                continue
            path = item["path"]

            # Exclude irrelevant dirs/files
            parts = path.split("/")
            if any(p in EXCLUDED_DIRS for p in parts):
                continue
            _, ext = os.path.splitext(path)
            if ext in EXCLUDED_EXTENSIONS:
                continue

            # Scope filter
            if scope and not path.startswith(scope.rstrip("/") + "/") and path != scope:
                continue

            files.append({"path": path, "url": item.get("url", "")})
        return files

    def fetch_github_code(self, repo: str, scope: str = "") -> List[Dict]:
        """Fetch code files from GitHub. Returns list of {path, content}."""
        max_files = int(os.environ.get("REVIEW_MAX_FILES", "60"))
        max_chars = int(os.environ.get("REVIEW_MAX_CHARS_PER_FILE", "20000"))

        print(f"[EngineeringReviewAgent] Fetching code from {repo}/{scope or '(root)'}")
        try:
            files = self._fetch_tree(repo, scope)
        except Exception as e:
            print(f"  [Error] Failed to fetch repo tree: {e}")
            return []

        print(f"  Found {len(files)} eligible files. Capping at {max_files}.")
        files = files[:max_files]

        results = []
        for f in files:
            try:
                blob = self._github_request(f["url"])
                if blob.get("encoding") != "base64":
                    continue
                content = base64.b64decode(blob["content"]).decode("utf-8", errors="replace")
                if max_chars:
                    content = content[:max_chars]
                results.append({"path": f["path"], "content": content})
            except Exception as e:
                print(f"  [Warning] Could not read {f['path']}: {e}")

        print(f"  Read {len(results)} files successfully.")
        return results

    # ── Google Drive ─────────────────────────────────────────────────────────

    def _get_drive_service(self):
        if self._drive_service:
            return self._drive_service
        if not HAS_GDRIVE:
            return None
        key_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", r"C:\Users\cjlea\Key\reformai-agent-dd4d7e12c73f.json")
        if not os.path.exists(key_path):
            print(f"  [Warning] Service account key not found at {key_path}")
            return None
        creds = service_account.Credentials.from_service_account_file(
            key_path, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        self._drive_service = build("drive", "v3", credentials=creds)
        return self._drive_service

    def fetch_feedback_from_drive(self, folder_id: str) -> List[Dict]:
        """Fetch and extract text from all docs in a GDrive folder."""
        svc = self._get_drive_service()
        if not svc:
            print("  [Warning] GDrive unavailable — skipping feedback fetch.")
            return []

        mimetypes = [
            "application/vnd.google-apps.document",
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ]
        mime_q = "(" + " or ".join([f"mimeType='{m}'" for m in mimetypes]) + ")"
        q = f"'{folder_id}' in parents and {mime_q}"

        results = svc.files().list(
            q=q, fields="files(id, name, mimeType)",
            supportsAllDrives=True, includeItemsFromAllDrives=True, corpora="allDrives"
        ).execute()
        files = results.get("files", [])
        print(f"  Found {len(files)} feedback docs in GDrive folder {folder_id}.")

        docs = []
        for f in files:
            text = self._read_drive_file(svc, f["id"], f["mimeType"])
            if text:
                docs.append({"name": f["name"], "content": text})
        return docs

    def _read_drive_file(self, svc, file_id: str, mime_type: str) -> str:
        try:
            if mime_type == "application/vnd.google-apps.document":
                req = svc.files().export_media(fileId=file_id, mimeType="text/plain")
            else:
                req = svc.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, req)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            data = fh.getvalue()

            if mime_type == "application/pdf" and pypdf:
                reader = pypdf.PdfReader(io.BytesIO(data))
                return "\n".join(p.extract_text() or "" for p in reader.pages)
            elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" and docx2txt:
                return docx2txt.process(io.BytesIO(data))
            return data.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  [Error] Could not read file {file_id}: {e}")
            return ""

    # ── LLM Synthesis ────────────────────────────────────────────────────────

    def synthesize_review(self, code_files: List[Dict], feedback_text: str) -> Dict:
        """Call LLM with the review prompt, code, and feedback."""
        prompt_path = os.path.join(os.path.dirname(__file__), "prompt.md")
        system_prompt = "You are a staff-level engineering review agent."
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                system_prompt = f.read()

        # Build code context
        code_context = ""
        for cf in code_files:
            code_context += f"\n\n--- FILE: {cf['path']} ---\n{cf['content']}"

        user_message = (
            f"FEEDBACK DOCUMENTS:\n{feedback_text}\n\n"
            f"CODEBASE:\n{code_context}"
        )

        provider = os.environ.get("REVIEW_LLM_PROVIDER", "gemini").lower()
        openai_key = os.environ.get("OPENAI_API_KEY")
        openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

        output_instruction = """

CRITICAL: Return ONLY a valid JSON object with this exact structure:
{
  "feedback_themes": [
    {
      "theme_name": "...",
      "summary": "...",
      "recurrence_signal": "...",
      "affected_workflow": "..."
    }
  ],
  "root_causes": [
    {
      "feedback_theme": "...",
      "affected_areas": ["file/module paths"],
      "technical_diagnosis": "...",
      "evidence_level": "Direct evidence | Strong inference | Hypothesis"
    }
  ],
  "recommendations": [
    {
      "title": "...",
      "feedback_theme": "...",
      "affected_area": "...",
      "current_behavior": "...",
      "root_cause": "...",
      "recommended_change": "...",
      "expected_user_impact": "...",
      "engineering_impact": "...",
      "effort": "Low | Medium | High",
      "confidence": "Low | Medium | High",
      "priority": "P0 | P1 | P2"
    }
  ],
  "quick_wins": ["recommendation titles"],
  "structural_improvements": ["recommendation titles"],
  "risks_and_open_questions": ["..."]
}
"""
        full_system = system_prompt + output_instruction

        print(f"  [EngineeringReviewAgent] Synthesizing review via {provider.upper()} ({openai_model if provider == 'openai' else gemini_model})...")

        try:
            if provider == "openai" and openai_key and OpenAI:
                oa = OpenAI(api_key=openai_key)
                resp = oa.chat.completions.create(
                    model=openai_model,
                    messages=[
                        {"role": "system", "content": full_system},
                        {"role": "user", "content": user_message}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2
                )
                return json.loads(resp.choices[0].message.content)

            else:
                if not genai:
                    return {"error": "google-genai not installed"}
                api_key = os.environ.get("GEMINI_API_KEY")
                if not api_key:
                    return {"error": "Missing GEMINI_API_KEY"}
                client_gen = genai.Client(api_key=api_key)
                resp = client_gen.models.generate_content(
                    model=gemini_model,
                    contents=user_message,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=full_system,
                        response_mime_type="application/json",
                        temperature=0.2,
                        max_output_tokens=8192,
                    ),
                )
                return json.loads(resp.text)

        except Exception as e:
            print(f"  [Error] LLM synthesis failed: {e}")
            return {"error": str(e)}

    # ── Main Entrypoint ──────────────────────────────────────────────────────

    def run(
        self,
        repo: str,
        scope: str = "",
        feedback_folder_id: Optional[str] = None,
        feedback_text: Optional[str] = None
    ) -> Dict:
        print(f"\n[EngineeringReviewAgent] repo={repo} scope={scope or '(root)'}")

        with self.client.run(agent_id=self.agent_id, metadata={"repo": repo, "scope": scope}) as run:
            try:
                # Step 1: Fetch feedback
                run.report(metadata={"step": "fetching_feedback"})
                feedback_docs = []
                if feedback_folder_id:
                    feedback_docs = self.fetch_feedback_from_drive(feedback_folder_id)
                    feedback_combined = "\n\n".join(
                        f"Source: {d['name']}\n{d['content']}" for d in feedback_docs
                    )
                elif feedback_text:
                    feedback_combined = feedback_text
                else:
                    feedback_combined = "(No feedback provided)"
                print(f"  Feedback: {len(feedback_docs)} doc(s), {len(feedback_combined)} chars total")

                # Step 2: Fetch code
                run.report(metadata={"step": "fetching_code"})
                code_files = self.fetch_github_code(repo, scope)
                file_paths = [cf["path"] for cf in code_files]

                # Step 3: Synthesize review
                run.report(metadata={"step": "synthesizing_review", "files_count": len(code_files)})
                review = self.synthesize_review(code_files, feedback_combined)

                result = {
                    "status": "success",
                    "review": review,
                    "files_reviewed": file_paths,
                    "feedback_docs": [d["name"] for d in feedback_docs]
                }
                print("Engineering review complete.")
                return result

            except Exception as e:
                print(f"Error in EngineeringReviewAgent: {e}")
                run.report(metadata={"error": str(e)})
                return {"status": "error", "message": str(e)}


def _load_instance_config() -> Dict:
    """Load the reformai instance config as defaults. Env vars always win."""
    config_path = os.path.join(
        os.path.dirname(__file__),
        "../../instances/reformai/engineering-review-agent.config.json"
    )
    try:
        with open(os.path.abspath(config_path), "r", encoding="utf-8") as f:
            return json.load(f).get("config", {})
    except Exception:
        return {}


if __name__ == "__main__":
    cfg = _load_instance_config()
    AGENT_ID = os.environ.get("AGENT_ID", "e6229606-78b9-4fd7-9424-6a62eb574255")
    agent = EngineeringReviewAgent(agent_id=AGENT_ID)
    result = agent.run(
        repo=os.environ.get("GITHUB_REPO", cfg.get("github_repo", "leazer7222/agent-oversight")),
        scope=os.environ.get("GITHUB_SCOPE", cfg.get("github_scope", "")),
        feedback_folder_id=os.environ.get("FEEDBACK_FOLDER_ID", cfg.get("feedback_folder_id")),
        feedback_text=os.environ.get("FEEDBACK_TEXT")
    )
    print(json.dumps(result, indent=2))
