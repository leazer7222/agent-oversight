"""
codebase-context-agent runtime entrypoint.

The v1 approach (a single LLM call DISCOVERS entities) is RETIRED - it sampled ~13% of the
schema and produced the Partner/Admin net-new error class. The runtime is now the deterministic
truth service in `pipeline.py`: drizzle-kit snapshot + static source scan discover structure;
the LLM only LABELS (domain_signals/glossary). See docs/codebase-context-agent-truth-service-design.md.

This module preserves the documented `agent.py` entrypoint by delegating to the truth-service pipeline.

Run:
    python agents/library/codebase-context-agent/agent.py \
        --repo-path <local clone> --target-key reformai-product \
        --feature-intent "..." --concepts-to-check Partner Admin ... [--semantic]

The full v1 implementation remains in git history if ever needed.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from pipeline import main  # noqa: E402

if __name__ == "__main__":
    main()
