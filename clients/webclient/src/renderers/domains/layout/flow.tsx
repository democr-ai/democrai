import React from 'react';
import { parseStyle } from '@/utils/style';
import { cn } from '@/lib/utils';

const justifyFromAlign = (align: string) => {
  switch (String(align || 'left').toLowerCase()) {
    case 'center':
      return 'justify-center';
    case 'right':
    case 'end':
      return 'justify-end';
    case 'between':
      return 'justify-between';
    case 'around':
      return 'justify-around';
    case 'evenly':
      return 'justify-evenly';
    case 'left':
    case 'start':
    default:
      return 'justify-start';
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
      className={cn(
        'flex w-full min-w-0 flex-row flex-wrap items-stretch',
        justifyFromAlign(align),
        isStretch && 'min-h-0 h-full flex-1',
      )}
      style={{
        ...parseStyle(style),
        gap: Number(spacing) || 0,
      }}
    >
      {ExplicitList}
    </div>
  );
};
