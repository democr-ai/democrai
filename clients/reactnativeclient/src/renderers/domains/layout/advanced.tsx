import React, { useEffect, useMemo, useState } from 'react';
import { LayoutChangeEvent, PanResponder, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { getLiteral } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';
import { numberOrDefault, usePhoneLayout, useResponsiveStyle } from '../../../utils/responsive';

const normalizeSizes = (raw: number[]): number[] => {
  const total = raw.reduce((acc, n) => acc + n, 0);
  if (total <= 0) return raw;
  return raw.map((n) => (n / total) * 100);
};

const asNumberArray = (value: any): number[] => {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => Number(entry));
};

const nodeContainsType = (node: any, typeName: string): boolean => {
  if (!node || typeof node !== 'object') return false;
  const props = node.props || {};
  const id = String(props.id || props.componentId || props.component_id || '');
  if (typeName === 'TreeView' && (id.includes('tree') || id.includes('comp_list_container'))) return true;
  const type = node?.props?.componentData?.component
    ? Object.keys(node.props.componentData.component)[0]
    : node?.type?.name;
  if (type === typeName) return true;
  const explicit = props.ExplicitList;
  if (Array.isArray(explicit) && explicit.some((child) => nodeContainsType(child, typeName))) return true;
  const children = props.children;
  if (Array.isArray(children)) return children.some((child) => nodeContainsType(child, typeName));
  return nodeContainsType(children, typeName);
};

export const Dialog: React.FC<any> = ({ ExplicitList, children, title, open = false, onClose, width, maxWidth }) => {
  const resolvedWidth = Number(width || maxWidth || 0);
  const cardStyle = [
    styles.inlineDialogCard,
    resolvedWidth > 0 ? { maxWidth: resolvedWidth } : null,
  ];

  return (
    <View style={cardStyle}>
      {getLiteral(title) ? (
        <View style={styles.header}>
          <Text style={styles.title}>{getLiteral(title)}</Text>
        </View>
      ) : null}
      <View style={styles.inlineContent}>
        {ExplicitList || children}
      </View>
    </View>
  );
};

export const Grid: React.FC<any> = ({ ExplicitList, columns = 2, style, mobile_columns, mobileColumns, spacing }) => {
  const isPhone = usePhoneLayout();
  const responsiveStyle = useResponsiveStyle(style);
  const declaredCols = Math.max(1, numberOrDefault(columns, 2));
  const gap = numberOrDefault(spacing, 8);
  const children = React.Children.toArray(ExplicitList);

  if (isPhone) {
    return (
      <View style={[styles.gridPhone, { gap }, responsiveStyle]}>
        {children}
      </View>
    );
  }

  return (
    <View style={[styles.grid, styles.gridDesktop, responsiveStyle]}>
      {children.map((child, index) => (
        <View
          key={`grid_item_${index}`}
          style={[
            styles.gridItem,
            {
              width: `${100 / declaredCols}%`,
              maxWidth: `${100 / declaredCols}%`,
              padding: gap / 2,
            },
          ]}
        >
          {child}
        </View>
      ))}
    </View>
  );
};

