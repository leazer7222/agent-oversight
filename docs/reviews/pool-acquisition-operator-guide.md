# Pool partnerships: how to run it (operator guide)

For Cameron and whoever operates the workspace at `/dashboard/sourcing`.
Plain steps, in the order the screen shows them. Written 2026-11-06 for the
supervised test phase (every email goes to the allow-listed test address, never
to a facility).

## Signing in

Go to `https://agent-oversight.vercel.app/login`. Two ways in:

- **Email and password.** The operator mailbox `partnerships@suitupswim.com`
  has a password (set by the platform admin on 2026-11-08; it is an owner of
  the Cameron Swim School company). Change it after the first sign-in if it was
  handed over in writing: the platform admin can set a new one.
- **Sign-in link.** Enter your email, press "Send sign-in link to my email",
  open the link. No password involved. Works for any address that the platform
  admin has made a member of the company.

Neither path creates an account. An address that is not a member sees a
"not a member" page after signing in.

## The one rule

Nothing is emailed unless a person did two things to that exact draft: pressed
**Approve this draft**, then pressed **Send it**. The system writes drafts,
sends what you approved, reads replies and flags what needs you. It never
decides price, schedule, insurance, exclusivity, contracts or meetings.

## The six steps (the Overview tab shows these with live status)

1. **Check what the emails say about the business.**
   Every draft is built from `agents/library/partnership-coordinator/business_profile.json`.
   Anything not in that file cannot appear in an email (a code check refuses the
   draft). Open "What the emails are allowed to say" on the Overview to read it.
   Still missing before any real send: the business mailing address (required in
   the footer of commercial email). Add it to the file, then press
   **Write or rewrite drafts**. Emails already sent are never changed.

2. **Let the researcher find and vet facilities.** Press **Run the researcher**
   (Overview step 2, or the top of the Facilities tab). It queues three steps
   in order: find facilities, read each website keeping only facts quoted from
   the page, rank them. **Re-vet known facilities** skips the find step. The
   worker does the work on its next pass. "Use recorded test facilities" stays
   ticked until a Google Places key is on the worker; unticked without a key,
   the find step is refused and nothing is written. For real facilities the
   read step opens the facility's own website (homepage plus up to three pool,
   rental or contact pages, robots.txt honoured) and keeps only facts it can
   quote from those pages; a site that cannot be read is listed in the run as
   "site unreadable" with the reason. The Facilities tab shows
   what was found about each pool, with the sentence from their website that
   backs each fact, and why it was ranked ready / needs research / not a fit /
   ruled out.

3. **Read each draft and approve it.** Conversations tab, filter
   **Needs approval**. Open one, read the email exactly as it will go out, press
   **Step 1 of 2: Approve this draft**. Approval records your name against those
   exact words; if the text changes it must be approved again.

4. **Send the approved drafts.** Filter **Approved, not sent**, open one, press
   **Step 2 of 2: Send it**. The worker sends it on its next pass. In test mode
   the email is redirected to the allow-listed test address with the intended
   recipient noted in the subject line; the facility receives nothing. At most
   8 sends a day.

5. **Check the mailbox for replies.** Replies are not read automatically. Press
   **Check mailbox for replies** on the Conversations tab after someone replies.
   The worker reads the partnerships inbox, matches each reply to its
   conversation (by the email headers, not by guessing) and classifies it.

6. **Decide on anything the system will not.** Decisions tab. Each item says
   what happened, why it is yours, and a suggested handling. Reply from the
   partnerships mailbox yourself; the system records the thread. Opt-outs are
   honoured.

## What each label means

| Label | Meaning | What to do |
|---|---|---|
| Needs your approval | A draft exists, nobody has approved it | Read it, press Approve |
| Approved - not sent yet | Approved, not yet released | Press Send it |
| Sending | Worker is sending now | Refresh in a moment |
| Sent - waiting for a reply | Delivered (confirmed in the Sent folder) | Nothing; check mailbox when they reply |
| Send failed | Provider refused it | Activity tab has the reason; press Send it again |
| They replied | A reply is recorded and classified | Read it; Decisions tab if flagged |
| Simulated | Scripted test reply from the prototype | Ignore for real decisions |
| Real reply | Came from the real mailbox | Treat as real |
| Replaced by a newer draft | An older version of a draft | Nothing; act on the newest |

