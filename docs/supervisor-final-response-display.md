# UI Change: Supervisor Agent — Real-Time Streaming with Per-Agent Panels

## Summary

The chat interface has been updated to work with a **Databricks Multi-Agent Supervisor (MAS)** using real-time streaming for every agent in the pipeline — sub-agents and the supervisor itself.

Instead of hiding all content and waiting for the supervisor to finish, the UI now:

1. **Streams each sub-agent's response live** as it arrives, displayed below the agent's label.
2. **Auto-collapses the sub-agent panel** (with a chevron to re-expand) once that agent finishes.
3. **Streams the supervisor's final response live** as the main chat reply — no waiting for a batch injection at the end.
4. Handles a **supervisor preamble** (introductory text before any sub-agent is called) by showing a "Consultando al supervisor..." label with no visible text.

---

## What the User Sees

### Step 1 — Before any sub-agent is called (supervisor preamble)
```
[Assistant icon]
Pensando...
  ✓  Consultando al supervisor...
```

### Step 2 — BCP sub-agent streaming
```
[Assistant icon]
Pensando...
  ✓  Consultando al supervisor...
  ⟳  Consultando BCP Productos...
      [live streaming text from BCP sub-agent]
```

### Step 3 — BCP done, Roemmers streaming
```
[Assistant icon]
Pensando...
  ✓  Consultando al supervisor...
  ✓  Consultando BCP Productos...  ˅
  ⟳  Consultando Roemmers Products...
      [live streaming text from Roemmers sub-agent]
```

### Step 4 — All sub-agents done, supervisor streaming as main reply
```
[Assistant icon]
Finalizado
  ✓  Consultando al supervisor...
  ✓  Consultando BCP Productos...  ˅
  ✓  Consultando Roemmers Products...  ˅

[live streaming supervisor final response...]
```

### Step 5 — Complete
```
[Assistant icon]
Finalizado
  ✓  Consultando al supervisor...
  ✓  Consultando BCP Productos...  ˅   (click to expand sub-agent answer)
  ✓  Consultando Roemmers Products...  ˅

Here is the synthesized answer from the supervisor...

Fuentes
  • visa-latampass-clasica
  • seguro-vida-digital
```

---

## Files Changed

| File | Purpose |
|---|---|
| `packages/core/src/types.ts` | Added 4 new stream data types |
| `server/src/routes/chat.ts` | Real-time delta routing + agent lifecycle events |
| `client/src/components/message.tsx` | Streaming agent panels + live supervisor response |
| `app.yaml` | Set `MLFLOW_EXPERIMENT_ID` to enable feedback |

---

## How It Works — Plain English

The Databricks Responses API emits a stream of events as the supervisor processes a request. Events arrive in this order:

1. **Supervisor preamble** — short introductory text ("Voy a consultar...") before any sub-agent is called. Comes as `output_text.delta` events with no active sub-agent.
2. **`function_call` done** — the supervisor dispatches a sub-agent. Contains the raw function name.
3. **`<name>` header** — a `step=None` message containing `<name>AgentName</name>`, identifying which sub-agent will respond next.
4. **Sub-agent text deltas** — `output_text.delta` events carrying the sub-agent's response tokens.
5. **`output_item.done`** — signals the sub-agent finished.
6. Steps 2–5 repeat for each sub-agent.
7. **Supervisor final deltas** — `output_text.delta` events after all sub-agents are done. These are the supervisor's synthesized answer.

The fix works in two layers:

- **Server layer** — intercepts each `output_text.delta` and routes it to the correct stream part based on which agent is currently active. Emits lifecycle events (`data-agentStart`, `data-agentEnd`) when agents start and finish.
- **Client layer** — accumulates the per-agent and supervisor text chunks from stream parts and renders them progressively. Sub-agent panels auto-collapse when `data-agentEnd` arrives; the supervisor stream renders as the main message body.

---

## Detailed Changes

### 1. `packages/core/src/types.ts`

Four new stream data types added to `CustomUIDataTypes`:

```typescript
export type CustomUIDataTypes = {
  error: string;
  usage: LanguageModelUsage;
  traceId: string | null;
  finalText: string;          // supervisor's full text (written after stream — for DB/history)
  thinkingStatus: string;     // backwards-compat for DB-loaded old messages
  thinkingDetail: string;     // sub-agent full text (written after stream — for chevron expand)
  kaSource: string;           // KA document citation titles
  agentStart: string;         // label emitted when an agent begins (real-time)
  agentChunk: { name: string; text: string }; // live text delta per sub-agent (real-time)
  agentEnd: string;           // raw agent name emitted when sub-agent finishes (real-time)
  supervisorChunk: string;    // live supervisor final response delta (real-time)
};
```

