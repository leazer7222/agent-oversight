import os
import sys
import json
import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types

class MarketingOutput(BaseModel):
    context_extracted: List[str]
    key_strategic_insights: List[str]
    audience_segmentation: Dict[str, Any]
    pain_outcome_mapping: Dict[str, Any]
    feature_value_mapping: Dict[str, Any]
    why_reformai_wins: List[str]
    objections_trust_strategy: Dict[str, Any]
    messaging_framework: Dict[str, Any]
    landing_page_blueprint: Dict[str, Any]
    cross_segment_strategy: List[str]
    gaps_assumptions: List[str]

class MarketingAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    # ── Strategy Synthesis ──────────────────────────────────────────────────
    def synthesize_strategy(self, goal: str, context: List[Dict]) -> Dict:
        """Produce the marketing brief and landing page blueprint via LLM."""
        
        # 1. Extract and process the context
        raw_context_text = ""
        for item in context:
            content = item.get("content", "")
            raw_context_text += f"\n{content}"
            
        print(f"  [Debug] Received Context Length: {len(raw_context_text)} characters")

        prompt_path = os.path.join(os.path.dirname(__file__), "prompt.md")
        system_instruction = "You are an elite marketing agent."
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                system_instruction = f.read()

        # Enforce JSON structure
        system_instruction += "\n\nCRITICAL INSTRUCTION: You MUST return ONLY a valid JSON object. The JSON keys MUST exactly match the 11 items in the 'Output Framework' (e.g. 'context_extracted', 'key_strategic_insights', 'landing_page_blueprint', etc)."

        api_key = os.environ.get("GEMINI_API_KEY")
        
        if not api_key or genai is None:
            print("  [Warning] GEMINI_API_KEY or google-genai not found. Returning mock.")
            return {
                "error": "Missing GEMINI_API_KEY or SDK dependencies.",
                "context_extracted": [raw_context_text[:100] + "..."],
                "gaps_assumptions": ["Mocked due to missing LLM integration"]
            }

        try:
            print("  [Debug] Calling Gemini API (gemini-2.5-flash)...")
            client = genai.Client(api_key=api_key)
            prompt = f"GOAL:\n{goal}\n\nCONTEXT:\n{raw_context_text}"
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            # Parse the structured JSON response
            return json.loads(response.text)
            
        except Exception as e:
            print(f"  [Error] LLM Generation failed: {e}")
            return { 
                "error": str(e),
                "context_extracted": ["Error during extraction"],
                "gaps_assumptions": [str(e)]
            }

    # ── Main Entrypoint ──────────────────────────────────────────────────────
    def run(self, goal: str, context: List[Dict]) -> Dict:
        try:
            print(f"\n[MarketingAgent] Goal: {goal}")
            print(f"Step 1: Validating passed context... (Received {len(context)} context packets)")
            
            print("Step 2: Conducting research and synthesizing strategy...")
            strategy = self.synthesize_strategy(goal, context)

            result = {
                "status":       "success",
                "full_output":  strategy
            }

            print("✅ Generation complete.")
            return result

        except Exception as e:
            print(f"❌ Error in MarketingAgent: {e}")
            return {"status": "error", "message": str(e)}
