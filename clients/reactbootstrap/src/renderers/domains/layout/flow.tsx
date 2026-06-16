import React from 'react';
import { parseStyle } from '@/utils/style';

const justifyFromAlign = (align: string) => {
  switch (String(align || 'left').toLowerCase()) {
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
    default:
      return 'justify-content-start';
  }
};

export const Flow: React.FC<any> = ({
  ExplicitList,
  spacing = 10,
  align = 'left',
  stretch,
  style,
}) => {
  const isStretch =
    stretch === true || stretch === 1 || (typeof stretch === 'number' && stretch > 0);

  return (
    <div
      className={`d-flex w-100 flex-row flex-wrap align-items-stretch ${justifyFromAlign(align)} ${isStretch ? 'min-vh-0 h-100 flex-grow-1' : ''}`}
      style={{
        ...parseStyle(style),
        gap: typeof spacing === 'number' ? `${spacing}px` : spacing,
      }}
    >
      {ExplicitList}
    </div>
  );
};
