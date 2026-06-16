import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import {
  emitActionSpec,
  getLiteral,
  parseActionSpec,
  requestActionConfirm,
  toBoolean,
} from '../../shared';
import { evaluateRule } from '../../rules';
import { parseStyle } from '../../../utils/style';
import { Icon } from '../../../components/a2ui/Icon';

type TreeViewProps = {
  items?: any[];
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
  full_height?: boolean;
  min_height?: number | string;
  onAction?: (name: string, ctx: any) => void;
  dataModel?: any;
  stateModel?: any;
  surfaceId?: string;
  item?: Record<string, any>;
};

const collectInitialState = (
  nodes: any[],
  expandAll: boolean,
  activeIds: Set<string>,
  expandedMap: Record<string, boolean>,
  forceExpand: boolean,
  ruleOptions: any,
): boolean => {
  let subtreeHasActive = false;
  (nodes || []).forEach((node) => {
    if (!node || typeof node !== 'object') return;
    const id = String(node.id || '');
    const nodeActive = evaluateRule(node.active, { ...ruleOptions, item: node }, false);
    const isActive = (id !== '' && activeIds.has(id)) || nodeActive;
    const isExpanded = toBoolean(node.expanded);

    if (expandAll || isExpanded || isActive) {
      if (expandedMap[id] === undefined || (isActive && forceExpand)) expandedMap[id] = true;
    }

    const childrenActive = Array.isArray(node.children)
      ? collectInitialState(node.children, expandAll, activeIds, expandedMap, forceExpand, ruleOptions)
      : false;
    if (childrenActive && id) expandedMap[id] = true;
    if (isActive || childrenActive) subtreeHasActive = true;
  });
  return subtreeHasActive;
};

