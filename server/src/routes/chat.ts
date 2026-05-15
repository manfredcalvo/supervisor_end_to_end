import {
  Router,
  type Request,
  type Response,
  type Router as RouterType,
} from 'express';
import {
  convertToModelMessages,
  createUIMessageStream,
  streamText,
  generateText,
  type LanguageModelUsage,
  pipeUIMessageStreamToResponse,
  type InferUIMessageChunk,
} from 'ai';
import type { LanguageModelV3Usage } from '@ai-sdk/provider';

// Convert ai's LanguageModelUsage to @ai-sdk/provider's LanguageModelV3Usage
function toV3Usage(usage: LanguageModelUsage): LanguageModelV3Usage {
  return {
    inputTokens: {
      total: usage.inputTokens,
      noCache: undefined,
      cacheRead: undefined,
      cacheWrite: undefined,
    },
    outputTokens: {
      total: usage.outputTokens,
      text: undefined,
      reasoning: undefined,
    },
  };
}
import {
  authMiddleware,
  requireAuth,
  requireChatAccess,
  getIdFromRequest,
} from '../middleware/auth';
import {
  deleteChatById,
  getMessagesByChatId,
  saveChat,
  saveMessages,
  updateChatLastContextById,
  updateChatVisiblityById,
  isDatabaseAvailable,
  updateChatTitleById,
} from '@chat-template/db';
import {
  type ChatMessage,
  checkChatAccess,
  convertToUIMessages,
  generateUUID,
  myProvider,
  postRequestBodySchema,
  type PostRequestBody,
  StreamCache,
  type VisibilityType,
  CONTEXT_HEADER_CONVERSATION_ID,
  CONTEXT_HEADER_USER_ID,
} from '@chat-template/core';
import { ChatSDKError } from '@chat-template/core/errors';
import { storeMessageMeta } from '../lib/message-meta-store';

export const chatRouter: RouterType = Router();

const streamCache = new StreamCache();
// Apply auth middleware to all chat routes
chatRouter.use(authMiddleware);

/**
 * POST /api/chat - Send a message and get streaming response
 *
 * Note: Works in ephemeral mode when database is disabled.
 * Streaming continues normally, but no chat/message persistence occurs.
 */
