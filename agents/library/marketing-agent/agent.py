import os
import sys
import json
import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types

# Fix Windows cp1252 stdout encoding (emojis crash otherwise)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# ── Cost estimators (approximate — prices as of 2026-05) ────────────────────
# These give a good-enough signal for cost dashboards without being exact.

def _estimate_cost_openai(model: str, tokens_in: int, tokens_out: int) -> float:
    # Prices per million tokens (input, output)
    pricing = {
        "gpt-4o":         (5.00,  15.00),
        "gpt-4o-mini":    (0.15,   0.60),
        "gpt-4-turbo":    (10.00, 30.00),
        "gpt-3.5-turbo":  (0.50,   1.50),
    }
    # Default to gpt-4o-mini rates for unknown models
    input_rate, output_rate = pricing.get(model, (0.15, 0.60))
    return round((tokens_in * input_rate + tokens_out * output_rate) / 1_000_000, 6)


def _estimate_cost_gemini(model: str, tokens_in: int, tokens_out: int) -> float:
    # Prices per million tokens (input, output)
    pricing = {
        "gemini-2.0-flash":       (0.10, 0.40),
        "gemini-2.0-flash-exp":   (0.00, 0.00),  # free tier
        "gemini-1.5-flash":       (0.075, 0.30),
        "gemini-1.5-pro":         (1.25,  5.00),
    }
    input_rate, output_rate = pricing.get(model, (0.10, 0.40))
    return round((tokens_in * input_rate + tokens_out * output_rate) / 1_000_000, 6)


class MarketingOutput(BaseModel):
    context_extracted: List[str]
    key_strategic_insights: List[str]
    audience_segmentation: Dict[str, Any]
    pain_outcome_mapping: Dict[str, Any]
    feature_value_mapping: Dict[str, Any]
    why_reformai_wins: List[str]
    objections_trust_strategy: Dict[str, Any]
    messaging_framework: Dict[str, Any]
    land_page_blueprint: Dict[str, Any]
    cross_segment_strategy: List[str]
    team_writeup: str
    gaps_assumptions: List[str]

class MarketingAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    # ── Strategy Synthesis ──────────────────────────────────────────────────
    def synthesize_strategy(self, goal: str, context: List[Dict]) -> Dict:
        """Produce the marketing brief and landing page blueprint via dual LLM calls."""
        
        # 1. Extract and process the context
        raw_context_text = ""
        for item in context:
            content = item.get("content", "")
            raw_context_text += f"\n{content}"
            
        print(f"  [Debug] Received Context Length: {len(raw_context_text)} characters")

        prompt_path = os.path.join(os.path.dirname(__file__), "prompt.md")
        base_instruction = "You are an elite marketing agent."
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                base_instruction = f.read()

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key or genai is None:
            return {"error": "Missing GEMINI_API_KEY"}

        client = genai.Client(api_key=api_key)
        results = {}

        # Provider Selection
        provider = os.environ.get("MARKETING_LLM_PROVIDER", "gemini").lower()
        openai_key = os.environ.get("OPENAI_API_KEY")
        openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        
        # 1. INTEGRATED GENERATION: Structured JSON + Strategy Write-up
        print(f"  [Debug] Generating Integrated Marketing Strategy via {provider.upper()} ({openai_model if provider == 'openai' else gemini_model}) (JSON + Markdown)...")
        
        integrated_instruction = base_instruction + """
        
        CRITICAL: Return ONLY a valid JSON object matching the 'Output Framework'. 
        The JSON MUST include a 'team_writeup' field containing your full, long-form Markdown Strategy Document for the team.
        
        You MUST cover all 11 sections of the framework within that 'team_writeup' (Markdown formatted):
        1. Context Extracted
        2. Key Strategic Insights
        3. Audience Segmentation
        4. Pain / Outcome Mapping
        5. Feature → Value Mapping
        6. Why ReformAI Wins
        7. Objections + Trust Strategy
        8. Messaging Framework
        9. Landing Page Blueprint (UI Ready)
        10. Cross-Segment Strategy
        11. Gaps / Assumptions
        
        Keep tables useful but concise within the Markdown to avoid structure issues.
        """

        try:
            if provider == "openai" and openai_key and OpenAI:
                client_oa = OpenAI(api_key=openai_key)
                response = client_oa.chat.completions.create(
                    model=openai_model,
                    messages=[
                        {"role": "system", "content": integrated_instruction},
                        {"role": "user", "content": f"GOAL:\n{goal}\n\nCONTEXT:\n{raw_context_text}"}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2
                )
                results = json.loads(response.choices[0].message.content)

                # Capture token usage from OpenAI response
                usage = response.usage
                results["_tokens_in"]  = usage.prompt_tokens
                results["_tokens_out"] = usage.completion_tokens
                results["_cost_usd"]   = _estimate_cost_openai(openai_model, usage.prompt_tokens, usage.completion_tokens)
                results["_model"]      = openai_model
                return results

            else:
                # Default to Gemini
                if not api_key:
                    return {"error": "Missing GEMINI_API_KEY"}

                client_gen = genai.Client(api_key=api_key)
                resp = client_gen.models.generate_content(
                    model=gemini_model,
                    contents=f"GOAL:\n{goal}\n\nCONTEXT:\n{raw_context_text}",
                    config=types.GenerateContentConfig(
                        system_instruction=integrated_instruction,
                        response_mime_type="application/json",
                        temperature=0.2,
                        max_output_tokens=8192,
                    ),
                )
                results = json.loads(resp.text)

                # Capture token usage from Gemini response
                usage = resp.usage_metadata
                tokens_in  = getattr(usage, "prompt_token_count",     0) or 0
                tokens_out = getattr(usage, "candidates_token_count", 0) or 0
                results["_tokens_in"]  = tokens_in
                results["_tokens_out"] = tokens_out
                results["_cost_usd"]   = _estimate_cost_gemini(gemini_model, tokens_in, tokens_out)
                results["_model"]      = gemini_model
                return results

        except Exception as e:
            print(f"  [Error] LLM Synthesis failed: {e}")
            results["error"] = str(e)
            return results

    # ── Main Entrypoint ──────────────────────────────────────────────────────
    def run(self, goal: str, context: List[Dict]) -> Dict:
        try:
            print(f"\n[MarketingAgent] Goal: {goal}")
            print(f"Step 1: Validating passed context... (Received {len(context)} context packets)")

            print("Step 2: Conducting research and synthesizing strategy...")
            strategy = self.synthesize_strategy(goal, context)

            # Extract and surface token usage for the orchestrator to report
            tokens_in  = strategy.pop("_tokens_in",  None)
            tokens_out = strategy.pop("_tokens_out", None)
            cost_usd   = strategy.pop("_cost_usd",   None)
            model      = strategy.pop("_model",       None)

            if tokens_in is not None:
                print(f"  [Usage] tokens_in={tokens_in}, tokens_out={tokens_out}, cost_usd=${cost_usd:.6f}, model={model}")

            result = {
                "status":      "success",
                "full_output": strategy,
                "tokens_in":   tokens_in,
                "tokens_out":  tokens_out,
                "cost_usd":    cost_usd,
                "model":       model,
            }

            print("✅ Generation complete.")
            return result

        except Exception as e:
            print(f"❌ Error in MarketingAgent: {e}")
            return {"status": "error", "message": str(e)}