export const Splitter: React.FC<any> = ({
  ExplicitList,
  direction = 'horizontal',
  sizes: declaredSizes,
  max_sizes: declaredMaxSizes,
  stretch,
  style,
  stateModel,
}) => {
  const isPhone = usePhoneLayout();
  const responsiveStyle = useResponsiveStyle(style);
  const panes = useMemo(() => React.Children.toArray(ExplicitList), [ExplicitList]);
  const initialSizes = useMemo(() => asNumberArray(declaredSizes).filter((n) => Number.isFinite(n) && n > 0), [declaredSizes]);
  const maxSizes = useMemo(() => asNumberArray(declaredMaxSizes), [declaredMaxSizes]);
  const [sizes, setSizes] = useState<number[]>([]);
  const [containerWidth, setContainerWidth] = useState(0);
  const [firstPaneOpen, setFirstPaneOpen] = useState(!isPhone);
  const isHorizontal = direction !== 'vertical';

  // Current route as tracked by the app (server-driven nav). When a menu pane
  // navigates, this changes — see modules/components nav items (type: "nav").
  const currentRoute = String(
    stateModel?.global?.current_path ?? stateModel?.current_path ?? stateModel?.currentPath ?? '',
  );
  const previousRouteRef = React.useRef(currentRoute);

  useEffect(() => {
    setFirstPaneOpen(!isPhone);
  }, [isPhone]);

  // On phone the panes share the screen via a toggle: the menu pane navigates,
  // then the user wants to land back on the main content. When the route
  // changes (i.e. a navigation actually happened), collapse the menu and show
  // the main pane. Expanding tree branches does not change the route, so the
  // menu stays open while browsing — only a real page change closes it.
  useEffect(() => {
    if (previousRouteRef.current === currentRoute) return;
    previousRouteRef.current = currentRoute;
    if (isPhone) setFirstPaneOpen(false);
  }, [currentRoute, isPhone]);

  useEffect(() => {
    if (panes.length === 0) {
      setSizes([]);
      return;
    }
    if (initialSizes.length === panes.length) {
      setSizes(normalizeSizes(initialSizes));
      return;
    }
    setSizes(new Array(panes.length).fill(100 / panes.length));
  }, [initialSizes, panes.length]);

  if (!isHorizontal || panes.length < 2) {
    return <View style={[styles.splitter, responsiveStyle]}>{ExplicitList}</View>;
  }

  const onLayout = (event: LayoutChangeEvent) => {
    setContainerWidth(event.nativeEvent.layout.width);
  };

  const resizePane = (index: number, deltaPx: number, startSizes: number[]) => {
    if (containerWidth <= 0) return;

    const separatorWidth = isPhone ? 34 : 12;
    const availableWidth = Math.max(1, containerWidth - (panes.length - 1) * separatorWidth);
    const deltaPct = (deltaPx / availableWidth) * 100;
    const minPct = Math.max(8, (96 / availableWidth) * 100);
    const leftMaxPx = maxSizes[index];
    const rightMaxPx = maxSizes[index + 1];
    const leftMaxPct = Number.isFinite(leftMaxPx) && leftMaxPx > 0 ? (leftMaxPx / availableWidth) * 100 : Infinity;
    const rightMaxPct = Number.isFinite(rightMaxPx) && rightMaxPx > 0 ? (rightMaxPx / availableWidth) * 100 : Infinity;
    const left = startSizes[index] + deltaPct;
    const right = startSizes[index + 1] - deltaPct;

    if (left < minPct || right < minPct) return;
    if (left > leftMaxPct || right > rightMaxPct) return;

    const next = [...startSizes];
    next[index] = left;
    next[index + 1] = right;
    setSizes(normalizeSizes(next));
  };

  const createSeparatorResponder = (index: number) => {
    let startSizes = sizes;
    return PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dx) > 2,
      onPanResponderGrant: () => {
        startSizes = [...sizes];
      },
      onPanResponderMove: (_, gesture) => {
        if (index === 0 && isPhone && !firstPaneOpen) return;
        resizePane(index, gesture.dx, startSizes);
      },
      onPanResponderRelease: (_, gesture) => {
        if (index === 0 && isPhone && Math.abs(gesture.dx) < 3) {
          setFirstPaneOpen((open) => !open);
        }
      },
    });
  };

  if (isPhone) {
    const menuPaneIndex = panes.findIndex((pane) => nodeContainsType(pane, 'TreeView'));
    const resolvedMenuIndex = menuPaneIndex >= 0 ? menuPaneIndex : 0;
    const menuPane = panes[resolvedMenuIndex];
    const mainPanes = panes.filter((_, index) => index !== resolvedMenuIndex);

    return (
      <View
        style={[styles.splitterPhone, stretch ? styles.splitterStretch : null, responsiveStyle]}
        onLayout={onLayout}
      >
        <View style={styles.splitterBar}>
          <TouchableOpacity
            style={[styles.splitterToggle, firstPaneOpen ? styles.splitterToggleActive : null]}
            onPress={() => setFirstPaneOpen(true)}
            activeOpacity={0.75}
          >
            <Icon
              name="ric.sidebar-unfold-line"
              size={18}
              color={firstPaneOpen ? '#E6EDF3' : '#8B949E'}
            />
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.splitterToggle, !firstPaneOpen ? styles.splitterToggleActive : null]}
            onPress={() => setFirstPaneOpen(false)}
            activeOpacity={0.75}
          >
            <Icon
              name="ric.file-list-3-line"
              size={18}
              color={!firstPaneOpen ? '#E6EDF3' : '#8B949E'}
            />
          </TouchableOpacity>
        </View>
        <View style={styles.splitterBody}>
          <View style={styles.splitterPaneFill}>
            {firstPaneOpen ? menuPane : mainPanes}
          </View>
        </View>
      </View>
    );
  }

  return (
    <View
      style={[styles.splitter, stretch ? styles.splitterStretch : null, responsiveStyle]}
      onLayout={onLayout}
    >
      {panes.map((child, idx) => {
        const separatorWidth = 12;
        const availableWidth = Math.max(0, containerWidth - (panes.length - 1) * separatorWidth);
        const size = sizes[idx] ?? (100 / panes.length);
        const maxPx = maxSizes[idx];
        const maxWidth = Number.isFinite(maxPx) && maxPx > 0 ? Number(maxPx) : undefined;
        const basis = availableWidth > 0 ? (availableWidth * size) / 100 : undefined;
        const paneStyle: any = [
          styles.splitterPaneFixed,
          basis ? { flexBasis: basis } : null,
          maxWidth ? { maxWidth } : null,
        ];
        const separatorResponder = idx < panes.length - 1 ? createSeparatorResponder(idx) : null;

        return (
          <React.Fragment key={idx}>
            <View style={paneStyle}>
              {child}
            </View>
            {separatorResponder ? (
              <View
                style={styles.splitterSeparator}
                {...separatorResponder.panHandlers}
              >
                <View style={styles.splitterGrip} pointerEvents="none">
                  <View style={styles.splitterGripLine} />
                  <View style={styles.splitterGripLine} />
                  <View style={styles.splitterGripLine} />
                </View>
              </View>
            ) : null}
          </React.Fragment>
        );
      })}
    </View>
  );
};

