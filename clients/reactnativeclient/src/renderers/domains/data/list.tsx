import React from 'react';
import { Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View, ViewStyle } from 'react-native';
import { InternalRenderer } from '../../../components/a2ui/Renderer';
import { Icon } from '../../../components/a2ui/Icon';
import { emitActionSpec, getLiteral, materializeActionContext, parseActionSpec, toBoolean } from '../../shared';
import { resolveActiveValue } from '../../rules';

const resolvePath = (root: any, path: string): any => {
  const clean = String(path || '').replace(/^\//, '').replace(/\//g, '.');
  if (!clean) return root;
  return clean.split('.').filter(Boolean).reduce((acc, segment) => (
    acc == null || typeof acc !== 'object' ? undefined : acc[segment]
  ), root);
};

const readStateValue = (stateModel: any, scope: string, path: string): any => {
  const normalizedScope = String(scope || 'auto').toLowerCase();
  if (normalizedScope === 'page') return resolvePath(stateModel?.page, path);
  if (normalizedScope === 'global') {
    const scoped = resolvePath(stateModel?.global, path);
    return scoped !== undefined ? scoped : resolvePath(stateModel, path);
  }
  const page = resolvePath(stateModel?.page, path);
  if (page !== undefined) return page;
  const global = resolvePath(stateModel?.global, path);
  return global !== undefined ? global : resolvePath(stateModel, path);
};

const resolveItems = (dataSource: any, dataModel: any, stateModel: any, surfaceId: string): any[] => {
  const source = dataSource || {};
  const type = String(source?.type || 'inline').toLowerCase();
  if (Array.isArray(source)) return source;
  if (type === 'inline') return Array.isArray(source?.data) ? source.data : [];
  if (type === 'binding') {
    const data = source?.data;
    if (Array.isArray(data)) return data;
    if (data && typeof data === 'object' && typeof data.path === 'string') {
      if (String(data?.type || '').toLowerCase() === 'store') {
        const fromState = readStateValue(stateModel, String(data?.scope || 'auto'), data.path);
        return Array.isArray(fromState) ? fromState : [];
      }
      const fromSurface = resolvePath(dataModel?.[surfaceId] || {}, data.path);
      return Array.isArray(fromSurface) ? fromSurface : [];
    }
  }
  return [];
};

const normalizeTemplate = (template: any): any => {
  if (!template || typeof template !== 'object') return null;
  if (template.component) return template;
  const kind = String(template.kind || '').trim();
  if (!kind) return null;
  const { kind: _kind, children, id, ...props } = template;
  return {
    id,
    component: { [kind]: props },
    children: Array.isArray(children) ? { explicitList: children.map(normalizeTemplate).filter(Boolean) } : undefined,
  };
};

const itemKey = (item: any, index: number): string => {
  const id = item?.id;
  return id === undefined || id === null || id === '' ? `idx:${index}` : `id:${String(id)}`;
};

const sameStringList = (left: string[], right: string[]): boolean => (
  left.length === right.length && left.every((entry, index) => entry === right[index])
);

const isActionVisible = (action: any, stateModel: any, item: any): boolean => {
  if (!action || typeof action !== 'object') return true;
  if (action.show_if !== undefined && !resolveActiveValue(action.show_if, { stateModel, item })) return false;
  if (action.hide_if !== undefined && resolveActiveValue(action.hide_if, { stateModel, item })) return false;
  return true;
};

const normalizeActionLabel = (value: any, fallback: string): string => {
  const label = getLiteral(value, fallback);
  if (!label || label.startsWith('@t/') || label === 'list.confirm.selected_label') return fallback;
  return label;
};

const DefaultItem: React.FC<{ item: any; template: string }> = ({ item, template }) => {
  const icon = item?.icon;
  const text = getLiteral(item?.text ?? item?.label ?? '');

  if (template === 'title_text') {
    return (
      <View style={styles.defaultRow}>
        {icon ? <Icon name={icon} size={18} color={String(item?.icon_color || '') || '#8B949E'} /> : null}
        <View style={styles.defaultTextWrap}>
          <Text style={styles.itemTitle} numberOfLines={1}>{getLiteral(item?.title || '')}</Text>
          {text ? <Text style={styles.itemText} numberOfLines={2}>{text}</Text> : null}
        </View>
      </View>
    );
  }

  return (
    <View style={styles.defaultRow}>
      {icon ? <Icon name={icon} size={18} color={String(item?.icon_color || '') || '#8B949E'} /> : null}
      <Text style={styles.itemText}>{text}</Text>
    </View>
  );
};

export const List: React.FC<any> = ({
  id,
  dataSource,
  data_source,
  itemTemplate,
  item_template,
  template = 'text',
  orientation = 'vertical',
  selectable = false,
  itemActions,
  item_actions,
  selectedItemsAction,
  selected_items_action,
  selectedItemsActionLabel,
  selected_items_action_label,
  onItemClick,
  on_item_click,
  sendAction,
  onAction,
  stateModel,
  dataModel,
  surfaceId,
  surfaces,
  setInput,
  userRole,
  userPermissions,
  pendingActions,
  backgroundTasks,
  jwt,
  style,
}) => {
  const [selectedKeys, setSelectedKeys] = React.useState<string[]>([]);
  const [actionMenu, setActionMenu] = React.useState<{ item: any; index: number; actions: any[] } | null>(null);
  const source = dataSource ?? data_source;
  const items = React.useMemo(() => resolveItems(source, dataModel, stateModel, surfaceId), [source, dataModel, stateModel, surfaceId]);
  const normalizedTemplate = React.useMemo(() => normalizeTemplate(itemTemplate ?? item_template), [itemTemplate, item_template]);
  const actions = Array.isArray(itemActions ?? item_actions) ? (itemActions ?? item_actions) : [];
  const batchAction = selectedItemsAction ?? selected_items_action;
  const batchLabel = normalizeActionLabel(selectedItemsActionLabel ?? selected_items_action_label, 'Apply to selected');
  const emit = onAction || sendAction;
  const isHorizontal = String(orientation || 'vertical').toLowerCase() === 'horizontal';
  const listSelectable = resolveActiveValue(selectable, { stateModel });

  React.useEffect(() => {
    const allowed = new Set(items.map((item, index) => itemKey(item, index)));
    setSelectedKeys((previous) => {
      const next = previous.filter((key) => allowed.has(key));
      return sameStringList(previous, next) ? previous : next;
    });
  }, [items]);

  const toggleSelection = (item: any, index: number) => {
    const key = itemKey(item, index);
    setSelectedKeys((previous) => (
      previous.includes(key) ? previous.filter((entry) => entry !== key) : [...previous, key]
    ));
  };

  const selectedItems = React.useMemo(() => {
    const selected = new Set(selectedKeys);
    return items.filter((item, index) => selected.has(itemKey(item, index)));
  }, [items, selectedKeys]);

  const selectedIds = selectedItems.map((entry: any) => entry?.id).filter((entry: any) => entry != null);

  const emitItemAction = React.useCallback((actionSpec: any, item: any, index: number) => {
    const { name, context } = parseActionSpec(actionSpec);
    const actionWithoutContext = actionSpec && typeof actionSpec === 'object'
      ? { ...actionSpec, context: {} }
      : actionSpec;
    const itemContext = item && typeof item === 'object' ? item : {};
    const payload: Record<string, any> = {
      ...materializeActionContext(context, itemContext),
      item,
      item_index: index,
    };

    if ((name === 'nav' || name === 'navigate') && !payload.path) {
      payload.path = itemContext.path ?? itemContext.route;
    }

    emitActionSpec(actionWithoutContext, emit, payload);
  }, [emit]);

  return (
    <View style={[styles.container, style as ViewStyle]}>
      <ScrollView
        horizontal={isHorizontal}
        style={styles.scroll}
        contentContainerStyle={isHorizontal ? styles.horizontalContent : styles.verticalContent}
      >
        {items.map((item: any, index: number) => {
          const key = itemKey(item, index);
          const itemSelectable = listSelectable && (Object.prototype.hasOwnProperty.call(item || {}, 'selectable')
            ? resolveActiveValue(item?.selectable, { stateModel, item })
            : true);
          const isSelected = itemSelectable && selectedKeys.includes(key);
          const visibleActions = actions.filter((entry: any) => isActionVisible(entry, stateModel, item));
          const clickable = Boolean(onItemClick ?? on_item_click) || itemSelectable;

          return (
            <TouchableOpacity
              key={`${id || 'list'}_${key}`}
              style={[
                styles.item,
                isHorizontal && styles.itemHorizontal,
                toBoolean(item?.active) && styles.itemActive,
                isSelected && styles.itemSelected,
              ]}
              onPress={() => {
                if (itemSelectable) {
                  toggleSelection(item, index);
                  return;
                }
                emitItemAction(onItemClick ?? on_item_click, item, index);
              }}
              activeOpacity={clickable ? 0.72 : 1}
            >
              <View style={styles.itemInner}>
                {listSelectable ? (
                  <TouchableOpacity
                    disabled={!itemSelectable}
                    style={[styles.checkbox, isSelected && styles.checkboxSelected, !itemSelectable && styles.checkboxDisabled]}
                    onPress={() => itemSelectable && toggleSelection(item, index)}
                    activeOpacity={0.75}
                  >
                    {isSelected ? <Icon name="ri-check-line" size={14} color="#FFFFFF" /> : null}
                  </TouchableOpacity>
                ) : null}

                <View style={styles.itemBody}>
                  {normalizedTemplate ? (
                    <InternalRenderer
                      componentData={normalizedTemplate}
                      surfaceId={surfaceId}
                      surfaces={surfaces}
                      dataModel={dataModel}
                      stateModel={stateModel}
                      sendAction={sendAction}
                      setInput={setInput}
                      componentId={`${id || 'list'}_item_${index}`}
                      userRole={userRole}
                      userPermissions={userPermissions}
                      pendingActions={pendingActions}
                      backgroundTasks={backgroundTasks}
                      jwt={jwt}
                      item={item}
                    />
                  ) : (
                    <DefaultItem item={item} template={String(template || '').toLowerCase()} />
                  )}
                </View>

                {visibleActions.length > 0 ? (
                  <TouchableOpacity
                    style={styles.actionButton}
                    onPress={() => setActionMenu({ item, index, actions: visibleActions })}
                    activeOpacity={0.75}
                  >
                    <Icon name="ri-more-2-fill" size={18} color="#8B949E" />
                  </TouchableOpacity>
                ) : null}
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {batchAction && listSelectable ? (
        <TouchableOpacity
          style={[styles.batchButton, selectedItems.length === 0 && styles.batchButtonDisabled]}
          disabled={selectedItems.length === 0}
          onPress={() => emitActionSpec(batchAction, emit, {
            selected_items: selectedItems,
            selected_count: selectedItems.length,
            selected_ids: selectedIds,
          })}
          activeOpacity={0.75}
        >
          <Text style={styles.batchText}>{batchLabel} ({selectedItems.length})</Text>
        </TouchableOpacity>
      ) : null}

      <Modal transparent animationType="fade" visible={Boolean(actionMenu)} onRequestClose={() => setActionMenu(null)}>
        <TouchableOpacity style={styles.modalBackdrop} activeOpacity={1} onPress={() => setActionMenu(null)}>
          <TouchableOpacity style={styles.menu} activeOpacity={1}>
            {actionMenu?.actions.map((entry: any, index: number) => (
              <TouchableOpacity
                key={`list_action_${index}`}
                style={styles.menuItem}
                onPress={() => {
                  const current = actionMenu;
                  setActionMenu(null);
                  emitItemAction(entry?.action, current?.item, current?.index ?? index);
                }}
                activeOpacity={0.75}
              >
                {entry?.icon ? <Icon name={entry.icon} size={17} color="#8B949E" /> : null}
                <Text style={styles.menuText}>{getLiteral(entry?.label, 'Action')}</Text>
              </TouchableOpacity>
            ))}
          </TouchableOpacity>
        </TouchableOpacity>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
    gap: 8,
  },
  scroll: {
    width: '100%',
  },
  verticalContent: {
    width: '100%',
    gap: 8,
  },
  horizontalContent: {
    flexDirection: 'row',
    gap: 8,
    paddingRight: 8,
  },
  item: {
    width: '100%',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    overflow: 'hidden',
  },
  itemHorizontal: {
    width: 260,
  },
  itemActive: {
    borderColor: '#6366F1',
  },
  itemSelected: {
    borderColor: '#6366F1',
    backgroundColor: 'rgba(99,102,241,0.12)',
  },
  itemInner: {
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  itemBody: {
    flex: 1,
    minWidth: 0,
  },
  defaultRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  defaultTextWrap: {
    flex: 1,
    minWidth: 0,
  },
  itemTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#E6EDF3',
    marginBottom: 2,
  },
  itemText: {
    fontSize: 13,
    lineHeight: 18,
    color: '#8B949E',
  },
  checkbox: {
    width: 20,
    height: 20,
    borderWidth: 1,
    borderColor: '#484F58',
    borderRadius: 5,
    backgroundColor: '#0D1117',
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxSelected: {
    borderColor: '#6366F1',
    backgroundColor: '#6366F1',
  },
  checkboxDisabled: {
    opacity: 0.35,
  },
  actionButton: {
    width: 32,
    height: 32,
    borderRadius: 7,
    alignItems: 'center',
    justifyContent: 'center',
  },
  batchButton: {
    alignSelf: 'flex-start',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#21262D',
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  batchButtonDisabled: {
    opacity: 0.45,
  },
  batchText: {
    color: '#E6EDF3',
    fontSize: 13,
    fontWeight: '700',
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.38)',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  menu: {
    alignSelf: 'stretch',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 10,
    backgroundColor: '#0D1117',
    paddingVertical: 6,
  },
  menuItem: {
    minHeight: 44,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  menuText: {
    color: '#C9D1D9',
    fontSize: 14,
    fontWeight: '600',
  },
});
