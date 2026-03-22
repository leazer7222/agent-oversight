import os
import sys
from typing import List, Dict, Any, Optional

# Add the project root to sys.path to allow importing the oversight SDK
# (Assumes oversight.py is in the root or a standard location)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
try:
    from oversight import OversightClient
except ImportError:
    print("Warning: oversight SDK not found. Reporting will be disabled.")
    OversightClient = None

class MarketingAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.client = OversightClient(
            url=os.environ.get("OVERSIGHT_URL", "http://localhost:3000/api/agents/ingest"),
            secret=os.environ.get("OVERSIGHT_SECRET")
        ) if OversightClient else None

    def extract_context(self, run, goal: str):
        """Pulls relevant documentation from the Context Agent."""
        run.report_step("extracting_context", {"goal": goal})
        # Logic to call context-agent would go here
        return ["Context from Pitch Deck", "Context from Roadmap"]

    def synthesize_strategy(self, run, context: list):
        """Synthesizes context into strategic segments."""
        run.report_step("synthesizing_strategy", {"source_count": len(context)})
        return "Elite marketing strategy synthesized..."

    def create_blueprint(self, run, strategy: str):
        """Generates a design-ready landing page blueprint."""
        run.report_step("creating_blueprint", {"status": "generating"})
        return {
            "hero": {"headline": "Reform Your Renovation", "cta": "Get Started"},
            "sections": ["Pain Points", "Solution", "Trust Elements"]
        }

    def run(self, goal: str, company_id: Optional[str] = None):
        if not self.client:
            return {"status": "error", "message": "Oversight client not initialized"}

        with self.client.run(agent_id=self.agent_id, metadata={"goal": goal, "company_id": company_id}) as run:
            try:
                # 1. No Blind Output - Extract Stage
                context = self.extract_context(run, goal)
                
                # 2. Strategy Stage
                strategy = self.synthesize_strategy(run, context)
                
                # 3. Output Stage
                blueprint = self.create_blueprint(run, strategy)
                
                run.report(metadata={"strategy_produced": True, "blueprint_generated": True})
                
                return {
                    "strategy": strategy,
                    "blueprint": blueprint,
                    "status": "success"
                }
            except Exception as e:
                print(f"Error in MarketingAgent: {e}")
                run.report(metadata={"error": str(e)})
                return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    # Test run
    agent = MarketingAgent("8482d8c3-1811-4712-881b-537449339e31")
    agent.run("Create landing page for homeowners", company_id="1021c018-fe0e-4ae8-a972-7487521cc3d9")
