import { z } from 'zod';
import type { LanguageModelUsage, UIMessage } from 'ai';

const messageMetadataSchema = z.object({
  createdAt: z.string(),
});

type MessageMetadata = z.infer<typeof messageMetadataSchema>;

export type CustomUIDataTypes = {
  error: string;
  usage: LanguageModelUsage;
  traceId: string | null;
  finalText: string;
  thinkingStatus: string;
  thinkingDetail: string;
  agentStart: string;
  agentChunk: { name: string; text: string };
  agentEnd: string;
  supervisorChunk: string;
  sources: Record<string, number>;
};

export type ChatMessage = UIMessage<MessageMetadata, CustomUIDataTypes>;

export interface Attachment {
  name: string;
  url: string;
  contentType: string;
}

export type { VisibilityType } from '@chat-template/utils';

export interface Feedback {
  messageId: string;
  feedbackType: 'thumbs_up' | 'thumbs_down';
  comment?: string;
  assessmentId: string | null;
}

export type FeedbackMap = Record<string, Feedback>;
