import React, { useState, useMemo, useCallback } from 'react';
import { useA2UI } from '@/hooks/useA2UI';
import { useAutoRefresh } from '../../../hooks/useAutoRefresh';
import { evaluateRule, hasRequiredPermissions, isNestedActionVisible, isSuperRole } from '../../rules';
import { applyTransform } from './cell_formatters';
import { emitActionSpec } from '@/renderers/shared';
import {
  Checkbox,
  DefaultButton,
  DirectionalHint,
  Dropdown,
  IconButton,
  PrimaryButton,
  TextField,
  type IContextualMenuItem,
} from '@fluentui/react';
import { resolveIconClass } from '../../../utils/icons';
import { readClientStateValue } from '@/state/clientState';

const normalizePermissions = (value: unknown): string[] => {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => String(entry)).filter(Boolean);
};

const resolveAccessContext = (stateModel: any, userRole: string, userPermissions: string[]) => {
  const storeRoleValue = readClientStateValue(stateModel, 'global', '/auth/role');
  const storeRole = typeof storeRoleValue === 'string' ? String(storeRoleValue) : '';
  const storePermissions = normalizePermissions(readClientStateValue(stateModel, 'global', '/auth/permissions'));
  const permissionsLoaded = readClientStateValue(stateModel, 'global', '/auth/permissions_loaded') === true;
  const shouldUseStore = permissionsLoaded || storePermissions.length > 0 || Boolean(storeRole && storeRole.toLowerCase() !== 'guest');
  return {
    role: shouldUseStore ? (storeRole || userRole || 'Guest') : (userRole || 'Guest'),
    permissions: shouldUseStore ? storePermissions : normalizePermissions(userPermissions),
  };
};

const RESERVED_TABLE_KEYS = new Set(['page', 'page_size', 'sort_field', 'sort_direction']);
const MIN_COLUMN_WIDTH = 72;

const columnKey = (col: any) => String(col?.field || col?.header || '').trim();

const rowKey = (row: any, rowIndex: number): string => String(row?.row_key ?? row?.rowKey ?? row?.id ?? rowIndex);

const normalizeSortPayload = (sort: any, fallbackSort: any) => {
  const fallbackField = String(fallbackSort?.field || '').trim();
  const fallbackDirection = String(fallbackSort?.direction || 'desc').trim().toLowerCase() === 'asc' ? 'asc' : 'desc';
  const field = String(sort?.field || fallbackField).trim() || fallbackField;
  const direction = String(sort?.direction || fallbackDirection).trim().toLowerCase() === 'asc' ? 'asc' : 'desc';
  return { field, direction };
};

