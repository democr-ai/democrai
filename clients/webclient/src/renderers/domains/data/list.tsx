import React, { useEffect, useMemo, useState } from 'react';
import { InternalRenderer, normalizeActive } from '@/components/a2ui/Renderer';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { resolveIconClass } from '@/renderers/domains/actions/button';
import { isNestedActionVisible, resolveActiveValue } from '@/renderers/rules';
import { cn } from '@/lib/utils';
import { readClientStateValue } from '@/state/clientState';
import { emitActionSpec } from '@/renderers/shared';

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

const defaultItemPreview = (template: string, item: any) => {
  const iconClass = item?.icon ? resolveIconClass(item.icon) : '';
  const hasIcon = Boolean(iconClass);
  const iconColor = typeof item?.icon_color === 'string' ? item.icon_color.trim() : '';
  const iconStyle = iconColor ? ({ color: iconColor } as React.CSSProperties) : undefined;

  if (template === 'title_text') {
    return (
      <div className="flex min-w-0 items-start gap-2">
        {hasIcon ? <i className={cn(iconClass, 'self-center text-sm text-muted-foreground')} style={iconStyle} /> : null}
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold tracking-tight text-foreground">{String(item?.title || '')}</div>
          <div className="text-xs leading-snug text-muted-foreground">{String(item?.text || '')}</div>
        </div>
      </div>
    );
  }

  if (template === 'text') {
    return (
      <div className="flex min-w-0 items-start gap-2">
        {hasIcon ? <i className={cn(iconClass, 'self-center text-sm text-muted-foreground')} style={iconStyle} /> : null}
        <div className="text-sm">{String(item?.text || '')}</div>
      </div>
    );
  }

  return null;
};

