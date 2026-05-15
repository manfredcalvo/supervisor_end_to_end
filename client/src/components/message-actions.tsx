import { useCopyToClipboard } from 'usehooks-ts';

import { Actions, Action } from './elements/actions';
import { memo, useState, useCallback, useRef, useEffect } from 'react';
import { toast } from 'sonner';
import type { ChatMessage, Feedback } from '@chat-template/core';
import { useAppConfig } from '@/contexts/AppConfigContext';
import {
  ChevronDown,
  ChevronUp,
  CopyIcon,
  PencilLineIcon,
  ThumbsUp,
  ThumbsDown,
  SendIcon,
  XIcon,
} from 'lucide-react';

function PureMessageActions({
  message,
  isLoading,
  setMode,
  errorCount = 0,
  showErrors = false,
  onToggleErrors,
  initialFeedback,
}: {
  message: ChatMessage;
  isLoading: boolean;
  setMode?: (mode: 'view' | 'edit') => void;
  errorCount?: number;
  showErrors?: boolean;
  onToggleErrors?: () => void;
  initialFeedback?: Feedback;
}) {
  // All hooks MUST be called before any early returns
  const { feedbackEnabled } = useAppConfig();
  const [_, copyToClipboard] = useCopyToClipboard();
  const [feedback, setFeedback] = useState<'thumbs_up' | 'thumbs_down' | null>(
    initialFeedback?.feedbackType || null,
  );
  const [showCommentBox, setShowCommentBox] = useState(false);
  const [comment, setComment] = useState('');
  const [pendingFeedbackType, setPendingFeedbackType] = useState<
    'thumbs_up' | 'thumbs_down' | null
  >(null);
  const isSubmittingRef = useRef(false);

  // Sync server-restored feedback into local state when it arrives after mount
  // (e.g. NewChatPage's useChatData resolves after the first stream completes).
  // Only applies when the user hasn't clicked anything yet (feedback === null).
  useEffect(() => {
    if (initialFeedback?.feedbackType && feedback === null) {
      setFeedback(initialFeedback.feedbackType);
    }
  }, [initialFeedback?.feedbackType]);

  const textFromParts = message.parts
    ?.filter((part) => part.type === 'text')
    .map((part) => part.text)
    .join('\n')
    .trim();

  // A data-traceId part with data: null means the endpoint doesn't emit traces,
  // so MLflow feedback submission isn't possible. When the part is absent (e.g.
  // for messages streamed before this feature), assume feedback is supported.
  const traceIdPart = message.parts?.find((p) => p.type === 'data-traceId') as
    | { type: 'data-traceId'; data: string | null }
    | undefined;
  const feedbackSupported = traceIdPart === undefined || traceIdPart.data !== null;

  const handleFeedbackClick = useCallback(
    (feedbackType: 'thumbs_up' | 'thumbs_down') => {
      setPendingFeedbackType(feedbackType);
      setShowCommentBox(true);
      setComment('');
    },
    [],
  );

  const submitFeedback = useCallback(
    async (feedbackComment?: string) => {
      if (isSubmittingRef.current || !pendingFeedbackType) return;
      isSubmittingRef.current = true;

      try {
        const body: Record<string, string> = {
          messageId: message.id,
          feedbackType: pendingFeedbackType,
        };
        if (feedbackComment?.trim()) {
          body.comment = feedbackComment.trim();
        }

        const response = await fetch('/api/feedback', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          throw new Error('Failed to submit feedback');
        }

        setFeedback(pendingFeedbackType);
        setShowCommentBox(false);
        setComment('');
        setPendingFeedbackType(null);
      } catch (error) {
        console.error('Error submitting feedback:', error);
        toast.error('Failed to submit feedback. Please try again, or contact the app developer if the error persists.');
      } finally {
        isSubmittingRef.current = false;
      }
    },
    [message.id, pendingFeedbackType],
  );

  const handleCopy = useCallback(async () => {
    if (!textFromParts) {
      toast.error("There's no text to copy!");
      return;
    }

    await copyToClipboard(textFromParts);
    toast.success('Copied to clipboard!');
  }, [textFromParts, copyToClipboard]);

  // Early return AFTER all hooks have been called
  if (isLoading) return null;

  // User messages get edit (on hover) and copy actions
  if (message.role === 'user') {
    return (
      <Actions className="-mr-0.5 justify-end">
        <div className="relative">
          {setMode && (
            <Action
              tooltip="Edit"
              onClick={() => setMode('edit')}
              className="-left-10 absolute top-0 opacity-0 transition-opacity group-hover/message:opacity-100"
              data-testid="message-edit-button"
            >
              <PencilLineIcon />
            </Action>
          )}
          <Action tooltip="Copy" onClick={handleCopy}>
            <CopyIcon />
          </Action>
        </div>
      </Actions>
    );
  }

  const feedbackButtons = (
    <>
      <Action
        tooltip="Thumbs up"
        onClick={() => handleFeedbackClick('thumbs_up')}
        className={feedback === 'thumbs_up' ? 'text-green-600' : ''}
        data-testid="thumbs-up-button"
      >
        <ThumbsUp />
      </Action>
      <Action
        tooltip="Thumbs down"
        onClick={() => handleFeedbackClick('thumbs_down')}
        className={feedback === 'thumbs_down' ? 'text-red-600' : ''}
        data-testid="thumbs-down-button"
      >
        <ThumbsDown />
      </Action>
    </>
  );

  return (
    <div className="flex flex-col gap-2">
      <Actions className="-ml-0.5">
        {textFromParts && (
          <Action tooltip="Copy" onClick={handleCopy}>
            <CopyIcon />
          </Action>
        )}
        {feedbackEnabled && feedbackSupported && feedbackButtons}
        {errorCount > 0 && onToggleErrors && (
          <Action
            tooltip={showErrors ? 'Hide errors' : 'Show errors'}
            onClick={onToggleErrors}
            iconOnly={false}
          >
            <div className="flex items-center gap-1.5">
              {showErrors ? <ChevronUp /> : <ChevronDown />}
              <span className="text-xs">
                {errorCount} {errorCount === 1 ? 'error' : 'errors'}
              </span>
            </div>
          </Action>
        )}
      </Actions>
      {showCommentBox && (
        <div className="flex items-start gap-2 max-w-md" data-testid="feedback-comment-box">
          <textarea
            className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
            placeholder="Add a comment (optional)"
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submitFeedback(comment);
              }
            }}
            data-testid="feedback-comment-input"
          />
          <button
            type="button"
            onClick={() => submitFeedback(comment)}
            className="inline-flex items-center justify-center rounded-md text-sm font-medium h-8 w-8 hover:bg-accent hover:text-accent-foreground text-primary"
            title="Submit feedback"
            data-testid="feedback-comment-submit"
          >
            <SendIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => {
              setShowCommentBox(false);
              setComment('');
              setPendingFeedbackType(null);
            }}
            className="inline-flex items-center justify-center rounded-md text-sm font-medium h-8 w-8 hover:bg-accent hover:text-accent-foreground text-muted-foreground"
            title="Cancel"
            data-testid="feedback-comment-cancel"
          >
            <XIcon className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}

export const MessageActions = memo(
  PureMessageActions,
  (prevProps, nextProps) => {
    if (prevProps.isLoading !== nextProps.isLoading) return false;
    if (prevProps.errorCount !== nextProps.errorCount) return false;
    if (prevProps.showErrors !== nextProps.showErrors) return false;
    if (prevProps.initialFeedback?.feedbackType !== nextProps.initialFeedback?.feedbackType) return false;
    const prevTraceId = prevProps.message.parts?.find(
      (p) => p.type === 'data-traceId',
    );
    const nextTraceId = nextProps.message.parts?.find(
      (p) => p.type === 'data-traceId',
    );
    if (prevTraceId !== nextTraceId) return false;

    return true;
  },
);