`data-thinkingStatus` and `data-thinkingDetail` are kept for backwards compatibility with messages already stored in the database.

---

### 2. `server/src/routes/chat.ts`

#### New state variables (per request)

```typescript
const doneAgents = new Set<string>();   // which sub-agents have finished
let supervisorFinalActive = false;      // true once all sub-agents are done
let preambleStarted = false;            // true after first supervisor-preamble agentStart emitted
```

#### Buffered event writer

The `writeThinkingStatus` callback pattern was replaced with a generic `writeEvent` that handles all new part types. Events detected in `onChunk` before the writer is ready are buffered in `pendingEvents` and flushed at the start of `execute`.

```typescript
type PendingEvent =
  | { type: 'data-agentStart'; data: string }
  | { type: 'data-agentChunk'; data: { name: string; text: string } }
  | { type: 'data-agentEnd'; data: string }
  | { type: 'data-supervisorChunk'; data: string }
  | { type: 'data-thinkingStatus'; data: string };

let writeEvent: ((event: PendingEvent) => void) | null = null;
const pendingEvents: PendingEvent[] = [];
```

#### `output_text.delta` routing (new)

Added before the `output_item.done` handler in `onChunk`:

```typescript
if (raw?.type === 'response.output_text.delta') {
  const delta: string = raw?.delta ?? '';
  if (delta) {
    if (currentSubAgentName && functionCallOrder.includes(currentSubAgentName)) {
      // Delta belongs to an active sub-agent
      emit({ type: 'data-agentChunk', data: { name: currentSubAgentName, text: delta } });
    } else if (supervisorFinalActive) {
      // Delta belongs to the supervisor's final response
      emit({ type: 'data-supervisorChunk', data: delta });
    } else if (functionCallOrder.length === 0) {
      // Supervisor preamble — emit agentStart label once, swallow the text
      if (!preambleStarted) {
        preambleStarted = true;
        emit({ type: 'data-agentStart', data: 'Consultando al supervisor...' });
      }
    }
  }
}
```

#### `function_call` done handler (updated)

Now emits both `data-agentStart` (new, real-time) and `data-thinkingStatus` (kept for DB-stored messages):

```typescript
emit({ type: 'data-agentStart', data: label });
emit({ type: 'data-thinkingStatus', data: label }); // backwards-compat
```

#### `output_item.done` message handler (updated)

When a numeric-step message arrives after a `<name>` header, emits `data-agentEnd` and switches to supervisor-final mode once all sub-agents are done:

```typescript
if (currentSubAgentName && functionCallOrder.includes(currentSubAgentName)) {
  subAgentResponsesByName.set(currentSubAgentName, text);
  emit({ type: 'data-agentEnd', data: currentSubAgentName });
  doneAgents.add(currentSubAgentName);
  if (doneAgents.size === functionCallOrder.length) {
    supervisorFinalActive = true;
  }
  currentSubAgentName = null;
}
```

#### After stream ends (unchanged logic, same result)

`data-finalText` and `data-thinkingDetail` are still written after the stream for DB persistence and history reload compatibility. KA sources (`data-kaSource`) are also still written via early-started `Promise` fetches.

---

### 3. `client/src/components/message.tsx`

#### New memoized values

```typescript
// One entry per data-agentStart part (supervisor preamble + sub-agents)
const agentStartParts = ...

// Set of raw agent names that have finished (from data-agentEnd parts)
const doneAgentNames = new Set<string>()

// Accumulated text per sub-agent: Map<rawName, concatenatedText>
const agentChunksByName = new Map<string, string>()

// Accumulated supervisor final response for real-time rendering
const supervisorStreamText: string = ...
```

Backwards-compat memos kept:
- `thinkingStatusParts` — for old DB-loaded messages without `agentStart`
- `thinkingDetailParts` — for chevron expand content on both live and history

#### Updated `isProcessingIntermediateSteps`

```typescript
// Before:
const isProcessingIntermediateSteps =
  isLoading && message.role === 'assistant' && !finalTextPart;

// After:
const isProcessingIntermediateSteps =
  isLoading &&
  message.role === 'assistant' &&
  !finalTextPart &&
  supervisorStreamText.length === 0;  // ← also clear once supervisor starts streaming
```

