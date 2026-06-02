import React from 'react';
import { parseStyle } from '@/utils/style';

export const Grid: React.FC<any> = ({ ExplicitList, columns = 2, spacing = 10, style }) => (
  <div
    className="grid w-full"
    style={{
      gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
      gap: spacing,
      ...parseStyle(style),
    }}
  >
    {ExplicitList}
  </div>
);
