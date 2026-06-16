import React from 'react';
import { parseStyle } from '@/utils/style';
import { Conversation, ConversationContent } from '@/components/ai-elements/conversation';

export const Thread: React.FC<any> = ({ ExplicitList, style }) => (
  <Conversation className="h-[75vh] min-h-0 min-w-0 w-full max-h-[75vh] overflow-hidden" style={parseStyle(style)}>
    <ConversationContent className="min-h-0">{ExplicitList}</ConversationContent>
  </Conversation>
);
