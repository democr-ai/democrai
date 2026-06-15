import React, { useEffect, useMemo, useRef, useState } from 'react';
import { parseStyle } from '@/utils/style';
import { resolveIconClass } from '@/renderers/domains/actions/button';
import { Nav, NavItem, NavLink, TabContainer, TabContent, TabPane } from 'design-react-kit';
import { A2UIRenderer } from '@/components/a2ui/Renderer';
import { readClientStateValue } from '@/state/clientState';

const routeSurfaceId = (componentId: string, tabId: string, idx: number) => {
  const raw = `${componentId || 'tabs'}__tab_route__${tabId || idx}`;
  return raw.replace(/[^a-zA-Z0-9_]/g, '_');
};

const tabQueryKey = (componentId: string) => {
  const safe = String(componentId || 'tabs').replace(/[^a-zA-Z0-9_]/g, '_');
  return `tab_${safe}`;
};

const tabFromPathQuery = (path: string, componentId: string): string => {
  const query = String(path || '').split('?')[1] || '';
  const params = new URLSearchParams(query);
  return String(params.get(tabQueryKey(componentId)) || '').trim();
};

const pathWithTabQuery = (currentPath: string, tabId: string, componentId: string): string => {
  const [baseRaw, queryRaw = ''] = String(currentPath || '/').split('?');
  const base = baseRaw || '/';
  const params = new URLSearchParams(queryRaw);
  params.set(tabQueryKey(componentId), String(tabId));
  const query = params.toString();
  return query ? `${base}?${query}` : base;
};

const resolveTabFromPath = (currentPath: string, componentId: string, allTabs: any[]): string => {
  if (!allTabs.length) return '';
  const fromQuery = tabFromPathQuery(currentPath, componentId);
  if (fromQuery) {
    const byId = allTabs.find((entry) => entry.id === fromQuery);
    if (byId) return byId.id;
    const asIndex = Number.parseInt(fromQuery, 10);
    if (!Number.isNaN(asIndex) && asIndex >= 0 && asIndex < allTabs.length) {
      return allTabs[asIndex]?.id || allTabs[0]?.id || '0';
    }
  }
  return '';
};

