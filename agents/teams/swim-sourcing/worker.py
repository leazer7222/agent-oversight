#!/usr/bin/env python3
"""
Swim-sourcing durable worker.

ONE process, THREE identities. Every job type is owned by exactly one registered
agent identity (IDENTITY_BY_JOB), and every job opens a run under that identity
in Agent Oversight. That is what makes the kill switch, the budget cap and the
cost attribution real per capability without a second process or any
agent-to-agent protocol - the queue is the only channel.

Execution protocol per job:
  1. claim with a LEASE (swim_claim_job)                 - SKIP LOCKED, atomic
  2. resolve the owning identity (agents row by name)   - the run is attributed to it
  3. run_started -> Agent Oversight                      - existing telemetry SDK
  4. PREFLIGHT, fail closed, UNCONDITIONALLY:
       - agent status must be 'active'                   - the kill switch
       - tenant budget must allow the estimate          - spend ceiling
       - tenant credential must resolve for LLM jobs    - no platform-key fallback
  5. do the work, HEARTBEATING                          - lease extension
       heartbeat returns False when cancellation is requested -> stop cleanly
  6. finish (done | failed | blocked | cancelled)        - bounded retry/backoff
  7. run_completed (done/blocked) or run_failed          - with tokens + cost

A crashed worker is recovered by swim_reap_expired_jobs, which returns
expired-lease jobs to the queue. 'blocked' is deliberately terminal: a paused
agent, an exhausted budget or a missing credential will not be fixed by retrying.

    python agents/teams/swim-sourcing/worker.py --once
    python agents/teams/swim-sourcing/worker.py --drain    # process until the queue is empty
    python agents/teams/swim-sourcing/worker.py            # poll loop
    python agents/teams/swim-sourcing/worker.py --reap     # reaper only

Prototype notes: discovery runs on recorded fixtures ONLY when the job payload
says use_fixtures=true, and the rows it writes carry source='fixture'. There is
no send handler in this file; nothing here can email anyone.
"""

from __future__ import annotations

import os
import sys
import json
import time
import uuid
import signal
import argparse
import importlib.util as ilu
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "python-sdk"))
sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)
except ImportError:
    pass

from agents.lib import credentials as CRED  # noqa: E402
from agents.lib import llm as LLM            # noqa: E402
from oversight import OversightClient        # noqa: E402

