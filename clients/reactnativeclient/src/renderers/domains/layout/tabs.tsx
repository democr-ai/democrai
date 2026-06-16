import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import { getLiteral } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';
import { A2UIRenderer } from '../../../components/a2ui/Renderer';

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
  tabs = [],
  ExplicitList,
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
  surfaceId,
  userRole,
  userPermissions,
  pendingActions,
  backgroundTasks,
  jwt,
  item,
}) => {
  const resolvedComponentId = String(componentId || comp_id || id || 'tabs');
  const list = Array.isArray(ExplicitList) ? ExplicitList : [];
  const tabsFromProps = Array.isArray(tabs) ? tabs : [];
  const [activeId, setActiveId] = useState<string | undefined>(undefined);
  const loadedRouteKeysRef = useRef<Record<string, true>>({});
  const requestedRouteKeysRef = useRef<Record<string, true>>({});
  const onActionRef = useRef(onAction);

  useEffect(() => {
    onActionRef.current = onAction;
  }, [onAction]);

  const propById = useMemo(
    () =>
      new Map<string, any>(
        tabsFromProps
          .filter((entry: any) => entry && typeof entry === 'object')
          .map((entry: any) => [String(entry.id || ''), entry]),
      ),
    [tabsFromProps],
  );

  const mergedTabs = React.useMemo(() => {
    return list.map((child: any, idx: number) => {
      const childId = String(child?.props?.componentId || tabsFromProps[idx]?.id || `tab_${idx}`);
      const fromProp = propById.get(childId) || tabsFromProps[idx] || {};
      const route = fromProp?.route ? String(fromProp.route) : null;
      return {
        id: childId,
        label: getLiteral(fromProp.label || fromProp.title || childId),
        icon: fromProp.icon || null,
        route,
        index: idx,
        surfaceId: route ? routeSurfaceId(resolvedComponentId, childId, idx) : null,
      };
    });
  }, [list, propById, resolvedComponentId, tabsFromProps]);

  const routeOnlyTabs = useMemo(
    () =>
      tabsFromProps
        .filter((entry: any) => entry?.route && !mergedTabs.some((tab: any) => tab.id === String(entry.id || '')))
        .map((entry: any, idx: number) => {
          const idValue = String(entry.id || `route_tab_${idx}`);
          return {
            id: idValue,
            label: getLiteral(entry.label || entry.title || idValue),
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
    stateModel?.current_path
      || stateModel?.currentPath
      || stateModel?.global?.current_path
      || stateModel?.global?.currentPath
      || '/',
  );
  const selectedFromPath = resolveTabFromPath(currentPath, resolvedComponentId, allTabs);
  const selectedTabId = allTabs.some((tab: any) => tab.id === activeId)
    ? activeId
    : (selectedFromPath || allTabs[0]?.id || '0');
  const selectedRouteTab = useMemo(
    () => allTabs.find((entry: any) => entry.id === selectedTabId),
    [allTabs, selectedTabId],
  );
  const selectedRoute = selectedRouteTab?.route ? String(selectedRouteTab.route) : '';
  const selectedSurfaceId = selectedRouteTab?.surfaceId ? String(selectedRouteTab.surfaceId) : '';
  const selectedRouteKey = selectedRoute && selectedSurfaceId ? `${selectedSurfaceId}|${selectedRoute}` : '';
  const selectedHostedSurface = selectedSurfaceId ? surfaces?.[selectedSurfaceId] : null;
  const selectedHostedRootId = selectedHostedSurface?.rootId || (selectedHostedSurface?.components?.root ? 'root' : '');

  useEffect(() => {
    if (!selectedRouteKey || !selectedRoute || !selectedSurfaceId) return;

    if (selectedHostedRootId) {
      loadedRouteKeysRef.current[selectedRouteKey] = true;
      delete requestedRouteKeysRef.current[selectedRouteKey];
      return;
    }

    if (loadedRouteKeysRef.current[selectedRouteKey] || requestedRouteKeysRef.current[selectedRouteKey]) return;

    requestedRouteKeysRef.current[selectedRouteKey] = true;
    onActionRef.current?.('render_route_surface', { path: selectedRoute, surface_id: selectedSurfaceId });
  }, [selectedHostedRootId, selectedRoute, selectedRouteKey, selectedSurfaceId]);

  const selectTab = (tabId: string) => {
    if (!tabId || !allTabs.some((entry: any) => entry.id === tabId)) return;
    setActiveId(tabId);
  };

  const renderHostedSurface = (tab: any) => {
    const hostedSurface = tab.surfaceId ? surfaces?.[tab.surfaceId] : null;
    const hostedRootId = hostedSurface?.rootId || (hostedSurface?.components?.root ? 'root' : '');
    const hostedRootData = hostedRootId ? hostedSurface?.components?.[hostedRootId] : null;
    const hostedRootType = hostedRootData?.component ? Object.keys(hostedRootData.component)[0] : '';
    const rootHasOwnScroll = hostedRootType === 'ScrollArea';
    if (!tab.surfaceId || !hostedRootId) {
      return (
        <View style={styles.loading}>
          <ActivityIndicator color="#8B949E" />
        </View>
      );
    }

    const content = (
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
        backgroundTasks={backgroundTasks}
        jwt={jwt}
        item={item}
        preserveRootStretch
        naturalRoot={!rootHasOwnScroll}
      />
    );

    return rootHasOwnScroll ? (
      <View style={styles.hostedSurface}>
        {content}
      </View>
    ) : (
      <ScrollView
        style={styles.hostedSurface}
        contentContainerStyle={styles.routeScrollContent}
        keyboardShouldPersistTaps="handled"
        directionalLockEnabled
        nestedScrollEnabled
      >
        {content}
      </ScrollView>
    );
  };

  return (
    <View style={[styles.container, stretch && styles.containerStretch, style]}>
      <View style={styles.tabBar}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {allTabs.map((tab: any) => {
            const isActive = tab.id === selectedTabId;
            return (
              <TouchableOpacity
                key={tab.id}
                style={[styles.tab, isActive && styles.tabActive]}
                onPress={() => selectTab(tab.id)}
                activeOpacity={0.7}
              >
                {tab.icon && (
                  <Icon 
                    name={tab.icon} 
                    size={18} 
                    color={isActive ? '#E6EDF3' : '#8B949E'}
                    style={styles.tabIcon} 
                  />
                )}
                <Text style={[styles.tabLabel, isActive && styles.tabLabelActive]}>
                  {tab.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>
      <View style={styles.content}>
        {mergedTabs.map((tab: any) => {
          const active = selectedTabId === tab.id;
          if (!active) return null;
          return tab.route ? renderHostedSurface(tab) : (list[tab.index] || <Text style={styles.emptyText}>No content for this tab.</Text>);
        })}
        {routeOnlyTabs.map((tab: any) => {
          const active = selectedTabId === tab.id;
          if (!active) return null;
          return renderHostedSurface(tab);
        })}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    width: '100%',
    minHeight: 0,
  },
  containerStretch: {
    flex: 1,
    minHeight: 0,
  },
  tabBar: {
    borderBottomWidth: 1,
    borderBottomColor: '#21262D',
    backgroundColor: '#161B22',
  },
  tab: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: {
    borderBottomColor: '#6366F1',
  },
  tabIcon: {
    marginRight: 6,
  },
  tabLabel: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '500',
    color: '#6E7681',
    flexShrink: 0,
  },
  tabLabelActive: {
    color: '#E6EDF3',
    fontWeight: '600',
  },
  content: {
    flex: 1,
    flexGrow: 1,
    alignSelf: 'stretch',
    width: '100%',
    padding: 12,
  },
  hostedSurface: {
    flex: 1,
    flexGrow: 1,
    alignSelf: 'stretch',
    width: '100%',
  },
  routeScrollContent: {
    width: '100%',
    paddingBottom: 24,
  },
  loading: {
    flex: 1,
    minHeight: 160,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyText: {
    textAlign: 'center',
    color: '#6E7681',
    marginTop: 20,
  },
});
