import React, { useEffect, useMemo, useRef, useState } from 'react';
import { parseStyle } from '@/utils/style';
import { cn } from '@/lib/utils';

type WidgetMeta = {
  id: string;
  row: number;
  col: number;
  w: number;
  h: number;
};

const sizeToSpan = (size: string): { w: number; h: number } => {
  switch (size) {
    case 'rect_h': return { w: 2, h: 1 };
    case 'rect_v': return { w: 1, h: 2 };
    case 'large': return { w: 2, h: 2 };
    default: return { w: 1, h: 1 };
  }
};

const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(v, max));
const toPositiveInt = (value: any, fallback: number) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(1, Math.trunc(n));
};

const getWidgetPropsFromSurface = (surfaces: any, surfaceId: string, componentId: string): any => {
  const comp = surfaces?.[surfaceId]?.components?.[componentId];
  const widget = comp?.component?.DashboardWidget;
  return widget && typeof widget === 'object' ? widget : null;
};

export const GridDropZone: React.FC<any> = ({
  id,
  ExplicitList,
  columns = 4,
  rows = 4,
  edit_mode = false,
  add_action = 'add_widget',
  move_action = 'move_widget',
  session_key = 'grid_widgets',
  insertable_items,
  style,
  onAction,
  surfaces,
  surfaceId,
}) => {
  const gridRef = useRef<HTMLDivElement | null>(null);
  const draggingWidgetRef = useRef<{ id: string; w: number; h: number } | null>(null);
  const [gridWidth, setGridWidth] = useState(0);
  const [hoverCell, setHoverCell] = useState<{ row: number; col: number } | null>(null);
  const [addMenuCell, setAddMenuCell] = useState<{ row: number; col: number } | null>(null);
  const cols = toPositiveInt(columns, 4);
  const rowCount = toPositiveInt(rows, 4);
  const cellGap = 8;
  const gridPadding = 8;

  useEffect(() => {
    const element = gridRef.current;
    if (!element) return;
    const update = () => setGridWidth(element.clientWidth || 0);
    update();
    const observer = new ResizeObserver(() => update());
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const cellSize = useMemo(() => {
    const available = Math.max(0, gridWidth - (gridPadding * 2) - (Math.max(0, cols - 1) * cellGap));
    return Math.max(42, Math.floor(available / cols) || 0);
  }, [gridWidth, cols]);
  const gridHeight = (cellSize * rowCount) + (Math.max(0, rowCount - 1) * cellGap) + (gridPadding * 2);

  const children = React.Children.toArray(ExplicitList) as React.ReactElement[];

  const { widgets, occupied } = useMemo(() => {
    const metas: WidgetMeta[] = [];
    const occ = new Set<string>();
    const toPlace = children.map(child => {
      if (!React.isValidElement(child)) return null;
      const componentId = String((child.props as any)?.componentId || (child.key ?? ''));
      if (!componentId) return null;
      const widgetProps = getWidgetPropsFromSurface(surfaces, surfaceId, componentId);
      const span = sizeToSpan(String(widgetProps?.size || 'square'));
      return { id: componentId, widgetProps, span };
    }).filter(Boolean) as any[];

    const unplaced: any[] = [];
    toPlace.forEach(item => {
      const explicitCoords = Array.isArray(item.widgetProps?.coords) ? item.widgetProps.coords : null;
      if (explicitCoords) {
        const row = clamp(Number(explicitCoords[0]) || 0, 0, rowCount - 1);
        const col = clamp(Number(explicitCoords[1]) || 0, 0, cols - 1);
        metas.push({ id: item.id, row, col, w: item.span.w, h: item.span.h });
        for (let r = 0; r < item.span.h; r++) for (let c = 0; c < item.span.w; c++) occ.add(`${row + r}:${col + c}`);
      } else unplaced.push(item);
    });

    unplaced.forEach(item => {
      const { w, h } = item.span;
      let placed = false;
      for (let r = 0; r < rowCount; r++) {
        for (let c = 0; c <= cols - w; c++) {
          let isFree = true;
          for (let dr = 0; dr < h; dr++) for (let dc = 0; dc < w; dc++) if (occ.has(`${r + dr}:${c + dc}`)) { isFree = false; break; }
          if (isFree) {
            metas.push({ id: item.id, row: r, col: c, w, h });
            for (let dr = 0; dr < h; dr++) for (let dc = 0; dc < w; dc++) occ.add(`${r + dr}:${c + dc}`);
            placed = true;
            break;
          }
        }
        if (placed) break;
      }
      if (!placed) metas.push({ id: item.id, row: 0, col: 0, w, h });
    });
    return { widgets: metas, occupied: occ };
  }, [children, surfaces, surfaceId, rowCount, cols]);

  const cellFromMouse = (event: React.DragEvent<HTMLDivElement>): { row: number; col: number } | null => {
    const target = event.currentTarget;
    const rect = target.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    return { row: clamp(Math.floor(y / (rect.height / rowCount)), 0, rowCount - 1), col: clamp(Math.floor(x / (rect.width / cols)), 0, cols - 1) };
  };

  const canPlace = (row: number, col: number, w = 1, h = 1, ignoreId?: string): boolean => {
    if (col + w > cols || row + h > rowCount) return false;

    const ignoreCells = new Set<string>();
    if (ignoreId) {
      const source = widgets.find(item => item.id === ignoreId);
      if (source) {
        for (let r = 0; r < source.h; r++) {
          for (let c = 0; c < source.w; c++) {
            ignoreCells.add(`${source.row + r}:${source.col + c}`);
          }
        }
      }
    }

    for (let r = 0; r < h; r++) {
      for (let c = 0; c < w; c++) {
        const key = `${row + r}:${col + c}`;
        if (occupied.has(key) && !ignoreCells.has(key)) return false;
      }
    }

    return true;
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    if (!edit_mode) return;
    event.preventDefault();
    setHoverCell(null);
    setAddMenuCell(null);
    const cell = cellFromMouse(event);
    if (!cell) return;
    const widgetId = event.dataTransfer.getData('application/x-dashboard-widget');
    const fallback = draggingWidgetRef.current;
    const resolvedWidgetId = widgetId || fallback?.id || '';
    const w = Number(event.dataTransfer.getData('application/x-dashboard-widget-w') || fallback?.w || '1') || 1;
    const h = Number(event.dataTransfer.getData('application/x-dashboard-widget-h') || fallback?.h || '1') || 1;
    if (!resolvedWidgetId) return;
    const col = clamp(cell.col, 0, Math.max(0, cols - w));
    const row = clamp(cell.row, 0, Math.max(0, rowCount - h));
    if (!canPlace(row, col, w, h, resolvedWidgetId)) return;
    onAction?.(move_action, { id: resolvedWidgetId, row, col, grid_id: id, session_key });
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    if (!edit_mode) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    if (addMenuCell) setAddMenuCell(null);
    const cell = cellFromMouse(event);
    if (!cell) return;
    const fallback = draggingWidgetRef.current;
    const w = Number(event.dataTransfer.getData('application/x-dashboard-widget-w') || fallback?.w || '1') || 1;
    const h = Number(event.dataTransfer.getData('application/x-dashboard-widget-h') || fallback?.h || '1') || 1;
    const col = clamp(cell.col, 0, Math.max(0, cols - w));
    const row = clamp(cell.row, 0, Math.max(0, rowCount - h));
    setHoverCell({ row, col });
  };

  const addOptions = Array.isArray(insertable_items) && insertable_items.length > 0 ? insertable_items : [
    { label: 'Square', size: 'square' },
    { label: 'Horizontal', size: 'rect_h' },
    { label: 'Vertical', size: 'rect_v' },
  ];

  const renderCellOverlay = () => {
    const cells = [];
    for (let row = 0; row < rowCount; row++) {
      for (let col = 0; col < cols; col++) {
        const isOccupied = occupied.has(`${row}:${col}`);
        const isHover = hoverCell?.row === row && hoverCell?.col === col;
        const isMenuOpen = addMenuCell?.row === row && addMenuCell?.col === col;
        cells.push(
          <div key={`cell_${row}_${col}`} className={cn("a2ui-grid-cell", isHover && "a2ui-grid-cell-hover", isOccupied && "a2ui-grid-cell-occupied")}>
            {edit_mode && !isOccupied && (
              <div className="a2ui-grid-cell-action">
                <button
                  type="button"
                  aria-label={`Add widget at row ${row + 1}, column ${col + 1}`}
                  onClick={() => setAddMenuCell(isMenuOpen ? null : { row, col })}
                  className="a2ui-grid-add-button"
                >
                  <span aria-hidden="true">+</span>
                </button>
              </div>
            )}
            {edit_mode && !isOccupied && isMenuOpen && (
              <div className="a2ui-grid-add-menu">
                {addOptions.map(opt => (
                  <button key={opt.size} type="button" className="a2ui-grid-add-menu-item" onClick={() => {
                    onAction?.(add_action, { component: 'DashboardWidget', size: opt.size, row, col, grid_id: id, session_key });
                    setAddMenuCell(null);
                  }}>{opt.label}</button>
                ))}
              </div>
            )}
          </div>
        );
      }
    }
    return cells;
  };

  const placeStyleFor = (meta: WidgetMeta): React.CSSProperties => ({
    gridColumn: `${meta.col + 1} / span ${meta.w}`,
    gridRow: `${meta.row + 1} / span ${meta.h}`,
  });

  const childById = new Map<string, React.ReactElement>();
  children.forEach(child => {
    if (!React.isValidElement(child)) return;
    const componentId = String((child.props as any)?.componentId || (child.key ?? ''));
    if (componentId) childById.set(componentId, child);
  });

  return (
    <div id={id} ref={gridRef} className={cn("a2ui-grid-dropzone", edit_mode && "a2ui-grid-dropzone-editing")} style={{ ...parseStyle(style), minHeight: gridHeight }} onDrop={handleDrop} onDragOver={handleDragOver} onDragLeave={() => edit_mode && setHoverCell(null)} onClick={ev => !ev.target?.closest('button') && setAddMenuCell(null)}>
      <div className="a2ui-grid-surface" style={{ gridTemplateColumns: `repeat(${cols}, ${cellSize}px)`, gridTemplateRows: `repeat(${rowCount}, ${cellSize}px)`, gap: cellGap, height: gridHeight }}>
        {edit_mode && renderCellOverlay()}
      </div>
      <div className="a2ui-grid-widget-layer" style={{ gridTemplateColumns: `repeat(${cols}, ${cellSize}px)`, gridTemplateRows: `repeat(${rowCount}, ${cellSize}px)`, gap: cellGap, height: gridHeight }}>
        {widgets.map(meta => {
          const child = childById.get(meta.id);
          if (!child) return null;
          return (
            <div key={meta.id} className="a2ui-grid-widget-slot" style={{ ...placeStyleFor(meta), pointerEvents: 'auto' }}>
              {React.cloneElement(child as any, {
                edit_mode,
                onGridDragStart: (widgetId: string, span: { w: number; h: number }) => {
                  draggingWidgetRef.current = { id: widgetId, w: span.w, h: span.h };
                },
                onGridDragEnd: () => {
                  draggingWidgetRef.current = null;
                  setHoverCell(null);
                },
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
};
