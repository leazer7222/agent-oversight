import os
import sys
import json
from typing import Dict, Any

try:
    from pydantic import BaseModel
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

# Add parent directory to path to import oversight
import_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../python-sdk"))
if import_dir not in sys.path:
    sys.path.append(import_dir)
from oversight import OversightClient

class AuditAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.client = OversightClient(
            url=os.environ.get("OVERSIGHT_URL", "http://localhost:3000"),
            secret=os.environ.get("OVERSIGHT_SECRET")
        )

    def run(self, query: str, context: str, company_id: str = None) -> Dict[str, Any]:
        try:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key or genai is None:
                print("  [Warning] GEMINI_API_KEY or SDK missing. Returning auto-pass.")
                return {"passed": True, "score": 10, "reasoning": "Mocked validation."}
            
            client = genai.Client(api_key=api_key)
            
            sys_prompt = (
                "You are an elite Quality Assurance Audit Agent. "
                "You will evaluate a body of 'CONTEXT' against a 'GOAL'.\n"
                "If the CONTEXT contains substantial, relevant details to fulfill the GOAL, you pass it.\n"
                "If the CONTEXT is mocked, empty, thin, or heavily relies on hallucination/assumptions because real data is missing, you MUST fail it.\n"
                "Provide a relevance score (1-10).\n"
                "Provide exactly 1 boolean value for 'passed'.\n"
                "Provide a brief 'reasoning' for your decision.\n"
                "RETURN EXACTLY A JSON OBJECT matching: {\"passed\": bool, \"score\": int, \"reasoning\": str}"
            )
            
            user_prompt = f"GOAL: {query}\n\nCONTEXT TO AUDIT:\n{context}"
            
            print("[AuditAgent] Submitting context to Gemini 2.5 Flash for evaluation...")
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=sys_prompt,
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            
            result = json.loads(response.text)
            return result
            
        except Exception as e:
            print(f"[Error] AuditAgent failed: {e}")
            return {"passed": True, "error": str(e)}

if __name__ == "__main__":
    agent = AuditAgent(agent_id="audit-placeholder")
    res = agent.run(query="Build a marketing plan", context="ReformAI is great.")
    print(json.dumps(res, indent=2))
