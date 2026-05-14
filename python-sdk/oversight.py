"""
oversight.py — Python SDK for the Agent Oversight System.

Usage:
    import os
    from oversight import OversightClient

    client = OversightClient(
        url=os.environ["OVERSIGHT_URL"],
        secret=os.environ["OVERSIGHT_SECRET"],
    )

    with client.run(agent_id="<uuid>", run_id="<uuid>") as run:
        with run.timer() as t:
            result = do_work()
        run.step("work_complete", message="Work finished", duration_ms=t.ms)
        run.report(tokens_in=100, tokens_out=200, cost_usd=0.001)
"""

from __future__ import annotations

import os
import time
import uuid
import contextlib
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, Optional


try:
    import httpx as _http_lib
    _USE_HTTPX = True
except ImportError:
    import urllib.request as _http_lib  # type: ignore
    import json as _json_lib
    _USE_HTTPX = False


# ---------------------------------------------------------------------------
# Error taxonomy — categorize exceptions before they reach the DB
# ---------------------------------------------------------------------------

ERROR_CATEGORIES = {
    "quota_exceeded":   ["quota", "rate limit", "resource_exhausted", "insufficient_quota", "429"],
    "auth_error":       ["unauthorized", "403", "401", "authentication", "permission denied"],
    "network_error":    ["connection", "timeout", "network", "unreachable", "eof"],
    "llm_error":        ["openai", "gemini", "anthropic", "model", "completion", "generate"],
    "validation_error": ["validation", "schema", "invalid", "missing field", "required"],
}


def categorize_error(exc: Exception) -> str:
    """Return a short error category string for the given exception."""
    msg = str(exc).lower()
    for category, keywords in ERROR_CATEGORIES.items():
        if any(k in msg for k in keywords):
            return category
    return "unknown"


# ---------------------------------------------------------------------------
# Timer context manager for measuring step durations
# ---------------------------------------------------------------------------

class StepTimer:
    """Simple wall-clock timer. Use as a context manager."""

    def __init__(self) -> None:
        self._start: float = 0.0
        self.ms: int = 0

    def __enter__(self) -> "StepTimer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *_: Any) -> None:
        self.ms = int((time.monotonic() - self._start) * 1000)


# ---------------------------------------------------------------------------
# Core SDK classes
# ---------------------------------------------------------------------------

class OversightError(Exception):
    pass