export const Tabs: React.FC<any> = ({
  id,
  ExplicitList,
  tabs = [],
  stretch,
  style,
  onAction,
  componentId,
  comp_id,
  surfaces,
  dataModel,
  stateModel,
  sendAction,
  setInput,
  userRole,
  userPermissions,
  pendingActions,
  item,
}) => {
  const resolvedComponentId = String(componentId || comp_id || id || 'tabs');
  const list = Array.isArray(ExplicitList) ? ExplicitList : [];
  const [activeTab, setActiveTab] = useState('0');
  const [loadedRouteKeys, setLoadedRouteKeys] = useState<Record<string, true>>({});
  const [userChangedTab, setUserChangedTab] = useState(false);
  const lastNavigateRequestRef = useRef<string>('');
  const requestedRouteKeysRef = useRef<Record<string, true>>({});

  const toLabel = (value: any) => {
    if (typeof value === 'string') return value;
    if (value && typeof value === 'object' && typeof value.literalString === 'string') return value.literalString;
    return value == null ? '' : String(value);
  };

  const tabsFromProps = Array.isArray(tabs) ? tabs : [];
  const propById = useMemo(
    () =>
      new Map<string, any>(
        tabsFromProps
          .filter((entry: any) => entry && typeof entry === 'object')
          .map((entry: any) => [String(entry.id || ''), entry]),
      ),
    [tabsFromProps],
  );

  const mergedTabs = useMemo(
    () =>
      list.map((child: any, idx: number) => {
        const childId = String(child?.props?.componentId || `tab_${idx}`);
        const fromProp = propById.get(childId);
        const route = fromProp?.route ? String(fromProp.route) : null;
        return {
          id: childId,
          label: toLabel(fromProp?.label || childId),
          icon: fromProp?.icon || null,
          route,
          index: idx,
          surfaceId: route ? routeSurfaceId(resolvedComponentId, childId, idx) : null,
        };
      }),
    [list, propById, resolvedComponentId],
  );

  const routeOnlyTabs = useMemo(
    () =>
      tabsFromProps
        .filter((entry: any) => entry?.route && !mergedTabs.some((t) => t.id === entry.id))
        .map((entry: any, idx: number) => {
          const idValue = String(entry.id || `route_tab_${idx}`);
          return {
            id: idValue,
            label: toLabel(entry.label || idValue),
            icon: entry.icon || null,
            route: String(entry.route || ''),
            index: -1,
            surfaceId: routeSurfaceId(resolvedComponentId, idValue, idx),
          };
        }),
    [tabsFromProps, mergedTabs, resolvedComponentId],
  );

  const allTabs = useMemo(() => [...mergedTabs, ...routeOnlyTabs], [mergedTabs, routeOnlyTabs]);
  const currentPath = String(
    readClientStateValue(stateModel, 'global', '/current_path')
    || `${window.location.pathname || '/'}${window.location.search || ''}`,
  );
  const currentPathname = useMemo(() => {
    try {
      return new URL(currentPath, window.location.origin).pathname || '/';
    } catch {
      return String(currentPath || '/').split('?')[0] || '/';
    }
  }, [currentPath]);
  const previousPathnameRef = useRef<string>(currentPathname);

  useEffect(() => {
    if (previousPathnameRef.current === currentPathname) return;
    previousPathnameRef.current = currentPathname;
    requestedRouteKeysRef.current = {};
    setLoadedRouteKeys({});
  }, [currentPathname]);

  const tabFromLocation = resolveTabFromPath(currentPath, resolvedComponentId, allTabs);
  const selectedTabId = tabFromLocation || (allTabs.some((tab) => tab.id === activeTab) ? activeTab : (allTabs[0]?.id || '0'));

  useEffect(() => {
    if (!allTabs.length) return;
    if (activeTab !== selectedTabId) setActiveTab(selectedTabId);
  }, [activeTab, selectedTabId, allTabs.length]);

  useEffect(() => {
    const tab = allTabs.find((entry) => entry.id === selectedTabId);
    if (!tab?.route || !tab.surfaceId) return;
    const key = `${tab.surfaceId}|${tab.route}`;
    const hostedSurface = surfaces?.[tab.surfaceId];
    const hostedRootId = hostedSurface?.rootId || (hostedSurface?.components?.root ? 'root' : '');
    if (hostedRootId) {
      delete requestedRouteKeysRef.current[key];
      if (!loadedRouteKeys[key]) {
        setLoadedRouteKeys((prev) => ({ ...prev, [key]: true }));
      }
      return;
    }
    if (loadedRouteKeys[key]) return;
    if (requestedRouteKeysRef.current[key]) return;
    requestedRouteKeysRef.current[key] = true;
    onAction?.('render_route_surface', { path: tab.route, surface_id: tab.surfaceId });
  }, [allTabs, loadedRouteKeys, onAction, selectedTabId, surfaces]);

  useEffect(() => {
    if (!userChangedTab) return;
    const activeEntry = allTabs.find((entry) => entry.id === activeTab);
    if (!activeEntry) {
      setUserChangedTab(false);
      return;
    }
    const nextPath = pathWithTabQuery(currentPath, activeEntry.id, resolvedComponentId);
    if (nextPath !== currentPath && lastNavigateRequestRef.current !== nextPath) {
      lastNavigateRequestRef.current = nextPath;
      onAction?.('navigate', { path: nextPath, render: false });
    }
    setUserChangedTab(false);
  }, [userChangedTab, activeTab, allTabs, onAction, resolvedComponentId, currentPath]);

  const selectTab = (tabId: any) => {
    const nextTabId = String(tabId || '');
    if (!nextTabId || !allTabs.some((entry) => entry.id === nextTabId)) return;
    setActiveTab(nextTabId);
    setUserChangedTab(true);
  };

  return (
    <div
      data-component-id={resolvedComponentId}
      className={`a2ui-tabs a2ui-tabs-${resolvedComponentId} d-flex flex-column w-100 ${stretch ? 'flex-grow-1 min-vh-0' : ''}`}
      style={parseStyle(style)}
    >
      <TabContainer activeKey={selectedTabId} onSelect={selectTab}>
        <Nav tabs activeKey={selectedTabId} className="a2ui-tabs-nav mb-3">
          {allTabs.map((tab) => {
            const iconClass = tab.icon ? resolveIconClass(tab.icon) : null;
            return (
              <NavItem key={tab.id}>
                <NavLink
                  active={selectedTabId === tab.id}
                  eventKey={tab.id}
                  role="tab"
                  aria-selected={selectedTabId === tab.id}
                  onClick={() => selectTab(tab.id)}
                  className="cursor-pointer"
                >
                  {iconClass && <i className={`${iconClass} ${tab.label ? 'me-2' : ''}`} />}
                  {tab.label}
                </NavLink>
              </NavItem>
            );
          })}
        </Nav>

        <TabContent className="flex-grow-1 min-vh-0">
          {allTabs.map((tab) => {
            const shouldRenderContent = selectedTabId === tab.id;
            const hostedSurface = tab.surfaceId ? surfaces?.[tab.surfaceId] : null;
            const hostedRootId = hostedSurface?.rootId || (hostedSurface?.components?.root ? 'root' : '');

            return (
              <TabPane key={tab.id} eventKey={tab.id} className="h-100">
                {shouldRenderContent ? (
                  tab.route && tab.surfaceId ? (
                    hostedRootId ? (
                      <A2UIRenderer
                        surfaceId={tab.surfaceId}
                        componentId={hostedRootId}
                        surfaces={surfaces}
                        dataModel={dataModel}
                        stateModel={stateModel}
                        sendAction={sendAction}
                        setInput={setInput}
                        userRole={userRole}
                        userPermissions={userPermissions}
                        pendingActions={pendingActions}
                        item={item}
                      />
                    ) : <div className="h-100 w-100" />
                  ) : (
                    tab.index >= 0 ? list[tab.index] : <div className="h-100 w-100" />
                  )
                ) : <div className="h-100 w-100" />}
              </TabPane>
            );
          })}
        </TabContent>
      </TabContainer>
    </div>
  );
};