#### Updated `partSegments`

Added a live-streaming path before the post-stream `finalTextPart` path:

```typescript
if (message.role === 'assistant' && finalTextPart) {
  // Post-stream history: render server-injected final text
  return createMessagePartSegments([{ type: 'text', text: finalTextPart.data }]);
}
if (message.role === 'assistant' && supervisorStreamText.length > 0) {
  // Live streaming: render accumulated supervisor chunks
  return createMessagePartSegments([{ type: 'text', text: supervisorStreamText }]);
}
```

#### New streaming agent panel render block

The thinking step list was replaced with a new block that handles three display states per sub-agent:

| State | Display |
|---|---|
| Agent not yet done, has live text | Spinner + label + live `<Response>` panel below |
| Agent not yet done, no text yet | Spinner + label only |
| Agent done, panel collapsed | Checkmark + label + chevron button |
| Agent done, panel expanded | Checkmark + label + chevron + `<Response>` with full text |

The supervisor preamble row (if present) is always shown as a completed checkmark with no expandable content.

A **fallback block** renders the old `thinkingStatusParts`-based UI for DB-loaded messages that pre-date the `agentStart` parts.

---

### 4. `app.yaml`

```yaml
# Before:
- name: MLFLOW_EXPERIMENT_ID
  valueFrom: experiment   # referenced a resource that no longer exists in databricks.yml

# After:
- name: MLFLOW_EXPERIMENT_ID
  value: "1530563030470510"
```

**Why:** The `experiment` DAB resource was removed from `databricks.yml` because the experiment ID it referenced didn't exist in the workspace. Without `MLFLOW_EXPERIMENT_ID`, `server/src/routes/config.ts` returns `feedback: false`, hiding the thumbs up/down buttons. Setting the value directly restores feedback.

---

## Complete Rendering Flow

```
User sends message
       │
       ▼
AwaitingResponseMessage: "Thinking..."
       │
       ▼  supervisor preamble text arrives
data-agentStart: "Consultando al supervisor..."
UI:  Pensando...
       ✓  Consultando al supervisor...
       │
       ▼  function_call: BCP-Productos
data-agentStart: "Consultando BCP Productos..."
data-thinkingStatus: (same, for DB compat)
UI:  Pensando...
       ✓  Consultando al supervisor...
       ⟳  Consultando BCP Productos...
       │
       ▼  output_text.delta (BCP tokens)
data-agentChunk: { name: "BCP-Productos", text: "..." }  × N
UI:  Pensando...
       ✓  Consultando al supervisor...
       ⟳  Consultando BCP Productos...
           [live BCP text streaming]
       │
       ▼  output_item.done (BCP)
data-agentEnd: "BCP-Productos"
UI:  Pensando...
       ✓  Consultando al supervisor...
       ✓  Consultando BCP Productos...  ˅   ← collapsed, chevron available
       │
       ▼  function_call: roemmers-products-chat-bot
       ... (same pattern as BCP)
       │
       ▼  supervisorFinalActive = true
       ▼  output_text.delta (supervisor tokens)
data-supervisorChunk: "..." × N
isProcessingIntermediateSteps → false  (supervisorStreamText.length > 0)
UI:  Finalizado
       ✓  Consultando al supervisor...
       ✓  Consultando BCP Productos...  ˅
       ✓  Consultando Roemmers Products...  ˅

       [supervisor answer streaming live in main body]
       │
       ▼  stream ends
data-finalText: (full supervisor text, for DB)
data-thinkingDetail: (BCP full text, for chevron)
data-thinkingDetail: (Roemmers full text, for chevron)
data-kaSource: (citation titles, if SEND_SOURCES=true)
data-traceId: (for MLflow feedback)
```

---

## Backwards Compatibility

- **Simple (non-supervisor) endpoints** — unaffected. No `agentStart` parts are emitted, no supervisor chunks. The fallback `getAssistantDisplayParts` path renders the response normally.
- **DB-loaded messages (old format)** — messages saved before `agentStart` was introduced still have `thinkingStatus`/`thinkingDetail` parts. The fallback render block handles these correctly.
- **DB-loaded messages (new format)** — `agentStart` and `thinkingDetail` parts are persisted. On reload, `agentChunksByName` is empty (no live chunks) but `thinkingDetail` fills the chevron expand content.
- **Feedback** — thumbs up/down buttons appear on all assistant messages. The `feedbackSupported` check (`data-traceId !== null`) still gates actual submission to messages that have an MLflow trace.
