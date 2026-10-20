# GCP Projects Reference

Detailed reference for every active project in the **reform-ai.com** GCP organization
(org id `219572162439`). GCP has no long-text description field on projects, so this
doc is the canonical prose reference; short structured metadata lives in project
**labels** (schema at the bottom).

Last reconciled: 2026-07-09 (after the 43 -> 6 project cleanup).

---

## Billing accounts

| Account ID | Name | Type | Notes |
|---|---|---|---|
| `019511-AE87A3-E7FF52` | ReformAI - Google Credits | Credits | **Hard cap: 5 projects.** All real ReformAI work runs here. |
| `01243E-6218B2-15673F` | My Billing Account | Real money | Holds only the idle gamma project (~$0). |
| `0181C9-620E9F-EF9AE4` | Mi cuenta de facturacion | Closed | Empty. |

---

## Active projects

### ReformAI Core - ML Backend
- **Project ID:** `reformai-core` (number `646800391584`)
- **Billing:** Credits `019511` | **Owner:** charles | **Env:** production
- **What it is:** The ML / asset-discovery backend and the platform workhorse. Heaviest-spending project (GKE cluster + Cloud SQL + Redis run 24/7).
- **Key resources:**
  - Cloud Run: `asset-discovery-web`, `asset-discovery-workers`, `reform-ai`, `reform-ai-image-visualization-service`, `reform-ai-vis`, `reformai-main`, `reformai-qa`
  - GKE (Kubernetes) cluster, Cloud SQL (Postgres), Redis / Memorystore, Cloud KMS
  - Cloud Translate, YouTube Data API, Maps/Geocoding/Places backends, Pub/Sub, Secret Manager, Artifact Registry

### ReformAI Product App
- **Project ID:** `reform-ai-32653` (number `206424009988`)
- **Billing:** Credits `019511` (moved from paid 2026-07-09) | **Owner:** charles | **Env:** production
- **What it is:** The customer-facing product application - UI and home surfaces, prod + QA, plus Firebase-backed notifications.
- **Key resources:**
  - Cloud Run: `reform-ai-ui-prod`, `reform-ai-ui-qa`, `reformai-home-prod`, `reformai-home-qa`, `slackalerterprod`, `slackalerterqa`, `cleanupoldnotifications`, `onnotificationcreate`
  - Firebase: Hosting, Firestore, Functions, Identity Toolkit (auth), FCM, Remote Config, App Distribution
  - Maps / Geocoding / Places backends

### ReformAI Stitch Design MCP
- **Project ID:** `reformai-stitch` (number `1060125879836`)
- **Billing:** Credits `019511` (moved from paid 2026-07-09) | **Owner:** charles | **Env:** shared
- **What it is:** Backing project for the Google **Stitch** design-generation MCP (AI UI/screen generation). No hosted resources - it exists to give Stitch API calls a project for quota/billing.
- **APIs:** `stitch`, `drive`, `bigquery`
- **Auth / config:**
  - ADC file: `C:\Users\cjlea\.stitch-mcp\config\application_default_credentials.json` (must contain `quota_project_id = reformai-stitch`)
  - All Stitch API calls send header `X-Goog-User-Project: reformai-stitch`
  - Screens generated via JSON-RPC to `https://stitch.googleapis.com/mcp`

### ReformAI Catalog Agent SA
- **Project ID:** `reformai-agent` (number `830962254743`)
- **Billing:** Credits `019511` | **Owner:** charles | **Env:** shared
- **What it is:** Holds the headless **service account** used for Google API access (no OAuth browser flow) by the catalog and context agents. No hosted resources.
- **Service account:** `reformai-catalog-agent@reformai-agent.iam.gserviceaccount.com`
  - Key file: `C:\Users\cjlea\Key\reformai-agent-dd4d7e12c73f.json`
  - Env var: `GOOGLE_SERVICE_ACCOUNT_KEY` = path to key file
- **APIs:** `drive`, `bigquery`
- **Usage note:** To grant the agents access to a Drive folder, **share the folder with the SA email** above.

### ReformAI Gemini API Key
- **Project ID:** `gen-lang-client-0130839180` (number `5445682869`)
- **Billing:** none | **Owner:** charles | **Env:** shared
- **What it is:** Auto-created by Google AI Studio; holds a **live Gemini API key** (`generativelanguage` API enabled). No hosted resources.
- **Caution:** Deleting this project **invalidates the bound Gemini API key** - check nothing depends on it first.

### Gamma to Drive - gerencia
- **Project ID:** `gamma-to-drive-automation` (number `576442703719`)
- **Billing:** Paid `01243E` (~$0) | **Owner:** `gerencia@reform-ai.com` (charles added as owner 2026-07-09 for visibility) | **Env:** automation
- **What it is:** OAuth/API backing project for a **Gamma -> Google Drive** automation that runs **outside GCP** (Make/Zapier/Apps Script or similar). Only the Drive API is enabled - no service accounts, no keys, no compute.
- **Notes:** Not charles's project. Parked on the paid account (costs ~$0) to keep a credits slot free. **Confirm with gerencia what this automation does before ever deleting it.**

---

## Apps Script shadow projects (`sys-*`)

Google Apps Script auto-creates one hidden `sys-<number>` GCP project per script. As of
2026-07-09 all 23 were deleted (17 blank experiments + 6 simple named scripts). If a live
script runs again, Apps Script auto-provisions a fresh default project. To remove a script
permanently, delete the **script file** in Google Drive / script.google.com - not the GCP
project (which only removes the cloud backing, leaving the file).

---

## Label schema

Every active project carries these labels (values are lowercase, dashes only, <=63 chars):

| Label | Meaning | Values in use |
|---|---|---|
| `purpose` | Short slug of what the project does | e.g. `ml-asset-discovery-backend`, `product-app-ui`, `stitch-design-mcp` |
| `env` | Environment / role | `production`, `shared`, `automation` |
| `owner` | Human owner | `charles`, `gerencia` |
| `component` | Architectural role | `backend`, `frontend`, `tooling`, `agent`, `api-key`, `integration` |
| `team` | Owning team | `reformai` |

Query examples:
```
gcloud projects list --filter="labels.env=production"
gcloud projects list --filter="labels.owner=charles"
gcloud projects list --format="table(projectId,name,labels.purpose,labels.env)"
```
