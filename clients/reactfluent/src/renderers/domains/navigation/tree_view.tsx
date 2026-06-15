import React from 'react';
import { Checkbox, Nav, type INavLink, type INavLinkGroup } from '@fluentui/react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, parseActionSpec, requestActionConfirm, toBoolean } from '@/renderers/shared';
import { evaluateRule } from '@/renderers/rules';

export const resolveIconClass = (icon: any): string | null => {
  const raw = String(icon?.iconName || icon || '').trim();
  if (!raw) return null;

  if (raw.startsWith('ric.')) return `ri-${raw.slice(4)}`;
  if (raw.startsWith('ri.')) return `ri-${raw.slice(3)}`;
  if (raw.startsWith('ri-')) return raw;

  const map: Record<string, string> = {
    app: 'ri-apps-2-line',
    dashboard: 'ri-dashboard-3-line',
    settings: 'ri-settings-2-line',
    user: 'ri-user-3-line',
    logout: 'ri-logout-box-line',
    chat: 'ri-chat-3-line',
    file: 'ri-file-line',
    folder: 'ri-folder-line',
  };

  return map[raw.toLowerCase()] || 'ri-apps-2-line';
};

interface TreeViewProps {
  nodes?: any[];
  action?: any; 
  click_action?: any;
  select_action?: any;
  params?: Record<string, any>;
  style?: any;
  expand_all?: boolean;
  selection_mode?: 'single' | 'multiple' | 'none';
  click_mode?: 'single' | 'double' | 'none';
  active_id?: string | number | Array<string | number> | null;
  onAction?: (name: string, ctx: any) => void;
  dataModel?: any;
  stateModel?: any;
  surfaceId?: string;
  item?: Record<string, any>;
}

const collectInitialState = (
  nodes: any[],
  expandAll: boolean,
  activeIds: Set<string>,
  expandedMap: Record<string, boolean>,
  forceExpand: boolean,
  ruleOptions: any
): boolean => {
  let anyActiveOrExpanded = false;
  (nodes || []).forEach((node) => {
    if (!node || typeof node !== 'object') return;
    const id = String(node.id || '');
    const nodeActive = evaluateRule(node.active, { ...ruleOptions, item: node }, false);
    const isThisActive = id !== '' && activeIds.has(id);
    const isActive = isThisActive || nodeActive;
    const isThisExpanded = toBoolean(node.expanded);

    if (expandAll || isThisExpanded || isActive) {
      if (expandedMap[id] === undefined || (isActive && forceExpand)) {
        expandedMap[id] = true;
      }
    }

    if (isActive) anyActiveOrExpanded = true;

    if (Array.isArray(node.children)) {
      const childrenActive = collectInitialState(node.children, expandAll, activeIds, expandedMap, forceExpand, ruleOptions);
      if (childrenActive) {
        expandedMap[id] = true;
        anyActiveOrExpanded = true;
      }
    }
  });
  return anyActiveOrExpanded;
};

