import React from 'react';
import { parseStyle } from '@/utils/style';
import { cn } from '@/lib/utils';

export const getAlignmentClasses = (direction: 'row' | 'col', align: string = 'top') => {
  if (direction === 'row') {
    switch (align) {
      case 'center': return 'items-center';
      case 'bottom': return 'items-end';
      case 'fill': return 'items-stretch';
      case 'top':
      default:
        return 'items-start';
    }
  }

  // Desktop parity for Column:
  // - top/fill should not constrain horizontal stretch
  // - bottom moves content to the end on the vertical axis
  // - left/right/center can constrain horizontal placement
  switch (align) {
    case 'bottom':
      return 'justify-end items-stretch';
    case 'left':
      return 'justify-start items-start';
    case 'right':
      return 'justify-start items-end';
    case 'center':
      return 'justify-center items-center';
    case 'fill':
    case 'top':
    default:
      return 'justify-start items-stretch';
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

  return (
    <div
      data-ui-role={normalizedUiRole || undefined}
      className={cn(
        'flex w-full min-w-0 flex-col gap-2',
        normalizedUiRole,
        isStretch && 'min-h-0 flex-1 h-full',
        getAlignmentClasses('col', align),
      )}
      style={{
        ...parseStyle(style),
        ...computePadding(padding),
        ...(Number.isFinite(minWidth as number) ? { minWidth } : {}),
        ...(Number.isFinite(maxWidth as number) ? { maxWidth } : {}),
      }}
    >
      {ExplicitList}
    </div>
  );
};