const styles = StyleSheet.create({
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.75)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  dialogCard: {
    width: '100%',
    maxWidth: 420,
    maxHeight: '86%',
    backgroundColor: '#1C2128',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#30363D',
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 12,
  },
  inlineDialogCard: {
    width: '100%',
    backgroundColor: '#1C2128',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#30363D',
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
    backgroundColor: '#161B22',
  },
  title: {
    fontSize: 17,
    fontWeight: '700',
    color: '#E6EDF3',
  },
  closeBtn: {
    padding: 4,
  },
  content: {
    flexGrow: 0,
    maxHeight: '100%',
  },
  contentInner: {
    padding: 14,
    flexGrow: 1,
    minHeight: 180,
  },
  contentSurface: {
    width: '100%',
    minHeight: 140,
    flexGrow: 1,
  },
  inlineContent: {
    padding: 14,
    width: '100%',
  },
  grid: {
    width: '100%',
    alignItems: 'stretch',
  },
  gridDesktop: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  gridPhone: {
    width: '100%',
    flexDirection: 'column',
    alignItems: 'stretch',
  },
  gridItem: {
    minWidth: 0,
    alignSelf: 'stretch',
  },
  splitter: {
    flex: 1,
    width: '100%',
    minHeight: 0,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  splitterPhone: {
    flex: 1,
    width: '100%',
    minHeight: 0,
    overflow: 'hidden',
    position: 'relative',
  },
  splitterStretch: {
    flexGrow: 1,
  },
  splitterBar: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 10,
    elevation: 8,
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 10,
    paddingTop: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
    backgroundColor: '#0F141B',
  },
  splitterToggle: {
    width: 54,
    minHeight: 40,
    borderTopLeftRadius: 7,
    borderTopRightRadius: 7,
    borderWidth: 1,
    borderBottomWidth: 0,
    borderColor: 'transparent',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  splitterToggleActive: {
    borderColor: '#30363D',
    backgroundColor: '#161B22',
  },
  splitterToggleLabel: {
    color: '#8B949E',
    fontSize: 13,
    fontWeight: '700',
  },
  splitterToggleLabelActive: {
    color: '#E6EDF3',
  },
  splitterBody: {
    flex: 1,
    minHeight: 0,
    flexDirection: 'row',
    overflow: 'hidden',
    paddingTop: 44,
  },
  splitterPaneFixed: {
    flexGrow: 0,
    flexShrink: 0,
    minWidth: 0,
    minHeight: 0,
    overflow: 'hidden',
  },
  splitterPaneFill: {
    flex: 1,
    minWidth: 0,
    minHeight: 0,
    overflow: 'hidden',
  },
  splitterPaneClosed: {
    width: 0,
    minWidth: 0,
    overflow: 'hidden',
  },
  splitterSeparator: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 12,
    flexShrink: 0,
    borderLeftWidth: 1,
    borderRightWidth: 1,
    borderLeftColor: '#30363D',
    borderRightColor: '#30363D',
    backgroundColor: '#0F141B',
  },
  splitterSeparatorToggle: {
    width: 34,
    backgroundColor: '#161B22',
  },
  splitterGrip: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
  },
  splitterGripLine: {
    width: 3,
    height: 3,
    borderRadius: 2,
    backgroundColor: '#8B949E',
  },
});
