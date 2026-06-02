import React from 'react';
import { parseStyle } from '@/utils/style';
import { cn } from '@/lib/utils';
import { computePadding } from './column';

export const Header: React.FC<any> = ({
  id,
  ExplicitList,
  leftExplicitList,
  centerExplicitList,
  rightExplicitList,
  style,
  padding,
  spacing = 8,
  stretch = true,
}) => {
  const leftNodes = React.Children.toArray(leftExplicitList);
  const rightNodes = React.Children.toArray(rightExplicitList);
  const centerNodes = React.Children.toArray(
    centerExplicitList && React.Children.count(centerExplicitList) > 0
      ? centerExplicitList
      : ExplicitList,
  );

  const slotGap = Number.isFinite(Number(spacing)) ? Number(spacing) : 8;

  return (
    <header
      id={id}
      className={cn('a2ui-header flex min-h-10 items-center border-b px-3 py-2', stretch && 'w-full')}
      style={{ ...parseStyle(style), ...computePadding(padding) }}
    >
      <div className="flex shrink-0 items-center" style={{ gap: slotGap }}>
        {leftNodes}
      </div>
      <div className="flex min-w-0 flex-1 items-center justify-center" style={{ gap: slotGap }}>
        {centerNodes}
      </div>
      <div className="flex shrink-0 items-center justify-end" style={{ gap: slotGap }}>
        {rightNodes}
      </div>
    </header>
  );
};
