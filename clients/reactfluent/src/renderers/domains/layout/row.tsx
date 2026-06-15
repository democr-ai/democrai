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

const getRowJustifyClass = (justify?: string) => {
  switch (justify) {
    case 'center':
      return 'justify-content-center';
    case 'right':
    case 'end':
      return 'justify-content-end';
    case 'between':
      return 'justify-content-between';
    case 'around':
      return 'justify-content-around';
    case 'evenly':
      return 'justify-content-evenly';
    case 'left':
    case 'start':
      return 'justify-content-start';
    default:
      return '';
  }
};

const getRowAlignItemsClass = (align: string = 'top') => {
  switch (align) {
    case 'center':
      return 'align-items-center';
    case 'bottom':
      return 'align-items-end';
    case 'fill':
      return 'align-items-stretch';
    case 'left':
    case 'right':
    case 'top':
    default:
      return 'align-items-start';
  }
};

export const Row: React.FC<any> = ({ ExplicitList, stretch, align = 'top', justify, style, padding, spacing = 0, ui_role }) => {
  const isStretch = stretch === true || stretch === 1 || (typeof stretch === 'number' && stretch > 0);
  const justifyClass = getRowJustifyClass(justify);
  const alignmentClasses = justifyClass
    ? `${justifyClass} ${getRowAlignItemsClass(align)}`
    : getRowAlignmentClasses(align);

  const normalizedUiRole = String(ui_role || '').trim();

  return (
    <div
      data-ui-role={normalizedUiRole || undefined}
      className={`a2ui-row d-flex w-100 flex-row ${isStretch ? 'flex-grow-1 h-100' : ''} ${alignmentClasses}`}
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
