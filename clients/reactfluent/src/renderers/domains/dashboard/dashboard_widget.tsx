import React from 'react';
import { parseStyle } from '@/utils/style';
import { cn } from '@/lib/utils';

const sizeToSpan = (size: string): { w: number; h: number } => {
  switch (size) {
    case 'rect_h': return { w: 2, h: 1 };
    case 'rect_v': return { w: 1, h: 2 };
    case 'large': return { w: 2, h: 2 };
    default: return { w: 1, h: 1 };
  }
};

export const DashboardWidget: React.FC<any> = ({
  id,
  ExplicitList,
  size = 'square',
  title,
  style,
  edit_mode = false,
  onGridDragStart,
  onGridDragEnd,
}) => {
  const span = sizeToSpan(size);

  const handleDragStart = (event: React.DragEvent<HTMLDivElement>) => {
    if (!edit_mode) return;
    event.stopPropagation();
    event.dataTransfer.setData('application/x-dashboard-widget', String(id || ''));
    event.dataTransfer.setData('application/x-dashboard-widget-w', String(span.w));
    event.dataTransfer.setData('application/x-dashboard-widget-h', String(span.h));
    event.dataTransfer.effectAllowed = 'move';
    onGridDragStart?.(String(id || ''), span);
  };

  return (
    <section
      draggable={Boolean(edit_mode)}
      onDragStart={handleDragStart}
      onDragEnd={() => onGridDragEnd?.()}
      className={cn('a2ui-dashboard-widget', edit_mode && 'a2ui-dashboard-widget-editing')}
      style={parseStyle(style)}
      data-widget-id={id}
      data-grid-w={span.w}
      data-grid-h={span.h}
    >
      {title ? (
        <header className="a2ui-dashboard-widget-header">
          <h3 className="a2ui-dashboard-widget-title">{title}</h3>
          {edit_mode ? <span className="a2ui-dashboard-widget-drag-label">Move</span> : null}
        </header>
      ) : null}
      <div className="a2ui-dashboard-widget-body">{ExplicitList}</div>
    </section>
  );
};
