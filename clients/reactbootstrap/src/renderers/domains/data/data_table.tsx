import React, { useState, useMemo, useCallback } from 'react';
import { useA2UI } from '@/hooks/useA2UI';
import { useAutoRefresh } from '../../../hooks/useAutoRefresh';
import { evaluateRule, hasRequiredPermissions, isNestedActionVisible, isSuperRole } from '../../rules';
import { applyTransform } from './cell_formatters';
import { emitActionSpec } from '@/renderers/shared';
import { 
  Button, 
  Table, 
  Input,
  FormGroup,
  Label
} from 'design-react-kit';
import { resolveIconClass } from '../../../utils/icons';
import { readClientStateValue } from '@/state/clientState';
import { SmartDropdown } from '@/components/ui/smart-dropdown';

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
      <select
        className="form-select form-select-sm xsmall datatable-filter-control"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">All</option>
        {col.options.map((o: string) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    );
  }
  if (col.filter_type === 'boolean') {
    return (
      <select
        className="form-select form-select-sm xsmall datatable-filter-control"
        value={value === true ? 'true' : value === false ? 'false' : ''}
        onChange={(e) => {
          const v = e.target.value;
          onChange(v === 'true' ? true : v === 'false' ? false : null);
        }}
      >
        <option value="">All</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    );
  }
  
  return (
    <input
      className="form-control form-control-sm xsmall datatable-filter-control"
      placeholder="Filter..."
      value={serverSide ? localText : (value ?? '')}
      onChange={(e) => {
        if (serverSide) setLocalText(e.target.value);
        else onChange(e.target.value || null);
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

  if (isEditable && col.type === 'bool') {
    return (
      <FormGroup check className="m-0">
        <Input
          type="checkbox"
          checked={localBool}
          onChange={(e) => {
            setLocalBool(e.target.checked);
            onEdit?.(e.target.checked);
          }}
        />
      </FormGroup>
    );
  }

  if (isEditable && col.type === 'enum' && Array.isArray(enumOptions)) {
    return (
      <Input
        type="select"
        tag="select"
        className="form-control-sm xsmall"
        value={localEnum}
        onChange={(e) => {
          setLocalEnum(e.target.value);
          onEdit?.(e.target.value);
        }}
      >
        {enumOptions.map((option: any) => (
          <option key={optionValue(option)} value={optionValue(option)}>
            {optionLabel(option)}
          </option>
        ))}
      </Input>
    );
  }

  if (isEditable) {
    return (
      <Input
        className="form-control-sm xsmall"
        value={localStr}
        onChange={(e) => {
          setLocalStr(e.target.value);
          onEdit?.(e.target.value);
        }}
      />
    );
  }

  if (col.type === 'bool') {
    return (
      <FormGroup check className="m-0">
        <Input type="checkbox" checked={Boolean(raw)} disabled />
      </FormGroup>
    );
  }

  return (
    <span className="small">{applyTransform(raw, col.transform, { stateModel, row })}</span>
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

  const handleColumnResizeStart = useCallback((event: React.MouseEvent, col: any) => {
    const key = columnKey(col);
    if (!key) return;
    event.preventDefault();
    event.stopPropagation();
    const th = (event.currentTarget as HTMLElement).closest('th') as HTMLElement | null;
    const startX = event.clientX;
    const startWidth = columnWidths[key] || th?.getBoundingClientRect().width || Number(col.width) || MIN_COLUMN_WIDTH;

    const onMove = (moveEvent: MouseEvent) => {
      const nextWidth = Math.max(MIN_COLUMN_WIDTH, Math.round(startWidth + moveEvent.clientX - startX));
      setColumnWidths((prev) => ({ ...prev, [key]: nextWidth }));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [columnWidths]);

  return (
    <div ref={refreshRef as any} className="a2ui-datatable d-flex flex-column gap-2 w-100">
      {someSelected && hasSelectionActions && (
        <div className="a2ui-datatable-selection d-flex align-items-center gap-2 px-3 py-2 bg-light border text-small flex-wrap">
          <span className="fw-bold me-2">{selectedIds.size} selected</span>
          {(selection_actions as any[]).filter((sa: any) => isVisible(sa, null, access.role, access.permissions)).map((sa: any, i: number) => {
            const iconCls = resolveIconClass(sa.icon);
            return (
              <Button
                key={i}
                size="sm"
                color={sa.variant === 'danger' ? 'danger' : (sa.variant || 'secondary')}
                onClick={() => callAction(sa.action, { selected_ids: [...selectedIds], selected_rows: getSelectedRows() })}
              >
                {iconCls && <i className={`${iconCls} ${sa.label ? 'me-1' : ''}`} />}
                {sa.label}
              </Button>
            );
          })}
          <Button size="sm" color="link" className="ms-auto" onClick={() => setSelectedIds(new Set())}>Clear</Button>
        </div>
      )}

      <div className="a2ui-datatable-toolbar d-flex align-items-center justify-content-between px-1">
        <span className="xsmall text-muted">{totalRows} rows</span>
        <div className="d-flex align-items-center gap-2">
          {tableModel.length > 0 && (
            <SmartDropdown
              menuClassName="a2ui-datatable-menu"
              placement="bottom-end"
              button={(
                <button type="button" className="a2ui-button a2ui-datatable-toolbar-button btn btn-outline-primary btn-sm">
                  <i className="ri-layout-column-line me-1" />Columns
                </button>
              )}
            >
              {tableModel.map((col: any) => {
                const key = columnKey(col);
                if (!key) return null;
                const checked = !hiddenColumns.has(key);
                return (
                  <label key={key} className={`dropdown-item d-flex align-items-center gap-2 ${checked && visibleColumnCount <= 1 ? 'disabled' : ''}`}>
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={checked && visibleColumnCount <= 1}
                      onChange={(event) => toggleColumn(key, event.target.checked)}
                    />
                    <span>{col.header || col.field}</span>
                  </label>
                );
              })}
            </SmartDropdown>
          )}
          {on_row_add && (
            <Button size="sm" outline color="primary" className="a2ui-button a2ui-datatable-toolbar-button" onClick={() => callAction(on_row_add)}>
              <i className="ri-add-line me-1" />Add row
            </Button>
          )}
        </div>
      </div>

      <div className="table-responsive border datatable-scroll">
        <Table hover size="sm" className="a2ui-datatable-table mb-0 xsmall" style={{ tableLayout: 'fixed' }}>
          <thead>
            <tr>
              {hasRowActions && (
                <th className="datatable-sticky-cell position-sticky start-0 bg-white" style={{ width: '40px', zIndex: 3 }} />
              )}
              {selectable && (
                <th style={{ width: '40px' }}>
                  <FormGroup check className="m-0">
                    <Input type="checkbox" checked={allSelected} onChange={toggleSelectAll} />
                  </FormGroup>
                </th>
              )}
              {show_row_numbers && <th style={{ width: '40px' }} className="text-muted">#</th>}
              {visibleColumns.map((col: any) => {
                const key = columnKey(col);
                const width = columnWidths[key] || Number(col.width) || undefined;
                return (
                <th key={key} className="position-relative" style={width ? { width } : {}}>
                  <button
                    type="button"
                    className={`btn btn-link btn-xs p-0 text-decoration-none fw-bold text-dark d-flex align-items-center gap-1 ${!remoteAction ? 'pe-none' : ''}`}
                    onClick={() => { if (col.field) handleSortChange(col.field); }}
                  >
                    {col.header || col.field}
                    {sort?.field === col.field && (
                      <i className={sort?.direction === 'asc' ? 'ri-arrow-up-s-line' : 'ri-arrow-down-s-line'} />
                    )}
                  </button>
                  <span
                    role="separator"
                    aria-orientation="vertical"
                    className="position-absolute top-0 end-0 h-100"
                    style={{ width: 8, cursor: 'col-resize', userSelect: 'none' }}
                    onMouseDown={(event) => handleColumnResizeStart(event, col)}
                  />
                </th>
                );
              })}
            </tr>

            {hasFilterableColumns && (
              <tr className="bg-light datatable-filter-row">
                {hasRowActions && (
                  <td className="datatable-sticky-cell position-sticky start-0 bg-light" style={{ zIndex: 3 }} />
                )}
                {selectable && <td />}
                {show_row_numbers && <td />}
                {visibleColumns.map((col: any) => (
                  <td key={columnKey(col)} className="py-1 align-middle">
                    {col.filterable && (
                      <FilterCell
                        col={col}
                        value={filters[col.field] ?? null}
                        onChange={(v) => handleFilterChange(col.field, v)}
                        serverSide={!!remoteAction}
                      />
                    )}
                  </td>
                ))}
              </tr>
            )}
          </thead>

          <tbody>
            {displayRows.map((row: any, rowIndex: number) => {
              const rowId = rowKey(row, rowIndex);
              const rowSelectable = getRowSelectable(row);
              const isSelected = selectedIds.has(rowId);

              return (
                <tr key={rowId} className={isSelected ? 'table-active' : ''}>
                  {hasRowActions && (
                    <td className="datatable-actions-cell datatable-sticky-cell position-sticky start-0 bg-white" style={{ zIndex: 2 }}>
                      <SmartDropdown
                        className="datatable-row-actions"
                        menuClassName="datatable-row-actions-menu a2ui-datatable-menu"
                        placement="bottom-start"
                        button={(
                          <button type="button" className="btn btn-icon btn-xs datatable-row-actions-button">
                            <i className="ri-more-2-fill" />
                          </button>
                        )}
                      >
                          {(row_actions as any[]).filter((ra: any) => isVisible(ra, row, access.role, access.permissions)).map((ra: any, i: number) => {
                            const iconCls = resolveIconClass(ra.icon);
                            return (
                              <button
                                type="button"
                                key={i}
                                className={`dropdown-item ${ra.variant === 'danger' ? 'text-danger' : ''}`}
                                onClick={() => callAction(ra.action, {
                                  item: row,
                                  item_index: rowIndex,
                                  row,
                                  rowIndex,
                                  rowId: row.id,
                                })}
                              >
                                {iconCls && <i className={`${iconCls} me-2`} />}
                                {ra.label}
                              </button>
                            );
                          })}
                      </SmartDropdown>
                    </td>
                  )}
                  {selectable && (
                    <td>
                      <FormGroup check className="m-0">
                        <Input
                          type="checkbox"
                          checked={isSelected}
                          disabled={!rowSelectable}
                          onChange={() => toggleSelectRow(rowId, rowSelectable)}
                        />
                      </FormGroup>
                    </td>
                  )}
                  {show_row_numbers && (
                    <td className="text-muted">
                      {pageForUi * pageSizeForUi + rowIndex + 1}
                    </td>
                  )}
                  {visibleColumns.map((col: any) => (
                    <td key={columnKey(col)}>
                      <CellDisplay
                        col={col}
                        row={row}
                        stateModel={stateModel}
                        editable={evalRowCondition(col.editable ?? false, row, access.role, access.permissions, false)}
                        onEdit={col.editable ? (v) => handleCellEdit(pageForUi * pageSizeForUi + rowIndex, row.id, col.field, v, row) : undefined}
                      />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </Table>
      </div>

      {showPagination && (
        <div className="a2ui-datatable-pagination d-flex align-items-center justify-content-between px-1 mt-2">
          <span className="xsmall text-muted">
            Page {pageForUi + 1} of {pageCount}
          </span>
          <div className="d-flex gap-2">
            <Button
              size="sm"
              outline
              color="primary"
              className="a2ui-button a2ui-datatable-toolbar-button"
              disabled={pageForUi <= 0}
              onClick={() => {
                if (remote_service) {
                  const nextPath = pathWithTableQuery(currentPath, String(id || ''), {
                    page: Math.max(0, pageForUi - 1),
                    pageSize: pageSizeForUi,
                    filters: queryState.filters,
                    sort: queryState.sort,
                  });
                  if (nextPath !== currentPath) callAction('navigate', { path: nextPath, render: false });
                  return;
                }
                if (remoteAction) callAction(remoteAction, { page: page - 1, pageSize: page_size, filters, sort });
              }}
            >
              <i className="ri-arrow-left-s-line" /> Prev
            </Button>
            <Button
              size="sm"
              outline
              color="primary"
              className="a2ui-button a2ui-datatable-toolbar-button"
              disabled={pageForUi >= pageCount - 1}
              onClick={() => {
                if (remote_service) {
                  const nextPath = pathWithTableQuery(currentPath, String(id || ''), {
                    page: pageForUi + 1,
                    pageSize: pageSizeForUi,
                    filters: queryState.filters,
                    sort: queryState.sort,
                  });
                  if (nextPath !== currentPath) callAction('navigate', { path: nextPath, render: false });
                  return;
                }
                if (remoteAction) callAction(remoteAction, { page: page + 1, pageSize: page_size, filters, sort });
              }}
            >
              Next <i className="ri-arrow-right-s-line" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
