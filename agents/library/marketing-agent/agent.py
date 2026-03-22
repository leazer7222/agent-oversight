import os
import sys
import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add project root to sys.path to import oversight SDK
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
try:
    from oversight import OversightClient
except ImportError:
    print("Warning: oversight SDK not found. Reporting will be disabled.")
    OversightClient = None

try:
    from supabase import create_client, Client as SupabaseClient
except ImportError:
    print("Warning: supabase-py not found. DB output will be disabled.")
    SupabaseClient = None

GDRIVE_OUTPUT_FOLDER_ID = "1dVzlTU8QUq__8YefaE_m7Ue8cNkTjRz0"  # ReformAI docs folder

class MarketingAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        oversight_url = os.environ.get("OVERSIGHT_URL", "http://localhost:3000/api/agents/ingest")
        self.oversight = OversightClient(
            url=oversight_url,
            secret=os.environ.get("OVERSIGHT_SECRET")
        ) if OversightClient else None

        self.db: Optional[SupabaseClient] = None
        if SupabaseClient:
            sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
            sb_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            if sb_url and sb_key:
                self.db = create_client(sb_url, sb_key)

    # ── Context Extraction ───────────────────────────────────────────────────
    def extract_context(self, goal: str, folder_id: str = GDRIVE_OUTPUT_FOLDER_ID) -> List[Dict]:
        """Pull relevant documentation from Google Drive (via gdrive MCP tool)."""
        print(f"  Searching GDrive for: {goal}")
        # In a live MCP environment this would call:
        # results = call_tool("gdrive", "gdrive_search", {"query": goal, "folderId": folder_id})
        return [
            {"id": "doc_1", "name": "ReformAI Pitch Deck",        "content": "..."},
            {"id": "doc_2", "name": "Homeowner Persona Research",  "content": "..."},
            {"id": "doc_3", "name": "Product Roadmap Q2",          "content": "..."},
        ]

    # ── Strategy Synthesis ──────────────────────────────────────────────────
    def synthesize_strategy(self, goal: str, context: List[Dict]) -> Dict:
        """Produce the marketing brief and landing page blueprint."""
        return {
            "goal": goal,
            "segments": ["homeowners", "service_providers", "home_sellers"],
            "brief": {
                "positioning":      "ReformAI removes renovation chaos through intelligent clarity.",
                "benefit_pillars":  ["Reduce Risk", "Build Trust", "Save Time"],
                "primary_headline": "Renovate With Confidence — Not Guesswork.",
                "cta":              "Get Your Free Renovation Plan"
            },
            "lp_blueprint": {
                "hero":     {"headline": "Renovate With Confidence", "sub": "...", "cta": "Get Started"},
                "section_2": {"title": "Why ReformAI?", "pillars": ["Risk Reduction", "Trusted Vendors", "Budget Clarity"]},
                "section_3": {"title": "How It Works",  "steps": ["Share Your Vision", "Get a Plan", "Connect With Pros"]},
                "section_4": {"title": "Trust",         "elements": ["Reviews", "Money-back Guarantee", "Contractor Vetting"]},
                "footer_cta": "Start Your Renovation Journey Today"
            }
        }

    # ── Option B: Publish to Supabase ────────────────────────────────────────
    def publish_to_db(self, run_id: str, company_id: str, output: Dict,
                      gdrive_file_id: Optional[str] = None, gdrive_url: Optional[str] = None) -> Optional[str]:
        """Write structured output to agent_outputs table."""
        if not self.db:
            print("  DB not available — skipping Supabase output.")
            return None

        row = {
            "id":             str(uuid.uuid4()),
            "agent_id":       self.agent_id,
            "run_id":         run_id,
            "company_id":     company_id,
            "output_type":    "lp_blueprint",
            "content":        output,
            "gdrive_file_id": gdrive_file_id,
            "gdrive_url":     gdrive_url,
            "version":        1,
        }

        result = self.db.table("agent_outputs").insert(row).execute()
        if result.data:
            output_id = result.data[0]["id"]
            print(f"  ✅ Output saved to Supabase: {output_id}")
            return output_id
        else:
            print(f"  ⚠ Supabase insert failed: {result}")
            return None

    # ── Option C: Write to Google Drive ─────────────────────────────────────
    def write_to_gdrive(self, strategy: Dict, run_id: str) -> Optional[Dict[str, str]]:
        """
        Write the marketing output to Google Drive as a structured doc.
        In a live MCP environment, this would call:
          call_tool("gdrive", "gdrive_create_file", {...})
        Returns dict with file_id and url, or None.
        """
        filename = f"Marketing Brief — {datetime.now().strftime('%Y-%m-%d')} (run {run_id[:8]})"
        content = json.dumps(strategy, indent=2)
        print(f"  Writing to GDrive: {filename}")

        # MCP call skeleton:
        # result = call_tool("gdrive", "gdrive_create_file", {
        #     "name":     filename,
        #     "mimeType": "application/vnd.google-apps.document",
        #     "parents":  [GDRIVE_OUTPUT_FOLDER_ID],
        #     "content":  content
        # })
        # return {"file_id": result["id"], "url": result["webViewLink"]}

        # Placeholder response (replace with real result above):
        mock_file_id = f"mock_{run_id[:8]}"
        return {
            "file_id": mock_file_id,
            "url":     f"https://drive.google.com/file/d/{mock_file_id}/view"
        }

    # ── Main Entrypoint ──────────────────────────────────────────────────────
    def run(self, goal: str = "Build landing page for homeowners",
            company_id: str = "1021c018-fe0e-4ae8-a972-7487521cc3d9"):

        if not self.oversight:
            print("Running without oversight SDK...")
            return self._core_run(goal, company_id, run_id=str(uuid.uuid4()))

        with self.oversight.run(agent_id=self.agent_id,
                                metadata={"goal": goal, "company_id": company_id}) as run:
            return self._core_run(goal, company_id, run_id=run.run_id, report=run.report)

    def _core_run(self, goal: str, company_id: str, run_id: str, report=None):
        try:
            print(f"\n[MarketingAgent] Goal: {goal}")

            # 1. No Blind Output rule — extract context first
            print("Step 1: Extracting context...")
            context = self.extract_context(goal)

            # 2. Synthesize strategy
            print("Step 2: Synthesizing strategy...")
            strategy = self.synthesize_strategy(goal, context)

            # 3. Option C — write to Google Drive
            print("Step 3: Writing to Google Drive...")
            gdrive_result = self.write_to_gdrive(strategy, run_id)

            gdrive_file_id = gdrive_result["file_id"] if gdrive_result else None
            gdrive_url     = gdrive_result["url"]     if gdrive_result else None

            # 4. Option B — persist to Supabase agent_outputs
            print("Step 4: Saving to Supabase...")
            output_id = self.publish_to_db(
                run_id=run_id,
                company_id=company_id,
                output=strategy,
                gdrive_file_id=gdrive_file_id,
                gdrive_url=gdrive_url
            )

            result = {
                "status":       "success",
                "output_id":    output_id,
                "gdrive_url":   gdrive_url,
                "strategy":     strategy["brief"],
                "blueprint":    strategy["lp_blueprint"],
            }

            if report:
                report(metadata={"output_id": output_id, "gdrive_file_id": gdrive_file_id})

            print("\n✅ Run complete.")
            return result

        except Exception as e:
            print(f"❌ Error in MarketingAgent: {e}")
            if report:
                report(metadata={"error": str(e)})
            return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    agent = MarketingAgent("761c56f6-4de8-4859-974a-43d964de62f0")
    result = agent.run()
    print(json.dumps(result, indent=2, default=str))
