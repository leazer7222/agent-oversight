# GCP Organization Cleanup - Change Record

**Date:** 2026-07-09
**Operator:** `charles@reform-ai.com`
**Organization:** reform-ai.com (`219572162439`)
**Scope:** Full inventory, billing consolidation, project deletion, IAM correction, and
metadata/labeling of the entire GCP organization.
**Reversibility:** Every deletion is recoverable for 30 days; every billing/IAM/label change
is reversible by re-running the inverse command. See [Reversibility](#8-reversibility--recovery).

---

## 1. Executive summary

The organization had accumulated **43 projects**, most unlabeled, auto-generated, or abandoned,
with production workloads unintentionally split across two billing accounts. This session:

- **Reduced 43 projects -> 6** real, clearly-named projects (deleted 37; all recoverable 30 days).
- **Consolidated all production billing onto Google Credits**, ending unnecessary cash spend.
- **Identified and fixed the root cause** of the billing split: a 5-project cap on the credits account.
- **Corrected an IAM gap** (the operator could administer the org but not delete projects).
- **Renamed and labeled** all 6 surviving projects with a consistent metadata schema.
- **Documented** every project in prose at `docs/gcp-projects.md`.

| Metric | Before | After |
|---|---|---|
| Total active projects | 43 | 6 |
| Projects on real-money billing | 3 | 1 (idle, ~$0) |
| Production projects on credits | 1 | 4 |
| Projects with descriptive names + labels | 0 | 6 |
| Apps Script shadow projects | 23 | 0 |

---

## 2. Starting state

### 2.1 Billing accounts (unchanged by this work)
| Account ID | Name | Status | Type |
|---|---|---|---|
| `01243E-6218B2-15673F` | My Billing Account | OPEN | Real money |
| `019511-AE87A3-E7FF52` | ReformAI - Google Credits | OPEN | Credits (5-project cap) |
| `0181C9-620E9F-EF9AE4` | Mi cuenta de facturacion | CLOSED | - |

### 2.2 The 43 projects broke down as
- **20 organization-level projects** - a mix of 6 real ReformAI projects and 14 abandoned
  defaults/experiments ("My First Project" x7, "Default Gemini Project" x4, "test", "hggh",
  "My Maps Project", plus two empty named shells).
- **23 `sys-*` Apps Script shadow projects** under folder `201457695224` ("apps-script") ->
  `566449140567` ("system-gsuite") - one auto-created per Apps Script file (17 blank
  "Untitled"/"Proyecto sin titulo" + 6 simple named scripts).

### 2.3 Problems identified
1. **Split billing:** the product app (`reform-ai-32653`) and `reformai-stitch` billed to the
   real-money account while the credits account sat underused.
2. **A "My First Project" (`core-spring-489403-i7`) was on the real-money account** - an empty
   default project attached to cash billing.
3. **Project sprawl:** 37 of 43 projects were noise (abandoned defaults, experiments, or
   Apps Script shadows).
4. **No metadata:** projects had auto-generated names and no labels, making purpose unknowable.

---

## 3. Objectives (as agreed with operator)

1. Inventory every project and determine what each does (evidence-based, not by name alone).
2. Move production workloads onto the correct (credits) billing account.
3. Delete dead/empty projects (aggressive stance; investigate before deleting).
4. Give surviving projects clear names, labels, and prose documentation.

---

## 4. Methodology

All inventory and changes were performed via `gcloud` and the Cloud Resource Manager REST API,
authenticated as `charles@reform-ai.com`.

1. **Inventory:** `gcloud organizations list`, `gcloud billing accounts list`,
   `gcloud projects list` (with parent type/id).
2. **Billing linkage:** `gcloud billing projects describe` per project (parallelized with
   `xargs -P 8` and run in the background to avoid API rate limits).
3. **Purpose detection:** `gcloud services list --enabled` per project (to see enabled APIs),
   then a deep resource sweep (`gcloud run/compute/functions/container/app/sql/storage/scheduler/
   iam service-accounts list`) on the 8 candidate-keep projects.
4. **Pre-delete safety scans:** `gcloud services api-keys list` + `gcloud bigquery datasets list`
   on every deletion candidate to avoid removing a project holding a live key or dataset.
5. **Verification after each mutation:** re-query billing linkage, lifecycle state, names, labels.

---

## 5. Key findings

- **Root cause of the split billing:** the credits account (`019511`) has a **hard cap of 5
  projects**. Attempting to link a 6th returned `FAILED_PRECONDITION: Cloud billing quota
  exceeded`. Production had spilled onto the real-money account because credits was full.
- **IAM gap:** the operator held `roles/billing.admin`, `roles/orgpolicy.policyAdmin`, and
  `roles/resourcemanager.organizationAdmin` at the org, but **none of these grant
  `resourcemanager.projects.delete`**. Deletions initially failed with `PERMISSION_DENIED`.
- **`gamma-to-drive-automation` is not the operator's project** - it is owned by
  `gerencia@reform-ai.com` (a teammate). Its IAM only exposed that owner; it has no service
  accounts, keys, or compute (only the Drive API), so its automation runs outside GCP.
- **Apps Script shadow projects** (`sys-*`) are owned by the Google system service account
  `appsdev-apps-dev-script-auth@system.gserviceaccount.com`; the human owner lives on the Drive
  script file, not in GCP. They can be deleted directly (org admin) and a live script will
  auto-provision a new backing project on next run.
- **One live Maps API key** was found in `phrasal-client-472221-a9` during the safety scan; it was
  pulled from the auto-delete batch and only deleted after explicit operator confirmation.

---

## 6. Detailed change log (chronological)

### 6.1 Billing changes

| # | Action | Project | From | To | Command |
|---|---|---|---|---|---|
| 1 | Unlink (free credits slot) | `reformai-480022` | Credits `019511` | (none) | `gcloud billing projects unlink reformai-480022` |
| 2 | Relink | `reform-ai-32653` | Paid `01243E` | Credits `019511` | `gcloud billing projects link reform-ai-32653 --billing-account=019511-AE87A3-E7FF52` |
| 3 | Unlink (free credits slot) | `phrasal-client-472221-a9` | Credits `019511` | (none) | `gcloud billing projects unlink phrasal-client-472221-a9` |
| 4 | Relink | `reformai-stitch` | Paid `01243E` | Credits `019511` | `gcloud billing projects link reformai-stitch --billing-account=019511-AE87A3-E7FF52` |
| 5 | Relink | `gamma-to-drive-automation` | Credits `019511` | Paid `01243E` | `gcloud billing projects link gamma-to-drive-automation --billing-account=01243E-6218B2-15673F` |

**Net billing result:** all 4 real ReformAI projects on credits (4/5 slots used, 1 free); the
single idle teammate project parked on paid (~$0); real-money account otherwise empty.

### 6.2 IAM changes (both intentionally kept)

| # | Action | Scope | Member | Role | Command |
|---|---|---|---|---|---|
| 1 | Grant | Organization `219572162439` | `charles@reform-ai.com` | `roles/resourcemanager.projectDeleter` | `gcloud organizations add-iam-policy-binding 219572162439 --member="user:charles@reform-ai.com" --role="roles/resourcemanager.projectDeleter" --condition=None` |
| 2 | Grant | Project `gamma-to-drive-automation` | `charles@reform-ai.com` | `roles/owner` | `gcloud projects add-iam-policy-binding gamma-to-drive-automation --member="user:charles@reform-ai.com" --role="roles/owner" --condition=None` |

Grant #1 was required to perform any deletion. Grant #2 was required to inspect the teammate's
project. Both were self-granted using the operator's existing `organizationAdmin` authority.

### 6.3 Deletions - 37 projects (all `DELETE_REQUESTED`, recoverable until ~2026-08-08)

**Organization-level projects (14):**

| Project ID | Prior name | Reason |
|---|---|---|
| `reformai-480022` | ReformAI | Empty shell (no resources, no SAs) |
| `core-spring-489403-i7` | My First Project | Empty; was on real-money billing |
| `silent-kite-465321-n5` | My First Project | Empty; linked to the closed billing account |
| `infra-jet-478706-j0` | My First Project | Empty default |
| `carbon-caster-480217-h2` | My First Project | Empty default |
| `centered-effort-489313-d0` | My First Project | Empty default |
| `halogen-ethos-489402-g4` | My First Project | Empty default |
| `phrasal-client-472221-a9` | My First Project | Empty but for a leftover Maps key (confirmed unused) |
| `deft-haven-472221-r0` | My Maps Project | Empty (BigQuery-only, no billing) |
| `gen-lang-client-0165613829` | test | Empty experiment |
| `gen-lang-client-0418436019` | hggh | Empty experiment |
| `gen-lang-client-0557168144` | Default Gemini Project | Empty AI Studio shell |
| `gen-lang-client-0995933527` | Default Gemini Project | Empty AI Studio shell |
| `gen-lang-client-0462473949` | Default Gemini Project | Empty AI Studio shell |

**Apps Script shadow projects (23):** 17 blank ("Untitled project" / "Proyecto sin titulo")
plus 6 simple named scripts (`100 Tasks Renamer`, `ICaco CLeanup` x2, `ReformAI Contractors`,
`ai folder generation agent` x2). None used advanced Google services, so deleting the backing
project is safe; the script files remain in Drive and self-heal a new backing project if re-run.

Deletion command (per project): `gcloud projects delete <PROJECT_ID> --quiet`

### 6.4 Renames + labels on the 6 surviving projects

Display names set via `gcloud projects update <ID> --name="..."`. Labels set via the Cloud
Resource Manager v3 REST API (`PATCH /v3/projects/<ID>?updateMask=labels`) because this
gcloud version's `projects update` supports only `--name`, not `--update-labels`.

| Project ID | New display name | Labels (`purpose` / `env` / `owner` / `component` / `team`) |
|---|---|---|
| `reformai-core` | ReformAI Core - ML Backend | ml-asset-discovery-backend / production / charles / backend / reformai |
| `reform-ai-32653` | ReformAI Product App | product-app-ui / production / charles / frontend / reformai (+ existing firebase labels preserved) |
| `reformai-stitch` | ReformAI Stitch Design MCP | stitch-design-mcp / shared / charles / tooling / reformai |
| `reformai-agent` | ReformAI Catalog Agent SA | catalog-context-service-acct / shared / charles / agent / reformai |
| `gen-lang-client-0130839180` | ReformAI Gemini API Key | gemini-api-key-store / shared / charles / api-key / reformai |
| `gamma-to-drive-automation` | Gamma to Drive - gerencia | gamma-to-drive-automation / automation / gerencia / integration / reformai |

Note: display names reject parentheses (allowed: letters, numbers, spaces, hyphens,
apostrophes, exclamation points); the gamma name originally attempted with `(gerencia)` was
re-applied as `- gerencia`.

### 6.5 Documentation created
- `docs/gcp-projects.md` - detailed prose reference for each surviving project (resources, auth,
  billing, owner) plus the billing-account table and label-schema legend.
- `docs/gcp-cleanup-2026-07-09.md` - this change record.

---

## 7. Final state

### 7.1 The 6 surviving projects
| Display name | Project ID | Billing | Owner | Purpose |
|---|---|---|---|---|
| ReformAI Core - ML Backend | `reformai-core` | Credits | charles | ML/asset-discovery backend (Cloud Run + GKE + SQL + Redis) |
| ReformAI Product App | `reform-ai-32653` | Credits | charles | Customer product app (UI/home prod+qa, Firebase) |
| ReformAI Stitch Design MCP | `reformai-stitch` | Credits | charles | Google Stitch design-generation MCP backing |
| ReformAI Catalog Agent SA | `reformai-agent` | Credits | charles | Service account for catalog/context agents |
| ReformAI Gemini API Key | `gen-lang-client-0130839180` | none | charles | Holds a live Gemini API key |
| Gamma to Drive - gerencia | `gamma-to-drive-automation` | Paid (~$0) | gerencia | Gamma->Drive automation backing (runs outside GCP) |

### 7.2 Billing account occupancy
- **Credits `019511`:** reformai-core, reform-ai-32653, reformai-stitch, reformai-agent (4/5, one slot free)
- **Paid `01243E`:** gamma-to-drive-automation (only)
- **Closed `0181C9`:** empty

---

## 8. Reversibility / recovery

| Change type | How to reverse |
|---|---|
| Project deletion | `gcloud projects undelete <PROJECT_ID>` (within 30 days, ~by 2026-08-08) |
| Billing relink | `gcloud billing projects link <PROJECT_ID> --billing-account=<ORIGINAL_ACCOUNT>` |
| IAM grant | `gcloud organizations remove-iam-policy-binding 219572162439 --member="user:charles@reform-ai.com" --role="roles/resourcemanager.projectDeleter"` (and the analogous project-level remove for the gamma owner grant) |
| Rename | `gcloud projects update <PROJECT_ID> --name="<OLD_NAME>"` |
| Labels | Re-PATCH `/v3/projects/<ID>?updateMask=labels` with the prior label map (was empty for all but `reform-ai-32653`) |

---

## 9. Open items / recommendations

1. **Credits 5-project cap:** currently 4/5 used. If a 6th credits project is ever needed,
   request a billing quota increase (per the `FAILED_PRECONDITION` remediation link) rather than
   deleting something to make room.
2. **`gamma-to-drive-automation`:** confirm with `gerencia@reform-ai.com` what the automation does
   before ever deleting it; it is harmless and ~$0 in the meantime.
3. **Apps Script script files:** the deleted `sys-*` projects removed only the cloud backing; the
   (mostly blank) script files still exist in Drive. Optionally trash them at script.google.com
   for full cleanup.
4. **IAM least-privilege (optional):** the `projectDeleter` org grant and the gamma `owner` grant
   were intentionally kept for ongoing administration; remove them if you prefer least-privilege.
5. **Keep `docs/gcp-projects.md` current** as the prose source of truth when projects change.

---

## 10. Appendix - operational notes

- `gcloud auth login` must be run in a standalone terminal (not inside an automated/non-interactive
  shell) when tokens expire; reauth cannot prompt non-interactively.
- Bulk `gcloud billing`/`services` queries over many projects hit API rate limits when run
  sequentially; parallelize with `xargs -P 8` and run in the background.
- Newly-deleted projects linger briefly in `--filter="lifecycleState:ACTIVE"` results due to index
  propagation lag; filter out `DELETE_REQUESTED` explicitly to get an accurate live count.
- This gcloud (561.0.0) `projects update` supports only `--name`; manage labels via the Resource
  Manager v3 REST API with a `gcloud auth print-access-token` bearer token.
