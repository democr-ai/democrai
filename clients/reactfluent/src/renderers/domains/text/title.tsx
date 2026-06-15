import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';

export const Title: React.FC<any> = ({ text, level = 3, style, align = 'left' }) => {
  const safeLevel = Math.min(5, Math.max(1, Number(level) || 3));
  const Component = (`h${safeLevel}` as any);

  const classesByLevel: Record<number, string> = {
    1: 'h1 text-dark',
    2: 'h2 text-dark',
    3: 'h3 text-dark',
    4: 'h6 text-uppercase text-muted small tracking-wider',
    5: 'h6 text-uppercase text-muted xsmall tracking-wider',
  };

  const alignClass = align === 'center' ? 'text-center' : (align === 'right' ? 'text-end' : '');

  return (
    <Component
      className={`a2ui-title a2ui-title-level-${safeLevel} m-0 ${classesByLevel[safeLevel]} ${alignClass}`}
      style={parseStyle(style)}
    >
      {getLiteral(text)}
    </Component>
  );
};
