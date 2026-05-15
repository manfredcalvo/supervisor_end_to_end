# Sura Customization — Change Log

This document describes all changes made to the `e2e-chatbot-app-next` template for the **Sura Tendencias y Riesgos** deployment.

---

## Deployment

**App name:** `sura-tendencias-riesgos`  
**Workspace:** `andreas_workspace`  
**URL:** `https://sura-tendencias-riesgos-7474647131359139.aws.databricksapps.com`  
**Serving endpoint:** `mas-2e7b4e02-endpoint` (Databricks Multi-Agent Supervisor)  
**MLflow experiment:** `1530563030470510`

---

## Changes Summary

| # | Change | Files |
|---|---|---|
| 1 | Real-time streaming UX for MAS sub-agents and supervisor final response | `types.ts`, `chat.ts`, `message.tsx` |
| 2 | Feedback (thumbs up/down) enabled via MLflow experiment ID | `app.yaml`, `config.ts` |
| 3 | Removed KA source fetching and Fuentes section | `providers-server.ts`, `chat.ts`, `types.ts`, `config.ts`, `AppConfigContext.tsx`, `message.tsx`, `app.yaml` |
| 4 | Branding — Sura logo, colors, UI copy | `client/index.html`, `client/src/index.css`, `app-sidebar.tsx`, `greeting.tsx`, `client/public/sura-logo.svg` |
| 5 | Bundle and deployment configuration | `databricks.yml`, `app.yaml` |

---

## Change 1 — Real-Time Streaming UX for Multi-Agent Supervisor

### What changed

The default template hides all intermediate content while the supervisor is processing and only shows the final response after the stream ends. This was replaced with a fully real-time experience:

- Each sub-agent's response **streams live** below its label as tokens arrive.
- When a sub-agent finishes, its panel **auto-collapses** with a chevron (▾) to re-expand.
- The **supervisor's final response streams in real-time** as the main chat reply — no waiting.
- A **supervisor preamble** (introductory text before sub-agents are called) shows as "Consultando al supervisor..." with no visible text.

### User-facing labels (Spanish)

| Label | Meaning |
|---|---|
| `Pensando...` | Supervisor is working, no sub-agent started yet |
| `Finalizado` | All agents done, final response visible |
| `Consultando al supervisor...` | Supervisor preamble before first sub-agent |
| `Consultando <AgentName>...` | Sub-agent is being queried |

### New stream data parts

| Part type | Direction | Data | When emitted |
|---|---|---|---|
| `data-agentStart` | server → client | label string | When function_call detected or supervisor preamble starts |
| `data-agentChunk` | server → client | `{ name: string, text: string }` | Each output_text.delta for an active sub-agent |
| `data-agentEnd` | server → client | raw agent name | When output_item.done fires for a sub-agent |
| `data-supervisorChunk` | server → client | text delta | Each output_text.delta after all sub-agents are done |
| `data-finalText` | server → client | full supervisor text | After stream ends (DB persistence) |
| `data-thinkingStatus` | server → client | label string | Same as agentStart (backwards compat for DB-loaded messages) |
| `data-thinkingDetail` | server → client | full sub-agent text | After stream ends (chevron expand content) |

### Files changed

**`packages/core/src/types.ts`**
- Added: `agentStart`, `agentChunk`, `agentEnd`, `supervisorChunk` to `CustomUIDataTypes`

**`server/src/routes/chat.ts`**
- Added `output_text.delta` handler in `onChunk` that routes each token to the right stream part based on which agent is active
- Added `data-agentStart` emission on function_call detection
- Added `data-agentEnd` emission when output_item.done fires for a sub-agent
- Added `supervisorFinalActive` flag — set once all sub-agents are done, routes subsequent deltas to `data-supervisorChunk`
- Added supervisor preamble detection (text before first function_call → one `data-agentStart` label, text swallowed)
- Replaced `writeThinkingStatus` callback with generic `writeEvent` that handles all new part types

