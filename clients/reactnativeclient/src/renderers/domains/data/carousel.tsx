import React from 'react';
import {
  LayoutChangeEvent,
  NativeScrollEvent,
  NativeSyntheticEvent,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  ViewStyle,
} from 'react-native';
import { InternalRenderer } from '../../../components/a2ui/Renderer';
import { Icon } from '../../../components/a2ui/Icon';
import { emitActionSpec, toBoolean } from '../../shared';

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
  const {
    kind: _kind,
    children,
    id,
    ...props
  } = template;

  return {
    id,
    component: { [kind]: props },
    children: Array.isArray(children) ? { explicitList: children.map(normalizeTemplate).filter(Boolean) } : undefined,
  };
};

export const Carousel: React.FC<any> = ({
  id,
  items,
  ExplicitList,
  dataSource,
  data_source,
  itemTemplate,
  item_template,
  onItemClick,
  on_item_click,
  onChange,
  on_change,
  activeIndex,
  active_index,
  autoplay = false,
  intervalMs,
  interval_ms,
  showDots,
  show_dots,
  showArrows,
  show_arrows,
  loop = true,
  style,
  surfaceId,
  surfaces,
  dataModel,
  stateModel,
  sendAction,
  onAction,
  setInput,
  userRole,
  userPermissions,
  pendingActions,
  backgroundTasks,
  jwt,
}) => {
  const scrollRef = React.useRef<ScrollView>(null);
  const [width, setWidth] = React.useState(0);
  const [selected, setSelected] = React.useState(Math.max(0, Number(activeIndex ?? active_index) || 0));
  const source = dataSource ?? data_source ?? (Array.isArray(items) ? { type: 'inline', data: items } : null);
  const template = React.useMemo(() => normalizeTemplate(itemTemplate ?? item_template), [itemTemplate, item_template]);
  const renderedChildren = Array.isArray(ExplicitList) ? ExplicitList : [];
  const dataItems = React.useMemo(
    () => resolveItems(source, dataModel, stateModel, surfaceId),
    [source, dataModel, stateModel, surfaceId],
  );
  const slides = template ? dataItems : renderedChildren;
  const count = slides.length;
  const dotsVisible = showDots ?? show_dots ?? true;
  const arrowsVisible = showArrows ?? show_arrows ?? true;
  const interval = Math.max(500, Number(intervalMs ?? interval_ms) || 3000);
  const emit = onAction || sendAction;

  const clampIndex = React.useCallback((index: number) => {
    if (count <= 0) return 0;
    if (toBoolean(loop)) return ((index % count) + count) % count;
    return Math.max(0, Math.min(count - 1, index));
  }, [count, loop]);

  const goTo = React.useCallback((index: number, emitChange = true) => {
    const next = clampIndex(index);
    setSelected(next);
    if (width > 0) {
      scrollRef.current?.scrollTo({ x: next * width, animated: true });
    }
    if (emitChange) {
      emitActionSpec(onChange ?? on_change, emit, {
        source: 'carousel',
        index: next,
        itemId: dataItems[next]?.id,
        item: dataItems[next],
      });
    }
  }, [clampIndex, dataItems, emit, onChange, on_change, width]);

  React.useEffect(() => {
    const next = clampIndex(Number(activeIndex ?? active_index) || 0);
    setSelected(next);
    if (width > 0) scrollRef.current?.scrollTo({ x: next * width, animated: false });
  }, [activeIndex, active_index, clampIndex, width]);

  React.useEffect(() => {
    if (!toBoolean(autoplay) || count <= 1) return undefined;
    const timer = setInterval(() => goTo(selected + 1), interval);
    return () => clearInterval(timer);
  }, [autoplay, count, goTo, interval, selected]);

  const handleLayout = (event: LayoutChangeEvent) => {
    setWidth(event.nativeEvent.layout.width);
  };

  const handleMomentumEnd = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (width <= 0) return;
    const next = clampIndex(Math.round(event.nativeEvent.contentOffset.x / width));
    if (next === selected) return;
    setSelected(next);
    emitActionSpec(onChange ?? on_change, emit, {
      source: 'carousel',
      index: next,
      itemId: dataItems[next]?.id,
      item: dataItems[next],
    });
  };

  if (!count) {
    return (
      <View style={[styles.empty, style as ViewStyle]}>
        <Text style={styles.emptyText}>{template ? 'No carousel items' : 'No carousel template'}</Text>
      </View>
    );
  }

  return (
    <View style={[styles.container, style as ViewStyle]} onLayout={handleLayout}>
      <View style={styles.viewport}>
        <ScrollView
          ref={scrollRef}
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          onMomentumScrollEnd={handleMomentumEnd}
          scrollEventThrottle={16}
        >
          {slides.map((slide: any, index: number) => (
            <TouchableOpacity
              key={dataItems[index]?.id || `${id || 'carousel'}_slide_${index}`}
              activeOpacity={(onItemClick || on_item_click) ? 0.86 : 1}
              onPress={() => emitActionSpec(onItemClick ?? on_item_click, emit, {
                item: dataItems[index],
                index,
                itemId: dataItems[index]?.id,
              })}
              style={[styles.slide, { width: Math.max(1, width) }]}
            >
              {template ? (
                <InternalRenderer
                  componentData={template}
                  surfaceId={surfaceId}
                  surfaces={surfaces}
                  dataModel={dataModel}
                  stateModel={stateModel}
                  sendAction={sendAction}
                  setInput={setInput}
                  componentId={`${id || 'carousel'}_item_${index}`}
                  userRole={userRole}
                  userPermissions={userPermissions}
                  pendingActions={pendingActions}
                  backgroundTasks={backgroundTasks}
                  jwt={jwt}
                  item={dataItems[index]}
                />
              ) : slide}
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {(arrowsVisible || dotsVisible) && count > 1 ? (
        <View style={styles.controls}>
          {arrowsVisible ? (
            <TouchableOpacity style={styles.arrowButton} onPress={() => goTo(selected - 1)} activeOpacity={0.75}>
              <Icon name="ri-arrow-left-s-line" size={20} color="#C9D1D9" />
            </TouchableOpacity>
          ) : null}

          {dotsVisible ? (
            <View style={styles.dots}>
              {slides.map((_: any, index: number) => (
                <TouchableOpacity
                  key={`dot_${index}`}
                  onPress={() => goTo(index)}
                  style={[styles.dot, index === selected && styles.dotActive]}
                  activeOpacity={0.75}
                />
              ))}
            </View>
          ) : null}

          {arrowsVisible ? (
            <TouchableOpacity style={styles.arrowButton} onPress={() => goTo(selected + 1)} activeOpacity={0.75}>
              <Icon name="ri-arrow-right-s-line" size={20} color="#C9D1D9" />
            </TouchableOpacity>
          ) : null}
        </View>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
    maxWidth: '100%',
    minWidth: 0,
    marginVertical: 6,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    overflow: 'hidden',
  },
  viewport: {
    width: '100%',
    minWidth: 0,
    overflow: 'hidden',
  },
  slide: {
    padding: 10,
  },
  controls: {
    minHeight: 48,
    borderTopWidth: 1,
    borderTopColor: '#30363D',
    backgroundColor: '#0D1117',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  arrowButton: {
    width: 34,
    height: 34,
    borderRadius: 7,
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#161B22',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dots: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    flexShrink: 1,
    minWidth: 0,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: '#484F58',
  },
  dotActive: {
    width: 18,
    backgroundColor: '#6366F1',
  },
  empty: {
    width: '100%',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    padding: 14,
  },
  emptyText: {
    color: '#8B949E',
    fontSize: 13,
  },
});