chatRouter.post('/', requireAuth, async (req: Request, res: Response) => {
  const dbAvailable = isDatabaseAvailable();
  if (!dbAvailable) {
    console.log('[Chat] Running in ephemeral mode - no persistence');
  }

  let requestBody: PostRequestBody;

  try {
    requestBody = postRequestBodySchema.parse(req.body);
  } catch (_) {
    console.error('Error parsing request body:', _);
    const error = new ChatSDKError('bad_request:api');
    const response = error.toResponse();
    return res.status(response.status).json(response.json);
  }

  try {
    const {
      id,
      message,
      selectedChatModel,
      selectedVisibilityType,
    }: {
      id: string;
      message?: ChatMessage;
      selectedChatModel: string;
      selectedVisibilityType: VisibilityType;
    } = requestBody;

    const session = req.session;
    if (!session) {
      const error = new ChatSDKError('unauthorized:chat');
      const response = error.toResponse();
      return res.status(response.status).json(response.json);
    }

    const { chat, allowed, reason } = await checkChatAccess(
      id,
      session?.user.id,
    );

    if (reason !== 'not_found' && !allowed) {
      const error = new ChatSDKError('forbidden:chat');
      const response = error.toResponse();
      return res.status(response.status).json(response.json);
    }

    if (!chat) {
      // Only create new chat if we have a message (not a continuation)
      if (isDatabaseAvailable() && message) {
        await saveChat({
          id,
          userId: session.user.id,
          title: 'New chat',
          visibility: selectedVisibilityType,
        });

        generateTitleFromUserMessage({ message })
          .then((title) =>
            updateChatTitleById({
              chatId: id,
              title,
            }),
          )
          .catch((error) => {
            console.error('Error generating title:', error);
            const textFromUserMessage = message?.parts.find(
              (part) => part.type === 'text',
            )?.text;
            if (textFromUserMessage) {
              updateChatTitleById({
                chatId: id,
                title: truncatePreserveWords(textFromUserMessage, 128),
              });
            }
          });
      }
    } else {
      if (chat.userId !== session.user.id) {
        const error = new ChatSDKError('forbidden:chat');
        const response = error.toResponse();
        return res.status(response.status).json(response.json);
      }
    }

    const messagesFromDb = await getMessagesByChatId({ id });

    // Use previousMessages from request body when:
    // 1. Ephemeral mode (DB not available) - always use client-side messages
    // 2. Continuation request (no message) - tool results only exist client-side
    const useClientMessages =
      !dbAvailable || (!message && requestBody.previousMessages);
    const previousMessages = useClientMessages
      ? (requestBody.previousMessages ?? [])
      : convertToUIMessages(messagesFromDb);

    // If message is provided, add it to the list and save it
    // If not (continuation/regeneration), just use previous messages
    let uiMessages: ChatMessage[];
    if (message) {
      uiMessages = [...previousMessages, message];
      await saveMessages({
        messages: [
          {
            chatId: id,
            id: message.id,
            role: 'user',
            parts: message.parts,
            attachments: [],
            createdAt: new Date(),
            traceId: null,
          },
        ],
      });
    } else {
      // Continuation: use existing messages without adding new user message
      uiMessages = previousMessages as ChatMessage[];

      // For continuations with database enabled, save any updated assistant messages
      // This ensures tool-result parts (like MCP approval responses) are persisted
      if (dbAvailable && requestBody.previousMessages) {
        const assistantMessages = requestBody.previousMessages.filter(
          (m: ChatMessage) => m.role === 'assistant',
        );
        if (assistantMessages.length > 0) {
          await saveMessages({
            messages: assistantMessages.map((m: ChatMessage) => ({
              chatId: id,
              id: m.id,
              role: m.role,
              parts: m.parts,
              attachments: [],
              createdAt: m.metadata?.createdAt
                ? new Date(m.metadata.createdAt)
                : new Date(),
              traceId: null,
            })),
          });

          // Check if this is an MCP denial - if so, we're done (no need to call LLM)
          // Denial is indicated by a dynamic-tool part with state 'output-denied'
          // or with approval.approved === false
          const hasMcpDenial = requestBody.previousMessages?.some(
            (m: ChatMessage) =>
              m.parts?.some(
                (p) =>
                  p.type === 'dynamic-tool' &&
                  (p.state === 'output-denied' ||
                    ('approval' in p && p.approval?.approved === false)),
              ),
          );

          if (hasMcpDenial) {
            // We don't need to call the LLM because the user has denied the tool call
            res.end();
            return;
          }
        }
      }
    }

    // Clear any previous active stream for this chat
    streamCache.clearActiveStream(id);

    let finalUsage: LanguageModelUsage | undefined;
    let traceId: string | null = null;
    const streamId = generateUUID();
    const sourceMap = new Map<string, number>();

    // Track the full text of each output item by step number.
    // The Databricks Responses API emits `response.output_item.done` events
    // with a `step` field. In a multi-agent supervisor setup the pattern is:
    //   sub-agents → steps 0, 1, 2 …; supervisor → highest step (maxStep).
    // The highest step number is the supervisor's final synthesized response.
    const stepTexts: Map<number, string> = new Map();
    // Ordered list of function_call names — matches the thinkingStatus parts order.
    const functionCallOrder: string[] = [];
    // Maps sub-agent name → its response text (keyed by raw function name).
    const subAgentResponsesByName = new Map<string, string>();

    // Tracks which sub-agents have finished so we know when to switch to
    // supervisor-final streaming mode.
    const doneAgents = new Set<string>();
    // True once all sub-agents are done — subsequent output_text.delta events
    // belong to the supervisor's final synthesized response.
    let supervisorFinalActive = false;
    // Set to true after the supervisor-preamble agentStart is emitted once.
    let preambleStarted = false;

    // Callback for injecting real-time agent events directly into the
    // UI message stream. Set inside `execute` once the writer is available.
    // Before the writer is ready, events are buffered here.
    type PendingEvent =
      | { type: 'data-agentStart'; data: string }
      | { type: 'data-agentChunk'; data: { name: string; text: string } }
      | { type: 'data-agentEnd'; data: string }
      | { type: 'data-supervisorChunk'; data: string }
      | { type: 'data-thinkingStatus'; data: string }
      | { type: 'data-thinkingDetail'; data: string };
    let writeEvent: ((event: PendingEvent) => void) | null = null;
    const pendingEvents: PendingEvent[] = [];

    // MAS emits a <name>AgentName</name> header message (step=None) right after
    // each function_call and before the actual sub-agent response. Its deltas
    // carry the same tool_name as the real response deltas, so without filtering
    // the agent name leaks into the expand panel text.
    // We buffer deltas after function_call done and discard them when we see the
    // header's output_item.done (step not a number). If the response done fires
    // first (step is a number), the agent has no header — flush the buffer.
    const agentNameHeaderMode = new Set<string>();
    const agentNameHeaderBuffer = new Map<string, PendingEvent[]>();

    const model = await myProvider.languageModel(selectedChatModel);
    const result = streamText({
      model,
      messages: await convertToModelMessages(uiMessages),
      providerOptions: {
        databricks: { includeTrace: true },
      },
      includeRawChunks: true,
      headers: {
        [CONTEXT_HEADER_CONVERSATION_ID]: id,
        [CONTEXT_HEADER_USER_ID]: session.user.email ?? session.user.id,
        // Forward OBO user token to the backend/serving endpoint
        ...(req.headers['x-forwarded-access-token']
          ? { 'x-forwarded-access-token': req.headers['x-forwarded-access-token'] as string }
          : {}),
      },
      onChunk: ({ chunk }) => {
        if (chunk.type === 'raw') {
          const raw = chunk.rawValue as any;
          // Log every raw event type so we can see the full picture
          console.log('[Chat] raw event type:', raw?.type, JSON.stringify(raw).slice(0, 600));

          // Real-time text delta routing using tool_name field on delta events.
          // tool_name is set for sub-agent deltas, null/undefined for supervisor.
          if (raw?.type === 'response.output_text.delta') {
            const delta: string = raw?.delta ?? '';
            const toolName: string | undefined = raw?.tool_name ?? undefined;
            if (delta) {
              if (toolName) {
                // Sub-agent delta
                const event: PendingEvent = { type: 'data-agentChunk', data: { name: toolName, text: delta } };
                if (agentNameHeaderMode.has(toolName)) {
                  // Buffered — may be <name> header content; decided on output_item.done
                  agentNameHeaderBuffer.get(toolName)?.push(event);
                } else if (writeEvent) writeEvent(event); else pendingEvents.push(event);
              } else if (supervisorFinalActive) {
                // Supervisor final response delta
                const event: PendingEvent = { type: 'data-supervisorChunk', data: delta };
                if (writeEvent) writeEvent(event); else pendingEvents.push(event);
              } else if (functionCallOrder.length === 0 && !preambleStarted) {
                // First delta of supervisor preamble — emit label once, swallow text
                preambleStarted = true;
                const event: PendingEvent = { type: 'data-agentStart', data: 'Consultando al supervisor...' };
                if (writeEvent) writeEvent(event); else pendingEvents.push(event);
              }
              // else: intermediate supervisor text between sub-agents — swallow
            }
          }

          // Extract trace in Databricks serving endpoint output format, if present
          if (raw?.type === 'response.output_item.done') {
            const traceIdFromChunk =
              raw?.databricks_output?.trace?.info?.trace_id;
            if (typeof traceIdFromChunk === 'string') {
              traceId = traceIdFromChunk;
            }
            // Collect complete text per step for supervisor final-response injection
            const item = raw?.item;
            const step = raw?.step;
            console.log('[Chat] output_item.done:', {
              step,
              itemType: item?.type,
              tool_name: raw?.tool_name,
              traceId: traceIdFromChunk ?? null,
              contentTypes: Array.isArray(item?.content)
                ? item.content.map((c: any) => c.type)
                : item?.content,
            });
            if (item?.type === 'function_call' && typeof item?.name === 'string') {
              // Track call order so we can write thinkingDetail in the same order.
              functionCallOrder.push(item.name);
              // Start buffering deltas — the next batch may be <name> header content
              agentNameHeaderMode.add(item.name);
              agentNameHeaderBuffer.set(item.name, []);
              const label = `Consultando ${formatAgentName(item.name)}...`;
              console.log(`[Chat] function_call done: name=${item.name}, label="${label}"`);
              // Emit agentStart for this sub-agent (replaces thinkingStatus)
              const agentStartEvent: PendingEvent = { type: 'data-agentStart', data: label };
              if (writeEvent) writeEvent(agentStartEvent); else pendingEvents.push(agentStartEvent);
              // Also keep thinkingStatus for backwards-compat with DB-stored messages
              const statusEvent: PendingEvent = { type: 'data-thinkingStatus', data: label };
              if (writeEvent) writeEvent(statusEvent); else pendingEvents.push(statusEvent);
            }
            if (item?.type === 'message') {
              const content = (item?.content as Array<{ type: string; text: string; annotations?: any[] }>) ?? [];
              const text = content
                .filter((c) => c.type === 'output_text')
                .map((c) => c.text)
                .join('');
              console.log(`[Chat] step=${step} text length: ${text.length}, textSnippet: ${text.slice(0, 200)}`);
              // output_item.done carries tool_name directly on the event (same as deltas)
              const doneToolName: string | undefined = raw?.tool_name ?? undefined;
              if (typeof step === 'number' && text) {
                const cleanText = stripDatabricksUrls(text);
                stepTexts.set(step, cleanText);
                if (doneToolName) {
                  // If we were in header-buffer mode, flush the buffered real-response
                  // deltas now before emitting agentEnd (agent had no <name> header).
                  if (agentNameHeaderMode.has(doneToolName)) {
                    const buffered = agentNameHeaderBuffer.get(doneToolName) ?? [];
                    for (const evt of buffered) {
                      if (writeEvent) writeEvent(evt); else pendingEvents.push(evt);
                    }
                    agentNameHeaderMode.delete(doneToolName);
                    agentNameHeaderBuffer.delete(doneToolName);
                  }
                  if (functionCallOrder.includes(doneToolName)) {
                    subAgentResponsesByName.set(doneToolName, cleanText);
                    // Emit thinkingDetail immediately so the expand panel shows the
                    // clean output_item.done text as soon as this agent finishes.
                    const thinkingDetailEvent: PendingEvent = { type: 'data-thinkingDetail', data: cleanText };
                    if (writeEvent) writeEvent(thinkingDetailEvent); else pendingEvents.push(thinkingDetailEvent);
                    // Emit agentEnd to signal this sub-agent finished streaming
                    const agentEndEvent: PendingEvent = { type: 'data-agentEnd', data: doneToolName };
                    if (writeEvent) writeEvent(agentEndEvent); else pendingEvents.push(agentEndEvent);
                    doneAgents.add(doneToolName);
                    // If all sub-agents are done, switch to supervisor-final mode
                    if (doneAgents.size === functionCallOrder.length) {
                      supervisorFinalActive = true;
                      console.log('[Chat] All sub-agents done — supervisor final phase active');
                    }
                  }
                }
              } else if (typeof step !== 'number' && doneToolName && agentNameHeaderMode.has(doneToolName)) {
                // This is the <name> header message (step=None) — discard buffered deltas
                console.log(`[Chat] Discarding <name> header deltas for agent: ${doneToolName}`);
                agentNameHeaderMode.delete(doneToolName);
                agentNameHeaderBuffer.delete(doneToolName);
              }
            }
          }
          // Extract trace from MLflow AgentServer output format, if present
          if (!traceId && typeof raw?.trace_id === 'string') {
            traceId = raw.trace_id;
          }

          // response.completed fires last and carries the supervisor's outer trace.
          // Always overwrite any sub-agent trace captured from output_item.done so
          // that feedback is submitted against the supervisor experiment.
          if (raw?.type === 'response.completed') {
            const completedTraceId = raw?.databricks_output?.trace?.info?.trace_id;
            if (typeof completedTraceId === 'string') {
              traceId = completedTraceId;
            }
          }

          if (raw?.type === 'response.output_text.annotation.added') {
            const title = raw?.annotation?.title;
            if (typeof title === 'string') {
              sourceMap.set(title, (sourceMap.get(title) ?? 0) + 1);
            }
          }
        }
      },
      onFinish: (finishData) => {
        finalUsage = finishData.usage;
      },
    });

    /**
     * We manually create the stream to have access to the stream writer.
     * This allows us to inject custom stream parts like data-error.
     */
    const stream = createUIMessageStream({
      // Pass originalMessages so that continuation responses reuse the existing
      // assistant message ID. Without this, handleUIMessageStreamFinish generates
      // a fresh ID, causing the client to push a second assistant message instead
      // of replacing the existing one.
      originalMessages: uiMessages,
      // The DB Message.id column is typed as uuid, so we must generate UUIDs
      // rather than the AI SDK's default short-id format (e.g. "Xt8nZiQRj1fS4yiU").
      generateId: generateUUID,
      execute: async ({ writer }) => {
        // Wire up direct writer access for real-time agent events.
        // Any events buffered before the writer was ready are flushed first.
        writeEvent = (event) => {
          writer.write(event as any);
        };
        while (pendingEvents.length > 0) {
          writer.write(pendingEvents.shift()! as any);
        }

        // Manually drain the AI stream so we can append the traceId data part
        // after all model chunks are processed (traceId is captured via onChunk).
        // result.toUIMessageStream() converts TextStreamPart → UIMessageChunk:
        // - text-delta: maps TextStreamPart.text → UIMessageChunk.delta
        // - start-step/finish-step: strips extra fields
        // - finish: strips rawFinishReason/totalUsage
        // - raw: dropped (trace_id captured via onChunk above)
        const aiStream = result.toUIMessageStream<ChatMessage>();
        const reader = aiStream.getReader();
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            writer.write(value as InferUIMessageChunk<ChatMessage>);
          }
        } finally {
          reader.releaseLock();
        }
        // When the endpoint is a multi-agent supervisor (multiple output steps),
        // inject the highest-step text as `data-finalText` so the client can
        // display only the supervisor's final synthesized response.
        console.log(`[Chat] stepTexts collected: size=${stepTexts.size}, steps=[${[...stepTexts.keys()].join(',')}]`);
        console.log(`[Chat] functionCallOrder=${JSON.stringify(functionCallOrder)}, subAgentKeys=${JSON.stringify([...subAgentResponsesByName.keys()])}`);
        if (stepTexts.size > 1) {
          const maxStep = Math.max(...stepTexts.keys());
          const finalText = stepTexts.get(maxStep);
          console.log(`[Chat] Injecting data-finalText from step ${maxStep}, length=${finalText?.length}`);
          if (finalText) {
            writer.write({ type: 'data-finalText', data: finalText });
          }
        }
        // Write traceId so the client knows whether feedback is supported.
        writer.write({ type: 'data-traceId', data: traceId });
        if (sourceMap.size > 0) {
          writer.write({ type: 'data-sources', data: Object.fromEntries(sourceMap) });
        }
      },
      onFinish: async ({ responseMessage }) => {
        // Store in-memory for ephemeral mode (also useful when DB is available)
        storeMessageMeta(responseMessage.id, id, traceId);

        try {
          await saveMessages({
            messages: [
              {
                id: responseMessage.id,
                role: responseMessage.role,
                parts: responseMessage.parts,
                createdAt: new Date(),
                attachments: [],
                chatId: id,
                traceId, // Store trace ID for feedback
              },
            ],
          });
        } catch (err) {
          console.error('[onFinish] Failed to save assistant message:', err);
        }

        if (finalUsage) {
          try {
            await updateChatLastContextById({
              chatId: id,
              context: toV3Usage(finalUsage),
            });
          } catch (err) {
            console.warn('Unable to persist last usage for chat', id, err);
          }
        }

        streamCache.clearActiveStream(id);
      },
    });

    pipeUIMessageStreamToResponse({
      stream,
      response: res,
      consumeSseStream({ stream }) {
        streamCache.storeStream({
          streamId,
          chatId: id,
          stream,
        });
      },
    });
  } catch (error) {
    console.error('[Chat] Caught error in chat API:', {
      errorType: error?.constructor?.name,
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
      error,
    });

    if (error instanceof ChatSDKError) {
      const response = error.toResponse();
      return res.status(response.status).json(response.json);
    }

    const chatError = new ChatSDKError('offline:chat');
    const response = chatError.toResponse();
    return res.status(response.status).json(response.json);
  }
});

