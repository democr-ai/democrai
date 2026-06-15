import React, { useEffect, useMemo, useState } from 'react';
import { InternalRenderer, normalizeActive } from '@/components/a2ui/Renderer';
import {
  Checkbox,
  DefaultButton,
  DirectionalHint,
  IconButton,
  type IContextualMenuItem,
} from '@fluentui/react';
import { resolveIconClass } from '@/renderers/domains/actions/button';
import { isNestedActionVisible, resolveActiveValue } from '@/renderers/rules';
import { readClientStateValue } from '@/state/clientState';

type ListSource = {
  type?: 'inline' | 'binding' | 'http' | 'websocket';
  data?: any;
  url?: string;
};

const resolvePath = (root: any, path: string): any => {
  const clean = path.replace(/^\//, '');
  if (!clean) return root;
  return clean.split('/').reduce((acc, segment) => {
    if (acc == null || typeof acc !== 'object') return undefined;
    return acc[segment];
  }, root);
};

const materializeContext = (ctx: Record<string, any>, item: Record<string, any>): Record<string, any> => {
  const resolve = (value: any): any => {
    if (typeof value === 'string') {
      if (value.startsWith('$item.')) {
        const key = value.slice(6);
        return key.split('.').reduce((acc, seg) => (acc == null ? undefined : acc[seg]), item);
      }

      const withMustache = value.replace(/\{\{\s*(.*?)\s*\}\}/g, (_m, p1) => {
        const key = String(p1 || '').trim().replace(/^item\./, '');
        const val = key.split('.').reduce((acc, seg) => (acc == null ? undefined : acc[seg]), item);
        return val == null ? '' : String(val);
      });

      return withMustache.replace(/\$item\.([A-Za-z0-9_.]+)/g, (_m, rawPath) => {
        const key = String(rawPath || '').trim();
        const val = key.split('.').reduce((acc, seg) => (acc == null ? undefined : acc[seg]), item);
        return val == null ? '' : String(val);
      });
    }

    if (Array.isArray(value)) return value.map(resolve);
    if (value && typeof value === 'object') {
      const next: Record<string, any> = {};
      Object.entries(value).forEach(([k, v]) => {
        next[k] = resolve(v);
      });
      return next;
    }

    return value;
  };

  return resolve(ctx || {});
};

const itemKey = (item: any, index: number): string => {
  const id = item?.id;
  if (id === undefined || id === null || id === '') {
    return `idx:${index}`;
  }
  return `id:${String(id)}`;
};

const normalizeAction = (action: any): { name: string; context: Record<string, any> } => {
  if (typeof action === 'string') {
    return { name: action, context: {} };
  }
  if (action && typeof action === 'object' && typeof action.name === 'string') {
    return {
      name: action.name,
      context: action.context && typeof action.context === 'object' ? action.context : {},
    };
  }
  return { name: '', context: {} };
};

const defaultItemPreview = (template: string, item: any) => {
  const iconClass = item?.icon ? resolveIconClass(item.icon) : '';
  const hasIcon = Boolean(iconClass);
  const iconColor = typeof item?.icon_color === 'string' ? item.icon_color.trim() : '';
  const iconStyle = iconColor ? ({ color: iconColor } as React.CSSProperties) : undefined;

  if (template === 'title_text') {
    return (
      <div className="a2ui-list-preview">
        {hasIcon ? <i className={`a2ui-list-preview-icon ${iconClass}`} style={iconStyle} /> : null}
        <div className="a2ui-list-preview-body">
          <div className="a2ui-list-preview-title">{String(item?.title || '')}</div>
          <div className="a2ui-list-preview-text">{String(item?.text || '')}</div>
        </div>
      </div>
    );
  }

  if (template === 'text') {
    return (
      <div className="a2ui-list-preview">
        {hasIcon ? <i className={`a2ui-list-preview-icon ${iconClass}`} style={iconStyle} /> : null}
        <div className="a2ui-list-preview-text">{String(item?.text || '')}</div>
      </div>
    );
  }

  return null;
};

export const List: React.FC<any> = ({
  id,
  orientation = 'vertical',
  dataSource,
  data_source,
  itemTemplate,
  item_template,
  template = 'custom',
  selectable = false,
  itemActions,
  item_actions,
  selectedItemsAction,
  selected_items_action,
  selectedItemsActionLabel,
  selected_items_action_label,
  onItemClick,
  on_item_click,
  surfaceId,
  surfaces,
  dataModel,
  stateModel,
  sendAction,
  onAction,
  setInput,
  userRole,
  userPermissions,
}) => {
  const [remoteItems, setRemoteItems] = useState<any[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const source: ListSource = dataSource || data_source || {};
  const resolvedItemTemplate = itemTemplate || item_template;
  const resolvedItemActions = Array.isArray(itemActions) ? itemActions : (Array.isArray(item_actions) ? item_actions : []);
  const resolvedSelectedItemsAction = selectedItemsAction || selected_items_action;
  const resolvedSelectedItemsActionLabel = selectedItemsActionLabel || selected_items_action_label;
  const resolvedOnItemClick = onItemClick || on_item_click;
  const sourceType = source.type || 'inline';
  const sourceUrl = source.url || '';
  const listSelectable = resolveActiveValue(selectable, {
    surfaceModel: surfaceId ? dataModel?.[surfaceId] : {},
    stateModel,
  });

  const emit = (actionSpec: any, itemCtx: Record<string, any>, extra: Record<string, any> = {}) => {
    const target = onAction || sendAction;
    if (!target) return;
    const { name, context } = normalizeAction(actionSpec);
    if (!name) return;
    const payload = {
      ...materializeContext(context || {}, itemCtx || {}),
      ...extra,
    };
    target(name, payload);
  };

  const bindingItems = useMemo(() => {
    if (sourceType !== 'binding') return [];
    const data = source.data;
    if (Array.isArray(data)) return data;
    if (data && typeof data === 'object' && typeof data.path === 'string') {
      if (String(data?.type || '').toLowerCase() === 'store') {
        const fromState = readClientStateValue(stateModel, String(data?.scope || 'auto').toLowerCase() as any, data.path);
        if (Array.isArray(fromState)) return fromState;
        return [];
      }
      const fromSurface = resolvePath(dataModel?.[surfaceId] || {}, data.path);
      if (Array.isArray(fromSurface)) return fromSurface;
    }
    return [];
  }, [sourceType, source.data, dataModel, surfaceId, stateModel]);

  useEffect(() => {
    if (sourceType !== 'http' && sourceType !== 'websocket') {
      setLoading(false);
      setError(null);
      return;
    }
    if (sourceType === 'http' && sourceUrl) {
      setLoading(true);
      setError(null);
      fetch(sourceUrl)
        .then((res) => res.json())
        .then((payload) => {
          setRemoteItems(Array.isArray(payload) ? payload : payload?.data || []);
          setLoading(false);
        })
        .catch((err) => {
          setError(String(err?.message || err));
          setLoading(false);
        });
      return;
    }
    if (sourceType === 'websocket' && sourceUrl) {
      setError(null);
      let wsUrl = sourceUrl;
      if (!wsUrl.startsWith('ws://') && !wsUrl.startsWith('wss://')) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname;
        const currentPort = window.location.port || (protocol === 'wss:' ? '443' : '80');
        const targetPort = currentPort === '5173' ? '8000' : currentPort;
        wsUrl = `${protocol}//${host}:${targetPort}/ws/stream/${wsUrl}`;
      }
      const ws = new WebSocket(wsUrl);
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (Array.isArray(payload)) {
            setRemoteItems(payload);
          } else if (payload && typeof payload === 'object' && Array.isArray(payload.data)) {
            setRemoteItems(payload.data);
          }
        } catch {}
      };
      ws.onerror = () => setError('Errore connessione websocket');
      return () => ws.close();
    }
    setRemoteItems([]);
    setLoading(false);
    setError(null);
  }, [sourceType, sourceUrl]);

  const items = useMemo(() => {
    if (sourceType === 'inline') return Array.isArray(source.data) ? source.data : [];
    if (sourceType === 'binding') return bindingItems;
    return remoteItems;
  }, [sourceType, source.data, bindingItems, remoteItems]);

  useEffect(() => {
    const allowed = new Set(items.map((item, index) => itemKey(item, index)));
    setSelectedKeys((prev) => prev.filter((key) => allowed.has(key)));
  }, [items]);

  const selectedItems = useMemo(() => {
    const selected = new Set(selectedKeys);
    return items.filter((item, index) => {
      if (!selected.has(itemKey(item, index))) return false;
      if (!listSelectable) return false;
      return Object.prototype.hasOwnProperty.call(item || {}, 'selectable')
        ? resolveActiveValue(item?.selectable, { surfaceModel: surfaceId ? dataModel?.[surfaceId] : {}, stateModel, item })
        : true;
    });
  }, [items, selectedKeys, listSelectable, surfaceId, dataModel, stateModel]);

  const selectedActionLabel = useMemo(() => {
    if (typeof resolvedSelectedItemsActionLabel === 'string' && resolvedSelectedItemsActionLabel.trim()) return resolvedSelectedItemsActionLabel.trim();
    if (resolvedSelectedItemsAction?.label) return String(resolvedSelectedItemsAction.label).trim();
    return 'Apply to selected';
  }, [resolvedSelectedItemsAction, resolvedSelectedItemsActionLabel]);

  const renderActionsMenu = (item: any, index: number, visibleItemActions: any[], className = '') => {
    const menuItems: IContextualMenuItem[] = visibleItemActions.map((entry: any, idx: number) => ({
      key: String(idx),
      text: String(entry?.label || 'Action'),
      iconProps: entry?.icon ? { className: resolveIconClass(entry.icon) || undefined } : undefined,
      onClick: (event) => {
        event?.preventDefault();
        event?.stopPropagation();
        emit(entry?.action, item || {}, { item, item_index: index });
      },
    }));

    return (
      <IconButton
        className={`a2ui-list-action-button ${className}`}
        iconProps={{ iconName: 'MoreVertical' }}
        menuIconProps={{ className: 'a2ui-list-action-menu-icon' }}
        ariaLabel="Item actions"
        title="Item actions"
        menuProps={{
          items: menuItems,
          directionalHint: DirectionalHint.bottomLeftEdge,
          calloutProps: {
            className: 'a2ui-list-action-menu',
            isBeakVisible: false,
          },
        }}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
        }}
      />
    );
  };

  if (loading) return <div className="a2ui-list-state">Loading...</div>;
  if (error) return <div className="a2ui-list-state a2ui-list-state-error">Error: {error}</div>;

  return (
    <div className="a2ui-list-shell">
      <div className="a2ui-list-stack">
        <div className={orientation === 'horizontal' ? 'a2ui-list a2ui-list-horizontal' : 'a2ui-list'}>
          {items.map((item, index) => {
            const key = item?.id || `${id}_item_${index}`;
            const logicalKey = itemKey(item, index);
            const isActive = normalizeActive(item?.active);
            const itemSelectable = listSelectable
              ? (Object.prototype.hasOwnProperty.call(item || {}, 'selectable')
                  ? resolveActiveValue(item?.selectable, { surfaceModel: surfaceId ? dataModel?.[surfaceId] : {}, stateModel, item })
                  : true)
              : false;
            const isSelected = itemSelectable && selectedKeys.includes(logicalKey);
            const visibleItemActions = resolvedItemActions.filter((entry: any) => isNestedActionVisible(
              entry,
              { surfaceModel: surfaceId ? dataModel?.[surfaceId] : {}, stateModel, item },
              String(userRole || 'Guest'),
              Array.isArray(userPermissions) ? userPermissions.map(String) : [],
            ));
            const hasItemActions = visibleItemActions.length > 0;
            const hasCustomTemplate = Boolean(resolvedItemTemplate);

            const renderedItem = resolvedItemTemplate ? (
              <InternalRenderer
                componentData={resolvedItemTemplate}
                surfaceId={surfaceId}
                surfaces={surfaces}
                dataModel={dataModel}
                stateModel={stateModel}
                sendAction={sendAction}
                setInput={setInput}
                componentId={String(key)}
                userRole={userRole}
                userPermissions={userPermissions}
                item={item}
              />
            ) : (
              defaultItemPreview(String(template || '').toLowerCase(), item)
            );

            return (
              <div
                key={key}
                onClick={() => {
                  if (listSelectable && itemSelectable) {
                    setSelectedKeys(prev => prev.includes(logicalKey) ? prev.filter(k => k !== logicalKey) : [...prev, logicalKey]);
                    return;
                  }
                  if (!resolvedOnItemClick) return;
                  emit(resolvedOnItemClick, item || {}, { item, item_index: index });
                }}
                className={`a2ui-list-row ${isActive ? 'a2ui-list-row-active' : ''} ${isSelected ? 'a2ui-list-row-selected' : ''} ${(resolvedOnItemClick || (listSelectable && itemSelectable)) ? 'a2ui-list-row-interactive' : ''}`}
              >
                <div className="a2ui-list-row-inner">
                  {listSelectable && (
                    <div className="a2ui-list-checkbox" onClick={e => e.stopPropagation()}>
                      <Checkbox
                        checked={isSelected}
                        disabled={!itemSelectable}
                        onChange={(_, checked) => {
                        setSelectedKeys(prev => checked ? [...prev, logicalKey] : prev.filter(k => k !== logicalKey));
                        }}
                      />
                    </div>
                  )}

                  {hasItemActions && !hasCustomTemplate && (
                    renderActionsMenu(item, index, visibleItemActions)
                  )}

                  <div className={`a2ui-list-row-content ${hasCustomTemplate && hasItemActions ? 'a2ui-list-row-content-card-actions' : ''}`}>
                    {hasItemActions && hasCustomTemplate && (
                      renderActionsMenu(item, index, visibleItemActions, 'a2ui-list-action-button-card')
                    )}
                    {renderedItem}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {resolvedSelectedItemsAction && listSelectable && isNestedActionVisible(
          resolvedSelectedItemsAction,
          { surfaceModel: surfaceId ? dataModel?.[surfaceId] : {}, stateModel },
          String(userRole || 'Guest'),
          Array.isArray(userPermissions) ? userPermissions.map(String) : [],
        ) ? (
          <div className="a2ui-list-selected-action">
            <DefaultButton
              className="a2ui-list-selected-action-button"
              disabled={selectedItems.length === 0}
              onClick={() => {
                emit(resolvedSelectedItemsAction, {
                  selected_items: selectedItems,
                  selected_count: selectedItems.length,
                  selected_ids: selectedItems.map((entry: any) => entry?.id).filter(Boolean),
                });
              }}
            >
              {`${selectedActionLabel} (${selectedItems.length})`}
            </DefaultButton>
          </div>
        ) : null}
      </div>
    </div>
  );
};