const TreeRow: React.FC<{
  node: any;
  depth: number;
  expandedMap: Record<string, boolean>;
  selectedIds: Set<string>;
  activeIds: Set<string>;
  activeBranchIds: Set<string>;
  clickMode: string;
  ruleOptions: any;
  onToggle: (id: string) => void;
  onClick: (node: any, selectOnly?: boolean) => void;
  onDoubleClick: (node: any) => void;
}> = ({
  node,
  depth,
  expandedMap,
  selectedIds,
  activeIds,
  activeBranchIds,
  clickMode,
  ruleOptions,
  onToggle,
  onClick,
  onDoubleClick,
}) => {
  const lastPressRef = React.useRef(0);
  const children = Array.isArray(node?.children) ? node.children : [];
  const hasChildren = children.length > 0;
  const nodeId = String(node?.id || '');
  const expanded = !!expandedMap[nodeId];
  const collapseLocked = hasChildren && expanded && activeBranchIds.has(nodeId);
  const isSelected = selectedIds.has(nodeId);
  const nodeActive = evaluateRule(node?.active, { ...ruleOptions, item: node }, false);
  const isActive = (nodeId !== '' && activeIds.has(nodeId)) || nodeActive;
  const isSelectable = node?.selectable !== false;
  const disabled = Boolean(node?.disabled);
  const label = getLiteral(node?.label || node?.title || nodeId);

  const handleRowPress = () => {
    if (disabled) return;

    if (clickMode === 'none') {
      if (hasChildren) onToggle(nodeId);
      return;
    }

    if (clickMode === 'double') {
      const now = Date.now();
      const isDouble = now - lastPressRef.current < 320;
      lastPressRef.current = now;
      if (isDouble) {
        if (isSelectable) onDoubleClick(node);
      } else if (isSelectable) {
        onClick(node, true);
      }
      return;
    }

    if (hasChildren) onToggle(nodeId);
    if (isSelectable) onClick(node);
  };

  const handleChevronPress = () => {
    if (!hasChildren || collapseLocked || disabled) return;
    onToggle(nodeId);
  };

  return (
    <View style={styles.rowGroup}>
      <TouchableOpacity
        style={[
          styles.item,
          { paddingLeft: 8 + depth * 16 },
          (isSelected || isActive) && styles.itemActive,
          disabled && styles.itemDisabled,
        ]}
        onPress={handleRowPress}
        activeOpacity={disabled ? 1 : 0.72}
      >
        <TouchableOpacity
          style={[styles.chevronContainer, collapseLocked && styles.chevronLocked]}
          onPress={handleChevronPress}
          disabled={!hasChildren || collapseLocked || disabled}
          activeOpacity={0.7}
        >
          {hasChildren ? (
            <Icon
              name={expanded ? 'arrow-down-s-line' : 'arrow-right-s-line'}
              size={16}
              color={isActive ? '#E6EDF3' : '#8B949E'}
            />
          ) : (
            <View style={styles.emptyChevron} />
          )}
        </TouchableOpacity>

        {node?.icon ? (
          <View style={styles.iconContainer}>
            <Icon name={node.icon} size={15} color={isActive ? '#E6EDF3' : '#8B949E'} />
          </View>
        ) : null}

        <Text
          style={[
            styles.label,
            (isSelected || isActive) && styles.labelActive,
            disabled && styles.labelDisabled,
          ]}
          numberOfLines={1}
        >
          {label}
        </Text>
      </TouchableOpacity>

      {hasChildren && expanded ? (
        <View style={styles.children}>
          {children.map((child: any, idx: number) => (
            <TreeRow
              key={`${nodeId || 'root'}::${idx}::${String(child?.id || '')}`}
              node={child}
              depth={depth + 1}
              expandedMap={expandedMap}
              selectedIds={selectedIds}
              activeIds={activeIds}
              activeBranchIds={activeBranchIds}
              clickMode={clickMode}
              ruleOptions={ruleOptions}
              onToggle={onToggle}
              onClick={onClick}
              onDoubleClick={onDoubleClick}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
};

export const TreeView: React.FC<TreeViewProps> = ({
  items,
  nodes,
  action,
  click_action,
  select_action,
  params = {},
  style,
  expand_all = false,
  selection_mode = 'single',
  click_mode = 'single',
  active_id,
  full_height,
  min_height,
  onAction,
  dataModel,
  stateModel,
  surfaceId,
  item,
}) => {
  const [expandedState, setExpandedState] = React.useState<Record<string, boolean>>({});
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  const [nodesMap, setNodesMap] = React.useState<Record<string, any>>({});
  const lastActiveSignatureRef = React.useRef<string | null>(null);
  const safeNodes = React.useMemo(
    () => (Array.isArray(nodes) ? nodes : Array.isArray(items) ? items : []),
    [items, nodes],
  );
  const minHeightValue = typeof min_height === 'number'
    ? min_height
    : typeof min_height === 'string' && min_height.trim()
      ? Number(min_height)
      : undefined;

  const effectiveActiveIds = React.useMemo(() => {
    if (active_id == null) return new Set<string>();
    if (Array.isArray(active_id)) {
      return new Set(active_id.map((entry) => String(entry)).filter(Boolean));
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
    item,
  }), [dataModel, item, stateModel, surfaceId]);

  const activeBranchIds = React.useMemo(() => {
    const branchSet = new Set<string>();
    const visit = (treeItems: any[]): boolean => {
      let subtreeHasActive = false;
      (treeItems || []).forEach((node) => {
        if (!node || typeof node !== 'object') return;
        const id = String(node.id || '');
        const nodeActive = evaluateRule(node.active, { ...ruleOptions, item: node }, false);
        const isActive = (id !== '' && effectiveActiveIds.has(id)) || nodeActive;
        const childrenActive = Array.isArray(node.children) ? visit(node.children) : false;
        if ((isActive || childrenActive) && id) branchSet.add(id);
        if (isActive || childrenActive) subtreeHasActive = true;
      });
      return subtreeHasActive;
    };
    visit(safeNodes);
    return branchSet;
  }, [effectiveActiveIds, ruleOptions, safeNodes]);

  React.useEffect(() => {
    const nextExpanded: Record<string, boolean> = { ...expandedState };
    const nextMap: Record<string, any> = {};
    const flatten = (treeItems: any[]) => {
      treeItems.forEach((node) => {
        if (!node) return;
        const id = String(node.id || '');
        if (id) nextMap[id] = node;
        if (Array.isArray(node.children)) flatten(node.children);
      });
    };
    flatten(safeNodes);

    const activeChanged = lastActiveSignatureRef.current !== null && activeSignature !== lastActiveSignatureRef.current;
    collectInitialState(safeNodes, toBoolean(expand_all), effectiveActiveIds, nextExpanded, activeChanged, ruleOptions);

    setNodesMap(nextMap);
    setExpandedState(nextExpanded);
    setSelectedIds((prev) => {
      const pruned = new Set<string>();
      prev.forEach((id) => {
        if (nextMap[id]) pruned.add(id);
      });
      return pruned;
    });
    lastActiveSignatureRef.current = activeSignature;
    // expandedState is intentionally not a dependency: this effect derives state
    // from server nodes/active id changes, while user toggles update state locally.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSignature, effectiveActiveIds, expand_all, ruleOptions, safeNodes]);

  const handleToggle = React.useCallback((id: string) => {
    if (!id) return;
    setExpandedState((prev) => {
      const isExpanded = !!prev[id];
      if (isExpanded && activeBranchIds.has(id)) return prev;
      return { ...prev, [id]: !isExpanded };
    });
  }, [activeBranchIds]);

  const confirmedEmit = React.useCallback(async (actionSpec: any, extra: Record<string, any>) => {
    const parsed = parseActionSpec(actionSpec);
    if (!parsed.name) return false;
    if (parsed.confirm && !(await requestActionConfirm(parsed.confirm))) return false;
    const actionWithoutConfirm = actionSpec && typeof actionSpec === 'object'
      ? { ...actionSpec, confirm: undefined }
      : actionSpec;
    emitActionSpec(actionWithoutConfirm, onAction, extra);
    return true;
  }, [onAction]);

  const handleSelectionAndAction = React.useCallback(async (node: any, selectOnly = false) => {
    const nodeId = String(node?.id || '');

    if (selection_mode !== 'none') {
      let nextSelected: Set<string>;
      if (selection_mode === 'multiple') {
        nextSelected = new Set(selectedIds);
        if (nextSelected.has(nodeId)) nextSelected.delete(nodeId);
        else if (nodeId) nextSelected.add(nodeId);
      } else {
        nextSelected = nodeId ? new Set([nodeId]) : new Set();
      }

      if (select_action) {
        const selectedPayload = Array.from(nextSelected).map((id) => {
          const selectedNode = nodesMap[id] || {};
          return {
            id,
            label: getLiteral(selectedNode.label || id),
            value: selectedNode.value,
            path: selectedNode.path,
            meta: selectedNode.meta,
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
      const clickAction = click_action || action;
      if (clickAction) {
        await confirmedEmit(clickAction, {
          ...params,
          id: nodeId,
          label: getLiteral(node?.label || nodeId),
          value: node?.value,
          path: node?.path,
          meta: node?.meta,
        });
      }
    }
  }, [action, click_action, confirmedEmit, nodesMap, params, select_action, selectedIds, selection_mode]);

  return (
    <ScrollView
      style={[
        styles.container,
        full_height ? styles.fullHeight : null,
        Number.isFinite(minHeightValue) ? { minHeight: minHeightValue } : null,
        parseStyle(style),
      ]}
      contentContainerStyle={styles.content}
      nestedScrollEnabled
    >
      {safeNodes.length > 0 ? (
        safeNodes.map((node: any, idx: number) => (
          <TreeRow
            key={`root::${idx}::${String(node?.id || '')}`}
            node={node}
            depth={0}
            expandedMap={expandedState}
            selectedIds={selectedIds}
            activeIds={effectiveActiveIds}
            activeBranchIds={activeBranchIds}
            clickMode={String(click_mode || 'single')}
            ruleOptions={ruleOptions}
            onToggle={handleToggle}
            onClick={handleSelectionAndAction}
            onDoubleClick={(entry) => handleSelectionAndAction(entry, false)}
          />
        ))
      ) : (
        <Text style={styles.empty}>No items</Text>
      )}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
    flex: 1,
    minHeight: 0,
  },
  fullHeight: {
    flex: 1,
  },
  content: {
    paddingVertical: 2,
    flexGrow: 1,
  },
  empty: {
    color: '#6E7681',
    fontSize: 13,
    padding: 12,
  },
  rowGroup: {
    width: '100%',
  },
  children: {
    width: '100%',
  },
  item: {
    minHeight: 34,
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    paddingRight: 8,
    borderRadius: 4,
  },
  itemActive: {
    backgroundColor: '#21262D',
  },
  itemDisabled: {
    opacity: 0.48,
  },
  chevronContainer: {
    width: 22,
    height: 22,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 2,
    borderRadius: 4,
  },
  chevronLocked: {
    opacity: 0.7,
  },
  emptyChevron: {
    width: 16,
  },
  iconContainer: {
    width: 20,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 7,
  },
  label: {
    flex: 1,
    fontSize: 14,
    color: '#8B949E',
  },
  labelActive: {
    color: '#E6EDF3',
    fontWeight: '600',
  },
  labelDisabled: {
    color: '#6E7681',
  },
});
