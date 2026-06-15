import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { Card, CardBody, Button } from 'design-react-kit';
import { cn } from '@/lib/utils';

export const ThreadList: React.FC<any> = ({
  threads = [],
  active_thread_id,
  action,
  onAction,
  style,
}) => (
  <Card style={parseStyle(style)} className="border-0 shadow-none bg-transparent">
    <CardBody className="p-0">
      <h6 className="text-uppercase xsmall fw-bold text-muted px-3 mb-3">Conversazioni</h6>
      <div className="d-grid gap-1">
        {threads.map((thread: any, index: number) => {
          const active = String(thread?.id) === String(active_thread_id);
          return (
            <Button
              key={thread?.id || `thread_${index}`}
              type="button"
              color={active ? 'primary' : 'link'}
              className={cn(
                "text-start p-3 rounded border-0 text-decoration-none",
                active ? "bg-primary text-white" : "text-dark hover-bg-light"
              )}
              onClick={() => emitActionSpec(action, onAction, { threadId: thread?.id, thread })}
            >
              <div className="d-flex flex-column overflow-hidden">
                <span className={cn("text-truncate small fw-bold", active ? "text-white" : "text-dark")}>
                  {getLiteral(thread?.title || 'Conversazione senza titolo')}
                </span>
                {thread?.preview && (
                  <span className={cn("text-truncate xsmall opacity-75 mt-1", active ? "text-white" : "text-muted")}>
                    {getLiteral(thread.preview)}
                  </span>
                )}
              </div>
            </Button>
          );
        })}
      </div>
    </CardBody>
  </Card>
);