const Row: React.FC<{
  node: any;
  depth: number;
  expandedMap: Record<string, boolean>;
  selectedIds: Set<string>;
  activeIds: Set<string>;
  activeBranchIds: Set<string>;
  clickMode: string;
  selectionMode: 'single' | 'multiple' | 'none';
  ruleOptions: any;
  onToggle: (id: string) => void;
  onClick: (node: any, selectOnly?: boolean) => void;
  onDoubleClick: (node: any) => void;
}> = ({ node, depth, expandedMap, selectedIds, activeIds, activeBranchIds, clickMode, selectionMode, ruleOptions, onToggle, onClick, onDoubleClick }) => {
  const children = Array.isArray(node?.children) ? node.children : [];
  const hasChildren = children.length > 0;
  const nodeId = String(node?.id || '');
  const expanded = !!expandedMap[nodeId];
  const isSelectable = node?.selectable !== false;
  const label = getLiteral(node?.label || nodeId);
  const nodeActive = evaluateRule(node?.active, { ...ruleOptions, item: node }, false);
  const isActive = (nodeId !== '' && activeIds.has(nodeId)) || nodeActive;
  const isActiveBranch = !isActive && nodeId !== '' && activeBranchIds.has(nodeId);
  const isSelected = nodeId !== '' && selectedIds.has(nodeId);
  const isDisabled = !!node?.disabled;

  const handleInteraction = (type: 'single' | 'double') => {
    if (isDisabled) return;
    
    if (type === 'single') {
      if (clickMode !== 'double') {
        if (!isSelectable) return;
        onClick(node);
      } else {
        if (!isSelectable) return;
        onClick(node, true); 
      }
    } else if (type === 'double' && clickMode === 'double' && isSelectable) {
      onDoubleClick(node);
    }
  };

  return (
    <div
      className="ds-tree-node"
      role="treeitem"
      aria-expanded={hasChildren ? expanded : undefined}
      aria-disabled={isDisabled || undefined}
      aria-selected={isSelected}
    >
      <div
        className={`ds-tree-item-layout ${isActive ? 'ds-tree-item-active' : ''} ${isActiveBranch ? 'ds-tree-item-active-branch' : ''} ${isSelected ? 'ds-tree-item-selected' : ''} ${isDisabled ? 'ds-tree-item-disabled' : ''}`}
        style={{ '--ds-tree-depth': depth } as React.CSSProperties}
        aria-current={isActive ? 'page' : undefined}
        onClick={() => handleInteraction('single')}
        onDoubleClick={() => handleInteraction('double')}
        onKeyDown={(event) => {
          if (event.key === 'Enter') handleInteraction('single');
          if (event.key === ' ' && selectionMode !== 'none') {
            event.preventDefault();
            handleInteraction('single');
          }
        }}
        tabIndex={isDisabled ? -1 : 0}
      >
        <button
          type="button"
          className="ds-tree-expander"
          disabled={!hasChildren || isDisabled}
          aria-label={expanded ? 'Collapse' : 'Expand'}
          onClick={(event) => {
            event.stopPropagation();
            if (hasChildren && !isDisabled) onToggle(nodeId);
          }}
        >
          {hasChildren ? <i className={expanded ? 'ri-arrow-down-s-line' : 'ri-arrow-right-s-line'} aria-hidden="true" /> : null}
        </button>
        {selectionMode === 'multiple' ? (
          <span className="ds-tree-checkbox" onClick={(event) => event.stopPropagation()}>
            <Checkbox
              checked={isSelected}
              disabled={!isSelectable || isDisabled}
              onChange={() => handleInteraction('single')}
              ariaLabel={label}
            />
          </span>
        ) : null}
        {node.icon ? <i className={`ds-tree-icon ${resolveIconClass(node.icon) || ''}`} aria-hidden="true" /> : null}
        <span className="ds-tree-label">{label}</span>
      </div>
      {hasChildren && expanded ? (
        <div className="ds-tree-group" role="group">
          {children.map((child: any, idx: number) => (
            <Row
              key={`${nodeId || 'root'}::${idx}::${String(child?.id || '')}`}
              node={child}
              depth={depth + 1}
              expandedMap={expandedMap}
              selectedIds={selectedIds}
              activeIds={activeIds}
              activeBranchIds={activeBranchIds}
              clickMode={clickMode}
              selectionMode={selectionMode}
              ruleOptions={ruleOptions}
              onToggle={onToggle}
              onClick={onClick}
              onDoubleClick={onDoubleClick}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
};

export const TreeView: React.FC<TreeViewProps> = ({
  nodes = [],
  action,
  click_action,
  select_action,
  params = {},
  style,
  expand_all = false,
  selection_mode = 'single',
  click_mode = 'single',
  active_id,
  onAction,
  dataModel,
  stateModel,
  surfaceId,
  item
}) => {
  const [expandedState, setExpandedState] = React.useState<Record<string, boolean>>({});
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  const [nodesMap, setNodesMap] = React.useState<Record<string, any>>({});
  const lastActiveSignatureRef = React.useRef<string | null>(null);
  const safeNodes = React.useMemo(() => (Array.isArray(nodes) ? nodes : []), [nodes]);

  const effectiveActiveIds = React.useMemo(() => {
    if (active_id == null) return new Set<string>();
    if (Array.isArray(active_id)) {
      return new Set(active_id.map((entry) => String(entry)).filter((entry) => entry !== ''));
    }
    const value = String(active_id);
    return value ? new Set([value]) : new Set<string>();
  }, [active_id]);
  const activeSignature = React.useMemo(
    () => Array.from(effectiveActiveIds).sort().join('|'),
    [effectiveActiveIds],
  );

  const ruleOptions = React.useMemo(() => ({
    surfaceModel: surfaceId ? dataModel?.[surfaceId] : {},
    stateModel,
    item
  }), [dataModel, stateModel, surfaceId, item]);

  const activeBranchIds = React.useMemo(() => {
    const branchSet = new Set<string>();
    const visit = (items: any[]): boolean => {
      let subtreeHasActive = false;
      (items || []).forEach((node) => {
        if (!node || typeof node !== 'object') return;
        const id = String(node.id || '');
        const nodeActive = evaluateRule(node.active, { ...ruleOptions, item: node }, false);
        const isActive = (id !== '' && effectiveActiveIds.has(id)) || nodeActive;
        const childrenActive = Array.isArray(node.children) ? visit(node.children) : false;
        const hasActive = isActive || childrenActive;
        if (hasActive && id) branchSet.add(id);
        if (hasActive) subtreeHasActive = true;
      });
      return subtreeHasActive;
    };
    visit(safeNodes);
    return branchSet;
  }, [safeNodes, effectiveActiveIds, ruleOptions]);

  React.useEffect(() => {
    const nextExp: Record<string, boolean> = { ...expandedState };
    const nextMap: Record<string, any> = {};

    const flatten = (items: any[]) => {
      items.forEach(node => {
        if (!node) return;
        const id = String(node.id || '');
        nextMap[id] = node;
        if (Array.isArray(node.children)) flatten(node.children);
      });
    };
    flatten(safeNodes);

    const activeIdChanged = lastActiveSignatureRef.current !== null && activeSignature !== lastActiveSignatureRef.current;
    
    collectInitialState(safeNodes, toBoolean(expand_all), effectiveActiveIds, nextExp, activeIdChanged, ruleOptions);
    
    setNodesMap(nextMap);
    setExpandedState(nextExp);
    setSelectedIds((prev) => {
      const pruned = new Set<string>();
      prev.forEach((id) => {
        if (nextMap[id]) pruned.add(id);
      });
      return pruned;
    });
    lastActiveSignatureRef.current = activeSignature;
  }, [safeNodes, expand_all, effectiveActiveIds, activeSignature, ruleOptions]);

  const handleToggle = (id: string) => {
    setExpandedState((prev) => {
      const isExpanded = !!prev[id];
      if (isExpanded && activeBranchIds.has(id)) return prev;
      return { ...prev, [id]: !isExpanded };
    });
  };

  const confirmedEmit = async (action: any, extra: Record<string, any>) => {
    const parsed = parseActionSpec(action);
    if (!parsed.name) return false;
    if (parsed.confirm && !(await requestActionConfirm(parsed.confirm))) {
      return false;
    }
    const actionWithoutConfirm = action && typeof action === 'object'
      ? { ...action, confirm: undefined }
      : action;
    emitActionSpec(actionWithoutConfirm, onAction, extra);
    return true;
  };

  const handleSelectionAndAction = async (node: any, selectOnly = false) => {
    const nodeId = String(node.id || '');
    
    if (selection_mode !== 'none') {
      let nextSelected: Set<string>;
      if (selection_mode === 'multiple') {
        nextSelected = new Set(selectedIds);
        if (nextSelected.has(nodeId)) nextSelected.delete(nodeId);
        else nextSelected.add(nodeId);
      } else {
        nextSelected = new Set([nodeId]);
      }

      if (select_action) {
        const selectedPayload = Array.from(nextSelected).map(id => {
          const n = nodesMap[id] || {};
          return {
            id,
            label: getLiteral(n.label || id),
            value: n.value,
            path: n.path,
            meta: n.meta,
          };
        });
        
        const accepted = await confirmedEmit(select_action, {
          ...params,
          selected_items: selectedPayload,
          active_id: nodeId,
        });
        if (!accepted) return;
      }
      setSelectedIds(nextSelected);
    }

    if (!selectOnly) {
      const clickAct = click_action || action;
      if (clickAct) {
        await confirmedEmit(clickAct, {
          ...params,
          id: nodeId,
          label: getLiteral(node.label || nodeId),
          value: node?.value,
          path: node?.path,
          meta: node?.meta,
        });
      }
    }
  };

  const navSelectedKey = React.useMemo(() => {
    const explicitActive = Array.from(effectiveActiveIds)[0];
    if (explicitActive) return explicitActive;

    let ruleActive = '';
    const findRuleActive = (items: any[]) => {
      for (const node of items || []) {
        if (!node || typeof node !== 'object') continue;
        const id = String(node.id || '');
        if (id && evaluateRule(node.active, { ...ruleOptions, item: node }, false)) {
          ruleActive = id;
          return;
        }
        if (Array.isArray(node.children)) findRuleActive(node.children);
        if (ruleActive) return;
      }
    };
    findRuleActive(safeNodes);
    if (ruleActive) return ruleActive;

    if (selection_mode === 'single') return Array.from(selectedIds)[0] || undefined;
    return undefined;
  }, [effectiveActiveIds, ruleOptions, safeNodes, selectedIds, selection_mode]);

  const buildNavLink = (node: any): INavLink => {
    const id = String(node?.id || '');
    const label = getLiteral(node?.label || id);
    const children = Array.isArray(node?.children) ? node.children : [];
    return {
      key: id,
      name: label,
      url: '',
      title: label,
      disabled: !!node?.disabled,
      ariaCurrent: id && id === navSelectedKey ? 'page' : undefined,
      isExpanded: children.length > 0 ? !!expandedState[id] : undefined,
      links: children.length > 0 ? children.map(buildNavLink) : undefined,
      expandAriaLabel: 'Expand',
      collapseAriaLabel: 'Collapse',
      onClick: async (event?: React.MouseEvent<HTMLElement>) => {
        event?.preventDefault();
        event?.stopPropagation();
        if (node?.disabled || node?.selectable === false) return;
        await handleSelectionAndAction(node, click_mode === 'double');
      },
      data: {
        node,
        iconClass: node?.icon ? resolveIconClass(node.icon) : null,
        activeBranch: id !== '' && activeBranchIds.has(id) && id !== navSelectedKey,
      },
    };
  };

  const navGroups: INavLinkGroup[] = [{
    links: safeNodes.map(buildNavLink),
  }];

  return (
    selection_mode === 'multiple' ? (
      <div className="ds-tree" role="tree" style={parseStyle(style)} aria-multiselectable>
        {safeNodes.map((node: any, idx: number) => (
          <Row
            key={`root::${idx}::${String(node?.id || '')}`}
            node={node}
            depth={0}
            expandedMap={expandedState}
            selectedIds={selectedIds}
            activeIds={effectiveActiveIds}
            activeBranchIds={activeBranchIds}
            clickMode={click_mode}
            selectionMode={selection_mode}
            ruleOptions={ruleOptions}
            onToggle={handleToggle}
            onClick={handleSelectionAndAction}
            onDoubleClick={(n) => handleSelectionAndAction(n, false)}
          />
        ))}
      </div>
    ) : (
      <Nav
        className="ds-tree-nav"
        styles={{ root: parseStyle(style) }}
        groups={navGroups}
        selectedKey={navSelectedKey}
        expandButtonAriaLabel="Expand or collapse"
        onLinkExpandClick={(event, item) => {
          event?.preventDefault();
          event?.stopPropagation();
          const id = String(item?.key || '');
          if (!id) return;
          if (item?.isExpanded && activeBranchIds.has(id)) return;
          setExpandedState((prev) => ({ ...prev, [id]: !item?.isExpanded }));
        }}
        onRenderLink={(link) => {
          const iconClass = link?.data?.iconClass;
          const activeBranch = link?.data?.activeBranch;
          return (
            <span className={`ds-tree-nav-link-content ${activeBranch ? 'ds-tree-nav-link-branch' : ''}`}>
              {iconClass ? <i className={`ds-tree-nav-icon ${iconClass}`} aria-hidden="true" /> : null}
              <span className="ds-tree-nav-label">{link?.name}</span>
            </span>
          );
        }}
      />
    )
  );
};
