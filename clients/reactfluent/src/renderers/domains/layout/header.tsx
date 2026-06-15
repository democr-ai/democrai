import React from 'react';
import { parseStyle } from '@/utils/style';
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
      className={`a2ui-header d-flex align-items-center border-bottom px-3 py-2 ${stretch ? 'w-100' : ''}`}
      style={{ ...parseStyle(style), ...computePadding(padding), minHeight: '40px' }}
    >
      <div className="d-flex flex-shrink-0 align-items-center" style={{ gap: slotGap }}>
        {leftNodes}
      </div>
      <div className="d-flex flex-grow-1 min-vw-0 align-items-center justify-content-center" style={{ gap: slotGap }}>
        {centerNodes}
      </div>
      <div className="d-flex flex-shrink-0 align-items-center justify-content-end" style={{ gap: slotGap }}>
        {rightNodes}
      </div>
    </header>
  );
};
