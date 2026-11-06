"""
Gmail mailbox adapter: SMTP for sending, IMAP for reconciliation and inbound.

Implements the mailbox interface that outreach-agent/send.py was written
against (`send(...)`, `find_by_attempt_id(...)`), using the account's own App
Password over TLS. No OAuth, no third-party relay.

Exactly-once, grounded in what Gmail actually offers: Gmail has no idempotency
key, so WE set the RFC 5322 Message-ID from the durable send_attempt_id before
the SMTP call. If the connection drops after the server accepted the message,
reconciliation searches the Sent folder for that Message-ID - a supported,
indexed lookup - and only then decides sent-vs-not. Nothing is ever resent on a
guess.

Recipient allow-list: the worker enforces it, not this module. This module
sends to whatever it is told; the chokepoint and the worker decide what it is
told. Keeping policy out of the transport is deliberate.

Credentials come from the environment (SWIM_SMTP_USER, SWIM_SMTP_APP_PASSWORD)
and are never logged. `[(Gmail)/Sent Mail` and INBOX are the only folders read.
"""

from __future__ import annotations

import os
import re
import email
import imaplib
import smtplib
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr, parsedate_to_datetime, parseaddr
from typing import Any, Optional

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_HOST = "imap.gmail.com"
SENT_FOLDER = '"[Gmail]/Sent Mail"'


class MailerConfigError(Exception):
    category = "validation_error"


class ProviderAmbiguous(Exception):
    """Delivery state unknown after the provider call. Reconcile, never retry blind."""
    category = "provider_ambiguous"


class ProviderRejected(Exception):
    """The provider refused the message before accepting it. Safe to retry later."""
    category = "send_error"


def message_id_for(attempt_id: str, domain: str) -> str:
    """Deterministic Message-ID from the durable attempt id."""
    return f"<swim-{attempt_id}@{domain}>"


def _decode(s: Any) -> str:
    if s is None:
        return ""
    try:
        return str(make_header(decode_header(str(s))))
    except Exception:
        return str(s)


def _text_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    continue
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                    return re.sub(r"<[^>]+>", " ", html)
                except Exception:
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")
    except Exception:
        return str(msg.get_payload())


def strip_quoted_reply(text: str) -> str:
    """Keep the reply, drop the quoted original (best effort, conservative)."""
    lines = []
    for line in (text or "").splitlines():
        if re.match(r"^\s*On .+ wrote:\s*$", line) or line.startswith("-----Original Message-----"):
            break
        if line.startswith(">"):
            continue
        lines.append(line)
    out = "\n".join(lines).strip()
    return out or (text or "").strip()


