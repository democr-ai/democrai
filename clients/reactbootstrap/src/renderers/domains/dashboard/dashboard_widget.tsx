import React from 'react';
import { parseStyle } from '@/utils/style';
import { cn } from '@/lib/utils';
import { Card, CardBody, CardHeader, CardTitle } from 'design-react-kit';

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
    <Card
      draggable={Boolean(edit_mode)}
      onDragStart={handleDragStart}
      onDragEnd={() => onGridDragEnd?.()}
      className={cn('a2ui-dashboard-widget d-flex flex-column h-100 overflow-hidden border', edit_mode && 'cursor-move')}
      style={parseStyle(style)}
      data-widget-id={id}
      data-grid-w={span.w}
      data-grid-h={span.h}
    >
      {title ? (
        <CardHeader className="a2ui-dashboard-widget-header d-flex align-items-center justify-content-between border-bottom py-2">
          <CardTitle className="text-truncate xsmall fw-bold text-uppercase m-0">{title}</CardTitle>
          {edit_mode ? <span className="a2ui-dashboard-widget-drag-label xsmall">MOVE</span> : null}
        </CardHeader>
      ) : null}
      <CardBody className="a2ui-dashboard-widget-body p-3 overflow-auto flex-grow-1">{ExplicitList}</CardBody>
    </Card>
  );
};
