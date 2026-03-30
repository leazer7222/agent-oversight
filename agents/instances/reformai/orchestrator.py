import os
import sys
import json
import uuid
from datetime import datetime

# Add project root to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../python-sdk")))

import importlib.util

def load_agent_module(name, rel_path):
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), rel_path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

context_mod = load_agent_module("context_agent", "../../library/context-agent/agent.py")
audit_mod = load_agent_module("audit_agent", "../../library/audit-agent/agent.py")
marketing_mod = load_agent_module("marketing_agent", "../../library/marketing-agent/agent.py")

ContextAgent = context_mod.ContextAgent
AuditAgent = audit_mod.AuditAgent
MarketingAgent = marketing_mod.MarketingAgent

try:
    from oversight import OversightClient
except ImportError:
    OversightClient = None

try:
    from supabase import create_client, Client as SupabaseClient
except ImportError:
    SupabaseClient = None

class Orchestrator:
    def __init__(self, company_id: str):
        self.company_id = company_id
        
        # Load clients
        oversight_url = os.environ.get("OVERSIGHT_URL", "http://localhost:3000")
        self.oversight = OversightClient(
            url=oversight_url,
            secret=os.environ.get("OVERSIGHT_SECRET")
        ) if OversightClient else None
        
        self.db = None
        if SupabaseClient:
            sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
            sb_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            if sb_url and sb_key:
                self.db = create_client(sb_url, sb_key)

    def publish_to_db(self, agent_id: str, run_id: str, output: dict) -> str:
        if not self.db:
            print("  DB not available — skipping Supabase output.")
            return None
        
        output_id = str(uuid.uuid4())
        row = {
            "id":             output_id,
            "agent_id":       agent_id,
            "run_id":         run_id,
            "company_id":     self.company_id,
            "output_type":    "lp_blueprint",
            "content":        output,
            "version":        1,
        }
        
        result = self.db.table("agent_outputs").insert(row).execute()
        if result.data:
            print(f"  ✅ Output saved to Supabase: {output_id}")
            return output_id
        else:
            print(f"  ⚠ Supabase insert failed: {result}")
            return None

    def execute_flow(self, goal: str):
        run_id = str(uuid.uuid4())
        
        # We assign an orchestrator 'run' conceptually. 
        # But we will specifically trace the marketing agent.
        marketing_agent_id = "761c56f6-4de8-4859-974a-43d964de62f0"
        context_agent_id = "40b5e259-5b28-44fd-9c5b-e758093e5d3d"
        
        print("\n=== Orchestrator Workflow Started ===")
        print(f"Goal: {goal}")
        
        # Step 1: Run Context Agent
        print("\n--- Step 1: Calling Context Agent ---")
        context_agent = ContextAgent(context_agent_id)
        # Note: In production we use actual SDK run wrapping, but here we just call it
        context_result = context_agent.run(query=goal, company_id=self.company_id)
        
        if context_result.get("status") != "success":
            print(f"❌ Context retrieval failed: {context_result}")
            return
            
        print(f"Context retrieved from docs: {context_result.get('docs')}")
        raw_text_context = context_result.get("context", "")
        context_data = [{"content": raw_text_context}]
        
        # Step 2: Run Audit Agent (DE-PRIORITIZED FOR NOW)
        print("\n--- Step 2: Bypassing Audit Agent ---")
        # audit_result = audit_agent.run(query=goal, context=raw_text_context, company_id=self.company_id)
        # ... logic to halt if failed ...


        # Step 3: Run Marketing Agent with Context
        print("\n--- Step 3: Calling Marketing Agent ---")
        marketing_agent = MarketingAgent(marketing_agent_id)
        
        if self.oversight:
            # We track the generation run
            with self.oversight.run(agent_id=marketing_agent_id, metadata={"goal": goal}) as run:
                marketing_result = marketing_agent.run(goal=goal, context=context_data)
                
                # Step 4: Local Persistence & DB
                if marketing_result.get("status") == "success":
                    self._handle_output(marketing_result.get("full_output"), marketing_agent_id, run.run_id)
                else:
                    run.report(metadata={"error": "Marketing generation failed."})
        else:
            marketing_result = marketing_agent.run(goal=goal, context=context_data)
            if marketing_result.get("status") == "success":
                self._handle_output(marketing_result.get("full_output"), marketing_agent_id, run_id)
                
        print("=== Orchestrator Workflow Complete ===")

    def _handle_output(self, full_output: dict, agent_id: str, run_id: str):
        print("\n--- Step 4: Persistence and Output Handling ---")
        # 3a. Save local file (JSON)
        output_dir = os.path.join(os.path.dirname(__file__), "outputs")
        os.makedirs(output_dir, exist_ok=True)
        json_filename = os.path.join(output_dir, f"local_output_{run_id[:8]}.json")
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(full_output, f, indent=2)
        print(f"✅ Local JSON created: {json_filename}")

        # 3b. Save Team Strategy Doc (Markdown)
        team_doc = full_output.get("team_writeup", "# No Writeup Generated")
        doc_filename = os.path.join(output_dir, f"team_strategy_{run_id[:8]}.md")
        with open(doc_filename, "w", encoding="utf-8") as f:
            f.write(team_doc)
        print(f"✅ Team Strategy Doc created: {doc_filename}")
        
        # 3c. Save to Database
        self.publish_to_db(agent_id, run_id, full_output)
        
        # 3c. Placeholder for async task dispatch for GDrive
        print("ℹ️ Google Drive upload pending. Orchestrator would dispatch asynchronous job here.")

if __name__ == "__main__":
    orchestrator = Orchestrator(company_id="1021c018-fe0e-4ae8-a972-7487521cc3d9")
    orchestrator.execute_flow("Build landing page for homeowners")
