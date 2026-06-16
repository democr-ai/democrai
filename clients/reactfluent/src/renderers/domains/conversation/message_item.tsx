import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import {
  Message,
  MessageContent,
  MessageResponse,
  MessageActions,
  MessageAction,
} from '@/components/ai-elements/message';
import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from '@/components/ai-elements/reasoning';
import { BackgroundTaskCard } from '@/renderers/domains/tasks/background_task_card';

export const MessageItem: React.FC<any> = ({ role, text, reasoning, actions = [], onAction, style, meta, sendAction }) => {
  const from = String(role || 'assistant').toLowerCase() as any;
  const reasoningText = String(getLiteral(reasoning) || '').trim();

  if (from === 'task') {
    const taskId = String((typeof meta === 'object' && meta !== null ? (meta as any).task_id : null) || '');
    return (
      <div style={parseStyle(style)}>
        <BackgroundTaskCard task_id={taskId} sendAction={sendAction} />
      </div>
    );
  }

  return (
    <div style={parseStyle(style)}>
      <Message from={from}>
        <MessageContent>
          {from !== 'user' && reasoningText ? (
            <Reasoning defaultOpen={false}>
              <ReasoningTrigger />
              <ReasoningContent>{reasoningText}</ReasoningContent>
            </Reasoning>
          ) : null}
          <MessageResponse>{getLiteral(text)}</MessageResponse>
          {actions && actions.length ? (
            <MessageActions>
              {actions.map((entry: any, index: number) => (
                <MessageAction
                  key={`message_action_${index}`}
                  tooltip={getLiteral(entry?.label)}
                  onClick={() => emitActionSpec(entry?.action, onAction, {})}
                >
                  {getLiteral(entry?.label)}
                </MessageAction>
              ))}
            </MessageActions>
          ) : null}
        </MessageContent>
      </Message>
    </div>
  );
};
