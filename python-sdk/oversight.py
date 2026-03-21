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
        result = do_work()
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


class OversightClient:
    def __init__(
        self,
        url: Optional[str] = None,
        secret: Optional[str] = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        self.url = (url or os.environ.get("OVERSIGHT_URL", "")).rstrip("/")
        self.secret = secret or os.environ.get("OVERSIGHT_SECRET", "")
        self.timeout = timeout

        if not self.url:
            raise OversightError("OVERSIGHT_URL is required (env var or constructor arg)")
        if not self.secret:
            raise OversightError("OVERSIGHT_SECRET is required (env var or constructor arg)")

    def _post(self, payload: Dict[str, Any]) -> None:
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
    ) -> None:
        payload: Dict[str, Any] = {
            "agent_id": agent_id,
            "event": event,
            "run_id": run_id,
        }
        if tokens_in is not None:
            payload["tokens_in"] = tokens_in
        if tokens_out is not None:
            payload["tokens_out"] = tokens_out
        if cost_usd is not None:
            payload["cost_usd"] = cost_usd
        if error is not None:
            payload["error"] = error
        if metadata:
            payload["metadata"] = metadata

        self._post(payload)

    @contextlib.contextmanager
    def run(
        self,
        agent_id: str,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Generator[RunContext, None, None]:
        """Context manager that emits run_started / run_completed / run_failed."""
        run_id = run_id or str(uuid.uuid4())
        ctx = RunContext(client=self, agent_id=agent_id, run_id=run_id)

        self.emit(agent_id=agent_id, event="run_started", run_id=run_id, metadata=metadata)

        try:
            yield ctx
        except Exception as exc:
            self.emit(
                agent_id=agent_id,
                event="run_failed",
                run_id=run_id,
                error=str(exc),
                tokens_in=ctx.tokens_in,
                tokens_out=ctx.tokens_out,
                cost_usd=ctx.cost_usd,
                metadata=ctx.metadata or None,
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
