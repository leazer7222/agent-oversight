"""
Outbound email with durable send state and exactly-once reconciliation.

Why this is more than an INSERT with a unique index:

A unique constraint stops a SECOND send from being RECORDED. It does nothing
about the case that actually bites - the provider accepted the message and the
connection dropped before the response arrived. The row still says 'approved' or
'sending', a naive retry sends a second copy to a real business, and the unique
index never fires because the first send produced no row.

The protocol here closes that:

  1. Generate send_attempt_id and persist status='sending' with that id BEFORE
     calling the provider. The intent to send is durable before the attempt.
  2. Call the provider, passing send_attempt_id as an idempotency header and
     embedding it in a message header so it is recoverable from the mailbox.
  3. On success, record provider_message_id and status='sent'.
  4. On ANY failure or ambiguity, leave status='sending' and DO NOT retry
     blindly. reconcile() later asks the provider whether a message bearing that
     send_attempt_id exists, and only then decides sent-vs-never-sent.

The approval gate is enforced here too: send() verifies an approval row whose
approved_sha256 equals the hash of the exact body being sent. Editing an
approved draft invalidates the approval, and no prompt can forge one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from safety import body_sha256  # same package directory


class SendError(Exception):
    category = "send_error"


class NotApproved(SendError):
    category = "not_approved"


class Suppressed(SendError):
    category = "suppressed"


class RateLimited(SendError):
    category = "rate_limited"


class ProviderAmbiguous(SendError):
    """The provider call failed in a way that leaves delivery UNKNOWN. Must be
    resolved by reconciliation, never by a blind retry."""
    category = "provider_ambiguous"


@dataclass
class SendResult:
    status: str                  # sent | pending_reconciliation | blocked
    message_id: Optional[str] = None
    provider_message_id: Optional[str] = None
    send_attempt_id: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class MockMailbox:
    """In-memory provider for development and tests.

    fail_mode drives the failure injection the tests need:
      'none'            - normal delivery
      'ambiguous'       - message IS delivered, then the call raises (the nasty one)
      'hard'            - message is NOT delivered and the call raises
    """
    sent: list = field(default_factory=list)
    fail_mode: str = "none"

    def send(self, *, to: str, subject: str, body: str, attempt_id: str,
             thread_id: Optional[str] = None) -> dict:
        if self.fail_mode == "hard":
            raise ProviderAmbiguous("connection reset before the provider accepted")
        record = {
            "provider_message_id": f"mock-msg-{len(self.sent) + 1}",
            "provider_thread_id": thread_id or f"mock-thread-{len(self.sent) + 1}",
            "to": to, "subject": subject, "body": body, "attempt_id": attempt_id,
        }
        self.sent.append(record)
        if self.fail_mode == "ambiguous":
            raise ProviderAmbiguous(
                "provider accepted the message but the response was lost")
        return record

    def find_by_attempt_id(self, attempt_id: str) -> Optional[dict]:
        """Reconciliation hook. A real Gmail implementation searches the mailbox
        for the custom header carrying this id."""
        for rec in self.sent:
            if rec["attempt_id"] == attempt_id:
                return rec
        return None


@dataclass
class SendStore:
    """Abstracts the swim_sourcing.outreach_messages rows the worker would write.
    In production these are RPC calls; in tests it is a dict, so the protocol can
    be verified without a database."""
    messages: dict = field(default_factory=dict)
    approvals: dict = field(default_factory=dict)
    suppressed: set = field(default_factory=set)
    sent_today: int = 0

    def get_message(self, message_id: str) -> dict:
        return self.messages[message_id]

    def approval_for(self, message_id: str) -> Optional[dict]:
        return self.approvals.get(message_id)

    def mark_sending(self, message_id: str, attempt_id: str) -> None:
        self.messages[message_id].update(status="sending", send_attempt_id=attempt_id)

    def mark_sent(self, message_id: str, provider_message_id: str,
                  provider_thread_id: Optional[str]) -> None:
        self.messages[message_id].update(
            status="sent", provider_message_id=provider_message_id,
            provider_thread_id=provider_thread_id)
        self.sent_today += 1

    def mark_failed(self, message_id: str, error: str) -> None:
        self.messages[message_id].update(status="failed", error=error)


def send(
    message_id: str,
    *,
    store: SendStore,
    mailbox: Any,
    recipient: str,
    daily_cap: int = 25,
) -> SendResult:
    """Send one approved message. Enforces, in order:
    suppression -> daily cap -> already-sent -> approval-hash -> durable attempt.
    """
    msg = store.get_message(message_id)

    if recipient.lower() in {s.lower() for s in store.suppressed}:
        return SendResult(status="blocked", reason="recipient is on the suppression list")

    if store.sent_today >= daily_cap:
        return SendResult(status="blocked", reason=f"daily send cap of {daily_cap} reached")

    if msg.get("status") == "sent":
        # Idempotent at the API level: asking twice does not send twice.
        return SendResult(status="sent", message_id=message_id,
                          provider_message_id=msg.get("provider_message_id"),
                          reason="already sent")

    if msg.get("status") == "sending" and msg.get("send_attempt_id"):
        return SendResult(status="pending_reconciliation",
                          message_id=message_id,
                          send_attempt_id=msg["send_attempt_id"],
                          reason="a previous attempt is unresolved - reconcile first")

    approval = store.approval_for(message_id)
    if not approval or approval.get("decision") != "approved":
        raise NotApproved(
            f"message {message_id} has no approval from an authenticated user")

    current_hash = body_sha256(msg["body"])
    if approval.get("approved_sha256") != current_hash:
        raise NotApproved(
            "the message body changed after it was approved - the approval is void. "
            "Re-approve the current text before sending.")

    attempt_id = str(uuid.uuid4())
    store.mark_sending(message_id, attempt_id)   # durable BEFORE the provider call

    try:
        rec = mailbox.send(
            to=recipient, subject=msg.get("subject") or "", body=msg["body"],
            attempt_id=attempt_id, thread_id=msg.get("provider_thread_id"))
    except ProviderAmbiguous as exc:
        # Deliberately leaves status='sending'. Delivery is UNKNOWN; only
        # reconciliation may decide, and it must never be a blind resend.
        return SendResult(status="pending_reconciliation", message_id=message_id,
                          send_attempt_id=attempt_id, reason=str(exc))

    store.mark_sent(message_id, rec["provider_message_id"], rec.get("provider_thread_id"))
    return SendResult(status="sent", message_id=message_id,
                      provider_message_id=rec["provider_message_id"],
                      send_attempt_id=attempt_id)


def reconcile(message_id: str, *, store: SendStore, mailbox: Any) -> SendResult:
    """Resolve an unresolved attempt by asking the provider what happened.

    This is the function that makes exactly-once real: it converts "we do not
    know" into a fact, rather than guessing. If the provider has the message, we
    record it as sent. If not, the message returns to 'approved' so it can be
    retried - and the original approval still binds it, so the retry sends the
    same approved bytes.
    """
    msg = store.get_message(message_id)
    attempt_id = msg.get("send_attempt_id")
    if msg.get("status") == "sent":
        return SendResult(status="sent", message_id=message_id,
                          provider_message_id=msg.get("provider_message_id"),
                          reason="already reconciled")
    if not attempt_id:
        return SendResult(status="blocked", message_id=message_id,
                          reason="nothing to reconcile")

    found = mailbox.find_by_attempt_id(attempt_id)
    if found:
        store.mark_sent(message_id, found["provider_message_id"],
                        found.get("provider_thread_id"))
        return SendResult(status="sent", message_id=message_id,
                          provider_message_id=found["provider_message_id"],
                          send_attempt_id=attempt_id,
                          reason="provider confirmed the earlier attempt was delivered")

    msg.update(status="approved", send_attempt_id=None)
    return SendResult(status="blocked", message_id=message_id,
                      reason="provider has no record - returned to approved for retry")
