import React from 'react';
import { parseStyle } from '@/utils/style';
import { Conversation, ConversationContent } from '@/components/ai-elements/conversation';

export const Thread: React.FC<any> = ({ ExplicitList, style }) => (
  <Conversation className="a2ui-chat-thread" style={parseStyle(style)}>
    <ConversationContent className="a2ui-chat-thread-content">{ExplicitList}</ConversationContent>
  </Conversation>
);
