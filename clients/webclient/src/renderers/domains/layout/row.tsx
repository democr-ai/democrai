import React from 'react';
import { parseStyle } from '@/utils/style';
import { cn } from '@/lib/utils';
import { computePadding } from './column';

const getRowAlignmentClasses = (align: string = 'top') => {
  switch (align) {
    case 'left':
      return 'justify-start items-start';
    case 'right':
      return 'justify-end items-start';
    case 'center':
      return 'justify-center items-center';
    case 'bottom':
      return 'justify-start items-end';
    case 'fill':
      return 'justify-start items-stretch';
    case 'top':
    default:
      return 'justify-start items-start';
  }
};

export const Row: React.FC<any> = ({ ExplicitList, stretch, align = 'top', style, padding, spacing = 0, ui_role }) => {
  const isStretch = stretch === true || stretch === 1 || (typeof stretch === 'number' && stretch > 0);

  const normalizedUiRole = String(ui_role || '').trim();

  return (
    <div
      data-ui-role={normalizedUiRole || undefined}
      className={cn('flex min-h-0 w-full flex-row', isStretch && 'min-w-0 flex-1 h-full', getRowAlignmentClasses(align))}
      style={{ ...parseStyle(style), ...computePadding(padding), gap: spacing }}
    >
      {ExplicitList}
    </div>
  );
};