POLL_SECONDS = float(os.environ.get("SWIM_WORKER_POLL_SECONDS", "5"))
LEASE_SECONDS = int(os.environ.get("SWIM_WORKER_LEASE_SECONDS", "300"))
HEARTBEAT_EVERY = max(10, LEASE_SECONDS // 3)
WORKER_ID = os.environ.get("SWIM_WORKER_ID") or f"swim-worker-{uuid.uuid4().hex[:8]}"
TENANT_PREFIX = os.environ.get("SWIM_TENANT_PREFIX", "swimschool")

SUPABASE_URL = (os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""

LIB = REPO_ROOT / "agents" / "library"

# Job type -> owning identity (capability suffix of the agents.name).
IDENTITY_BY_JOB = {
    "discover":        "facility-researcher",
    "enrich":          "facility-researcher",
    "qualify":         "facility-researcher",
    "draft_outreach":  "partnership-coordinator",
    "poll_inbox":      "partnership-coordinator",
    "classify_reply":  "partnership-coordinator",
}
# Job types that make a provider call and therefore need the tenant credential.
LLM_JOBS = {"enrich", "draft_outreach", "classify_reply"}
MODEL_BY_JOB = {"enrich": "claude-haiku-5-5", "classify_reply": "claude-haiku-5-5",
                "draft_outreach": "claude-sonnet-5-5"}

_STOP = False


def _handle_signal(signum, _frame):
    global _STOP
    _STOP = True
    print(f"[worker] signal {signum} received; finishing current job then exiting")


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# Supabase access (service role, public RPCs only - PostgREST does not expose
# swim_sourcing, verified live 2026-10-20)
# ---------------------------------------------------------------------------

def _headers(extra: Optional[dict] = None) -> dict:
    h = {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
         "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def rpc(fn: str, payload: dict):
    """Call a public RPC with the service role key."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise RuntimeError(
            "NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/{fn}",
        data=json.dumps(payload).encode(), headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read(600).decode("utf-8", "replace")
        raise RuntimeError(f"rpc {fn} failed ({exc.code}): {detail}") from exc


def rest_get(path: str, query: dict) -> list:
    qs = urllib.parse.urlencode(query)
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{path}?{qs}", headers=_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


_AGENT_CACHE: dict = {}


def resolve_agent(company_id: str, capability: str) -> dict:
    """The agents row for {prefix}.{capability} in this company. Cached per process;
    status is re-read in preflight so a pause takes effect on the next job."""
    key = (company_id, capability)
    if key not in _AGENT_CACHE:
        rows = rest_get("agents", {"company_id": f"eq.{company_id}",
                                   "name": f"eq.{TENANT_PREFIX}.{capability}",
                                   "select": "id,name,status,model"})
        if not rows:
            raise Blocked(f"no registered agent {TENANT_PREFIX}.{capability} for company {company_id}",
                          "validation_error")
        _AGENT_CACHE[key] = rows[0]
    return _AGENT_CACHE[key]


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

_OVERSIGHT: Optional[OversightClient] = None


def oversight() -> OversightClient:
    global _OVERSIGHT
    if _OVERSIGHT is None:
        # Raises if OVERSIGHT_URL / secret are missing. That is deliberate: a
        # worker that silently runs without telemetry is the defect this
        # rewrite exists to close.
        _OVERSIGHT = OversightClient()
    return _OVERSIGHT


# ---------------------------------------------------------------------------
# Preflight: every check fails CLOSED
# ---------------------------------------------------------------------------

class Blocked(Exception):
    """A precondition failed. Terminal - retrying will not help."""

    def __init__(self, reason: str, category: str):
        super().__init__(reason)
        self.category = category


class Cancelled(Exception):
    """Cooperative cancellation requested through the heartbeat."""


def check_kill_switch(company_id: str, agent_id: str) -> None:
    """Raises Blocked unless the identity is registered, active and this company's.

    Runs BEFORE the telemetry run opens: /api/ingest refuses run_started for a
    non-active agent (403), so a paused identity must be blocked without
    needing to report - otherwise the job would be aborted mid-flight and left
    'running' until the reaper, which is what the first pause demo showed.
    """
    try:
        rows = rest_get("agents", {"id": f"eq.{agent_id}", "select": "status,company_id"})
    except Exception as exc:
        raise Blocked(f"could not verify agent status: {exc}", "validation_error")
    if not rows:
        raise Blocked(f"agent {agent_id} is not registered", "validation_error")
    if rows[0].get("status") != "active":
        raise Blocked(f"agent {agent_id} is not active (status={rows[0].get('status')})",
                      "agent_paused")
    if rows[0].get("company_id") != company_id:
        raise Blocked("agent does not belong to the job's company", "cross_tenant")


def preflight(company_id: str, agent_id: str, *, needs_llm: bool, estimate_usd: float = 0.05):
    """Returns a ResolvedCredential (or None for non-LLM jobs), or raises Blocked.

    Order matters: the cheapest and most definitive checks run first so a paused
    agent or an exhausted budget never reaches credential decryption.
    """
    # 1. Kill switch (re-checked here too, so a pause between claim and run start
    # is still honoured).
    check_kill_switch(company_id, agent_id)

    # 2. Spend ceiling.
    budget = CRED.check_tenant_budget(company_id, estimate_usd)
    if not budget["allowed"]:
        raise Blocked(
            f"budget check failed: {budget['reason']} "
            f"(spent {budget.get('spent_usd')} of {budget.get('limit_usd')})",
            "budget_exceeded")

    if not needs_llm:
        return None

    # 3. Tenant credential. No fallback, by design.
    try:
        return CRED.resolve_tenant_api_key(company_id, "anthropic")
    except CRED.MissingTenantCredential as exc:
        raise Blocked(str(exc), "missing_tenant_credential") from exc
    except CRED.CredentialError as exc:
        raise Blocked(str(exc), exc.category) from exc


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _load_module(path: Path, name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = ilu.spec_from_file_location(name, path)
    mod = ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _llm_for(cred, model: str) -> Callable:
    client = LLM.make_client(cred.api_key)

    def _call(system: str, user: str, tool: dict, max_tokens: int = 8000):
        return LLM.call_tool(client, model=model, system=system, user=user, tool=tool,
                             max_tokens=max_tokens)
    return _call


def _merge_usage(total: dict, usage: Optional[dict]) -> None:
    if not usage:
        return
    total["tokens_in"] = total.get("tokens_in", 0) + int(usage.get("tokens_in", 0))
    total["tokens_out"] = total.get("tokens_out", 0) + int(usage.get("tokens_out", 0))
    total["cost_usd"] = round(total.get("cost_usd", 0.0) + float(usage.get("cost_usd", 0.0)), 6)
    total.setdefault("model", usage.get("model"))


def handle_discover(job: dict, cred, heartbeat, ctx) -> dict:
    """Discovery does not call an LLM. It consumes paid Places quota when live,
    which is why the request ceiling lives in the agent rather than the caller.

    Fixtures are used ONLY when the payload says so, and the rows then carry
    source='fixture'. A missing key with no explicit opt-in fails closed."""
    disc = _load_module(LIB / "facility-discovery-agent" / "discovery.py", "discovery")
    payload = job.get("payload") or {}
    cfg = disc.SearchConfig(
        center_lat=float(payload.get("center_lat", disc.KATY_TX[0])),
        center_lng=float(payload.get("center_lng", disc.KATY_TX[1])),
        radius_miles=float(payload.get("radius_miles", 15.0)),
        max_requests=int(payload.get("max_requests", 8)),
    )

    transport = None
    if payload.get("use_fixtures"):
        fx_path = LIB / "facility-discovery-agent" / "fixtures" / "katy_tx_places.json"
        transport = disc.fixture_transport(json.loads(fx_path.read_text(encoding="utf-8")),
                                           label=fx_path.name)
        print("[worker] discovery: using RECORDED FIXTURES by request (rows carry source='fixture')")
    elif not os.environ.get("GOOGLE_PLACES_API_KEY"):
        raise Blocked("GOOGLE_PLACES_API_KEY is not set and use_fixtures was not requested; "
                      "refusing to invent facilities", "validation_error")

    facilities, stats = disc.discover(cfg, transport=transport)
    heartbeat()
    ctx.step("places_search", payload=stats.as_dict())

    inserted = matched = 0
    for fac in facilities:
        res = rpc("swim_upsert_facility", {"p_company_id": job["company_id"], "p_facility": fac})
        row = res[0] if isinstance(res, list) and res else (res or {})
        if row.get("was_inserted"):
            inserted += 1
        else:
            matched += 1
    ctx.step("facilities_upserted", payload={"inserted": inserted, "matched_existing": matched})
    return {"found": len(facilities), "inserted": inserted, "matched_existing": matched,
            "source": getattr(transport, "source", "google_places"), "stats": stats.as_dict()}


def handle_enrich(job: dict, cred, heartbeat, ctx) -> dict:
    """Evidence-bound enrichment: an LLM extracts facts and contacts from a page,
    and NOTHING is written unless its verbatim snippet is found in that page."""
    enrich = _load_module(LIB / "facility-researcher" / "enrich.py", "enrich")
    company_id = job["company_id"]
    payload = job.get("payload") or {}
    limit = int(payload.get("limit", 40))
    llm = _llm_for(cred, MODEL_BY_JOB["enrich"])
    pages = enrich.load_fixture_pages()

    rows = rpc("swim_list_research", {"p_company_id": company_id, "p_limit": 500}) or []
    todo = [r for r in rows if (r.get("known_count") or 0) <= 1 and r.get("source") in ("fixture", "google_places")]
    todo = todo[:limit]

    usage: dict = {}
    counts = {"enriched": 0, "no_page": 0, "facts_written": 0, "contacts_written": 0,
              "evidence_rejected": 0, "skipped": len(rows) - len(todo)}
    for i, r in enumerate(todo):
        fac = rpc("swim_facility_attributes", {"p_facility_id": r["facility_id"]}) or {}
        page = enrich.page_for(fac, pages)
        if page is None:
            counts["no_page"] += 1
            continue
        result, u = enrich.extract(fac, page, llm)
        _merge_usage(usage, u)
        counts["evidence_rejected"] += result["evidence_rejected"]
        if result["attributes"]:
            rpc("swim_apply_enrichment", {"p_company_id": company_id, "p_payload": {
                "facility_id": r["facility_id"],
                "attributes": result["attributes"],
                "attributes_confidence": result["attributes_confidence"]}})
            counts["facts_written"] += len(result["attributes"])
        for c in result["contacts"]:
            rpc("swim_record_contact", {"p_company_id": company_id,
                                        "p_payload": {**c, "facility_id": r["facility_id"]}})
            counts["contacts_written"] += 1
        counts["enriched"] += 1
        if i % 5 == 0:
            heartbeat()
    ctx.step("enrichment", payload=counts)
    return {**counts, "usage": usage}


def handle_qualify(job: dict, cred, heartbeat, ctx) -> dict:
    scoring = _load_module(LIB / "facility-qualification-agent" / "scoring.py", "scoring")
    triage = _load_module(LIB / "facility-researcher" / "triage.py", "triage")
    company_id = job["company_id"]
    config = (job.get("payload") or {}).get("config") or {}

    rows = rpc("swim_list_research", {"p_company_id": company_id, "p_limit": 500}) or []
    counts = {"scored": 0, "contact_first": 0, "research_further": 0,
              "not_currently_suitable": 0, "disqualified": 0}
    for i, row in enumerate(rows):
        fac = rpc("swim_facility_attributes", {"p_facility_id": row["facility_id"]}) or {}
        facility = {
            "id": row["facility_id"],
            "distance_miles": fac.get("distance_miles"),
            "attributes": fac.get("attributes") or {},
            "attributes_confidence": fac.get("attributes_confidence") or {},
        }
        result = scoring.qualify(facility, config)
        verdict = triage.triage(result, fac)
        payload = result.to_payload(run_id=job.get("run_id"))
        payload["status"] = verdict["status_legacy"]
        payload["score_breakdown"] = {**payload["score_breakdown"], **verdict["breakdown_extra"]}
        rpc("swim_record_qualification", {"p_company_id": company_id, "p_payload": payload})
        counts["scored"] += 1
        counts[verdict["triage_state"]] = counts.get(verdict["triage_state"], 0) + 1
        if i % 10 == 0:
            heartbeat()
    ctx.step("triage", payload=counts)
    return counts


def handle_draft_outreach(job: dict, cred, heartbeat, ctx) -> dict:
    draft = _load_module(LIB / "partnership-coordinator" / "draft.py", "draft")
    company_id = job["company_id"]
    payload = job.get("payload") or {}
    limit = int(payload.get("limit", 8))
    campaign_id = payload.get("campaign_id") or str(uuid.uuid4())
    business = payload.get("business_facts") or draft.PROTOTYPE_BUSINESS_FACTS
    llm = _llm_for(cred, MODEL_BY_JOB["draft_outreach"])

    actions = rpc("swim_next_actions", {"p_company_id": company_id}) or []
    targets = [a for a in actions if a.get("action_type") == "prepare_outreach"][:limit]

    usage: dict = {}
    counts = {"drafted": 0, "refused_by_fabrication_gate": 0, "no_contact": 0, "campaign_id": campaign_id}
    for i, a in enumerate(targets):
        fac = rpc("swim_facility_attributes", {"p_facility_id": a["facility_id"]}) or {}
        try:
            d, u = draft.compose(fac, business, llm)
        except draft.FabricationError as exc:
            counts["refused_by_fabrication_gate"] += 1
            ctx.step("draft_refused", payload={"facility_id": a["facility_id"], "reason": str(exc)},
                     severity="warning")
            continue
        _merge_usage(usage, u)
        if d is None:
            counts["no_contact"] += 1
            continue
        rpc("swim_record_draft", {"p_company_id": company_id, "p_payload": {
            "facility_id": a["facility_id"], "contact_id": d.get("contact_id"),
            "campaign_id": campaign_id, "subject": d["subject"], "body": d["body"],
            "body_sha256": d["body_sha256"]}})
        counts["drafted"] += 1
        if i % 3 == 0:
            heartbeat()
    ctx.step("drafting", payload=counts)
    return {**counts, "usage": usage}


def handle_poll_inbox(job: dict, cred, heartbeat, ctx) -> dict:
    """PROTOTYPE: polls a SIMULATED inbox - a labelled fixture of scripted replies.
    Every row written carries a '[SIMULATED]' subject, enforced by the RPC."""
    company_id = job["company_id"]
    payload = job.get("payload") or {}
    fx_path = LIB / "partnership-coordinator" / "fixtures" / "replies.json"
    scenarios = json.loads(fx_path.read_text(encoding="utf-8"))["scenarios"]
    limit = int(payload.get("limit", len(scenarios)))

    threads = rpc("swim_list_threads", {"p_company_id": company_id, "p_limit": 500}) or []
    open_threads = [t for t in threads if (t.get("inbound_count") or 0) == 0
                    and (t.get("outbound_count") or 0) > 0]
    open_threads.sort(key=lambda t: t.get("updated_at") or "")
    # Scenarios are consumed sequentially across runs: the number of replies
    # already recorded is the offset, so a second poll continues the script
    # instead of replaying scenario 1.
    already = sum(int(t.get("inbound_count") or 0) for t in threads)
    start = already % len(scenarios) if scenarios else 0
    pending = scenarios[start:start + limit]

    written = 0
    for scenario, t in zip(pending, open_threads):
        subject = f"[SIMULATED] Re: {t.get('subject') or 'Recurring swim lesson space'}"
        rpc("swim_record_inbound", {"p_company_id": company_id, "p_payload": {
            "thread_id": t["thread_id"], "subject": subject,
            "body": scenario["body"], "scenario_id": scenario["id"]}})
        written += 1
    heartbeat()
    ctx.step("simulated_inbox", payload={"replies_written": written,
                                         "threads_without_reply": max(0, len(open_threads) - written)})
    return {"replies_written": written, "scenarios_available": len(scenarios),
            "simulated": True}


def handle_classify_reply(job: dict, cred, heartbeat, ctx) -> dict:
    classify = _load_module(LIB / "partnership-coordinator" / "classify.py", "classify")
    company_id = job["company_id"]
    payload = job.get("payload") or {}
    faq = payload.get("faq") or classify.PROTOTYPE_FAQ
    llm = _llm_for(cred, MODEL_BY_JOB["classify_reply"])

    threads = rpc("swim_list_threads", {"p_company_id": company_id, "p_limit": 500}) or []
    todo = [t for t in threads if (t.get("inbound_count") or 0) > 0 and not t.get("last_classification")]

    usage: dict = {}
    counts = {"classified": 0, "escalated": 0, "auto_reply_candidates": 0, "opt_outs": 0,
              "injection_flagged": 0, "answers_applied": 0}
    for i, t in enumerate(todo):
        inbound = t.get("last_inbound_excerpt") or ""
        verdict, u = classify.classify(inbound, t, faq, llm)
        _merge_usage(usage, u)
        rpc("swim_record_classification", {"p_company_id": company_id, "p_payload": {
            "thread_id": t["thread_id"], "intent": verdict["intent"],
            "requires_approval": verdict["safety"]["requires_approval"],
            "classification": verdict}})
        counts["classified"] += 1
        if verdict["safety"]["requires_approval"]:
            counts["escalated"] += 1
        if verdict["proposed_action"] == "auto_reply":
            counts["auto_reply_candidates"] += 1
        if verdict["intent"] == "unsubscribe":
            counts["opt_outs"] += 1
        if verdict["safety"]["injection_suspected"]:
            counts["injection_flagged"] += 1
        if verdict.get("answered_questions"):
            attrs = {q["attribute"]: q["value"] for q in verdict["answered_questions"]}
            rpc("swim_apply_enrichment", {"p_company_id": company_id, "p_payload": {
                "facility_id": t["facility_id"], "attributes": attrs,
                "attributes_confidence": {k: "verified" for k in attrs}}})
            counts["answers_applied"] += len(attrs)
        if i % 3 == 0:
            heartbeat()
    ctx.step("classification", payload=counts)
    return {**counts, "usage": usage}


HANDLERS = {
    "discover": handle_discover,
    "enrich": handle_enrich,
    "qualify": handle_qualify,
    "draft_outreach": handle_draft_outreach,
    "poll_inbox": handle_poll_inbox,
    "classify_reply": handle_classify_reply,
}
# Deliberately absent: send_outreach, schedule_meeting, reconcile_sends. The
# prototype has no path that reaches a real mailbox or calendar.


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------

class run_cm_guard:
    """Re-enter an already-opened run context so the body below can stay a plain
    `with` block while run_started errors are handled separately above."""

    def __init__(self, cm, ctx):
        self.cm, self.ctx = cm, ctx

    def __enter__(self):
        return self.ctx

    def __exit__(self, exc_type, exc, tb):
        return self.cm.__exit__(exc_type, exc, tb)


def process_one() -> bool:
    """Claim and process one job. Returns False when the queue is empty."""
    claimed = rpc("swim_claim_job",
                  {"p_worker_id": WORKER_ID, "p_lease_seconds": LEASE_SECONDS,
                   "p_job_types": list(HANDLERS.keys())})
    rows = claimed if isinstance(claimed, list) else ([claimed] if claimed else [])
    if not rows:
        return False

    job = rows[0]
    job_id = job["job_id"]
    company_id = job["company_id"]
    job_type = job["job_type"]
    print(f"[worker] claimed {job_type} {job_id} (attempt {job['attempts']}/{job['max_attempts']})")

    last_beat = [time.time()]

    def heartbeat():
        if time.time() - last_beat[0] < HEARTBEAT_EVERY:
            return
        alive = rpc("swim_heartbeat_job",
                    {"p_job_id": job_id, "p_worker_id": WORKER_ID,
                     "p_lease_seconds": LEASE_SECONDS})
        last_beat[0] = time.time()
        if alive is False:
            raise Cancelled("cancellation requested")

    def finish(status: str, result: Optional[dict] = None, error: Optional[str] = None):
        rpc("swim_finish_job", {"p_job_id": job_id, "p_worker_id": WORKER_ID,
                                "p_status": status, "p_result": result, "p_error": error})

    run_id = str(uuid.uuid4())
    job["run_id"] = run_id

    # Identity resolution and the kill switch happen BEFORE the run opens: a job
    # with no owning identity, or a paused identity, is blocked terminally here
    # rather than attributed to nobody or aborted by ingest's 403.
    try:
        agent = resolve_agent(company_id, IDENTITY_BY_JOB[job_type])
        check_kill_switch(company_id, agent["id"])
    except Blocked as exc:
        finish("blocked", error=f"[{exc.category}] {exc}")
        print(f"[worker] BLOCKED {job_id}: [{exc.category}] {exc}")
        return True

    needs_llm = job_type in LLM_JOBS
    model = MODEL_BY_JOB.get(job_type)
    try:
        run_cm = oversight().run(agent_id=agent["id"], run_id=run_id,
                                 metadata={"job_id": job_id, "job_type": job_type,
                                           "company_id": company_id, "worker_id": WORKER_ID,
                                           "prototype": True},
                                 model=model, provider="anthropic" if needs_llm else None)
        ctx = run_cm.__enter__()
    except Exception as exc:
        # Telemetry could not open the run. Do not leave the job leased: record
        # the failure so bounded retry/backoff applies.
        finish("failed", error=f"[telemetry] run_started refused: {str(exc)[:300]}")
        print(f"[worker] FAILED {job_id}: run_started refused: {exc}")
        return True

    with run_cm_guard(run_cm, ctx) as ctx:
        try:
            cred = preflight(company_id, agent["id"], needs_llm=needs_llm)
            ctx.step("preflight", payload={"agent": agent["name"], "needs_llm": needs_llm})
            result = HANDLERS[job_type](job, cred, heartbeat, ctx)
            usage = (result or {}).pop("usage", None) or {}
            ctx.report(tokens_in=int(usage.get("tokens_in", 0)),
                       tokens_out=int(usage.get("tokens_out", 0)),
                       cost_usd=float(usage.get("cost_usd", 0.0)),
                       metadata={"outcome": "done", "run_id": run_id, "job_id": job_id,
                                 "job_type": job_type, "prototype": True,
                                 "summary": {k: v for k, v in (result or {}).items()
                                             if isinstance(v, (int, float, str, bool))},
                                 **({"model": usage.get("model")} if usage.get("model") else {})})
            finish("done", result={**(result or {}), "run_id": run_id, "usage": usage})
            print(f"[worker] done {job_id}: {json.dumps(result)[:200]}")

        except Blocked as exc:
            # Terminal by design. Recorded as a COMPLETED run with outcome=blocked:
            # the governance control worked, which is not a failure.
            ctx.report(tokens_in=0, tokens_out=0, cost_usd=0.0,
                       metadata={"outcome": "blocked", "blocked_category": exc.category,
                                 "run_id": run_id, "job_id": job_id, "job_type": job_type,
                                 "prototype": True})
            finish("blocked", error=f"[{exc.category}] {exc}")
            print(f"[worker] BLOCKED {job_id}: [{exc.category}] {exc}")

        except Cancelled as exc:
            finish("cancelled", error=str(exc))
            print(f"[worker] cancelled {job_id}")
            raise  # run_failed with the cancellation reason

        except Exception as exc:  # retryable
            finish("failed", error=str(exc)[:500])
            print(f"[worker] FAILED {job_id}: {exc}")
            raise  # run_failed with the error taxonomy

    return True


def drain(max_jobs: int = 500) -> int:
    n = 0
    while n < max_jobs and not _STOP:
        try:
            if not process_one():
                break
        except Exception as exc:
            print(f"[worker] job error (recorded): {exc}")
        n += 1
    return n


def reap() -> int:
    rows = rpc("swim_reap_expired_jobs", {}) or []
    if rows:
        print(f"[worker] reaped {len(rows)} expired-lease job(s)")
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="process one job then exit")
    ap.add_argument("--drain", action="store_true", help="process jobs until the queue is empty")
    ap.add_argument("--reap", action="store_true", help="run the reaper only")
    args = ap.parse_args()

    print(f"[worker] id={WORKER_ID} lease={LEASE_SECONDS}s poll={POLL_SECONDS}s "
          f"identities={TENANT_PREFIX}.*")

    # Scrub inherited provider keys at startup. On a shared host this is what
    # stops a tenant's agent from ever seeing the platform's key. Also drop the
    # EMPTY-string vars Claude Code injects, which break the Anthropic SDK.
    removed = CRED.scrub_platform_provider_env()
    for k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"):
        if os.environ.get(k, None) is not None:
            os.environ.pop(k, None)
            removed.append(k)
    if removed:
        print(f"[worker] scrubbed inherited provider env: {', '.join(sorted(set(removed)))}")

    oversight()  # fail fast if telemetry cannot be configured

    if args.reap:
        reap()
        return 0
    if args.once:
        reap()
        process_one()
        return 0
    if args.drain:
        reap()
        n = drain()
        print(f"[worker] drained {n} job(s)")
        return 0

    idle_cycles = 0
    while not _STOP:
        try:
            if idle_cycles % 12 == 0:
                reap()
            worked = process_one()
            idle_cycles = 0 if worked else idle_cycles + 1
            if not worked:
                time.sleep(POLL_SECONDS)
        except Exception as exc:
            print(f"[worker] loop error: {exc}")
            time.sleep(min(60.0, POLL_SECONDS * 4))
    print("[worker] exited cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
