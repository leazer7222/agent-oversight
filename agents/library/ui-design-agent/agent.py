import os
import sys
import json
import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types

# OversightClient for run lifecycle telemetry
_sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../python-sdk"))
if _sdk_path not in sys.path:
    sys.path.insert(0, _sdk_path)
try:
    from oversight import OversightClient
except ImportError:
    OversightClient = None

AGENT_ID = "5927c32b-36f4-4e2b-8a8b-1e5f8f322e70"

class UIOutput(BaseModel):
    components: List[Dict[str, str]]  # List of { "name": "Hero.tsx", "code": "..." }
    page_tsx: str
    layout_tsx: Optional[str]
    globals_css_additions: Optional[str]
    design_rationale: str

class UIDesignAgent:
    def __init__(self, agent_id: str = AGENT_ID):
        self.agent_id = agent_id
        oversight_url = os.environ.get("OVERSIGHT_URL", "http://localhost:3000")
        oversight_secret = os.environ.get("OVERSIGHT_SECRET") or os.environ.get("INGEST_SECRET")
        if OversightClient and oversight_secret:
            self.client = OversightClient(url=oversight_url, secret=oversight_secret)
        else:
            self.client = None

    def generate_ui(self, goal: str, blueprint: Dict[str, Any]) -> Dict:
        """Produce Next.js components based on a marketing blueprint."""
        
        prompt_path = os.path.join(os.path.dirname(__file__), "prompt.md")
        base_instruction = "You are an elite UI/UX engineer."
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                base_instruction = f.read()

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return {"error": "Missing GEMINI_API_KEY"}

        client = genai.Client(api_key=api_key)
        model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        
        print(f"  [Debug] Generating UI for goal: {goal} using {model}...")

        combined_prompt = f"""
        {base_instruction}
        
        GOAL:
        {goal}
        
        MARKETING BLUEPRINT:
        {json.dumps(blueprint, indent=2)}
        
        CRITICAL: Return ONLY a valid JSON object matching the 'UIOutput' schema.
        Extract the 'components' field as an array of objects with 'name' and 'code'.
        Include a full 'page.tsx' that imports and uses these components.
        """

        try:
            resp = client.models.generate_content(
                model=model,
                contents=combined_prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are a senior frontend architect. Output MUST be valid JSON components.",
                    response_mime_type="application/json",
                    temperature=0.2,
                    max_output_tokens=8192,
                ),
            )
            results = json.loads(resp.text)
            return results
            
        except Exception as e:
            print(f"  [Error] UI Generation failed: {e}")
            return {"error": str(e)}

    def run(self, goal: str, blueprint: Dict[str, Any]) -> Dict:
        run_id = str(uuid.uuid4())

        def _execute():
            try:
                print(f"\n[UIDesignAgent] Goal: {goal}")
                print("Step 1: Analyzing marketing blueprint...")

                print("Step 2: Generating high-fidelity UI components...")
                ui_output = self.generate_ui(goal, blueprint)

                result = {
                    "status":      "success",
                    "full_output": ui_output,
                }

                print("UI Generation complete.")
                return result

            except Exception as e:
                print(f"Error in UIDesignAgent: {e}")
                return {"status": "error", "message": str(e)}

        if self.client:
            try:
                with self.client.run(agent_id=self.agent_id, metadata={"goal": goal, "run_id": run_id}) as run:
                    result = _execute()
                    run.report(metadata={"status": result.get("status")})
                return result
            except Exception:
                pass  # oversight unavailable — run anyway
        return _execute()

if __name__ == "__main__":
    # Test stub
    agent = UIDesignAgent("ui-design-agent-test")
    # For testing, we would provide a mock blueprint
    # result = agent.run("Test Landing Page", {"sections": [{"name": "Hero", "content": "Welcome"}]})
    # print(result)
    pass