/**
 * DELETE /api/chat?id=:id - Delete a chat
 */
chatRouter.delete(
  '/:id',
  [requireAuth, requireChatAccess],
  async (req: Request, res: Response) => {
    const id = getIdFromRequest(req);
    if (!id) return;

    const deletedChat = await deleteChatById({ id });
    return res.status(200).json(deletedChat);
  },
);

/**
 * GET /api/chat/:id
 */

chatRouter.get(
  '/:id',
  [requireAuth, requireChatAccess],
  async (req: Request, res: Response) => {
    const id = getIdFromRequest(req);
    if (!id) return;

    const { chat } = await checkChatAccess(id, req.session?.user.id);

    return res.status(200).json(chat);
  },
);

/**
 * GET /api/chat/:id/stream - Resume a stream
 */
chatRouter.get(
  '/:id/stream',
  [requireAuth],
  async (req: Request, res: Response) => {
    const chatId = getIdFromRequest(req);
    if (!chatId) return;
    const cursor = req.headers['x-resume-stream-cursor'] as string;

    console.log(`[Stream Resume] Cursor: ${cursor}`);

    console.log(`[Stream Resume] GET request for chat ${chatId}`);

    // Check if there's an active stream for this chat first
    const streamId = streamCache.getActiveStreamId(chatId);

    if (!streamId) {
      console.log(`[Stream Resume] No active stream for chat ${chatId}`);
      const streamError = new ChatSDKError('empty:stream');
      const response = streamError.toResponse();
      return res.status(response.status).json(response.json);
    }

    const { allowed, reason } = await checkChatAccess(
      chatId,
      req.session?.user.id,
    );

    // If chat doesn't exist in DB, it's a temporary chat from the homepage - allow it
    if (reason === 'not_found') {
      console.log(
        `[Stream Resume] Resuming stream for temporary chat ${chatId} (not yet in DB)`,
      );
    } else if (!allowed) {
      console.log(
        `[Stream Resume] User ${req.session?.user.id} does not have access to chat ${chatId} (reason: ${reason})`,
      );
      const streamError = new ChatSDKError('forbidden:chat', reason);
      const response = streamError.toResponse();
      return res.status(response.status).json(response.json);
    }

    // Get all cached chunks for this stream
    const stream = streamCache.getStream(streamId, {
      cursor: cursor ? Number.parseInt(cursor) : undefined,
    });

    if (!stream) {
      console.log(`[Stream Resume] No stream found for ${streamId}`);
      const streamError = new ChatSDKError('empty:stream');
      const response = streamError.toResponse();
      return res.status(response.status).json(response.json);
    }

    console.log(`[Stream Resume] Resuming stream ${streamId}`);

    // Set headers for SSE
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    // Pipe the cached stream directly to the response
    stream.pipe(res);

    // Handle stream errors
    stream.on('error', (error) => {
      console.error('[Stream Resume] Stream error:', error);
      if (!res.headersSent) {
        res.status(500).end();
      }
    });
  },
);

