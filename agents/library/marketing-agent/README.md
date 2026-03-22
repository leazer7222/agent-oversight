# Marketing Strategy Executive Agent (Elite v4)

> Senior strategic operator responsible for turning company context into clear segmentation, sharp positioning, and conversion-driven messaging.

## Owner
`reformai`

## What it does
- **Strategy & Positioning**: Synthesizes company context into elite-level strategic insights.
- **Multi-Segment Focus**: Tailors messaging for Homeowners, Service Providers, and Home Sellers.
- **UI Design Handoff**: Produces structured, design-ready landing page blueprints for the UI Design Agent.

## Tools & MCP Dependencies
| Tool/MCP | Purpose |
|---|---|
| `gdrive` | Context extraction (via Context Agent pattern) |

## Setup
1. Ensure the `context-agent` is active and configured for the target company.
2. Provide the high-level marketing goal or segment focus as input.

## Running it
Invoke via the Oversight system with a `marketing_strategy` goal. The agent will automatically query the `context-agent` for necessary background materials.

## Inputs
- **Goal**: High-level objective (e.g., "Create landing page for Homeowners").
- **Context**: Project context pulled from Google Drive materials.

## Outputs
- **Strategic Brief**: Audience, pain points, and value proposition.
- **Messaging Framework**: Positioning, benefit pillars, and headlines.
- **Landing Page Blueprint**: UI-ready section-by-section breakdown.

## Notes
- Operates on a **"No Blind Output"** principle—always pings the Context Agent first.
