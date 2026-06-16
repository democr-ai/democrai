import React from 'react';
import { parseStyle } from '@/utils/style';
import { computePadding } from './column';

const getRowAlignmentClasses = (align: string = 'top') => {
  switch (align) {
    case 'left':
      return 'justify-content-start align-items-start';
    case 'right':
      return 'justify-content-end align-items-start';
    case 'center':
      return 'justify-content-center align-items-center';
    case 'bottom':
      return 'justify-content-start align-items-end';
    case 'fill':
      return 'justify-content-start align-items-stretch';
    case 'top':
    default:
      return 'justify-content-start align-items-start';
  }
};

export const Row: React.FC<any> = ({ ExplicitList, stretch, align = 'top', style, padding, spacing = 0, ui_role }) => {
  const isStretch = stretch === true || stretch === 1 || (typeof stretch === 'number' && stretch > 0);

  const normalizedUiRole = String(ui_role || '').trim();

  return (
    <div
      data-ui-role={normalizedUiRole || undefined}
      className={`a2ui-row d-flex w-100 flex-row ${isStretch ? 'flex-grow-1 h-100' : ''} ${getRowAlignmentClasses(align)}`}
      style={{ 
        ...parseStyle(style), 
        ...computePadding(padding), 
        gap: typeof spacing === 'number' ? `${spacing}px` : spacing,
        minHeight: 0,
        minWidth: 0,
      }}
    >
      {ExplicitList}
    </div>
  );
};