/**
 * POST /api/chat/title - Generate title from message
 */
chatRouter.post('/title', requireAuth, async (req: Request, res: Response) => {
  try {
    const { message } = req.body;
    const title = await generateTitleFromUserMessage({ message });
    res.json({ title });
  } catch (error) {
    console.error('Error generating title:', error);
    res.status(500).json({ error: 'Failed to generate title' });
  }
});

/**
 * PATCH /api/chat/:id/visibility - Update chat visibility
 */
chatRouter.patch(
  '/:id/visibility',
  [requireAuth, requireChatAccess],
  async (req: Request, res: Response) => {
    try {
      const id = getIdFromRequest(req);
      if (!id) return;
      const { visibility } = req.body;

      if (!visibility || !['public', 'private'].includes(visibility)) {
        return res.status(400).json({ error: 'Invalid visibility type' });
      }

      await updateChatVisiblityById({ chatId: id, visibility });
      res.json({ success: true });
    } catch (error) {
      console.error('Error updating visibility:', error);
      res.status(500).json({ error: 'Failed to update visibility' });
    }
  },
);

// Helper function to generate title from user message
async function generateTitleFromUserMessage({
  message,
  maxMessageLength = 256,
}: {
  message: ChatMessage;
  maxMessageLength?: number;
}) {
  const model = await myProvider.languageModel('title-model');

  // Truncate each text part to the maxMessageLength
  const truncatedMessage = {
    ...message,
    parts: message.parts.map((part) =>
      part.type === 'text'
        ? { ...part, text: part.text.slice(0, maxMessageLength) }
        : part,
    ),
  };

  const { text: title } = await generateText({
    model,
    system: `\n
    - you will generate a short title based on the first message a user begins a conversation with
    - ensure it is not more than 80 characters long
    - the title should be a summary of the user's message
    - do not use quotes or colons. do not include other expository content ("I'll help...")`,
    prompt: JSON.stringify(truncatedMessage),
  });

  return title;
}