@dataclass
class GmailMailbox:
    """Sends through Gmail SMTP. Reconciles against Gmail's Sent folder. Reads
    INBOUND replies from whichever IMAP mailbox actually receives mail for the
    domain - by default the same Gmail account, but when the domain's MX points
    elsewhere (suitupswim.com's does), SWIM_IMAP_* selects that host instead.
    Nothing about the domain's own mail setup is changed by this code."""
    user: str
    app_password: str
    from_name: str = ""
    reply_to: Optional[str] = None
    # Inbound mailbox (defaults to the Gmail account itself)
    imap_host: str = IMAP_HOST
    imap_port: int = 993
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    inbox_folder: str = "INBOX"

    @classmethod
    def from_env(cls, from_name: str = "") -> "GmailMailbox":
        user = os.environ.get("SWIM_SMTP_USER", "").strip()
        pw = os.environ.get("SWIM_SMTP_APP_PASSWORD", "").strip().replace(" ", "")
        if not user or not pw:
            raise MailerConfigError(
                "SWIM_SMTP_USER and SWIM_SMTP_APP_PASSWORD are required (a Gmail App Password, "
                "not the account password)")
        imap_host = os.environ.get("SWIM_IMAP_HOST", "").strip() or IMAP_HOST
        imap_user = os.environ.get("SWIM_IMAP_USER", "").strip() or None
        imap_pw = os.environ.get("SWIM_IMAP_PASSWORD", "").strip() or None
        if imap_host != IMAP_HOST and not (imap_user and imap_pw):
            raise MailerConfigError(
                "SWIM_IMAP_HOST is set to a non-Gmail host, so SWIM_IMAP_USER and "
                "SWIM_IMAP_PASSWORD for that mailbox are required too")
        return cls(user=user, app_password=pw, from_name=from_name,
                   reply_to=os.environ.get("SWIM_REPLY_TO") or None,
                   imap_host=imap_host,
                   imap_port=int(os.environ.get("SWIM_IMAP_PORT", "993") or 993),
                   imap_user=imap_user, imap_password=imap_pw,
                   inbox_folder=os.environ.get("SWIM_IMAP_INBOX", "INBOX") or "INBOX")

    @property
    def inbound_is_gmail(self) -> bool:
        return self.imap_host == IMAP_HOST and not self.imap_user

    @property
    def domain(self) -> str:
        return self.user.split("@", 1)[-1] or "localhost"

    # -- sending -----------------------------------------------------------

    def build(self, *, to: str, subject: str, body: str, attempt_id: str,
              in_reply_to: Optional[str] = None, extra_headers: Optional[dict] = None) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = formataddr((self.from_name, self.user)) if self.from_name else self.user
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = message_id_for(attempt_id, self.domain)
        if self.reply_to:
            msg["Reply-To"] = self.reply_to
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg["X-Swim-Attempt-Id"] = attempt_id
        for k, v in (extra_headers or {}).items():
            msg[k] = v
        msg.set_content(body)
        return msg

    def send(self, *, to: str, subject: str, body: str, attempt_id: str,
             thread_id: Optional[str] = None, in_reply_to: Optional[str] = None,
             extra_headers: Optional[dict] = None) -> dict:
        msg = self.build(to=to, subject=subject, body=body, attempt_id=attempt_id,
                         in_reply_to=in_reply_to, extra_headers=extra_headers)
        mid = msg["Message-ID"]
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
                s.ehlo()
                s.starttls()
                s.ehlo()
                s.login(self.user, self.app_password)
                refused = s.send_message(msg)
        except smtplib.SMTPAuthenticationError as exc:
            raise ProviderRejected(f"SMTP authentication failed for {self.user}: use a Gmail App Password") from exc
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
            raise ProviderRejected(f"SMTP refused the message: {exc}") from exc
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPResponseException, OSError) as exc:
            # The server may or may not have accepted the DATA. Unknown -> reconcile.
            raise ProviderAmbiguous(f"connection problem after submission: {exc}") from exc
        if refused:
            raise ProviderRejected(f"recipients refused: {refused}")
        return {"provider_message_id": mid, "provider_thread_id": thread_id or mid,
                "to": to, "subject": subject, "attempt_id": attempt_id}

    # -- reconciliation -------------------------------------------------------

    def _imap(self) -> imaplib.IMAP4_SSL:
        """The SENDING account's mailbox (Gmail): used for reconciliation only."""
        conn = imaplib.IMAP4_SSL(IMAP_HOST)
        conn.login(self.user, self.app_password)
        return conn

    def _imap_inbound(self) -> imaplib.IMAP4_SSL:
        """The mailbox that RECEIVES mail for the domain (may be a different host)."""
        if self.inbound_is_gmail:
            return self._imap()
        conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        conn.login(self.imap_user or self.user, self.imap_password or self.app_password)
        return conn

    def find_by_attempt_id(self, attempt_id: str) -> Optional[dict]:
        """Was a message with this attempt's Message-ID accepted by Gmail?"""
        mid = message_id_for(attempt_id, self.domain)
        conn = self._imap()
        try:
            conn.select(SENT_FOLDER, readonly=True)
            typ, data = conn.search(None, "HEADER", "Message-ID", mid)
            if typ != "OK" or not data or not data[0]:
                return None
            return {"provider_message_id": mid, "provider_thread_id": mid, "attempt_id": attempt_id}
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    # -- inbound ------------------------------------------------------------------

    def fetch_replies(self, known_message_ids: set, *, limit: int = 50, unseen_only: bool = True) -> list:
        """Inbox messages that reply to one of OUR Message-IDs. Marks them seen.

        Returns dicts: provider_message_id, in_reply_to, references[], from_email,
        subject, body (quoted text stripped), raw_body, received_at. Mail that
        does not reference a known id is left alone (and unseen).
        """
        conn = self._imap_inbound()
        out: list = []
        try:
            conn.select(self.inbox_folder)
            typ, data = conn.search(None, "UNSEEN" if unseen_only else "ALL")
            if typ != "OK" or not data or not data[0]:
                return out
            ids = data[0].split()[-limit:]
            for num in ids:
                typ, parts = conn.fetch(num, "(BODY.PEEK[])")
                if typ != "OK" or not parts or not parts[0]:
                    continue
                raw = parts[0][1]
                msg = email.message_from_bytes(raw)
                refs = [r.strip() for r in re.split(r"\s+", msg.get("References", "")) if r.strip()]
                irt = (msg.get("In-Reply-To") or "").strip()
                candidates = set(refs + ([irt] if irt else []))
                if not (candidates & known_message_ids):
                    continue
                try:
                    received = parsedate_to_datetime(msg.get("Date")).isoformat()
                except Exception:
                    received = None
                raw_body = _text_body(msg)
                out.append({
                    "provider_message_id": (msg.get("Message-ID") or "").strip(),
                    "in_reply_to": irt,
                    "references": refs,
                    "from_email": parseaddr(msg.get("From", ""))[1],
                    "subject": _decode(msg.get("Subject")),
                    "body": strip_quoted_reply(raw_body),
                    "raw_body": raw_body,
                    "received_at": received,
                })
                conn.store(num, "+FLAGS", "\\Seen")
            return out
        finally:
            try:
                conn.logout()
            except Exception:
                pass
