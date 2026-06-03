# UI Design Agent

The UI Design Agent is a specialized agent for ReformAI that transforms marketing blueprints and messaging frameworks into high-fidelity React/Next.js code.

## Standard of Excellence

This agent adheres to the ReformAI design system:
- **Typography**: Red Hat Display (Google Fonts)
- **Palette**: 
  - Teal: `#00ADB5` (Primary)
  - Dark Navy: `#0A192F` (Background)
  - Light Navy: `#112240` (Cards/Sections)
  - Accent: `#64FFDA`
- **Aesthetics**: Glassmorphism, 3D tilt effects, dark mode by default.
- **Interactivity**: Framer Motion for `whileInView` reveals, floating background elements, and smooth transitions.

## Inputs
- `marketing_blueprint`: A structured JSON or Markdown description of the landing page sections, goals, and content.
- `messaging_framework`: Positioning, headlines, and CTAs.

### Next.js & React
- **Target Version**: Next.js `15.5.14` (stable/secure). Avoid `16.x` experimental releases.
- **Client Components**: Mandatory `"use client"` for all interactive elements and `framer-motion` animations.
- **Security**: Always verify dependencies against current CVEs (e.g., CVE-2025-66478).

## Tools
- `google-genai`: Primary engine for high-fidelity code generation (using `gemini-2.0-flash-exp`).
- `openai`: Fallback engine (using `gpt-4o-mini`).

## Performance Considerations

When generating UI, the agent must:
1. Avoid unnecessary 3D transforms on many elements.
2. Use standard Framer Motion patterns for text animations (avoiding `.get()` in render).
3. Ensure images are optimized or sized correctly.
4. Favor stability over experimental Next.js/React features.
