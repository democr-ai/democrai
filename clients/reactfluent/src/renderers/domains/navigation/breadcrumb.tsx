import React from 'react';
import {
  Breadcrumb as FluentBreadcrumb,
  type IBreadcrumbItem,
  type IDividerAsProps,
} from '@fluentui/react';
import { parseStyle } from '@/utils/style';
import { getLiteral, toBoolean } from '@/renderers/shared';

export const Breadcrumb: React.FC<any> = ({ segments = [], separator = '/', onAction, style }) => {
  const separatorText = getLiteral(separator, '/');
  const items = Array.isArray(segments) ? segments : [];
  const fluentItems: IBreadcrumbItem[] = items.map((segment: any, index: number) => {
    const label = getLiteral(segment?.label);
    const current = toBoolean(segment?.current) || index === items.length - 1;
    const path = segment?.path;
    return {
      key: String(segment?.id || path || label || index),
      text: label,
      isCurrentItem: current,
      onClick: current || !path ? undefined : (ev?: React.MouseEvent<HTMLElement>) => {
        ev?.preventDefault();
        onAction?.('navigate', { path });
      },
    };
  });

  const dividerAs = React.useCallback((props?: IDividerAsProps) => (
    <span aria-hidden="true" className="ds-breadcrumb-separator">
      {separatorText}
    </span>
  ), [separatorText]);

  return (
    <nav className="ds-breadcrumb" aria-label="Breadcrumb" style={parseStyle(style)}>
      <FluentBreadcrumb
        items={fluentItems}
        className="ds-breadcrumb-list"
        dividerAs={dividerAs}
        maxDisplayedItems={items.length || 1}
        onReduceData={() => undefined}
      />
    </nav>
  );
};
