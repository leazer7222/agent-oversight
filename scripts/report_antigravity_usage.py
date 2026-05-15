#!/usr/bin/env python3
import sys
import os
import argparse
from dotenv import load_dotenv, find_dotenv

# Load .env.local
load_dotenv(find_dotenv(".env.local", usecwd=True))

sdk_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../python-sdk"))
if sdk_dir not in sys.path:
    sys.path.append(sdk_dir)
from oversight import OversightClient

AGENT_ID = "0f1e2d3c-4b5a-4a9b-8c7d-6e5f4d3c2b1a" # Antigravity ID
OVERSIGHT_URL = os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app")
OVERSIGHT_SECRET = (
    os.environ.get("AGENT_OVERSIGHT_SECRET") or
    os.environ.get("OVERSIGHT_SECRET") or
    os.environ.get("INGEST_SECRET", "")
)

def main():
    parser = argparse.ArgumentParser(description="Report Antigravity usage to Oversight.")
    parser.add_argument("--tokens-in", type=int, default=0)
    parser.add_argument("--tokens-out", type=int, default=0)
    parser.add_argument("--cost", type=float, default=0.0)
    parser.add_argument("--message", type=str, default="Conversation turn")
    
    args = parser.parse_args()
    
    try:
        client = OversightClient(url=OVERSIGHT_URL, secret=OVERSIGHT_SECRET)
        with client.run(agent_id=AGENT_ID) as run:
            run.step("turn", message=args.message)
            run.report(tokens_in=args.tokens_in, tokens_out=args.tokens_out, cost_usd=args.cost)
        print(f"Successfully reported usage: {args.tokens_in} in, {args.tokens_out} out, ${args.cost}")
    except Exception as e:
        print(f"Error reporting usage: {e}")

if __name__ == "__main__":
    main()