export const List: React.FC<any> = ({
  id,
  orientation = 'vertical',
  dataSource,
  itemTemplate,
  template = 'custom',
  selectable = false,
  itemActions = [],
  selectedItemsAction,
  selectedItemsActionLabel,
  onItemClick,
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

  const source: ListSource = dataSource || {};
  const sourceType = source.type || 'inline';
  const sourceUrl = source.url || '';
  const listSelectable = resolveActiveValue(selectable, {
    surfaceModel: surfaceId ? dataModel?.[surfaceId] : {},
    stateModel,
  });

  const emit = (actionSpec: any, itemCtx: Record<string, any>, extra: Record<string, any> = {}) => {
    const target = onAction || sendAction;
    if (!target) return;
    const actionWithoutContext = actionSpec && typeof actionSpec === 'object'
      ? { ...actionSpec, context: {} }
      : actionSpec;
    const payload = {
      ...materializeContext(actionSpec?.context || {}, itemCtx || {}),
      ...extra,
    };
    emitActionSpec(actionWithoutContext, target, payload);
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
        } catch {
          // ignore malformed frame
        }
      };

      ws.onerror = () => {
        setError('Errore connessione websocket');
      };

      return () => ws.close();
    }

    setRemoteItems([]);
    setLoading(false);
    setError(null);
    return;
  }, [sourceType, sourceUrl]);

  const items = useMemo(() => {
    if (sourceType === 'inline') {
      return Array.isArray(source.data) ? source.data : [];
    }
    if (sourceType === 'binding') {
      return bindingItems;
    }
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
      const selectableByItem = Object.prototype.hasOwnProperty.call(item || {}, 'selectable')
        ? resolveActiveValue(item?.selectable, {
          surfaceModel: surfaceId ? dataModel?.[surfaceId] : {},
          stateModel,
          item,
        })
        : true;
      return selectableByItem;
    });
  }, [items, selectedKeys, listSelectable, surfaceId, dataModel, stateModel]);

  const selectedActionLabel = (() => {
    if (typeof selectedItemsActionLabel === 'string' && selectedItemsActionLabel.trim()) {
      return selectedItemsActionLabel.trim();
    }
    if (selectedItemsAction && typeof selectedItemsAction.label === 'string' && selectedItemsAction.label.trim()) {
      return selectedItemsAction.label.trim();
    }
    return 'Apply to selected';
  })();

  if (loading) return <div className="p-3 text-sm text-muted-foreground">Loading list...</div>;
  if (error) return <div className="p-3 text-sm text-destructive">Error: {error}</div>;

  return (
    <ScrollArea className="h-full w-full">
      <div className="w-full space-y-2">
        <div className={cn('w-full', orientation === 'horizontal' ? 'flex flex-row flex-wrap gap-2' : 'grid gap-2')}>
          {items.map((item, index) => {
            const key = item?.id || `${id}_item_${index}`;
            const logicalKey = itemKey(item, index);
            const isActive = normalizeActive(item?.active);
            const itemSelectable = listSelectable
              ? (
                Object.prototype.hasOwnProperty.call(item || {}, 'selectable')
                  ? resolveActiveValue(item?.selectable, {
                    surfaceModel: surfaceId ? dataModel?.[surfaceId] : {},
                    stateModel,
                    item,
                  })
                  : true
              )
              : false;
            const isSelected = itemSelectable && selectedKeys.includes(logicalKey);
            const visibleItemActions = Array.isArray(itemActions)
              ? itemActions.filter((entry: any) => isNestedActionVisible(
                  entry,
                  {
                    surfaceModel: surfaceId ? dataModel?.[surfaceId] : {},
                    stateModel,
                    item,
                  },
                  String(userRole || 'Guest'),
                  Array.isArray(userPermissions) ? userPermissions.map((entry: any) => String(entry)) : [],
                ))
              : [];
            const hasItemActions = visibleItemActions.length > 0;

            const renderedItem = itemTemplate ? (
              <InternalRenderer
                componentData={itemTemplate}
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
                    setSelectedKeys((prev) => (
                      prev.includes(logicalKey)
                        ? prev.filter((k) => k !== logicalKey)
                        : [...prev, logicalKey]
                    ));
                    return;
                  }

                  if (!onItemClick) return;
                  emit(onItemClick, item || {}, { item, item_index: index });
                }}
                className={cn(
                  'rounded-none border-b border-border/50 transition',
                  (onItemClick || (listSelectable && itemSelectable)) && 'cursor-pointer hover:bg-muted/40',
                  isActive && 'ring-2 ring-ring',
                  isSelected && 'border-primary/70 ring-1 ring-primary/40',
                )}
                data-active={isActive ? 'true' : 'false'}
                data-selected={isSelected ? 'true' : 'false'}
              >
                <div className="flex items-start gap-2 px-2 py-1.5">
                  {listSelectable ? (
                    <input
                      type="checkbox"
                      className="h-3.5 w-3.5 self-center"
                      checked={isSelected}
                      disabled={!itemSelectable}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(event) => {
                        const checked = event.currentTarget.checked;
                        setSelectedKeys((prev) => {
                          if (checked) {
                            if (!itemSelectable) return prev;
                            return prev.includes(logicalKey) ? prev : [...prev, logicalKey];
                          }
                          return prev.filter((k) => k !== logicalKey);
                        });
                      }}
                    />
                  ) : null}

                  <div className="min-w-0 flex-1">{renderedItem}</div>

                  {hasItemActions ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <i className={cn(resolveIconClass('ric.more-2-fill'), 'text-base')} />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {visibleItemActions.map((entry: any, idx: number) => (
                          <DropdownMenuItem
                            key={`${String(key)}_action_${idx}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              emit(entry?.action, item || {}, { item, item_index: index });
                            }}
                          >
                            {entry?.icon ? (
                              <i className={cn(resolveIconClass(entry.icon), 'mr-2 text-sm text-muted-foreground')} />
                            ) : null}
                            {String(entry?.label || 'Action')}
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>

        {selectedItemsAction && listSelectable && isNestedActionVisible(
          selectedItemsAction,
          {
            surfaceModel: surfaceId ? dataModel?.[surfaceId] : {},
            stateModel,
          },
          String(userRole || 'Guest'),
          Array.isArray(userPermissions) ? userPermissions.map((entry: any) => String(entry)) : [],
        ) ? (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={selectedItems.length === 0}
            onClick={() => {
              emit(
                selectedItemsAction,
                {
                  selected_items: selectedItems,
                  selected_count: selectedItems.length,
                  selected_ids: selectedItems
                    .map((entry: any) => entry?.id)
                    .filter((entry: any) => entry != null),
                },
                {
                  selected_items: selectedItems,
                  selected_count: selectedItems.length,
                  selected_ids: selectedItems
                    .map((entry: any) => entry?.id)
                    .filter((entry: any) => entry != null),
                },
              );
            }}
          >
            {`${selectedActionLabel} (${selectedItems.length})`}
          </Button>
        ) : null}
      </div>
    </ScrollArea>
  );
};
