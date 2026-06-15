import React from 'react';
import { parseStyle } from '@/utils/style';
import { Conversation, ConversationContent } from '@/components/ai-elements/conversation';

export const Thread: React.FC<any> = ({ ExplicitList, style }) => (
  <Conversation className="ds-chat-thread" style={parseStyle(style)}>
    <ConversationContent className="ds-chat-thread-content">{ExplicitList}</ConversationContent>
  </Conversation>
);
