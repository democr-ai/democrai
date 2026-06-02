import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { cn } from '@/lib/utils';

export const Title: React.FC<any> = ({ text, level = 3, style, align = 'left' }) => {
  const safeLevel = Math.min(5, Math.max(1, Number(level) || 3));
  const Component = (`h${safeLevel}` as any);

  const classesByLevel: Record<number, string> = {
    1: 'text-2xl md:text-3xl font-semibold tracking-tight text-foreground',
    2: 'text-xl md:text-2xl font-semibold tracking-tight text-foreground',
    3: 'text-lg md:text-xl font-semibold text-foreground',
    4: 'text-xs font-semibold uppercase tracking-[0.14em] text-foreground/85',
    5: 'text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground/80',
  };

  return (
    <Component
      className={cn(
        classesByLevel[safeLevel],
        align === 'center' && 'text-center',
        align === 'right' && 'text-right',
      )}
      style={parseStyle(style)}
    >
      {getLiteral(text)}
    </Component>
  );
};