/**
 * Strips Databricks-internal URLs from sub-agent response text.
 * Removes:
 *   - Databricks workspace URLs: https://*.databricks.com/... and https://*.azuredatabricks.net/...
 *   - Unity Catalog Volume paths: /Volumes/catalog/schema/volume/...
 *   - DBFS paths: dbfs:/...
 * Leaves all other URLs (e.g. https://www.viabcp.com/creditos) intact.
 */
function stripDatabricksUrls(text: string): string {
  return text
    .replace(/【[^】]+】/g, '')
    .replace(/\n?\[\^[^\]]+\]:[^\n]*/g, '')
    .replace(/\[\^[^\]]+\]/g, '')
    .replace(/\[([^\]]*)\]\(https?:\/\/[^)]*\)/g, '$1')
    .replace(/https?:\/\/[^\s]*\.(?:cloud|azuredatabricks|gcp)\.databricks\.com[^\s]*/gi, '')
    .replace(/https?:\/\/[^\s]*\.azuredatabricks\.net[^\s]*/gi, '')
    .replace(/dbfs:\/[^\s]*/gi, '')
    .replace(/\/Volumes\/[^\s]*/gi, '')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n{3,}/g, '\n\n');
}

/**
 * Converts a raw sub-agent function name to a human-readable label.
 * Examples:
 *   "invoke_TendenciasAgent" → "Tendencias Agent"
 *   "call_riesgos_agent"     → "Riesgos Agent"
 */
function formatAgentName(rawName: string): string {
  return rawName
    .replace(/^(invoke|call|query|run)_/i, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

function truncatePreserveWords(input: string, maxLength: number): string {
  if (maxLength <= 0) return '';
  if (input.length <= maxLength) return input;

  // Take the raw slice first
  const slice = input.slice(0, maxLength);

  // Find the last whitespace within the slice
  const lastSpaceIndex = slice.lastIndexOf(' ');

  // If no whitespace found, we must break mid-word
  if (lastSpaceIndex === -1) {
    return slice;
  }

  // If the whitespace is too close to the start (e.g., leading space),
  // fallback to mid-word break to avoid returning an empty string
  if (lastSpaceIndex === 0) {
    return slice;
  }

  return slice.slice(0, lastSpaceIndex);
}
