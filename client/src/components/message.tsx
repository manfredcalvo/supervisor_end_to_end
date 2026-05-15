import { motion } from 'framer-motion';
import React, { memo, useState } from 'react';
import { AnimatedAssistantIcon } from './animation-assistant-icon';
import { Response } from './elements/response';
import { MessageContent } from './elements/message';
import {
  Tool,
  ToolHeader,
  ToolContent,
  ToolInput,
  ToolOutput,
  type ToolState,
} from './elements/tool';
import {
  McpTool,
  McpToolHeader,
  McpToolContent,
  McpToolInput,
  McpApprovalActions,
} from './elements/mcp-tool';
import { MessageActions } from './message-actions';
import { PreviewAttachment } from './preview-attachment';
import equal from 'fast-deep-equal';
import { cn, sanitizeText } from '@/lib/utils';
import { MessageEditor } from './message-editor';
import { MessageReasoning } from './message-reasoning';
import type { UseChatHelpers } from '@ai-sdk/react';
import type { ChatMessage, Feedback } from '@chat-template/core';
import { useDataStream } from './data-stream-provider';
import {
  createMessagePartSegments,
  formatNamePart,
  isNamePart,
  joinMessagePartSegments,
} from './databricks-message-part-transformers';
import { MessageError } from './message-error';
import { MessageOAuthError } from './message-oauth-error';
import { isCredentialErrorMessage } from '@/lib/oauth-error-utils';
import { Streamdown } from 'streamdown';
import { useApproval } from '@/hooks/use-approval';
import { Loader2Icon, CheckIcon, ChevronDownIcon } from 'lucide-react';

/**
 * Animated gradient text used for loading states ("Thinking...", "Analyzing...").
 * Defined at module level so it can be shared by PurePreviewMessage and AwaitingResponseMessage.
 */
const LoadingText = ({ children }: { children: React.ReactNode }) => {
  return (
    <motion.div
      animate={{ backgroundPosition: ['100% 50%', '-100% 50%'] }}
      transition={{
        duration: 1.5,
        repeat: Number.POSITIVE_INFINITY,
        ease: 'linear',
      }}
      style={{
        background:
          'linear-gradient(90deg, hsl(var(--muted-foreground)) 0%, hsl(var(--muted-foreground)) 35%, hsl(var(--foreground)) 50%, hsl(var(--muted-foreground)) 65%, hsl(var(--muted-foreground)) 100%)',
        backgroundSize: '200% 100%',
        WebkitBackgroundClip: 'text',
        backgroundClip: 'text',
      }}
      className="flex items-center text-transparent"
    >
      {children}
    </motion.div>
  );
};

/**
 * Filters assistant message parts for display when no server-side final text
 * is available (fallback for old messages stored before `data-finalText` was
 * introduced, or for simple non-supervisor endpoints).
 *
 * Strategy: find the last "separator" (a dynamic-tool call or a reasoning
 * block). Everything BEFORE that separator is intermediate processing; only
 * parts AFTER it are candidates for display. This reliably hides sub-agent
 * responses for saved supervisor messages that have a reasoning block or that
 * end with a tool call before the supervisor synthesis.
 *
 * If no separator exists (simple endpoint), all non-tool, non-reasoning parts
 * pass through unchanged.
 */
function getAssistantDisplayParts(
  parts: ChatMessage['parts'],
): ChatMessage['parts'] {
  let lastSeparatorIdx = -1;
  for (let i = parts.length - 1; i >= 0; i--) {
    if (parts[i].type === 'dynamic-tool' || parts[i].type === 'reasoning') {
      lastSeparatorIdx = i;
      break;
    }
  }

  const partsToFilter =
    lastSeparatorIdx !== -1 ? parts.slice(lastSeparatorIdx + 1) : parts;

  return partsToFilter.filter((part) => {
    if (part.type === 'dynamic-tool') return false;
    if (part.type === 'reasoning') return false;
    if (part.type === 'source-url') return false;
    if (part.type === 'text' && isNamePart(part)) return false;
    return true;
  });
}