## The worker: the part that actually does things

Every button on the screen only queues work. A separate program, the worker,
picks the queue up, calls the model, reads websites, sends and reads mail. If
no worker is running, buttons appear to do nothing and the jobs simply wait.

The worker runs on the operator's PC as a Windows Scheduled Task that fires
every 2 minutes (`AgentOversight-SwimSourcingWorker`). Manage it from the
repository folder:

```
powershell -ExecutionPolicy Bypass -File scripts/swim-worker-task.ps1 -Status
powershell -ExecutionPolicy Bypass -File scripts/swim-worker-task.ps1 -Install
powershell -ExecutionPolicy Bypass -File scripts/swim-worker-task.ps1 -RunNow
```

It runs only while that Windows user is logged on. Work queued while the PC is
off waits and runs on the next tick. Its log is `.claude/swim-worker.log`. For
use with the PC off, the same worker has to run on an always-on machine; that
is a deliberate later step because it means copying the secrets there.

## What the worker needs (one-time setup, done by the operator)

In `.env.local` on the machine that runs `python agents/teams/swim-sourcing/worker.py --drain`:

- `SWIM_SMTP_USER` / `SWIM_SMTP_APP_PASSWORD`: the sending mailbox
  (`partnerships@suitupswim.com`, a Google Workspace app password).
- `SWIM_SEND_ALLOWLIST`: the only addresses mail may go to. Unset = sending is
  off. During the test phase this is the operator's own address.
- `GOOGLE_PLACES_API_KEY`: a Google Cloud API key with "Places API (New)"
  enabled, for finding real facilities. Without it, only the recorded test set
  can be used. One research run makes at most 8 Places requests.
- Replies: since 2026-11-08 the domain's incoming mail (MX) points at Google, so
  replies to `partnerships@` land in the same Gmail mailbox the worker sends
  from and no extra settings are needed. `SWIM_IMAP_HOST` / `SWIM_IMAP_USER` /
  `SWIM_IMAP_PASSWORD` (and optionally `SWIM_IMAP_PORT`, `SWIM_IMAP_INBOX`) exist
  only for the case where incoming mail is hosted somewhere other than Google.
- The business's own Anthropic key. The worker never reads `ANTHROPIC_API_KEY`
  from the machine (it scrubs it on start); each company's key lives encrypted
  in the credential vault and the worker decrypts it per job. To store or
  replace Cameron's key without it ever appearing in a chat or a shell history:
  1. Add one line to `.env.local`: `NEW_ANTHROPIC_API_KEY=sk-ant-...`
  2. Run `python scripts/set_tenant_credential.py --company-slug cameron-swim-school-prototype --from-env NEW_ANTHROPIC_API_KEY --label "Suit Up - Cameron's Anthropic key"`
     It checks the key with the provider (free call), encrypts it, stores it as
     the active key and marks the old one revoked. It prints only the last four
     characters.
  3. Delete that line from `.env.local` again.
  Until this is done the vault holds the platform key (last four `XQAA`) and
  prototype usage bills to the platform, not to the business.

Database migration `056_swim_thread_campaigns.sql` must be applied before
**Write or rewrite drafts** can rewrite existing unsent drafts (until then it
only writes new ones and says so in the run).

## Before the first real send (not yet done)

- Mailing address in the business profile.
- Insurance confirmed and documented (only then may a draft mention it; today
  it cannot).
- Cameron's own Anthropic key in the vault (`scripts/set_tenant_credential.py`,
  above).
- Remove the test allow-list restriction deliberately, per facility batch, with
  the daily cap left on.

## Test record

| Date | What | Result |
|---|---|---|
| 2026-11-06 | First supervised send (old draft copy), FIXTURE Facility 012, redirected to the test address | Sent, confirmed in the Sent folder |
| 2026-11-08 | Suit Up profile draft for FIXTURE Facility 003, approved by charles@reform-ai.com, redirected to the test address | Sent, confirmed in the Sent folder; reply path now reaches Gmail (MX moved to Google) |
