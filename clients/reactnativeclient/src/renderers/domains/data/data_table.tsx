import React from 'react';
import { Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View, ViewStyle } from 'react-native';
import { getLiteral, emitActionSpec, toBoolean } from '../../shared';
import { resolveActiveValue } from '../../rules';
import { Icon } from '../../../components/a2ui/Icon';
import { usePhoneLayout, useResponsiveStyle } from '../../../utils/responsive';

const columnKey = (col: any): string => String(col?.field || col?.header || '').trim();

const rowKey = (row: any, index: number): string => String(row?.row_key ?? row?.rowKey ?? row?.id ?? index);
const EMPTY_ARRAY: any[] = [];
const EMPTY_OBJECT: Record<string, any> = {};

const resolvePath = (root: any, path: string): any => {
  const clean = String(path || '').replace(/^\//, '').replace(/\//g, '.');
  if (!clean) return root;
  return clean.split('.').filter(Boolean).reduce((acc, segment) => (
    acc == null || typeof acc !== 'object' ? undefined : acc[segment]
  ), root);
};

const currentPathFromState = (stateModel: any): string => {
  const fromGlobal = resolvePath(stateModel?.global, '/current_path');
  if (typeof fromGlobal === 'string' && fromGlobal.trim()) return fromGlobal.trim();
  const fromRoot = stateModel?.current_path ?? stateModel?.currentPath;
  return typeof fromRoot === 'string' && fromRoot.trim() ? fromRoot.trim() : '/';
};

const normalizeSortPayload = (sort: any, fallbackSort: any) => {
  const fallbackField = String(fallbackSort?.field || '').trim();
  const fallbackDirection = String(fallbackSort?.direction || 'desc').trim().toLowerCase() === 'asc' ? 'asc' : 'desc';
  const field = String(sort?.field || fallbackField).trim() || fallbackField;
  const direction = String(sort?.direction || fallbackDirection).trim().toLowerCase() === 'asc' ? 'asc' : 'desc';
  return { field, direction };
};

const parseTableQueryState = (
  currentPath: string,
  tableId: string,
  defaults: {
    page: number;
    pageSize: number;
    filters: Record<string, any>;
    sort: { field?: string; direction?: string };
  },
) => {
  const params = new URLSearchParams((String(currentPath || '').split('?')[1] || '').trim());
  const prefix = `${tableId}[`;
  const parsedFilters: Record<string, any> = {};

  params.forEach((rawValue, key) => {
    if (!key.startsWith(prefix) || !key.endsWith(']')) return;
    const innerKey = key.slice(prefix.length, -1).trim();
    if (!innerKey || ['page', 'page_size', 'sort_field', 'sort_direction'].includes(innerKey)) return;
    const value = String(rawValue || '').trim();
    if (value) parsedFilters[innerKey] = value;
  });

  const fallbackSort = normalizeSortPayload(defaults.sort, defaults.sort);
  const nextPage = Number.parseInt(String(params.get(`${tableId}[page]`) || defaults.page), 10);
  const nextPageSize = Number.parseInt(String(params.get(`${tableId}[page_size]`) || defaults.pageSize), 10);
  const nextSort = normalizeSortPayload(
    {
      field: String(params.get(`${tableId}[sort_field]`) || fallbackSort.field || '').trim(),
      direction: String(params.get(`${tableId}[sort_direction]`) || fallbackSort.direction || '').trim(),
    },
    fallbackSort,
  );

  return {
    page: Number.isFinite(nextPage) ? Math.max(0, nextPage) : Math.max(0, defaults.page),
    pageSize: Number.isFinite(nextPageSize) ? Math.max(1, nextPageSize) : Math.max(1, defaults.pageSize),
    filters: Object.keys(parsedFilters).length > 0 ? parsedFilters : (defaults.filters || {}),
    sort: nextSort,
  };
};

const normalizeColumns = (model: any, columns: any): any[] => {
  const source = Array.isArray(model) && model.length ? model : columns;
  return Array.isArray(source) ? source.filter((entry) => entry && typeof entry === 'object' && columnKey(entry)) : [];
};

const formatValue = (value: any): string => {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const isActionVisible = (action: any, stateModel: any, row: any): boolean => {
  if (!action || typeof action !== 'object') return true;
  if (action.show_if !== undefined && !resolveActiveValue(action.show_if, { stateModel, item: row })) return false;
  if (action.hide_if !== undefined && resolveActiveValue(action.hide_if, { stateModel, item: row })) return false;
  return true;
};

const actionLabel = (value: any, fallback: string): string => {
  const label = getLiteral(value, fallback);
  if (!label || label.startsWith('@t/')) return fallback;
  const last = label.split('.').filter(Boolean).pop();
  return last ? last.replace(/_/g, ' ') : label;
};

export const DataTable: React.FC<any> = ({
  id,
  model = EMPTY_ARRAY,
  columns = EMPTY_ARRAY,
  rows = EMPTY_ARRAY,
  data = EMPTY_ARRAY,
  page = 0,
  page_size = 25,
  total_rows,
  selectable = false,
  show_row_numbers = false,
  row_actions = [],
  selection_actions = [],
  paginated = true,
  pagination,
  filters: incomingFilters = EMPTY_OBJECT,
  sort: incomingSort = EMPTY_OBJECT,
  remote_service,
  auto_refresh,
  on_page_change,
  on_cell_edit,
  onAction,
  sendAction,
  stateModel,
  style,
}) => {
  const isPhone = usePhoneLayout();
  const responsiveStyle = useResponsiveStyle(style);
  const emit = onAction || sendAction;
  const normalizedRows = React.useMemo(() => {
    const source = Array.isArray(rows) && rows.length ? rows : data;
    return Array.isArray(source) ? source : [];
  }, [rows, data]);
  const normalizedCols = React.useMemo(() => normalizeColumns(model, columns), [model, columns]);
  const currentPath = currentPathFromState(stateModel);
  const queryState = React.useMemo(
    () => parseTableQueryState(currentPath, String(id || ''), {
      page: Number(page) || 0,
      pageSize: Number(page_size) || 25,
      filters: incomingFilters || {},
      sort: incomingSort || {},
    }),
    [currentPath, id, page, page_size, incomingFilters, incomingSort],
  );
  const remoteAction = remote_service || on_page_change;
  const lastRemoteQueryRef = React.useRef('');
  const [selectedKeys, setSelectedKeys] = React.useState<string[]>([]);
  const [actionMenu, setActionMenu] = React.useState<{ row: any; rowIndex: number; actions: any[] } | null>(null);

  const pageIndex = remote_service ? queryState.page : Math.max(0, Number(page) || 0);
  const pageSize = remote_service ? queryState.pageSize : Math.max(1, Number(page_size) || normalizedRows.length || 1);
  const totalRows = Number(total_rows ?? normalizedRows.length) || normalizedRows.length;
  const pageCount = Math.max(1, Math.ceil(Math.max(totalRows, 1) / pageSize));
  const showPagination = toBoolean(pagination ?? paginated) && (Boolean(remoteAction) || pageCount > 1);
  const visibleRows = React.useMemo(() => {
    if (!remoteAction && showPagination && normalizedRows.length > pageSize && totalRows === normalizedRows.length) {
      return normalizedRows.slice(pageIndex * pageSize, pageIndex * pageSize + pageSize);
    }
    return normalizedRows;
  }, [normalizedRows, pageIndex, pageSize, remoteAction, showPagination, totalRows]);

  const callTableAction = React.useCallback((action: any, ctx: Record<string, any>) => {
    emitActionSpec(action, emit, { ...ctx, tableId: id });
  }, [emit, id]);

  React.useEffect(() => {
    if (!remote_service) return;
    const requestPayload = {
      page: queryState.page,
      pageSize: queryState.pageSize,
      filters: queryState.filters,
      sort: queryState.sort,
    };
    const queryKey = JSON.stringify({ id, remote_service, currentPath, requestPayload });
    if (lastRemoteQueryRef.current === queryKey) return;
    lastRemoteQueryRef.current = queryKey;
    callTableAction(remote_service, requestPayload);
  }, [callTableAction, currentPath, id, queryState, remote_service]);

  React.useEffect(() => {
    if (!auto_refresh || Number(auto_refresh) < 1 || !remoteAction) return undefined;
    const interval = setInterval(() => {
      callTableAction(remoteAction, {
        page: remote_service ? queryState.page : pageIndex,
        pageSize,
        filters: remote_service ? queryState.filters : incomingFilters,
        sort: remote_service ? queryState.sort : incomingSort,
        autoRefresh: true,
      });
    }, Number(auto_refresh) * 1000);
    return () => clearInterval(interval);
  }, [auto_refresh, callTableAction, incomingFilters, incomingSort, pageIndex, pageSize, queryState, remoteAction, remote_service]);

  React.useEffect(() => {
    const allowed = new Set(normalizedRows.map((row, index) => rowKey(row, index)));
    setSelectedKeys((previous) => {
      const next = previous.filter((key) => allowed.has(key));
      return next.length === previous.length ? previous : next;
    });
  }, [normalizedRows]);

  const toggleRow = (row: any, index: number) => {
    if (!toBoolean(selectable) || !resolveActiveValue(row?.selectable ?? true, { stateModel, item: row })) return;
    const key = rowKey(row, index);
    setSelectedKeys((previous) => (
      previous.includes(key) ? previous.filter((entry) => entry !== key) : [...previous, key]
    ));
  };

  const selectedRows = normalizedRows.filter((row, index) => selectedKeys.includes(rowKey(row, index)));
  const selectedIds = selectedRows.map((row: any) => row?.id).filter((value: any) => value != null);

  const emitPageChange = (nextPage: number) => {
    callTableAction(remote_service || on_page_change, {
      page: Math.max(0, Math.min(pageCount - 1, nextPage)),
      pageSize,
      filters: remote_service ? queryState.filters : incomingFilters,
      sort: remote_service ? queryState.sort : incomingSort,
    });
  };

  const renderSelectionBar = () => (
    selectedKeys.length > 0 && Array.isArray(selection_actions) && selection_actions.length > 0 ? (
      <View style={styles.selectionBar}>
        <Text style={styles.selectionText}>{selectedKeys.length} selected</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.selectionActions}>
          {selection_actions.filter((entry: any) => isActionVisible(entry, stateModel, null)).map((entry: any, index: number) => (
            <TouchableOpacity
              key={`selection_action_${index}`}
              style={[styles.smallButton, entry?.variant === 'danger' && styles.dangerButton]}
              onPress={() => emitActionSpec(entry?.action, emit, {
                selected_ids: selectedIds,
                selected_rows: selectedRows,
                tableId: id,
              })}
              activeOpacity={0.75}
            >
              {entry?.icon ? <Icon name={entry.icon} size={15} color="#E6EDF3" /> : null}
              <Text style={styles.smallButtonText}>{actionLabel(entry?.label, 'Action')}</Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity style={styles.smallButtonGhost} onPress={() => setSelectedKeys([])} activeOpacity={0.75}>
            <Text style={styles.smallButtonGhostText}>Clear</Text>
          </TouchableOpacity>
        </ScrollView>
      </View>
    ) : null
  );

  const renderPagination = () => (
    showPagination ? (
      <View style={styles.pagination}>
        <Text style={styles.pageInfo}>{totalRows} rows · page {pageIndex + 1}/{pageCount}</Text>
        <View style={styles.pageButtons}>
          <TouchableOpacity
            style={[styles.pageButton, pageIndex <= 0 && styles.pageButtonDisabled]}
            disabled={pageIndex <= 0}
            onPress={() => emitPageChange(pageIndex - 1)}
            activeOpacity={0.75}
          >
            <Icon name="ri-arrow-left-s-line" size={19} color={pageIndex <= 0 ? '#484F58' : '#C9D1D9'} />
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.pageButton, pageIndex >= pageCount - 1 && styles.pageButtonDisabled]}
            disabled={pageIndex >= pageCount - 1}
            onPress={() => emitPageChange(pageIndex + 1)}
            activeOpacity={0.75}
          >
            <Icon name="ri-arrow-right-s-line" size={19} color={pageIndex >= pageCount - 1 ? '#484F58' : '#C9D1D9'} />
          </TouchableOpacity>
        </View>
      </View>
    ) : (
      <Text style={styles.tableMeta}>{totalRows} rows</Text>
    )
  );

  const renderActionMenu = () => (
    <Modal transparent animationType="fade" visible={Boolean(actionMenu)} onRequestClose={() => setActionMenu(null)}>
      <TouchableOpacity style={styles.modalBackdrop} activeOpacity={1} onPress={() => setActionMenu(null)}>
        <TouchableOpacity style={styles.menu} activeOpacity={1}>
          {actionMenu?.actions.map((entry: any, index: number) => (
            <TouchableOpacity
              key={`datatable_action_${index}`}
              style={styles.menuItem}
              onPress={() => {
                const current = actionMenu;
                setActionMenu(null);
                emitActionSpec(entry?.action, emit, {
                  item: current?.row,
                  row: current?.row,
                  rowIndex: current?.rowIndex,
                  item_id: current?.row?.id,
                  tableId: id,
                });
              }}
              activeOpacity={0.75}
            >
              {entry?.icon ? <Icon name={entry.icon} size={17} color={entry?.variant === 'danger' ? '#FF7B72' : '#8B949E'} /> : null}
              <Text style={[styles.menuText, entry?.variant === 'danger' && styles.menuDangerText]}>{actionLabel(entry?.label, 'Action')}</Text>
            </TouchableOpacity>
          ))}
        </TouchableOpacity>
      </TouchableOpacity>
    </Modal>
  );

  const cellWidth = isPhone ? 116 : 132;
  const hasRowActions = Array.isArray(row_actions) && row_actions.length > 0;

  return (
    <View style={[styles.container, isPhone && styles.mobileTableContainer, responsiveStyle as ViewStyle]}>
      {renderSelectionBar()}
      {renderPagination()}
      <View style={styles.tableFrame}>
        {hasRowActions ? (
          <View style={styles.fixedActionColumn}>
            <View style={[styles.header, styles.fixedActionHeader]}>
              <View style={[styles.cell, isPhone && styles.mobileCell, styles.actionCell, isPhone && styles.mobileActionCell]} />
            </View>
            <View style={styles.body}>
              {visibleRows.map((row: any, rowIdx: number) => {
                const absoluteRowIndex = normalizedRows.indexOf(row);
                const resolvedRowIndex = absoluteRowIndex >= 0 ? absoluteRowIndex : rowIdx;
                const key = rowKey(row, resolvedRowIndex);
                const actions = row_actions.filter((entry: any) => isActionVisible(entry, stateModel, row));
                const isSelected = selectedKeys.includes(key);
                return (
                  <View key={`fixed_action_${key}`} style={[styles.row, rowIdx % 2 === 1 && styles.rowAlt, isSelected && styles.rowSelected]}>
                    <TouchableOpacity
                      style={[styles.cell, isPhone && styles.mobileCell, styles.actionCell, isPhone && styles.mobileActionCell]}
                      onPress={() => setActionMenu({ row, rowIndex: resolvedRowIndex, actions })}
                      activeOpacity={0.75}
                    >
                      <Icon name="ri-more-2-fill" size={18} color="#8B949E" />
                    </TouchableOpacity>
                  </View>
                );
              })}
            </View>
          </View>
        ) : null}
        <ScrollView horizontal showsHorizontalScrollIndicator directionalLockEnabled nestedScrollEnabled>
          <View>
            <View style={styles.header}>
              {toBoolean(selectable) ? <View style={[styles.cell, isPhone && styles.mobileCell, styles.checkCell, isPhone && styles.mobileCheckCell]} /> : null}
              {show_row_numbers ? (
                <View style={[styles.cell, isPhone && styles.mobileCell, styles.numberCell, isPhone && styles.mobileNumberCell]}>
                  <Text style={[styles.headerText, isPhone && styles.mobileHeaderText]}>#</Text>
                </View>
              ) : null}
              {normalizedCols.map((col: any, idx: number) => (
                <View key={`head_${idx}`} style={[styles.cell, isPhone && styles.mobileCell, { width: Number(col.width) || cellWidth }]}>
                  <Text style={[styles.headerText, isPhone && styles.mobileHeaderText]} numberOfLines={1}>
                    {getLiteral(col.label || col.header || col.field)}
                  </Text>
                </View>
              ))}
            </View>
            <View style={styles.body}>
              {visibleRows.map((row: any, rowIdx: number) => {
                const absoluteRowIndex = normalizedRows.indexOf(row);
                const resolvedRowIndex = absoluteRowIndex >= 0 ? absoluteRowIndex : rowIdx;
                const key = rowKey(row, resolvedRowIndex);
                const isSelectable = toBoolean(selectable) && resolveActiveValue(row?.selectable ?? true, { stateModel, item: row });
                const isSelected = selectedKeys.includes(key);
                return (
                  <View key={`row_${key}`} style={[styles.row, rowIdx % 2 === 1 && styles.rowAlt, isSelected && styles.rowSelected]}>
                    {toBoolean(selectable) ? (
                      <TouchableOpacity
                        style={[styles.cell, isPhone && styles.mobileCell, styles.checkCell, isPhone && styles.mobileCheckCell]}
                        disabled={!isSelectable}
                        onPress={() => toggleRow(row, resolvedRowIndex)}
                        activeOpacity={0.75}
                      >
                        <View style={[styles.checkbox, isSelected && styles.checkboxSelected, !isSelectable && styles.checkboxDisabled]}>
                          {isSelected ? <Icon name="ri-check-line" size={14} color="#FFFFFF" /> : null}
                        </View>
                      </TouchableOpacity>
                    ) : null}
                    {show_row_numbers ? (
                      <View style={[styles.cell, isPhone && styles.mobileCell, styles.numberCell, isPhone && styles.mobileNumberCell]}>
                        <Text style={styles.cellMuted}>{resolvedRowIndex + 1}</Text>
                      </View>
                    ) : null}
                    {normalizedCols.map((col: any, colIdx: number) => (
                      <View key={`cell_${rowIdx}_${colIdx}`} style={[styles.cell, isPhone && styles.mobileCell, { width: Number(col.width) || cellWidth }]}>
                        <Text style={[styles.cellText, isPhone && styles.mobileTableText]} numberOfLines={isPhone ? 1 : 2}>
                          {formatValue(row[col.field])}
                        </Text>
                      </View>
                    ))}
                  </View>
                );
              })}
            </View>
          </View>
        </ScrollView>
      </View>
      {renderActionMenu()}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    maxHeight: 460,
    overflow: 'hidden',
  },
  mobileContainer: {
    maxHeight: undefined,
    padding: 10,
    gap: 10,
  },
  mobileTableContainer: {
    maxHeight: undefined,
  },
  selectionBar: {
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#21262D',
    padding: 9,
    gap: 8,
  },
  selectionText: {
    color: '#E6EDF3',
    fontSize: 13,
    fontWeight: '800',
  },
  selectionActions: {
    gap: 8,
  },
  smallButton: {
    minHeight: 32,
    borderRadius: 7,
    backgroundColor: '#30363D',
    paddingHorizontal: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dangerButton: {
    backgroundColor: '#2A1216',
  },
  smallButtonText: {
    color: '#E6EDF3',
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'capitalize',
  },
  smallButtonGhost: {
    minHeight: 32,
    borderRadius: 7,
    paddingHorizontal: 9,
    justifyContent: 'center',
  },
  smallButtonGhostText: {
    color: '#8B949E',
    fontSize: 12,
    fontWeight: '700',
  },
  pagination: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  tableMeta: {
    color: '#8B949E',
    fontSize: 12,
    paddingLeft: 8,
    paddingRight: 2,
  },
  pageInfo: {
    color: '#8B949E',
    fontSize: 12,
    flex: 1,
  },
  pageButtons: {
    flexDirection: 'row',
    gap: 6,
  },
  pageButton: {
    width: 32,
    height: 32,
    borderRadius: 7,
    borderWidth: 1,
    borderColor: '#30363D',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#161B22',
  },
  pageButtonDisabled: {
    opacity: 0.55,
  },
  tableFrame: {
    flexDirection: 'row',
    width: '100%',
    minWidth: 0,
  },
  fixedActionColumn: {
    zIndex: 2,
    elevation: 2,
    backgroundColor: '#161B22',
    borderRightWidth: 1,
    borderRightColor: '#30363D',
  },
  fixedActionHeader: {
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
  },
  mobileCard: {
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#0D1117',
    overflow: 'hidden',
  },
  mobileCardSelected: {
    borderColor: '#6366F1',
    backgroundColor: 'rgba(99,102,241,0.11)',
  },
  mobileHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
  },
  mobileTitleWrap: {
    flex: 1,
    minWidth: 0,
  },
  mobileTitle: {
    color: '#E6EDF3',
    fontSize: 15,
    fontWeight: '800',
    lineHeight: 20,
  },
  mobileSub: {
    color: '#6E7681',
    fontSize: 11,
    marginTop: 2,
  },
  mobileFields: {
    padding: 12,
    gap: 9,
  },
  mobileField: {
    gap: 2,
  },
  mobileLabel: {
    color: '#8B949E',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  mobileValue: {
    color: '#C9D1D9',
    fontSize: 13,
    lineHeight: 18,
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
  header: {
    flexDirection: 'row',
    backgroundColor: '#21262D',
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
    minHeight: 43,
  },
  headerText: {
    fontSize: 12,
    fontWeight: '800',
    color: '#E6EDF3',
  },
  body: {
    minHeight: 100,
  },
  row: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
    minHeight: 45,
  },
  rowAlt: {
    backgroundColor: '#0D1117',
  },
  rowSelected: {
    backgroundColor: 'rgba(99,102,241,0.1)',
  },
  cell: {
    padding: 12,
    justifyContent: 'center',
  },
  mobileCell: {
    paddingHorizontal: 9,
    paddingVertical: 10,
    minHeight: 42,
  },
  checkCell: {
    width: 44,
    alignItems: 'center',
  },
  mobileCheckCell: {
    width: 38,
  },
  numberCell: {
    width: 42,
  },
  mobileNumberCell: {
    width: 36,
  },
  actionCell: {
    width: 44,
    alignItems: 'center',
  },
  mobileActionCell: {
    width: 38,
  },
  cellText: {
    fontSize: 13,
    color: '#C9D1D9',
  },
  mobileTableText: {
    fontSize: 12,
    lineHeight: 16,
  },
  mobileHeaderText: {
    fontSize: 11,
  },
  cellMuted: {
    fontSize: 12,
    color: '#8B949E',
  },
  empty: {
    color: '#6E7681',
    fontSize: 13,
    padding: 12,
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
    textTransform: 'capitalize',
  },
  menuDangerText: {
    color: '#FF7B72',
  },
});
