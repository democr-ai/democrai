import React from 'react';
import { parseStyle } from '@/utils/style';

export const getAlignmentClasses = (direction: 'row' | 'col', align: string = 'top') => {
  if (direction === 'row') {
    switch (align) {
      case 'center': return 'align-items-center';
      case 'bottom': return 'align-items-end';
      case 'fill': return 'align-items-stretch';
      case 'top':
      default:
        return 'align-items-start';
    }
  }

  // Vertical (Column)
  switch (align) {
    case 'bottom':
      return 'justify-content-end align-items-stretch';
    case 'left':
      return 'justify-content-start align-items-start';
    case 'right':
      return 'justify-content-start align-items-end';
    case 'center':
      return 'justify-content-center align-items-center';
    case 'fill':
    case 'top':
    default:
      return 'justify-content-start align-items-stretch';
  }
};

export const computePadding = (padding: any): React.CSSProperties => {
  if (!Array.isArray(padding) || padding.length !== 4) return {};
  return { padding: `${padding[0]}px ${padding[1]}px ${padding[2]}px ${padding[3]}px` };
};

export const Column: React.FC<any> = ({ ExplicitList, stretch, align = 'top', style, padding, width, max_width, ui_role }) => {
  const isStretch = stretch === true || stretch === 1 || (typeof stretch === 'number' && stretch > 0);
  const minWidth = width != null ? Number(width) : undefined;
  const maxWidth = max_width != null ? Number(max_width) : undefined;

  const normalizedUiRole = String(ui_role || '').trim();

  // Using d-flex flex-column to maintain the "Stack" behavior of SDUI Column
  return (
    <div
      data-ui-role={normalizedUiRole || undefined}
      className={`a2ui-column d-flex w-100 flex-column gap-2 ${normalizedUiRole} ${isStretch ? 'flex-grow-1 h-100' : ''} ${getAlignmentClasses('col', align)}`}
      style={{
        ...parseStyle(style),
        ...computePadding(padding),
        ...(Number.isFinite(minWidth as number) ? { minWidth } : {}),
        ...(Number.isFinite(maxWidth as number) ? { maxWidth } : {}),
        minWidth: Number.isFinite(minWidth as number) ? minWidth : 0,
        minHeight: 0,
      }}
    >
      {ExplicitList}
    </div>
  );
};