**`client/src/components/message.tsx`**
- Added `agentStartParts`, `doneAgentNames`, `agentChunksByName`, `supervisorStreamText` memos
- Updated `isProcessingIntermediateSteps` to also clear when `supervisorStreamText.length > 0`
- Updated `partSegments` to render from `supervisorStreamText` during live streaming, `finalTextPart` for history
- Replaced static thinking step list with streaming agent panels:
  - Spinner + live text while streaming
  - Auto-collapse with chevron when done
  - Expand shows full sub-agent text from `data-thinkingDetail`
- Added fallback render block for old DB-loaded messages (only have `data-thinkingStatus`)

---

## Change 2 — Feedback Enabled

### What changed

Thumbs up/down feedback buttons now appear on all assistant messages. Clicking submits an MLflow assessment linked to the message's trace.

### Why it was disabled

The template gates feedback on `!!process.env.MLFLOW_EXPERIMENT_ID`. The original `app.yaml` used `valueFrom: experiment`, but the `experiment` DAB resource was removed from `databricks.yml` (its ID didn't exist in the workspace), so the env var was always empty.

### Files changed

**`app.yaml`**
- Changed `MLFLOW_EXPERIMENT_ID` from `valueFrom: experiment` to `value: "1530563030470510"`

---

## Change 3 — KA Source Fetching Removed

### What was removed

The template originally re-queried KA (Knowledge Asset) endpoints directly to extract `url_citation` annotation titles and display them as a "Fuentes" (Sources) section below the final response. This was removed entirely.

**Reason:** The Fuentes section surfaced internal document file names (e.g. `visa-latampass-clasica.md`) and added extra API calls with no user value. Sub-agent responses already contain the relevant content inline.

### Files changed

**`packages/ai-sdk-providers/src/providers-server.ts`**
- Removed: `fetchKaSourceTitles`, `fetchCitationsFromKa`, `getKaEndpointList`
- Removed: `kaEndpointByFunctionName` and `kaEndpointListCache` module-level caches

**`server/src/routes/chat.ts`**
- Removed: `fetchKaSourceTitles` import
- Removed: `kaCalls`, `kaSourceFetches` Maps
- Removed: `kaQuery` parsing inside function_call handler
- Removed: `Promise.allSettled` block that wrote `data-kaSource` parts

**`packages/core/src/types.ts`**
- Removed: `kaSource: string` from `CustomUIDataTypes`

**`server/src/routes/config.ts`**
- Removed: `sendSources` feature flag

**`client/src/contexts/AppConfigContext.tsx`**
- Removed: `sendSources` from `ConfigResponse`
- Removed: `sendSourcesEnabled` from `AppConfigContextType` and provider value

**`client/src/components/message.tsx`**
- Removed: `sourceParts` memo
- Removed: Fuentes render section
- Removed: `useAppConfig` import (no longer used in this file)

**`app.yaml`**
- Removed: `SEND_SOURCES` env var

---

## Change 4 — Branding

### Files changed

| File | Change |
|---|---|
| `client/public/sura-logo.svg` | Added Sura logo asset |
| `client/index.html` | Updated page title and favicon reference |
| `client/src/index.css` | Sura brand colors and theme overrides |
| `client/src/components/app-sidebar.tsx` | Sura logo in sidebar header |
| `client/src/components/greeting.tsx` | Updated welcome message copy |

---

## Change 5 — Bundle and Deployment Configuration

### Files changed

**`databricks.yml`**
- Bundle name: `sura-tendencias-riesgos`
- App name: `sura-tendencias-riesgos`
- Serving endpoint default: `mas-2e7b4e02-endpoint`
- Removed: Lakebase database resource (workspace at instance limit)
- Removed: MLflow experiment resource (ID didn't exist in workspace)

**`app.yaml`**
- Added: `PGHOST`, `PGDATABASE`, `PGPORT`, `PGUSER`, `PGSSLMODE` for Lakebase connection
- Added: `MLFLOW_EXPERIMENT_ID: "1530563030470510"`
- Removed: `SEND_SOURCES` env var

---

## Additional Documentation

Full technical detail on the streaming UX implementation:
[`docs/supervisor-final-response-display.md`](docs/supervisor-final-response-display.md)