const currentPathFromState = (stateModel: any): string => {
  const fromStore = readClientStateValue(stateModel, 'global', '/current_path');
  if (typeof fromStore === 'string' && fromStore.trim()) return fromStore.trim();
  return `${window.location.pathname || '/'}${window.location.search || ''}`;
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
  const params = new URLSearchParams((currentPath.split('?')[1] || '').trim());
  const prefix = `${tableId}[`;
  const parsedFilters: Record<string, any> = {};

  params.forEach((rawValue, key) => {
    if (!key.startsWith(prefix) || !key.endsWith(']')) return;
    const innerKey = key.slice(prefix.length, -1).trim();
    if (!innerKey || RESERVED_TABLE_KEYS.has(innerKey)) return;
    const value = String(rawValue || '').trim();
    if (!value) return;
    parsedFilters[innerKey] = value;
  });

  const fallbackSort = normalizeSortPayload(defaults.sort, defaults.sort);
  const pageRaw = String(params.get(`${tableId}[page]`) || '').trim();
  const pageSizeRaw = String(params.get(`${tableId}[page_size]`) || '').trim();
  const sortFieldRaw = String(params.get(`${tableId}[sort_field]`) || '').trim();
  const sortDirectionRaw = String(params.get(`${tableId}[sort_direction]`) || '').trim().toLowerCase();

  const nextPage = Number.parseInt(pageRaw || `${defaults.page}`, 10);
  const nextPageSize = Number.parseInt(pageSizeRaw || `${defaults.pageSize}`, 10);
  const nextSort = normalizeSortPayload(
    {
      field: sortFieldRaw || fallbackSort.field,
      direction: sortDirectionRaw || fallbackSort.direction,
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

const pathWithTableQuery = (
  currentPath: string,
  tableId: string,
  state: {
    page: number;
    pageSize: number;
    filters: Record<string, any>;
    sort: { field?: string; direction?: string };
  },
): string => {
  const [pathnameRaw, queryRaw = ''] = currentPath.split('?');
  const pathname = pathnameRaw || '/';
  const params = new URLSearchParams(queryRaw);
  const prefix = `${tableId}[`;

  Array.from(params.keys()).forEach((key) => {
    if (key.startsWith(prefix)) params.delete(key);
  });

  params.set(`${tableId}[page]`, String(Math.max(0, Number(state.page) || 0)));
  params.set(`${tableId}[page_size]`, String(Math.max(1, Number(state.pageSize) || 1)));
  if (state.sort?.field) params.set(`${tableId}[sort_field]`, String(state.sort.field));
  if (state.sort?.direction) params.set(`${tableId}[sort_direction]`, String(state.sort.direction).toLowerCase() === 'asc' ? 'asc' : 'desc');
  Object.entries(state.filters || {}).forEach(([key, value]) => {
    if (!key) return;
    if (value === null || value === undefined || value === '') return;
    params.set(`${tableId}[${key}]`, String(value));
  });

  const nextQuery = params.toString();
  return nextQuery ? `${pathname}?${nextQuery}` : pathname;
};

function evalRowCondition(rule: any, row: any, role: string, permissions: string[], defaultVal = true): boolean {
  if (rule === null || rule === undefined) return defaultVal;
  if (typeof rule === 'boolean') return rule;
  if (typeof rule === 'object') {
    if (!hasRequiredPermissions(rule.required_permissions, role, permissions)) {
      return false;
    }
    const hideIf = rule.hide_if;
    if (hideIf !== undefined && evaluateRule(hideIf, { item: row ?? undefined }, false)) {
      return false;
    }
    const showIf = rule.show_if;
    if (showIf !== undefined) return evaluateRule(showIf, { item: row ?? undefined }, defaultVal);
    if ((rule as any).op || (rule as any).operator || (rule as any).left || (rule as any).value1) {
      return evaluateRule(rule, { item: row ?? undefined }, defaultVal);
    }
    return defaultVal;
  }
  return defaultVal;
}

function isVisible(spec: any, row: any, role: string, permissions: string[]): boolean {
  return isNestedActionVisible(
    spec,
    { item: row ?? undefined },
    role,
    permissions,
  );
}

function FilterCell({ col, value, onChange, serverSide }: { col: any; value: any; onChange: (v: any) => void; serverSide?: boolean }) {
  const [localText, setLocalText] = useState<string>(value ?? '');
  React.useEffect(() => { setLocalText(value ?? ''); }, [value]);

  if (col.filter_type === 'select' && Array.isArray(col.options)) {
    return (
      <Dropdown
        className="a2ui-datatable-filter-control"
        selectedKey={value ?? ''}
        options={[
          { key: '', text: 'All' },
          ...col.options.map((o: string) => ({ key: o, text: o })),
        ]}
        onChange={(_, option) => onChange(option?.key ? String(option.key) : null)}
      />
    );
  }
  if (col.filter_type === 'boolean') {
    return (
      <Dropdown
        className="a2ui-datatable-filter-control"
        selectedKey={value === true ? 'true' : value === false ? 'false' : ''}
        options={[
          { key: '', text: 'All' },
          { key: 'true', text: 'Yes' },
          { key: 'false', text: 'No' },
        ]}
        onChange={(_, option) => {
          const v = String(option?.key || '');
          onChange(v === 'true' ? true : v === 'false' ? false : null);
        }}
      />
    );
  }
  
  return (
    <TextField
      className="a2ui-datatable-filter-control"
      placeholder="Filter..."
      value={serverSide ? localText : (value ?? '')}
      onChange={(_, nextValue) => {
        const text = nextValue || '';
        if (serverSide) setLocalText(text);
        else onChange(text || null);
      }}
      onKeyDown={(e) => { if (serverSide && e.key === 'Enter') onChange(localText || null); }}
    />
  );
}

function CellDisplay({
  col,
  row,
  onEdit,
  editable,
  stateModel,
}: {
  col: any;
  row: any;
  onEdit?: (v: any) => void;
  editable?: boolean;
  stateModel?: any;
}) {
  const raw = row[col.field] ?? '';
  const [localStr, setLocalStr] = useState(String(raw));
  const [localBool, setLocalBool] = useState(Boolean(raw));
  const [localEnum, setLocalEnum] = useState(String(raw));
  const [editing, setEditing] = useState(false);

  React.useEffect(() => { setLocalStr(String(raw)); }, [raw]);
  React.useEffect(() => { setLocalBool(Boolean(raw)); }, [raw]);
  React.useEffect(() => { setLocalEnum(String(raw)); }, [raw]);

  const isEditable = editable !== undefined ? editable : Boolean(col.editable);
  const enumOptions = Array.isArray(row[col.options_field])
    ? row[col.options_field]
    : col.options;
  const optionValue = (option: any) =>
    typeof option === 'object' && option !== null ? String(option.value ?? '') : String(option);
  const optionLabel = (option: any) =>
    typeof option === 'object' && option !== null
      ? String(option.label ?? option.value ?? '')
      : String(option);
  const formattedValue = applyTransform(raw, col.transform, { stateModel, row });
  const currentEnumLabel = Array.isArray(enumOptions)
    ? optionLabel(enumOptions.find((option: any) => optionValue(option) === String(raw)) ?? raw)
    : String(formattedValue ?? '');

  const startEditing = () => {
    if (isEditable) setEditing(true);
  };

  const finishEditing = () => setEditing(false);

  const handleEditorKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Enter' || event.key === 'Escape') {
      event.preventDefault();
      finishEditing();
    }
  };

  if (isEditable && !editing) {
    const displayValue = col.type === 'bool'
      ? (Boolean(raw) ? 'Yes' : 'No')
      : (col.type === 'enum' ? currentEnumLabel : formattedValue);
    return (
      <span
        className="a2ui-datatable-cell-text a2ui-datatable-cell-editable"
        onDoubleClick={startEditing}
        title="Double click to edit"
      >
        {displayValue}
      </span>
    );
  }

  if (isEditable && col.type === 'bool') {
    return (
      <Checkbox
        className="a2ui-datatable-checkbox"
        checked={localBool}
        onBlur={finishEditing}
        onKeyDown={handleEditorKeyDown}
        onChange={(_, checked) => {
          const next = Boolean(checked);
          setLocalBool(next);
          onEdit?.(next);
        }}
      />
    );
  }

  if (isEditable && col.type === 'enum' && Array.isArray(enumOptions)) {
    return (
      <Dropdown
        className="a2ui-datatable-cell-dropdown"
        selectedKey={localEnum}
        options={enumOptions.map((option: any) => ({
          key: optionValue(option),
          text: optionLabel(option),
        }))}
        onBlur={finishEditing}
        onKeyDown={handleEditorKeyDown}
        onChange={(_, option) => {
          const next = String(option?.key ?? '');
          setLocalEnum(next);
          onEdit?.(next);
        }}
      />
    );
  }

  if (isEditable) {
    return (
      <TextField
        className="a2ui-datatable-cell-input"
        value={localStr}
        autoFocus
        onBlur={finishEditing}
        onKeyDown={handleEditorKeyDown}
        onChange={(_, nextValue) => {
          const next = nextValue || '';
          setLocalStr(next);
          onEdit?.(next);
        }}
      />
    );
  }

  if (col.type === 'bool') {
    return (
      <Checkbox className="a2ui-datatable-checkbox" checked={Boolean(raw)} disabled />
    );
  }

  return (
    <span className="a2ui-datatable-cell-text">{applyTransform(raw, col.transform, { stateModel, row })}</span>
  );
}

export const DataTable: React.FC<any> = ({
  id,
  model = [],
  rows = [],
  page = 0,
  page_size = 25,
  total_rows,
  filters: incomingFilters = {},
  sort: incomingSort = {},
  remote_service,
  on_page_change,
  on_row_add,
  on_row_delete,
  on_cell_edit,
  on_filter_change,
  selectable = false,
  row_actions = [],
  selection_actions = [],
  paginated = true,
  auto_refresh,
  show_row_numbers = false,
  onAction,
  userRole = 'Guest',
  userPermissions = [],
  stateModel,
}) => {
  const [filters, setFilters] = useState<Record<string, any>>(incomingFilters || {});
  const [sort, setSort] = useState<{ field?: string; direction?: string }>(incomingSort || {});
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [cellEdits, setCellEdits] = useState<Map<string, Record<string, any>>>(new Map());
  const resizeRef = React.useRef<{
    key: string;
    startX: number;
    startWidth: number;
    move: (event: MouseEvent) => void;
    up: () => void;
  } | null>(null);
  const prevRowKeysRef = React.useRef('');
  const prevIncomingFiltersRef = React.useRef(JSON.stringify(incomingFilters || {}));
  const prevIncomingSortRef = React.useRef(JSON.stringify(incomingSort || {}));
  const lastRemoteQueryRef = React.useRef<string>('');
  const access = useMemo(
    () => resolveAccessContext(stateModel, userRole, userPermissions),
    [stateModel, userRole, userPermissions],
  );
  const tableModel = useMemo(() => (Array.isArray(model) ? model : []), [model]);
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({});
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(() => new Set());
  const visibleColumns = useMemo(
    () => tableModel.filter((col: any) => {
      const key = columnKey(col);
      return key && !hiddenColumns.has(key);
    }),
    [tableModel, hiddenColumns],
  );
  const visibleColumnCount = visibleColumns.length;
  const remoteAction = remote_service || on_page_change || on_filter_change;
  const bootstrapFilters = incomingFilters || {};
  const bootstrapSort = incomingSort || {};
  const tableRows = useMemo(() => (Array.isArray(rows) ? rows : []), [rows]);
  const currentPath = String(currentPathFromState(stateModel) || '/');
  const queryState = useMemo(
    () =>
      parseTableQueryState(currentPath, String(id || ''), {
        page,
        pageSize: page_size,
        filters: bootstrapFilters,
        sort: bootstrapSort,
      }),
    [currentPath, id, page, page_size, bootstrapFilters, bootstrapSort],
  );

  React.useEffect(() => {
    const nextSerialized = JSON.stringify(incomingFilters || {});
    if (nextSerialized === prevIncomingFiltersRef.current) return;
    prevIncomingFiltersRef.current = nextSerialized;
    setFilters(incomingFilters || {});
  }, [incomingFilters]);

  React.useEffect(() => {
    const nextSerialized = JSON.stringify(incomingSort || {});
    if (nextSerialized === prevIncomingSortRef.current) return;
    prevIncomingSortRef.current = nextSerialized;
    setSort(incomingSort || {});
  }, [incomingSort]);

  React.useEffect(() => {
    const keys = (tableRows as any[]).map((r: any) => String(r.id ?? '')).join(',');
    if (keys !== prevRowKeysRef.current) {
      prevRowKeysRef.current = keys;
      setCellEdits(new Map());
    }
  }, [tableRows]);

  const callAction = useCallback(
    (action: any, ctx: any = {}) => {
      emitActionSpec(action, onAction, { ...ctx, tableId: id });
    },
    [onAction, id],
  );

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
    callAction(remote_service, requestPayload);
  }, [callAction, id, remote_service, currentPath, queryState]);

  React.useEffect(() => {
    if (!remote_service) return;
    setFilters(queryState.filters || {});
    setSort(queryState.sort || {});
  }, [remote_service, queryState]);

  const refreshRef = useAutoRefresh(
    auto_refresh,
    remoteAction,
    onAction,
    {
      page: remote_service ? queryState.page : page,
      pageSize: remote_service ? queryState.pageSize : page_size,
      filters: remote_service ? queryState.filters : filters,
      sort: remote_service ? queryState.sort : sort,
      tableId: id,
    },
    [page, page_size, filters, sort, remoteAction, remote_service, queryState]
  );

  const handleFilterChange = useCallback(
    (field: string, value: any) => {
      const newFilters = { ...filters, [field]: value };
      if (value === null || value === '' || value === undefined) delete newFilters[field];
      setFilters(newFilters);
      if (remote_service) {
        const nextPath = pathWithTableQuery(currentPath, String(id || ''), {
          page: 0,
          pageSize: queryState.pageSize,
          filters: newFilters,
          sort: queryState.sort,
        });
        if (nextPath !== currentPath) callAction('navigate', { path: nextPath, render: false });
        return;
      }
      if (remoteAction) callAction(remoteAction, { filters: newFilters, page: 0, pageSize: page_size, sort });
    },
    [filters, remote_service, remoteAction, callAction, page_size, sort, currentPath, id, queryState],
  );

  const handleSortChange = useCallback(
    (field: string) => {
      if (!remoteAction) return;
      const currentField = String(sort?.field || '').trim();
      const currentDirection = String(sort?.direction || '').trim().toLowerCase();
      let nextDirection = 'asc';
      if (currentField === field) nextDirection = currentDirection === 'asc' ? 'desc' : 'asc';
      const nextSort = { field, direction: nextDirection };
      setSort(nextSort);
      if (remote_service) {
        const nextPath = pathWithTableQuery(currentPath, String(id || ''), {
          page: queryState.page,
          pageSize: queryState.pageSize,
          filters: queryState.filters,
          sort: nextSort,
        });
        if (nextPath !== currentPath) callAction('navigate', { path: nextPath, render: false });
        return;
      }
      callAction(remoteAction, { page, pageSize: page_size, filters, sort: nextSort });
    },
    [remoteAction, remote_service, sort, callAction, page, page_size, filters, currentPath, id, queryState],
  );

  const handleCellEdit = useCallback(
    (rowIndex: number, rowId: any, field: string, value: any, row: any) => {
      const key = rowKey(row, rowIndex);
      setCellEdits((prev) => {
        const next = new Map(prev);
        next.set(key, { ...(next.get(key) ?? {}), [field]: value });
        return next;
      });
      if (on_cell_edit) callAction(on_cell_edit, { rowIndex, rowId, field, value, row });
    },
    [on_cell_edit, callAction],
  );

  const localRows = useMemo(() => {
    if (cellEdits.size === 0) return tableRows as any[];
    return (tableRows as any[]).map((r: any, i: number) => {
      const key = rowKey(r, i);
      const edits = cellEdits.get(key);
      return edits ? { ...r, ...edits } : r;
    });
  }, [tableRows, cellEdits]);

  const displayRows = useMemo(() => {
    if (remoteAction || Object.keys(filters).length === 0) return localRows;
    return localRows.filter((row: any) =>
      Object.entries(filters).every(([field, value]) => {
        if (value === null || value === undefined || value === '') return true;
        const cell = row[field];
        if (typeof value === 'boolean') return Boolean(cell) === value;
        return String(cell ?? '').toLowerCase().includes(String(value).toLowerCase());
      }),
    );
  }, [localRows, filters, remoteAction]);

  const pageForUi = remote_service ? queryState.page : page;
  const pageSizeForUi = remote_service ? queryState.pageSize : page_size;
  const totalRows = typeof total_rows === 'number' ? total_rows : displayRows.length;
  const pageCount = Math.max(1, Math.ceil(Math.max(totalRows, 1) / Math.max(pageSizeForUi, 1)));

  const hasFilterableColumns = visibleColumns.some((c: any) => c.filterable);
  const hasRowActions = Array.isArray(row_actions) && row_actions.length > 0;
  const hasSelectionActions = selectable && Array.isArray(selection_actions) && selection_actions.length > 0;

  const getRowSelectable = (row: any) => {
    if (!selectable) return false;
    return evalRowCondition(row.selectable ?? true, row, access.role, access.permissions);
  };

  const selectableRows = displayRows.filter(getRowSelectable);
  const allSelected = selectableRows.length > 0 && selectableRows.every((r: any) => selectedIds.has(String(r.id)));
  const someSelected = selectedIds.size > 0;

  const toggleSelectAll = () => {
    if (allSelected) setSelectedIds(new Set());
    else setSelectedIds(new Set(selectableRows.map((r: any) => String(r.id))));
  };

  const toggleSelectRow = (rowId: string, isSelectable: boolean) => {
    if (!isSelectable) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(rowId) ? next.delete(rowId) : next.add(rowId);
      return next;
    });
  };

  const getSelectedRows = () => tableRows.filter((r: any) => selectedIds.has(String(r.id)));
  const showPagination = paginated && (Boolean(remoteAction) || totalRows > pageSizeForUi);

  const toggleColumn = (key: string, visible: boolean) => {
    setHiddenColumns((prev) => {
      const next = new Set(prev);
      if (visible) {
        next.delete(key);
      } else if (visibleColumnCount > 1) {
        next.add(key);
      }
      return next;
    });
  };

  const startColumnResize = useCallback((key: string, startWidth: number, event: React.MouseEvent<HTMLSpanElement>) => {
    event.preventDefault();
    event.stopPropagation();
    resizeRef.current?.up();
    const startX = event.clientX;
    const move = (moveEvent: MouseEvent) => {
      const nextWidth = Math.max(MIN_COLUMN_WIDTH, Math.round(startWidth + moveEvent.clientX - startX));
      setColumnWidths((prev) => ({ ...prev, [key]: nextWidth }));
    };
    const up = () => {
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseup', up);
      document.body.classList.remove('a2ui-datatable-resizing');
      resizeRef.current = null;
    };
    resizeRef.current = { key, startX, startWidth, move, up };
    document.body.classList.add('a2ui-datatable-resizing');
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
  }, []);

  React.useEffect(() => () => resizeRef.current?.up(), []);

  const tableItems = useMemo(
    () => displayRows.map((row: any, rowIndex: number) => ({
      ...row,
      __rowIndex: rowIndex,
      __rowId: rowKey(row, rowIndex),
    })),
    [displayRows],
  );

  const buildRowActionItems = (row: any, rowIndex: number): IContextualMenuItem[] =>
    (row_actions as any[])
      .filter((ra: any) => isVisible(ra, row, access.role, access.permissions))
      .map((ra: any, i: number) => ({
        key: String(i),
        text: String(ra.label || 'Action'),
        iconProps: ra.icon ? { className: resolveIconClass(ra.icon) || undefined } : undefined,
        className: ra.variant === 'danger' ? 'a2ui-datatable-menu-danger' : undefined,
        onClick: () => callAction(ra.action, {
          item: row,
          item_index: rowIndex,
          row,
          rowIndex,
          rowId: row.id,
        }),
      }));

  const columnsMenuItems: IContextualMenuItem[] = tableModel
    .map((col: any) => {
      const key = columnKey(col);
      if (!key) return null;
      const checked = !hiddenColumns.has(key);
      return {
        key,
        text: String(col.header || col.field || key),
        canCheck: true,
        isChecked: checked,
        disabled: checked && visibleColumnCount <= 1,
        onClick: () => toggleColumn(key, !checked),
      } as IContextualMenuItem;
    })
    .filter(Boolean) as IContextualMenuItem[];

  const nativeColumns = [
    ...(hasRowActions ? [{
      key: '__actions',
      name: '',
      width: 36,
      render: (item: any) => (
        <IconButton
          className="a2ui-datatable-row-action"
          iconProps={{ iconName: 'MoreVertical' }}
          menuIconProps={{ className: 'a2ui-datatable-menu-icon' }}
          ariaLabel="Row actions"
          title="Row actions"
          menuProps={{
            items: buildRowActionItems(item, item.__rowIndex),
            directionalHint: DirectionalHint.bottomLeftEdge,
            calloutProps: { className: 'a2ui-datatable-menu', isBeakVisible: false },
          }}
        />
      ),
    }] : []),
    ...(selectable ? [{
      key: '__select',
      name: '',
      width: 36,
      render: (item: any) => {
        const rowSelectable = getRowSelectable(item);
        const isSelected = selectedIds.has(item.__rowId);
        return (
          <Checkbox
            className="a2ui-datatable-checkbox"
            checked={isSelected}
            disabled={!rowSelectable}
            onChange={() => toggleSelectRow(item.__rowId, rowSelectable)}
          />
        );
      },
    }] : []),
    ...(show_row_numbers ? [{
      key: '__rowNumber',
      name: '#',
      width: 48,
      render: (item: any) => (
        <span className="a2ui-datatable-row-number">{pageForUi * pageSizeForUi + item.__rowIndex + 1}</span>
      ),
    }] : []),
    ...visibleColumns.map((col: any) => {
      const key = columnKey(col);
      const fieldName = String(col.field || key).toLowerCase();
      const typeName = String(col.type || '').toLowerCase();
      const inferredWidth =
        fieldName.includes('name') || fieldName.includes('title') ? 160 :
        fieldName.includes('team') || fieldName.includes('owner') ? 140 :
        typeName === 'date' || typeName === 'datetime' || fieldName.includes('joined') ? 128 :
        typeName === 'enum' || fieldName.includes('status') || fieldName.includes('role') ? 112 :
        typeName === 'float' || typeName === 'int' || fieldName.includes('score') ? 96 :
        Math.max(MIN_COLUMN_WIDTH, Math.min(180, String(col.header || col.field || '').length * 10 + 72));
      const width = columnWidths[key] || Number(col.width) || Number(col.min_width) || inferredWidth;
      return {
        key,
        name: String(col.header || col.field || key),
        fieldName: String(col.field || key),
        width: Math.max(width, MIN_COLUMN_WIDTH),
        source: col,
        render: (item: any) => (
          <CellDisplay
            col={col}
            row={item}
            stateModel={stateModel}
            editable={evalRowCondition(col.editable ?? false, item, access.role, access.permissions, false)}
            onEdit={col.editable ? (v) => handleCellEdit(pageForUi * pageSizeForUi + item.__rowIndex, item.id, col.field, v, item) : undefined}
          />
        ),
      };
    }),
  ];

  const totalColumnWidth = nativeColumns.reduce((acc, col) => acc + (Number(col.width) || MIN_COLUMN_WIDTH), 0);

  const goToPage = (nextPage: number) => {
    if (remote_service) {
      const nextPath = pathWithTableQuery(currentPath, String(id || ''), {
        page: nextPage,
        pageSize: pageSizeForUi,
        filters: queryState.filters,
        sort: queryState.sort,
      });
      if (nextPath !== currentPath) callAction('navigate', { path: nextPath, render: false });
      return;
    }
    if (remoteAction) callAction(remoteAction, { page: nextPage, pageSize: page_size, filters, sort });
  };

  return (
    <div ref={refreshRef as any} className="a2ui-datatable">
      {someSelected && hasSelectionActions && (
        <div className="a2ui-datatable-selection">
          <span className="a2ui-datatable-selection-count">{selectedIds.size} selected</span>
          {(selection_actions as any[]).filter((sa: any) => isVisible(sa, null, access.role, access.permissions)).map((sa: any, i: number) => {
            const iconCls = resolveIconClass(sa.icon);
            const ActionButton = sa.variant === 'primary' ? PrimaryButton : DefaultButton;
            return (
              <ActionButton
                key={i}
                className={`a2ui-datatable-command ${sa.variant === 'danger' ? 'a2ui-datatable-command-danger' : ''}`}
                onRenderIcon={iconCls ? () => <i className={iconCls} aria-hidden="true" /> : undefined}
                onClick={() => callAction(sa.action, { selected_ids: [...selectedIds], selected_rows: getSelectedRows() })}
              >
                {sa.label}
              </ActionButton>
            );
          })}
          <DefaultButton className="a2ui-datatable-clear" onClick={() => setSelectedIds(new Set())}>Clear</DefaultButton>
        </div>
      )}

      <div className="a2ui-datatable-toolbar">
        <div className="a2ui-datatable-count">
          {selectable && (
            <Checkbox
              className="a2ui-datatable-select-all"
              checked={allSelected}
              disabled={selectableRows.length === 0}
              onChange={toggleSelectAll}
            />
          )}
          <span>{totalRows} rows</span>
        </div>
        <div className="a2ui-datatable-actions">
          {tableModel.length > 0 && (
            <DefaultButton
              className="a2ui-datatable-toolbar-button"
              menuProps={{
                items: columnsMenuItems,
                directionalHint: DirectionalHint.bottomRightEdge,
                calloutProps: { className: 'a2ui-datatable-menu', isBeakVisible: false },
              }}
            >
              Columns
            </DefaultButton>
          )}
          {on_row_add && (
            <PrimaryButton className="a2ui-datatable-toolbar-button" onClick={() => callAction(on_row_add)}>
              Add row
            </PrimaryButton>
          )}
        </div>
      </div>

      <div className="a2ui-datatable-surface">
        {hasFilterableColumns && (
          <table className="a2ui-datatable-filter-table" style={{ minWidth: totalColumnWidth }}>
            <colgroup>
              {nativeColumns.map((col) => (
                <col key={`filter_col_${col.key}`} style={{ width: col.width || MIN_COLUMN_WIDTH }} />
              ))}
            </colgroup>
            <tbody>
              <tr>
                {nativeColumns.map((col) => {
                  const modelCol = visibleColumns.find((entry: any) => columnKey(entry) === col.key);
                  return (
                    <td className="a2ui-datatable-filter-cell" key={`filter_${col.key}`}>
                      {modelCol?.filterable ? (
                        <FilterCell
                          col={modelCol}
                          value={filters[modelCol.field] ?? null}
                          onChange={(v) => handleFilterChange(modelCol.field, v)}
                          serverSide={!!remoteAction}
                        />
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        )}
        <table className="a2ui-datatable-table" style={{ minWidth: totalColumnWidth }}>
          <colgroup>
            {nativeColumns.map((col) => (
              <col key={`col_${col.key}`} style={{ width: col.width || MIN_COLUMN_WIDTH }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              {nativeColumns.map((col) => {
                const modelCol = visibleColumns.find((entry: any) => columnKey(entry) === col.key);
                const sortable = Boolean(modelCol?.field);
                const sorted = modelCol?.field && sort?.field === modelCol.field;
                return (
                  <th key={col.key}>
                    {sortable ? (
                      <button
                        type="button"
                        className="a2ui-datatable-header-button"
                        onClick={() => handleSortChange(modelCol.field)}
                      >
                        <span>{col.name}</span>
                        {sorted ? <i className={String(sort?.direction || '').toLowerCase() === 'asc' ? 'ri-arrow-up-s-line' : 'ri-arrow-down-s-line'} aria-hidden="true" /> : null}
                      </button>
                    ) : (
                      <span className="a2ui-datatable-header-label">{col.name}</span>
                    )}
                    <span
                      className="a2ui-datatable-column-resizer"
                      role="separator"
                      aria-orientation="vertical"
                      aria-label={`Resize ${col.name || 'column'}`}
                      onMouseDown={(event) => startColumnResize(col.key, Math.max(Number(col.width) || MIN_COLUMN_WIDTH, MIN_COLUMN_WIDTH), event)}
                    />
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {tableItems.map((item: any) => (
              <tr key={item.__rowId} className={selectedIds.has(item.__rowId) ? 'a2ui-datatable-row-selected' : ''}>
                {nativeColumns.map((col) => (
                  <td key={`${item.__rowId}_${col.key}`}>
                    {col.render ? col.render(item) : null}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showPagination && (
        <div className="a2ui-datatable-pagination">
          <span className="a2ui-datatable-page-label">Page {pageForUi + 1} of {pageCount}</span>
          <div className="a2ui-datatable-page-actions">
            <DefaultButton
              className="a2ui-datatable-toolbar-button"
              disabled={pageForUi <= 0}
              onClick={() => goToPage(Math.max(0, pageForUi - 1))}
            >
              Prev
            </DefaultButton>
            <DefaultButton
              className="a2ui-datatable-toolbar-button"
              disabled={pageForUi >= pageCount - 1}
              onClick={() => goToPage(pageForUi + 1)}
            >
              Next
            </DefaultButton>
          </div>
        </div>
      )}
    </div>
  );
};
