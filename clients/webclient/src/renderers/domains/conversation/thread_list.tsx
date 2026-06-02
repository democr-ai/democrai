import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export const ThreadList: React.FC<any> = ({
  threads = [],
  active_thread_id,
  action,
  onAction,
  style,
}) => (
  <Card style={parseStyle(style)}>
    <CardHeader className="py-3 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Threads</CardHeader>
    <CardContent className="grid gap-1">
      {threads.map((thread: any, index: number) => {
        const active = String(thread?.id) === String(active_thread_id);
        return (
          <Button
            key={thread?.id || `thread_${index}`}
            type="button"
            variant={active ? 'secondary' : 'ghost'}
            className="h-auto justify-start whitespace-normal px-3 py-2 text-left"
            onClick={() => emitActionSpec(action, onAction, { threadId: thread?.id, thread })}
          >
            <span className="grid">
              <span className="truncate font-medium">{getLiteral(thread?.title || 'Untitled Thread')}</span>
              {thread?.preview ? (
                <span className="truncate text-xs text-muted-foreground opacity-70">
                  {getLiteral(thread.preview)}
                </span>
              ) : null}
            </span>
          </Button>
        );
      })}
    </CardContent>
  </Card>
);