const PurePreviewMessage = ({
  message,
  allMessages,
  isLoading,
  setMessages,
  addToolApprovalResponse,
  sendMessage,
  regenerate,
  isReadonly,
  requiresScrollPadding,
  initialFeedback,
}: {
  message: ChatMessage;
  allMessages: ChatMessage[];
  isLoading: boolean;
  setMessages: UseChatHelpers<ChatMessage>['setMessages'];
  addToolApprovalResponse: UseChatHelpers<ChatMessage>['addToolApprovalResponse'];
  sendMessage: UseChatHelpers<ChatMessage>['sendMessage'];
  regenerate: UseChatHelpers<ChatMessage>['regenerate'];
  isReadonly: boolean;
  requiresScrollPadding: boolean;
  initialFeedback?: Feedback;
}) => {
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [showErrors, setShowErrors] = useState(false);

  // Hook for handling MCP approval requests
  const { submitApproval, isSubmitting, pendingApprovalId } = useApproval({
    addToolApprovalResponse,
    sendMessage,
  });

  const attachmentsFromMessage = message.parts.filter(
    (part) => part.type === 'file',
  );

  // Extract non-OAuth error parts separately (OAuth errors are rendered inline)
  const errorParts = React.useMemo(
    () =>
      message.parts
        .filter((part) => part.type === 'data-error')
        .filter((part) => {
          // OAuth errors are rendered inline, not in the error section
          return !isCredentialErrorMessage(part.data);
        }),
    [message.parts],
  );

  useDataStream();

  /**
   * The server-injected final text from the supervisor's highest-step output.
   * Present only for multi-agent supervisor endpoints, injected after the stream
   * finishes. When present, the client renders only this text (hiding all
   * intermediate sub-agent content).
   */
  const finalTextPart = React.useMemo(() => {
    if (message.role !== 'assistant') return undefined;
    return message.parts.find((p) => p.type === 'data-finalText');
  }, [message.parts, message.role]);

  /**
   * Agent start labels — one per sub-agent (or supervisor preamble).
   * Emitted in real-time as function_calls are detected.
   */
  const agentStartParts = React.useMemo(() => {
    if (message.role !== 'assistant') return [];
    return message.parts.filter((p) => p.type === 'data-agentStart');
  }, [message.parts, message.role]);

  /**
   * Agents that have finished streaming — set of agent display labels.
   */
  const doneAgentNames = React.useMemo(() => {
    if (message.role !== 'assistant') return new Set<string>();
    const s = new Set<string>();
    for (const p of message.parts) {
      if (p.type === 'data-agentEnd') s.add(p.data as string);
    }
    return s;
  }, [message.parts, message.role]);

  /**
   * Accumulated supervisor final response chunks for real-time display.
   */
  const supervisorStreamText = React.useMemo(() => {
    if (message.role !== 'assistant') return '';
    return message.parts
      .filter((p) => p.type === 'data-supervisorChunk')
      .map((p) => p.data as string)
      .join('');
  }, [message.parts, message.role]);

  /**
   * Backwards-compat: thinkingStatus parts for DB-loaded history (old messages).
   * Used only when agentStartParts is empty (pre-migration messages).
   */
  const thinkingStatusParts = React.useMemo(() => {
    if (message.role !== 'assistant') return [];
    return message.parts.filter((p) => p.type === 'data-thinkingStatus');
  }, [message.parts, message.role]);

  /**
   * Sub-agent response texts written after the stream, one per function_call.
   * Used for chevron expand content (both live session and DB-loaded history).
   */
  const thinkingDetailParts = React.useMemo(() => {
    if (message.role !== 'assistant') return [];
    return message.parts.filter(
      (p): p is Extract<typeof p, { type: 'data-thinkingDetail' }> =>
        p.type === 'data-thinkingDetail',
    );
  }, [message.parts, message.role]);

  const sourcesPart = React.useMemo(() => {
    if (message.role !== 'assistant') return undefined;
    return message.parts.find((p) => p.type === 'data-sources');
  }, [message.parts, message.role]);

  /**
   * True while the assistant message is streaming and the final text hasn't
   * arrived yet. Suppresses ALL streaming text (including supervisor preamble
   * that arrives before sub-agent tool calls) and shows "Analyzing..." instead.
   *
   * Once the server injects `data-finalText` (end-of-stream), this flips to
   * false and the final synthesized response is rendered. For simple endpoints
   * that never inject `data-finalText`, this also becomes false once loading
   * ends and the fallback text filter takes over.
   */
  // True while the assistant is streaming and neither the final text nor
  // any real-time supervisor chunks have arrived yet.
  const isProcessingIntermediateSteps =
    isLoading &&
    message.role === 'assistant' &&
    !finalTextPart &&
    supervisorStreamText.length === 0;

  const [expandedSteps, setExpandedSteps] = React.useState<Set<number>>(
    new Set(),
  );
  const toggleStep = (i: number) =>
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });

  const partSegments = React.useMemo(
    /**
     * Segments message parts for rendering.
     *
     * For supervisor endpoints: when `data-finalText` is present (injected by the
     * server after the stream ends), render only that text — hiding all tool calls,
     * reasoning steps, and sub-agent responses.
     *
     * Fallback (simple endpoints or during streaming): filter out tool calls,
     * reasoning, and sub-agent name headers, then render remaining text parts.
     *
     * Non-OAuth errors are excluded here and rendered separately below.
     */
    () => {
      const baseParts = message.parts.filter(
        (part) =>
          part.type !== 'data-error' || isCredentialErrorMessage(part.data),
      );

      if (message.role === 'assistant' && finalTextPart) {
        // Post-stream: render the server-injected final text
        return createMessagePartSegments([
          { type: 'text', text: finalTextPart.data },
        ] as ChatMessage['parts']);
      }
      if (message.role === 'assistant' && supervisorStreamText.length > 0) {
        // Live streaming: render accumulated supervisor chunks
        return createMessagePartSegments([
          { type: 'text', text: supervisorStreamText },
        ] as ChatMessage['parts']);
      }

      const parts =
        message.role === 'assistant'
          ? getAssistantDisplayParts(baseParts)
          : baseParts;
      return createMessagePartSegments(parts);
    },
    [message.parts, message.role, finalTextPart, supervisorStreamText],
  );

  // Check if message only contains non-OAuth errors (no other content)
  const hasOnlyErrors = React.useMemo(() => {
    const nonErrorParts = message.parts.filter(
      (part) => part.type !== 'data-error',
    );
    // Only consider non-OAuth errors for this check
    return errorParts.length > 0 && nonErrorParts.length === 0;
  }, [message.parts, errorParts.length]);

  return (
    <div
      data-testid={`message-${message.role}`}
      className="group/message w-full"
      data-role={message.role}
    >
      <div
        className={cn('flex w-full items-start gap-2 md:gap-3', {
          'justify-end': message.role === 'user',
          'justify-start': message.role === 'assistant',
        })}
      >
        {message.role === 'assistant' && (
          <AnimatedAssistantIcon size={14} isLoading={isLoading} />
        )}

        <div
          className={cn('flex min-w-0 flex-col gap-3', {
            'w-full': message.role === 'assistant' || mode === 'edit',
            'min-h-96': message.role === 'assistant' && requiresScrollPadding,
            'max-w-[70%] sm:max-w-[min(fit-content,80%)]':
              message.role === 'user' && mode !== 'edit',
          })}
        >
          {attachmentsFromMessage.length > 0 && (
            <div
              data-testid={`message-attachments`}
              className="flex flex-row justify-end gap-2"
            >
              {attachmentsFromMessage.map((attachment) => (
                <PreviewAttachment
                  key={attachment.url}
                  attachment={{
                    name: attachment.filename ?? 'file',
                    contentType: attachment.mediaType,
                    url: attachment.url,
                  }}
                />
              ))}
            </div>
          )}

          {/* "Pensando..." with no steps yet */}
          {isProcessingIntermediateSteps && agentStartParts.length === 0 && thinkingStatusParts.length === 0 && (
            <p className="animate-pulse text-muted-foreground text-sm">
              Pensando...
            </p>
          )}

          {/* New streaming agent panels — shown when agentStart parts are present */}
          {agentStartParts.length > 0 && (() => {
            // We need to map agentStart labels to sub-agent names (raw names from agentEnd/agentChunk).
            // agentStart[0] may be the supervisor preamble ("Consultando al supervisor..."),
            // real sub-agents follow. We use thinkingDetailParts for expanded content (indexed
            // by sub-agent position among non-preamble agentStarts).
            const subAgentStartParts = agentStartParts.filter(
              (p) => !(p.data as string).startsWith('Consultando al supervisor'),
            );
            const hasPreamble = agentStartParts.length > subAgentStartParts.length;
            const allDone = !isLoading;
            const subAgentsDone = allDone || supervisorStreamText.length > 0 || !!finalTextPart;

            return (
              <div className="flex flex-col gap-1.5">
                <p
                  className={cn('text-muted-foreground text-sm', {
                    'animate-pulse': isProcessingIntermediateSteps,
                  })}
                >
                  {isProcessingIntermediateSteps ? 'Pensando...' : 'Finalizado'}
                </p>

                {/* Supervisor preamble row — always done once sub-agents start */}
                {hasPreamble && (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
                    <CheckIcon className="size-3 shrink-0 text-green-500" />
                    <span>Consultando al supervisor...</span>
                  </div>
                )}

                {/* Sub-agent rows */}
                {subAgentStartParts.map((part, i) => {
                  const label = part.data as string;
                  // Extract raw agent name from agentChunk/agentEnd parts to look up text.
                  // We find the raw name by seeing which agentEnd name has index i among doneAgentNames.
                  const doneNamesList = message.parts
                    .filter((p) => p.type === 'data-agentEnd')
                    .map((p) => p.data as string);
                  const rawName = doneNamesList[i];
                  const isDone = subAgentsDone || rawName !== undefined;
                  const isCurrentStep = !isDone;
                  // Expand content comes from thinkingDetail (output_item.done text),
                  // emitted inline by the server as soon as each agent finishes.
                  const detail = thinkingDetailParts[i];
                  const expandContent = detail?.data as string | undefined;
                  const isExpanded = expandedSteps.has(i);

                  return (
                    <div key={i}>
                      <div
                        className={cn('flex items-center gap-1.5 text-xs', {
                          'text-muted-foreground/50': isProcessingIntermediateSteps && !isCurrentStep,
                          'animate-pulse text-muted-foreground': isCurrentStep,
                          'text-muted-foreground/60': !isProcessingIntermediateSteps,
                        })}
                      >
                        {isCurrentStep ? (
                          <Loader2Icon className="size-3 shrink-0 animate-spin" />
                        ) : (
                          <CheckIcon className="size-3 shrink-0 text-green-500" />
                        )}
                        <span>{label}</span>
                        {!isCurrentStep && expandContent && (
                          <button
                            type="button"
                            onClick={() => toggleStep(i)}
                            className="p-0.5 rounded hover:bg-muted/50 transition-colors"
                          >
                            <ChevronDownIcon
                              className={cn('size-3 transition-transform', {
                                'rotate-180': isExpanded,
                              })}
                            />
                          </button>
                        )}
                      </div>

                      {/* Expanded collapsed content */}
                      {!isCurrentStep && isExpanded && expandContent && (
                        <div className="mt-1 ml-5 rounded-md border px-3 py-2">
                          <Response>{expandContent}</Response>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })()}

          {/* Fallback: old thinkingStatus panels for DB-loaded messages without agentStart */}
          {agentStartParts.length === 0 && thinkingStatusParts.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p
                className={cn('text-muted-foreground text-sm', {
                  'animate-pulse': isProcessingIntermediateSteps,
                })}
              >
                {isProcessingIntermediateSteps ? 'Pensando...' : 'Finalizado'}
              </p>
              {thinkingStatusParts.map((part, i) => {
                const isCurrentStep =
                  isProcessingIntermediateSteps &&
                  i === thinkingStatusParts.length - 1;
                const detail = thinkingDetailParts[i];
                const isExpanded = expandedSteps.has(i);
                return (
                  <div key={i}>
                    <div
                      className={cn('flex items-center gap-1.5 text-xs', {
                        'text-muted-foreground/50':
                          isProcessingIntermediateSteps && !isCurrentStep,
                        'animate-pulse text-muted-foreground': isCurrentStep,
                        'text-muted-foreground/60':
                          !isProcessingIntermediateSteps,
                      })}
                    >
                      {isCurrentStep ? (
                        <Loader2Icon className="size-3 shrink-0 animate-spin" />
                      ) : (
                        <CheckIcon className="size-3 shrink-0 text-green-500" />
                      )}
                      <span>{part.data}</span>
                      {!isCurrentStep && detail && (
                        <button
                          type="button"
                          onClick={() => toggleStep(i)}
                          className="p-0.5 rounded hover:bg-muted/50 transition-colors"
                        >
                          <ChevronDownIcon
                            className={cn('size-3 transition-transform', {
                              'rotate-180': isExpanded,
                            })}
                          />
                        </button>
                      )}
                    </div>
                    {isExpanded && detail && (
                      <div className="mt-1 ml-5 rounded-md border px-3 py-2">
                        <Response>{detail.data}</Response>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {!isProcessingIntermediateSteps && partSegments?.map((parts, index) => {
            const [part] = parts;
            const { type } = part;
            const key = `message-${message.id}-part-${index}`;

            if (type === 'reasoning' && part.text?.trim().length > 0) {
              return (
                <MessageReasoning
                  key={key}
                  isLoading={isLoading}
                  reasoning={part.text}
                />
              );
            }

            if (type === 'text') {
              if (isNamePart(part)) {
                return (
                  <Streamdown
                    key={key}
                    className="-mb-2 mt-0 border-l-4 pl-2 text-muted-foreground"
                  >{`# ${formatNamePart(part)}`}</Streamdown>
                );
              }
              if (mode === 'view') {
                return (
                  <div key={key}>
                    <MessageContent
                      data-testid="message-content"
                      className={cn({
                        'w-fit break-words rounded-2xl px-3 py-2 text-right text-white':
                          message.role === 'user',
                        'bg-transparent px-0 py-0 text-left':
                          message.role === 'assistant',
                      })}
                      style={
                        message.role === 'user'
                          ? { backgroundColor: '#006cff' }
                          : undefined
                      }
                    >
                      <Response>
                        {sanitizeText(joinMessagePartSegments(parts))}
                      </Response>
                    </MessageContent>
                  </div>
                );
              }

              if (mode === 'edit') {
                return (
                  <div
                    key={key}
                    className="flex w-full flex-row items-start gap-3"
                  >
                    <div className="size-8" />
                    <div className="min-w-0 flex-1">
                      <MessageEditor
                        key={message.id}
                        message={message}
                        setMode={setMode}
                        setMessages={setMessages}
                        regenerate={regenerate}
                      />
                    </div>
                  </div>
                );
              }
            }

            // Render Databricks tool calls and results
            if (part.type === `dynamic-tool`) {
              const { toolCallId, input, state, errorText, output, toolName } =
                part;

              // Check if this is an MCP tool call by looking for approvalRequestId in metadata
              // This works across all states (approval-requested, approval-denied, output-available)
              const isMcpApproval =
                part.callProviderMetadata?.databricks?.approvalRequestId !=
                null;
              const mcpServerName =
                part.callProviderMetadata?.databricks?.mcpServerName?.toString();

              // Extract approval outcome for 'approval-responded' state
              // When addToolApprovalResponse is called, AI SDK sets the `approval` property
              // on the tool-call part and changes state to 'approval-responded'
              const approved: boolean | undefined =
                'approval' in part ? part.approval?.approved : undefined;

              // When approved but only have approval status (not actual output), show as input-available
              const effectiveState: ToolState = (() => {
                if (
                  part.providerExecuted &&
                  !isLoading &&
                  state === 'input-available'
                ) {
                  return 'output-available';
                }
                return state;
              })();

              // Render MCP tool calls with special styling
              if (isMcpApproval) {
                return (
                  <McpTool key={toolCallId} defaultOpen={true}>
                    <McpToolHeader
                      serverName={mcpServerName}
                      toolName={toolName}
                      state={effectiveState}
                      approved={approved}
                    />
                    <McpToolContent>
                      <McpToolInput input={input} />
                      {state === 'approval-requested' && (
                        <McpApprovalActions
                          onApprove={() =>
                            submitApproval({
                              approvalRequestId: toolCallId,
                              approve: true,
                            })
                          }
                          onDeny={() =>
                            submitApproval({
                              approvalRequestId: toolCallId,
                              approve: false,
                            })
                          }
                          isSubmitting={
                            isSubmitting && pendingApprovalId === toolCallId
                          }
                        />
                      )}
                      {state === 'output-available' && output != null && (
                        <ToolOutput
                          output={
                            errorText ? (
                              <div className="rounded border p-2 text-red-500">
                                Error: {errorText}
                              </div>
                            ) : (
                              <div className="whitespace-pre-wrap font-mono text-sm">
                                {typeof output === 'string'
                                  ? output
                                  : JSON.stringify(output, null, 2)}
                              </div>
                            )
                          }
                          errorText={undefined}
                        />
                      )}
                    </McpToolContent>
                  </McpTool>
                );
              }

              // Render regular tool calls
              return (
                <Tool key={toolCallId} defaultOpen={true}>
                  <ToolHeader type={toolName} state={effectiveState} />
                  <ToolContent>
                    <ToolInput input={input} />
                    {state === 'output-available' && (
                      <ToolOutput
                        output={
                          errorText ? (
                            <div className="rounded border p-2 text-red-500">
                              Error: {errorText}
                            </div>
                          ) : (
                            <div className="whitespace-pre-wrap font-mono text-sm">
                              {typeof output === 'string'
                                ? output
                                : JSON.stringify(output, null, 2)}
                            </div>
                          )
                        }
                        errorText={undefined}
                      />
                    )}
                  </ToolContent>
                </Tool>
              );
            }

            // Support for citations/annotations
            if (type === 'source-url') {
              return (
                <a
                  key={key}
                  href={part.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-baseline text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                >
                  <sup className="text-xs">[{part.title || part.url}]</sup>
                </a>
              );
            }

            // Render OAuth errors inline
            if (type === 'data-error' && isCredentialErrorMessage(part.data)) {
              return (
                <MessageOAuthError
                  key={key}
                  error={part.data}
                  allMessages={allMessages}
                  setMessages={setMessages}
                  sendMessage={sendMessage}
                />
              );
            }
          })}

          {sourcesPart &&
            Object.keys(sourcesPart.data as Record<string, number>).length >
              0 && (
              <div className="mt-4 border-t pt-3">
                <h2 className="mt-6 mb-2 font-semibold text-2xl">Fuentes</h2>
                <ul className="list-disc list-inside space-y-1">
                  {Object.entries(
                    sourcesPart.data as Record<string, number>,
                  ).map(([name, count]) => (
                    <li key={name}>
                      {name}{' '}
                      <span>
                        ({count}{' '}
                        {count === 1 ? 'referencia' : 'referencias'})
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

          {!isReadonly && !hasOnlyErrors && (
            <MessageActions
              key={`action-${message.id}`}
              message={message}
              isLoading={isLoading}
              setMode={setMode}
              errorCount={errorParts.length}
              showErrors={showErrors}
              onToggleErrors={() => setShowErrors(!showErrors)}
              initialFeedback={initialFeedback}
            />
          )}

          {errorParts.length > 0 && (hasOnlyErrors || showErrors) && (
            <div className="flex flex-col gap-2">
              {errorParts.map((part, index) => (
                <MessageError
                  key={`error-${message.id}-${index}`}
                  error={part.data}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export const PreviewMessage = memo(
  PurePreviewMessage,
  (prevProps, nextProps) => {
    if (prevProps.isLoading !== nextProps.isLoading) return false;
    // While streaming, re-render whenever the AI SDK produces a new message
    // object (each throttled update). We use reference equality rather than
    // deep-equal on parts because fast-deep-equal short-circuits on identical
    // references — and the SDK may mutate parts in place during streaming.
    if (nextProps.isLoading && prevProps.message !== nextProps.message)
      return false;

    if (prevProps.message.id !== nextProps.message.id) return false;
    if (prevProps.requiresScrollPadding !== nextProps.requiresScrollPadding)
      return false;
    if (!equal(prevProps.message.parts, nextProps.message.parts)) return false;
    if (prevProps.initialFeedback?.feedbackType !== nextProps.initialFeedback?.feedbackType)
      return false;

    return true; // Props are equal, skip re-render
  },
);

export const AwaitingResponseMessage = () => {
  const role = 'assistant';

  return (
    <div
      data-testid="message-assistant-loading"
      className="group/message w-full"
      data-role={role}
    >
      <div className="flex items-start justify-start gap-3">
        <AnimatedAssistantIcon size={14} isLoading={false} muted={true} />

        <div className="flex w-full flex-col gap-2 md:gap-4">
          <div className="p-0 text-muted-foreground text-sm">
            <LoadingText>Thinking...</LoadingText>
          </div>
        </div>
      </div>
    </div>
  );
};
