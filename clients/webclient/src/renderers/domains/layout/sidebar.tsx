import React from 'react';
import { parseStyle } from '@/utils/style';
import { ScrollArea as UIScrollArea } from '@/components/ui/scroll-area';
import { Column } from './column';
import { cn } from '@/lib/utils';

export const Sidebar: React.FC<any> = ({
  id,
  ExplicitList,
  style,
  stretch = true,
  align = "top",
  padding = [8, 4, 8, 4],
  width,
  max_width,
  ui_role,
}) => {
  const isMainSidebar = id === 'main_sidebar';
  const childArray = React.Children.toArray(ExplicitList).filter(Boolean);

  const isSpacerNode = (node: React.ReactNode): boolean => {
    if (!React.isValidElement(node)) return false;
    const componentId = String((node.props as any)?.componentId || '');
    const nodeKey = String(node.key || '');
    return componentId === 'nav_spacer' || nodeKey.includes('nav_spacer');
  };
  const isTopNavNode = (node: React.ReactNode): boolean => {
    if (!React.isValidElement(node)) return false;
    const componentId = String((node.props as any)?.componentId || '');
    const nodeKey = String(node.key || '');
    return componentId === 'top_nav' || nodeKey.includes('top_nav');
  };

  const spacerIndex = isMainSidebar ? childArray.findIndex((n) => isSpacerNode(n)) : -1;
  const topNodesRaw = isMainSidebar
    ? (spacerIndex >= 0 ? childArray.slice(0, spacerIndex) : childArray)
    : childArray;
  const bottomNodes = isMainSidebar && spacerIndex >= 0 ? childArray.slice(spacerIndex + 1) : [];
  const topNavNode = isMainSidebar ? (topNodesRaw.find((node) => isTopNavNode(node)) || null) : null;
  const topFixedNodes = isMainSidebar ? topNodesRaw.filter((node) => !isTopNavNode(node)) : topNodesRaw;

  const resolvedPadding =
    Array.isArray(padding) && padding.length === 4 ? padding : [8, 4, 8, 4];
  const topPadding: [number, number, number, number] = [
    Number(resolvedPadding[0]) || 0,
    Number(resolvedPadding[1]) || 0,
    0,
    Number(resolvedPadding[3]) || 0,
  ];
  const bottomPadding: [number, number, number, number] = [
    0,
    Number(resolvedPadding[1]) || 0,
    Number(resolvedPadding[2]) || 0,
    Number(resolvedPadding[3]) || 0,
  ];

  const normalizedUiRole = String(ui_role || '').trim();

  return (
    <aside
      id={id}
      data-ui-role={normalizedUiRole || undefined}
      className={cn('h-full min-h-0 self-stretch overflow-hidden border-r bg-background', !isMainSidebar && 'module-sidebar-panel')}
      style={{
        ...parseStyle(style),
        ...(width != null && Number.isFinite(Number(width)) ? { minWidth: Number(width) } : {}),
        ...(max_width != null && Number.isFinite(Number(max_width)) ? { maxWidth: Number(max_width) } : {}),
      }}
    >
      {isMainSidebar ? (
        <div className="flex h-full min-h-0 flex-col">
          <div className="flex min-h-0 flex-1 flex-col" style={{ padding: `${topPadding[0]}px ${topPadding[1]}px ${topPadding[2]}px ${topPadding[3]}px` }}>
            {topFixedNodes}
            {topNavNode ? <div className="min-h-0 flex-1">{topNavNode}</div> : null}
          </div>
          {bottomNodes.length > 0 ? (
            <Column
              ExplicitList={bottomNodes}
              stretch={false}
              align={align}
              padding={bottomPadding}
              width={width}
              max_width={max_width}
            />
          ) : null}
        </div>
      ) : (
        <UIScrollArea className="h-full w-full">
          <Column
            ExplicitList={ExplicitList}
            stretch={stretch}
            align={align}
            padding={padding}
            width={width}
            max_width={max_width}
          />
        </UIScrollArea>
      )}
    </aside>
  );
};