@dataclass
class RunContext:
    client: "OversightClient"
    agent_id: str
    run_id: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def report(
        self,
        *,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        cost_usd: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Accumulate token / cost data to send on run completion."""
        if tokens_in is not None:
            self.tokens_in = (self.tokens_in or 0) + tokens_in
        if tokens_out is not None:
            self.tokens_out = (self.tokens_out or 0) + tokens_out
        if cost_usd is not None:
            self.cost_usd = (self.cost_usd or 0.0) + cost_usd
        if metadata:
            self.metadata.update(metadata)

    def step(
        self,
        step_name: str,
        *,
        message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
        severity: str = "info",
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        cost_usd: Optional[float] = None,
    ) -> None:
        """
        Emit a mid-run step event to agent_events.
        Non-fatal — if the emit fails, execution continues.

        Args:
            step_name: Short identifier for this step (e.g. 'context_retrieved').
            message:   Human-readable description. Defaults to step_name.
            duration_ms: Wall-clock time for this step in milliseconds.
            payload:   Arbitrary structured data for this step.
            severity:  'info', 'warning', or 'error'.
            tokens_in/tokens_out/cost_usd: Also accumulates into run totals.
        """
        # Accumulate cost data if provided at step level
        if tokens_in is not None or tokens_out is not None or cost_usd is not None:
            self.report(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd)

        try:
            self.client._post({
                "agent_id":    self.agent_id,
                "event":       "run_step",
                "run_id":      self.run_id,
                "step_name":   step_name,
                "message":     message or step_name,
                "duration_ms": duration_ms,
                "severity":    severity,
                "metadata":    payload or {},
            })
        except Exception:
            # Step events are non-fatal — never block the agent's work
            pass

    def timer(self) -> StepTimer:
        """Return a StepTimer context manager for measuring step duration."""
        return StepTimer()


class OversightClient:
    def __init__(
        self,
        url: Optional[str] = None,
        secret: Optional[str] = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        self.url = (url or os.environ.get("OVERSIGHT_URL", "")).rstrip("/")
        self.secret = (
            secret
            or os.environ.get("OVERSIGHT_SECRET")
            or os.environ.get("INGEST_SECRET")
            or ""
        )
        self.timeout = timeout

        if not self.url:
            raise OversightError("OVERSIGHT_URL is required (env var or constructor arg)")
        if not self.secret:
            raise OversightError("OVERSIGHT_SECRET is required (env var or constructor arg)")

    def _post(self, payload: Dict[str, Any]) -> None:
        # Strip None values — ingest route ignores missing optional fields
        payload = {k: v for k, v in payload.items() if v is not None}

        endpoint = f"{self.url}/api/ingest"
        headers = {
            "Content-Type": "application/json",
            "x-agent-secret": self.secret,
        }

        if _USE_HTTPX:
            resp = _http_lib.post(endpoint, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code >= 400:
                raise OversightError(f"Ingest failed ({resp.status_code}): {resp.text}")
        else:
            import json
            data = json.dumps(payload).encode()
            req = _http_lib.Request(endpoint, data=data, headers=headers, method="POST")
            try:
                with _http_lib.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status >= 400:
                        raise OversightError(f"Ingest failed ({resp.status})")
            except Exception as exc:
                raise OversightError(f"Ingest request failed: {exc}") from exc

    def emit(
        self,
        *,
        agent_id: str,
        event: str,
        run_id: str,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        cost_usd: Optional[float] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        team_id: Optional[str] = None,
        context_bundle_id: Optional[str] = None,
        context_bundle_version: Optional[int] = None,
        parent_run_id: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "agent_id": agent_id,
            "event":    event,
            "run_id":   run_id,
        }
        if tokens_in              is not None: payload["tokens_in"]               = tokens_in
        if tokens_out             is not None: payload["tokens_out"]              = tokens_out
        if cost_usd               is not None: payload["cost_usd"]                = cost_usd
        if error                  is not None: payload["error"]                   = error
        if metadata:                           payload["metadata"]                = metadata
        if team_id                is not None: payload["team_id"]                 = team_id
        if context_bundle_id      is not None: payload["context_bundle_id"]       = context_bundle_id
        if context_bundle_version is not None: payload["context_bundle_version"]  = context_bundle_version
        if parent_run_id          is not None: payload["parent_run_id"]           = parent_run_id

        self._post(payload)

    @contextlib.contextmanager
    def run(
        self,
        agent_id: str,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        team_id: Optional[str] = None,
        context_bundle_id: Optional[str] = None,
        context_bundle_version: Optional[int] = None,
        parent_run_id: Optional[str] = None,
    ) -> Generator[RunContext, None, None]:
        """Context manager that emits run_started / run_completed / run_failed."""
        run_id = run_id or str(uuid.uuid4())
        ctx = RunContext(client=self, agent_id=agent_id, run_id=run_id)

        self.emit(
            agent_id=agent_id,
            event="run_started",
            run_id=run_id,
            metadata=metadata,
            team_id=team_id,
            context_bundle_id=context_bundle_id,
            context_bundle_version=context_bundle_version,
            parent_run_id=parent_run_id,
        )

        try:
            yield ctx
        except Exception as exc:
            error_category = categorize_error(exc)
            self.emit(
                agent_id=agent_id,
                event="run_failed",
                run_id=run_id,
                error=f"[{error_category}] {exc}",
                tokens_in=ctx.tokens_in,
                tokens_out=ctx.tokens_out,
                cost_usd=ctx.cost_usd,
                metadata={**ctx.metadata, "error_category": error_category} or None,
            )
            raise
        else:
            self.emit(
                agent_id=agent_id,
                event="run_completed",
                run_id=run_id,
                tokens_in=ctx.tokens_in,
                tokens_out=ctx.tokens_out,
                cost_usd=ctx.cost_usd,
                metadata=ctx.metadata or None,
            )
