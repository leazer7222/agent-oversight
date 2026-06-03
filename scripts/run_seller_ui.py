import os
import json
import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types
from openai import OpenAI

# --- Environment Loading ---
def load_env():
    env_path = "c:/Users/cjlea/AgentProjects/agent-oversight/.env.local"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key] = value

load_env()

# --- Self-Contained UIDesignAgent with OpenAI Fallback ---

class UIOutput(BaseModel):
    components: List[Dict[str, str]]
    page_tsx: str
    layout_tsx: Optional[str]
    globals_css_additions: Optional[str]
    design_rationale: str

class UIDesignAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    def generate_ui(self, goal: str, blueprint: Dict[str, Any]) -> Dict:
        """Produce Next.js components based on a marketing blueprint."""
        
        prompt_path = "c:/Users/cjlea/AgentProjects/agent-oversight/agents/library/ui-design-agent/prompt.md"
        base_instruction = "You are an elite UI/UX engineer."
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                base_instruction = f.read()

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

        provider = os.environ.get("UI_LLM_PROVIDER", "gemini").lower()
        
        if provider == "openai":
            openai_key = os.environ.get("OPENAI_API_KEY")
            if not openai_key:
                return {"error": "Missing OPENAI_API_KEY"}
            
            print(f"  [Debug] Generating UI via OpenAI (gpt-4o-mini)...")
            client = OpenAI(api_key=openai_key)
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a senior frontend architect. Output MUST be valid JSON components."},
                        {"role": "user", "content": combined_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2
                )
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                print(f"  [Error] OpenAI Generation failed: {e}")
                return {"error": str(e)}

        else:
            # Gemini Path
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                return {"error": "Missing GEMINI_API_KEY"}

            client = genai.Client(api_key=api_key)
            model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp")
            
            print(f"  [Debug] Generating UI via Gemini ({model})...")

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
                return json.loads(resp.text)
            except Exception as e:
                print(f"  [Error] Gemini Generation failed: {e}")
                return {"error": str(e)}

    def run(self, goal: str, blueprint: Dict[str, Any]) -> Dict:
        try:
            print(f"\n[UIDesignAgent] Goal: {goal}")
            print("Step 1: Analyzing marketing blueprint...")
            ui_output = self.generate_ui(goal, blueprint)
            return {"status": "success", "full_output": ui_output}
        except Exception as e:
            return {"status": "error", "message": str(e)}

# --- Runner Logic ---

async def run_seller_ui():
    print("--- Running UI Design Agent for Homeowner Seller Type ---")
    
    # Mocking the Marketing Blueprint for Homeowner Sellers (v7.1 Strategy)
    blueprint = {
      "core_upgrade": "From 'improve your listing' → 'sell the future of your property'",
      "messaging_framework": {
        "one_big_promise": "Sell your property as its full potential, not its current condition",
        "positioning": "Turn outdated properties into high-value, ready-to-execute projects",
        "headline": "Don’t sell what your property is. Sell what it can become.",
        "subheadline": "Show buyers the transformation, cost, and execution path — before they decide.",
        "cta": "Analyze My Property"
      },
      "solution_upgrade": {
        "before": "better listing",
        "after": "project-based listing with execution built in"
      },
      "feature_value_mapping": {
        "enhanced_listing": "Turn property into a renovation-ready project",
        "visualization": "Show buyers the future state",
        "cost_clarity": "Eliminate buyer uncertainty",
        "contractor_integration": "Attach execution to the listing",
        "market_positioning": "Increase perceived value and demand"
      },
      "why_reformai_wins": [
        "Transforms listings into decision-ready assets",
        "Reduces time on market",
        "Increases buyer confidence",
        "Maximizes value without blind renovation"
      ],
      "hero_upgrade": {
        "visual": "Outdated property → premium finished concept with value indicator",
        "message": "You are selling the outcome, not the asset"
      }
    }

    agent = UIDesignAgent(agent_id="ui-design-seller-test")
    goal = "Generate a high-fidelity landing page for Home Sellers that focuses on selling the 'future potential' and outcome of a property listing."
    result = agent.run(goal, blueprint)
    
    if result.get("status") == "success":
        output = result.get("full_output", {})
        if "error" in output:
            print(f"ERROR: {output['error']}")
            return
            
        components = output.get("components", [])
        page_tsx = output.get("page_tsx", "")
        output_dir = "c:/Users/cjlea/OneDrive/Desktop/Anti-Gravity_ReformAI/Mockup Agent/seller_v7"
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"Step 2: Saving {len(components)} components to {output_dir}...")
        for comp in components:
            name = comp.get("name", "Component").replace(".tsx", "") + ".tsx"
            code = comp.get("code", "")
            with open(f"{output_dir}/{name}", "w", encoding="utf-8") as f:
                f.write(code)
        
        with open(f"{output_dir}/page.tsx", "w", encoding="utf-8") as f:
            f.write(page_tsx)
            
        print(f"SUCCESS! UI generated in {output_dir}")

if __name__ == "__main__":
    asyncio.run(run_seller_ui())
