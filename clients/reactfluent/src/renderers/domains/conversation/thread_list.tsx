import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { cn } from '@/lib/utils';

export const ThreadList: React.FC<any> = ({
  threads = [],
  active_thread_id,
  action,
  onAction,
  style,
}) => (
  <aside style={parseStyle(style)} className="ds-thread-list">
      <h3 className="ds-thread-list-title">Conversations</h3>
      <div className="ds-thread-list-items">
        {threads.map((thread: any, index: number) => {
          const active = String(thread?.id) === String(active_thread_id);
          return (
            <button
              key={thread?.id || `thread_${index}`}
              type="button"
              className={cn("ds-thread-list-item", active && "is-active")}
              onClick={() => emitActionSpec(action, onAction, { threadId: thread?.id, thread })}
            >
              <div className="ds-thread-list-copy">
                <span className="ds-thread-list-item-title">
                  {getLiteral(thread?.title || 'Untitled conversation')}
                </span>
                {thread?.preview && (
                  <span className="ds-thread-list-item-preview">
                    {getLiteral(thread.preview)}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
  </aside>
);
