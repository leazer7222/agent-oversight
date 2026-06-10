# Jira Sprint Reporting Agent - Standing Lessons

Per-agent rules learned building this capability. Read before working on it.

## Jira data
- Query sprint membership by **sprint ID** (`sprint = 540`), NOT name (`sprint = "Sprint 1"`) -
  the name matches identically-named sprints on other boards and over-returns.
- **Exclude sub-tasks** from work-item counts (`issuetype != Sub-task`).
- The team does **not** use story points (`customfield_10016` empty). Report counts, not points.
- T-Shirt Size = `customfield_10225` (select: XS, S, M, L, XL, XXL, Spike). Set via
  `editJiraIssue` with `{value: "M"}`.
- Sprint field = `customfield_10020`. It only accepts a **single** sprint id on edit
  ("The Sprint id must be a number") - you CANNOT remove an issue from sprints via field edit.
  Removing from a sprint needs the Agile board API, which this integration does not expose.
  Handle wrongly-tagged items by **report-level exclusion**, not Jira edits.
- Large JQL results exceed the tool token cap and save to a file; parse with PowerShell
  (`ConvertFrom-Json`). `jq` is not installed on this machine.

## Confluence
- **Whiteboards are not API-readable** (404). The retro MUST be a structured page.
- Cell background colors (`data-highlight-colour`) are **stripped** by the HTML->ADF converter.
  Brand color on pages comes from status lozenges + panels only; true colored tables live in the PDF.
- **Drafts are invisible to the API** - a page must be Published before the agent can read edits
  (critical for the Set-Size write-back: the human must publish before the agent applies).

## Reporting design
- **Goal-aware health overrides raw completion.** Goal met = GREEN even at low %.
- Business Design (`RAI-629`) is its own initiative group, separate from Product.
- Carryover = item in both the closed and the next sprint (`sprint in (A) AND sprint in (B)`).

## Branding
- Use the bundled `logo_en.png` from the `reformai-design-system` skill (no SVG exists in source).
  Two teals: `#00ADB5` primary, `#3B8AA2` system. Semantic palette: success `#27AE60`,
  info `#2D9CDB`, accent `#F5A623`, warning `#F2C94C`, danger `#EB5757`. Old QA chart hexes are stale.

## Email / comms
- No em dashes in outbound copy (reads as AI). Use periods, commas, colons.
