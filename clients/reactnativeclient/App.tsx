import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  StatusBar,
  ActivityIndicator,
  TouchableOpacity,
  ScrollView,
  Modal,
  Pressable,
  Image as RNImage,
  Dimensions,
  useWindowDimensions,
  type ImageSourcePropType,
} from 'react-native';
import { SvgUri } from 'react-native-svg';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { useA2UI } from './src/hooks/useA2UI';
import { A2UIRenderer } from './src/components/a2ui/Renderer';
import { Icon } from './src/components/a2ui/Icon';
import { evaluateRule } from './src/renderers/rules';
import { getLiteral } from './src/renderers/shared';

// ─── Types ────────────────────────────────────────────────────────────────────

type NavEntry = {
  id?: string;
  label?: any;
  icon?: any;
  action?: { name: string; context?: Record<string, any> };
  active_condition?: any;
};

type DrawerPosition = 'top' | 'right' | 'bottom' | 'left';

const HEADER_LOGO = require('./assets/logo.svg') as ImageSourcePropType;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function visitSurfaceTree(surface: any, visitor: (componentData: any, componentId: string) => any): any {
  const components = surface?.components || {};
  const rootId = surface?.rootId || (components.root ? 'root' : '');
  const seen = new Set<string>();

  const visit = (node: any): any => {
    const componentId = typeof node === 'string' ? node : String(node?.id || '');
    const componentData = typeof node === 'string' ? components[node] : node;
    if (!componentData || typeof componentData !== 'object') return null;
    const seenKey = componentId || JSON.stringify(componentData).slice(0, 80);
    if (seen.has(seenKey)) return null;
    seen.add(seenKey);

    const result = visitor(componentData, componentId);
    if (result) return result;

    const explicitList = componentData.children?.explicitList;
    if (!Array.isArray(explicitList)) return null;
    for (const child of explicitList) {
      const nested = visit(child);
      if (nested) return nested;
    }
    return null;
  };

  return rootId ? visit(rootId) : null;
}

function findClientTagByPosition(surface: any, pos: string): any | null {
  return visitSurfaceTree(surface, (cd) => {
    const type = Object.keys(cd?.component || {})[0];
    const props = type === 'ClientTag' ? cd.component.ClientTag : null;
    return props?.position === pos ? props : null;
  });
}

function findClientTagById(surface: any, id: string): any | null {
  return visitSurfaceTree(surface, (cd, componentId) => {
    const type = Object.keys(cd?.component || {})[0];
    return type === 'ClientTag' && componentId === id ? cd.component.ClientTag : null;
  });
}

function readStatePath(source: any, path: string): any {
  const read = (root: any) => String(path || '')
    .replace(/^\//, '')
    .split(/[./]/)
    .filter(Boolean)
    .reduce((cursor: any, key) => (cursor == null ? undefined : cursor[key]), root);
  const page = read(source?.page);
  if (page !== undefined) return page;
  const global = read(source?.global);
  if (global !== undefined) return global;
  return read(source);
}

function resolveNavItems(tag: string | undefined, stateModel: any): NavEntry[] {
  if (!tag) return [];
  if (tag === 'appmainlist') return readStatePath(stateModel, '/system/modules/top') || [];
  if (tag === 'appbottommainlist') return readStatePath(stateModel, '/system/modules/bottom') || [];
  return [];
}

function drawerSide(value: unknown): DrawerPosition {
  return value === 'top' || value === 'bottom' || value === 'left' || value === 'right' ? value : 'right';
}

function positiveNumber(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function toastTone(notification: any): 'success' | 'error' | 'warning' | 'info' | 'default' {
  const raw = String(notification?.variant || notification?.kind || 'info').trim().toLowerCase();
  if (raw === 'success') return 'success';
  if (raw === 'error' || raw === 'danger') return 'error';
  if (raw === 'warning' || raw === 'warn') return 'warning';
  if (raw === 'info') return 'info';
  return 'default';
}

const ToastHost: React.FC<{ notification: any }> = ({ notification }) => {
  const [visible, setVisible] = useState(false);
  const [current, setCurrent] = useState<any>(null);

  useEffect(() => {
    const text = getLiteral(notification?.text || notification?.title || '');
    if (!text) return;
    setCurrent(notification);
    setVisible(true);
    const timer = setTimeout(() => setVisible(false), 4200);
    return () => clearTimeout(timer);
  }, [notification]);

  if (!visible || !current) return null;

  const tone = toastTone(current);
  const text = getLiteral(current.text || current.title || '');
  const title = current.text && current.title ? getLiteral(current.title) : '';
  const icon = tone === 'success'
    ? 'ri-checkbox-circle-fill'
    : tone === 'error'
      ? 'ri-error-warning-fill'
      : tone === 'warning'
        ? 'ri-alert-fill'
        : 'ri-information-fill';

  return (
    <TouchableOpacity
      style={[toastStyles.container, toastStyles[tone]]}
      activeOpacity={0.9}
      onPress={() => setVisible(false)}
    >
      <Icon name={icon} size={22} color={toastColors[tone]} />
      <View style={toastStyles.textWrap}>
        {title ? <Text style={toastStyles.title} numberOfLines={1}>{title}</Text> : null}
        <Text style={toastStyles.text} numberOfLines={3}>{text}</Text>
      </View>
      <Icon name="ri-close-line" size={18} color="#8B949E" />
    </TouchableOpacity>
  );
};

const toastColors = {
  success: '#3FB950',
  error: '#F85149',
  warning: '#D29922',
  info: '#58A6FF',
  default: '#8B949E',
};

const toastStyles = StyleSheet.create({
  container: {
    position: 'absolute',
    left: 12,
    right: 12,
    bottom: 18,
    zIndex: 1000,
    elevation: 12,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
    borderRadius: 8,
    borderWidth: 1,
    backgroundColor: '#161B22',
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 8 },
  },
  success: {
    borderColor: 'rgba(63,185,80,0.45)',
  },
  error: {
    borderColor: 'rgba(248,81,73,0.45)',
  },
  warning: {
    borderColor: 'rgba(210,153,34,0.45)',
  },
  info: {
    borderColor: 'rgba(88,166,255,0.45)',
  },
  default: {
    borderColor: '#30363D',
  },
  textWrap: {
    flex: 1,
    minWidth: 0,
  },
  title: {
    color: '#E6EDF3',
    fontSize: 13,
    fontWeight: '800',
    marginBottom: 2,
  },
  text: {
    color: '#C9D1D9',
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '600',
  },
});

// ─── Drawer Surface ──────────────────────────────────────────────────────────

const DrawerSurface: React.FC<{
  surface: any;
  rendererProps: any;
  onClose: () => void;
}> = ({ surface, rendererProps, onClose }) => {
  const position = drawerSide(surface?.options?.position);
  const dim = positiveNumber(surface?.options?.dim);
  const isHorizontal = position === 'left' || position === 'right';
  const windowSize = Dimensions.get('window');
  const panelDim = isHorizontal
    ? Math.min(dim || Math.round(windowSize.width * 0.86), Math.round(windowSize.width * 0.92))
    : Math.min(dim || Math.round(windowSize.height * 0.42), Math.round(windowSize.height * 0.72));
  const panelStyle = [
    drawerStyles.panel,
    drawerStyles[position],
    isHorizontal
      ? { width: panelDim }
      : { height: panelDim },
  ];
  const alignStyle = position === 'left'
    ? drawerStyles.alignLeft
    : position === 'top'
      ? drawerStyles.alignTop
      : position === 'bottom'
        ? drawerStyles.alignBottom
        : drawerStyles.alignRight;

  return (
    <Modal transparent animationType="fade" visible={Boolean(surface?.rootId)} onRequestClose={onClose}>
      <View style={[drawerStyles.overlay, alignStyle]}>
        <Pressable style={drawerStyles.backdrop} onPress={onClose} />
        <View style={panelStyle as any}>
          <View style={[drawerStyles.header, position === 'right' ? drawerStyles.headerLeft : drawerStyles.headerRight]}>
            <TouchableOpacity style={drawerStyles.closeButton} onPress={onClose} activeOpacity={0.7}>
              <Icon name="ric.close-line" size={20} color="#8B949E" />
            </TouchableOpacity>
          </View>
          <ScrollView
            style={drawerStyles.content}
            contentContainerStyle={drawerStyles.contentInner}
            keyboardShouldPersistTaps="handled"
          >
            {surface?.rootId ? (
              <A2UIRenderer
                {...rendererProps}
                surfaceId="drawer"
                componentId={surface.rootId}
              />
            ) : null}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
};

const drawerStyles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.45)',
  },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  alignRight: {
    alignItems: 'flex-end',
    justifyContent: 'flex-start',
  },
  alignLeft: {
    alignItems: 'flex-start',
    justifyContent: 'flex-start',
  },
  alignTop: {
    alignItems: 'stretch',
    justifyContent: 'flex-start',
  },
  alignBottom: {
    alignItems: 'stretch',
    justifyContent: 'flex-end',
  },
  panel: {
    zIndex: 1,
    backgroundColor: '#161B22',
    borderColor: '#30363D',
    overflow: 'hidden',
  },
  right: {
    height: '100%',
    borderLeftWidth: 1,
    borderTopLeftRadius: 10,
    borderBottomLeftRadius: 10,
  },
  left: {
    height: '100%',
    borderRightWidth: 1,
    borderTopRightRadius: 10,
    borderBottomRightRadius: 10,
  },
  top: {
    width: '100%',
    borderBottomWidth: 1,
    borderBottomLeftRadius: 10,
    borderBottomRightRadius: 10,
  },
  bottom: {
    width: '100%',
    borderTopWidth: 1,
    borderTopLeftRadius: 10,
    borderTopRightRadius: 10,
  },
  header: {
    minHeight: 42,
    justifyContent: 'center',
    paddingHorizontal: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#21262D',
  },
  headerLeft: {
    alignItems: 'flex-start',
  },
  headerRight: {
    alignItems: 'flex-end',
  },
  closeButton: {
    width: 34,
    height: 34,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: {
    flex: 1,
  },
  contentInner: {
    flexGrow: 1,
    padding: 10,
  },
});

// ─── Modal Surface ───────────────────────────────────────────────────────────

const ModalSurface: React.FC<{
  surfaceId: string;
  surface: any;
  rendererProps: any;
  onClose: () => void;
}> = ({ surfaceId, surface, rendererProps, onClose }) => {
  const windowSize = Dimensions.get('window');
  const declaredWidth = positiveNumber(surface?.options?.width);
  const panelWidth = Math.min(declaredWidth || Math.round(windowSize.width * 0.9), Math.round(windowSize.width * 0.92));
  const maxBodyHeight = Math.round(windowSize.height * 0.68);
  const title = getLiteral(surface?.options?.title || surfaceId);
  const components = surface?.components || {};
  const requestedRootId = String(surface?.rootId || '');
  const firstRenderableComponentId = Object.keys(components).find((key) => Boolean(components[key]?.component)) || '';
  const resolvedRootId = requestedRootId && components[requestedRootId]
    ? requestedRootId
    : firstRenderableComponentId;

  return (
    <Modal transparent animationType="fade" visible={Boolean(surface?.rootId)} onRequestClose={onClose}>
      <View style={modalSurfaceStyles.overlay}>
        <Pressable style={modalSurfaceStyles.backdrop} onPress={onClose} />
        <View style={[modalSurfaceStyles.panel, { width: panelWidth }]}>
          <View style={modalSurfaceStyles.header}>
            <Text style={modalSurfaceStyles.title}>{title}</Text>
            <TouchableOpacity style={modalSurfaceStyles.closeButton} onPress={onClose} activeOpacity={0.7}>
              <Icon name="ric.close-line" size={22} color="#8B949E" />
            </TouchableOpacity>
          </View>
          <ScrollView
            style={[modalSurfaceStyles.body, { maxHeight: maxBodyHeight }]}
            contentContainerStyle={modalSurfaceStyles.bodyContent}
            keyboardShouldPersistTaps="handled"
          >
            {resolvedRootId ? (
              <A2UIRenderer
                {...rendererProps}
                surfaceId={surfaceId}
                componentId={resolvedRootId}
              />
            ) : (
              <View style={modalSurfaceStyles.loading}>
                <ActivityIndicator color="#6366F1" />
                <Text style={modalSurfaceStyles.loadingText}>Loading...</Text>
              </View>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
};

const modalSurfaceStyles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.62)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 18,
  },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  panel: {
    maxHeight: '86%',
    minHeight: 220,
    zIndex: 1,
    backgroundColor: '#1C2128',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 14,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 12,
  },
  header: {
    minHeight: 58,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
    backgroundColor: '#161B22',
  },
  title: {
    flex: 1,
    color: '#E6EDF3',
    fontSize: 17,
    fontWeight: '800',
  },
  closeButton: {
    width: 34,
    height: 34,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: {
    flexGrow: 0,
  },
  bodyContent: {
    padding: 14,
    flexGrow: 1,
  },
  loading: {
    flex: 1,
    minHeight: 140,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  loadingText: {
    color: '#8B949E',
    fontSize: 13,
    fontWeight: '600',
  },
});

// ─── Overflow Sheet ───────────────────────────────────────────────────────────

const OverflowSheet: React.FC<{
  items: NavEntry[];
  stateModel: any;
  onAction: (name: string, ctx: any) => void;
  onClose: () => void;
}> = ({ items, stateModel, onAction, onClose }) => (
  <Modal transparent animationType="slide" onRequestClose={onClose}>
    <Pressable style={sheetStyles.backdrop} onPress={onClose} />
    <View style={sheetStyles.sheet}>
      <View style={sheetStyles.handle} />
      {items.map((entry, index) => {
        const isActive = evaluateRule(entry?.active_condition, { stateModel, item: entry }, false);
        const label = getLiteral(entry?.label, '');
        return (
          <TouchableOpacity
            key={entry?.id || `overflow_${index}`}
            style={sheetStyles.row}
            onPress={() => {
              onClose();
              const action = entry?.action;
              if (action?.name) onAction(action.name, action.context || {});
            }}
            activeOpacity={0.7}
          >
            <View style={[sheetStyles.iconWrap, isActive && sheetStyles.iconWrapActive]}>
              <Icon name={entry?.icon} size={20} color={isActive ? '#6366F1' : '#C9D1D9'} />
            </View>
            {label ? (
              <Text style={[sheetStyles.label, isActive && sheetStyles.labelActive]}>
                {label}
              </Text>
            ) : null}
          </TouchableOpacity>
        );
      })}
    </View>
  </Modal>
);

const sheetStyles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  sheet: {
    backgroundColor: '#161B22',
    borderTopWidth: 1,
    borderTopColor: '#21262D',
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    paddingHorizontal: 16,
    paddingBottom: 32,
    paddingTop: 12,
  },
  handle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#30363D',
    alignSelf: 'center',
    marginBottom: 16,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#21262D',
  },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconWrapActive: {
    backgroundColor: 'rgba(99,102,241,0.15)',
  },
  label: {
    fontSize: 14,
    color: '#C9D1D9',
    fontWeight: '500',
  },
  labelActive: {
    color: '#6366F1',
    fontWeight: '600',
  },
});

// ─── Bottom Tab Bar ────────────────────────────────────────────────────────────

const MAX_BOTTOM_SLOTS = 4;
const BOTTOM_TAB_ITEM_WIDTH = 88;

const BottomTabBar: React.FC<{
  items: NavEntry[];
  stateModel: any;
  onAction: (name: string, ctx: any) => void;
}> = ({ items, stateModel, onAction }) => {
  const [overflowOpen, setOverflowOpen] = useState(false);
  const { width } = useWindowDimensions();

  if (!items.length) return null;

  const slotsByScreenWidth = Math.floor(width / BOTTOM_TAB_ITEM_WIDTH);
  const availableSlots = Math.max(1, Math.min(MAX_BOTTOM_SLOTS, slotsByScreenWidth));
  const hasOverflow = items.length > availableSlots;
  const visibleCount = hasOverflow ? Math.max(0, availableSlots - 1) : availableSlots;
  const visibleItems = items.slice(0, visibleCount);
  const overflowItems = hasOverflow ? items.slice(visibleCount) : [];

  return (
    <>
      <View style={tabStyles.container}>
        <View style={tabStyles.row}>
          {visibleItems.map((entry, index) => {
            const isActive = evaluateRule(entry?.active_condition, { stateModel, item: entry }, false);
            const label = getLiteral(entry?.label, '');
            return (
              <TouchableOpacity
                key={entry?.id || `tab_${index}`}
                style={tabStyles.tab}
                onPress={() => {
                  const action = entry?.action;
                  if (action?.name) onAction(action.name, action.context || {});
                }}
                activeOpacity={0.7}
              >
                {isActive && <View style={tabStyles.activeIndicator} />}
                <View style={[tabStyles.iconWrap, isActive && tabStyles.iconWrapActive]}>
                  <Icon name={entry?.icon} size={20} color={isActive ? '#FFFFFF' : '#6E7681'} />
                </View>
                {label ? (
                  <Text style={[tabStyles.label, isActive && tabStyles.labelActive]} numberOfLines={1}>
                    {label}
                  </Text>
                ) : null}
              </TouchableOpacity>
            );
          })}

          {hasOverflow && (
            <TouchableOpacity
              style={tabStyles.tab}
              onPress={() => setOverflowOpen(true)}
              activeOpacity={0.7}
            >
              <View style={tabStyles.iconWrap}>
                <Icon name="ric.more-2-fill" size={20} color="#6E7681" />
              </View>
              <Text style={tabStyles.label}>More</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      {overflowOpen && (
        <OverflowSheet
          items={overflowItems}
          stateModel={stateModel}
          onAction={onAction}
          onClose={() => setOverflowOpen(false)}
        />
      )}
    </>
  );
};

const tabStyles = StyleSheet.create({
  container: {
    borderTopWidth: 1,
    borderTopColor: '#21262D',
    backgroundColor: '#161B22',
    width: '100%',
    maxWidth: '100%',
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'stretch',
    width: '100%',
    maxWidth: '100%',
  },
  tab: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 4,
    gap: 4,
    position: 'relative',
  },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  activeIndicator: {
    position: 'absolute',
    top: 0,
    left: '20%',
    right: '20%',
    height: 2,
    borderRadius: 1,
    backgroundColor: '#6366F1',
  },
  iconWrapActive: {
    backgroundColor: 'rgba(99,102,241,0.15)',
  },
  label: {
    fontSize: 10,
    color: '#6E7681',
    fontWeight: '500',
    textAlign: 'center',
    maxWidth: '100%',
  },
  labelActive: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
});

// ─── Language Picker ──────────────────────────────────────────────────────────

const LANGUAGES = [
  { label: 'EN', value: 'en' },
  { label: 'IT', value: 'it' },
  { label: 'ES', value: 'es' },
  { label: 'FR', value: 'fr' },
  { label: 'DE', value: 'de' },
];

const LanguagePicker: React.FC<{
  current: string;
  languages?: Array<{ label: any; value: any }>;
  onSelect: (lang: string) => void;
}> = ({ current, languages, onSelect }) => {
  const [open, setOpen] = useState(false);
  const options = Array.isArray(languages) && languages.length > 0
    ? languages
        .map((entry) => ({
          label: getLiteral(entry?.label, String(entry?.value || '').toUpperCase()),
          value: String(entry?.value || '').trim().toLowerCase(),
        }))
        .filter((entry) => entry.value)
    : LANGUAGES;
  const label = options.find((l) => l.value === current)?.label ?? current.toUpperCase().slice(0, 2);

  return (
    <>
      <TouchableOpacity style={headerStyles.langBtn} onPress={() => setOpen(true)} activeOpacity={0.7}>
        <Text style={headerStyles.langLabel}>{label}</Text>
      </TouchableOpacity>

      {open && (
        <Modal transparent animationType="fade" onRequestClose={() => setOpen(false)}>
          <Pressable style={langStyles.backdrop} onPress={() => setOpen(false)} />
          <View style={langStyles.sheet}>
            {options.map((lang) => (
              <TouchableOpacity
                key={lang.value}
                style={[langStyles.option, current === lang.value && langStyles.optionActive]}
                onPress={() => { setOpen(false); onSelect(lang.value); }}
                activeOpacity={0.7}
              >
                <Text style={[langStyles.optionText, current === lang.value && langStyles.optionTextActive]}>
                  {lang.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </Modal>
      )}
    </>
  );
};

const langStyles = StyleSheet.create({
  backdrop: {
    flex: 1,
  },
  sheet: {
    position: 'absolute',
    top: 56,
    right: 12,
    backgroundColor: '#1C2128',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    overflow: 'hidden',
    minWidth: 80,
  },
  option: {
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  optionActive: {
    backgroundColor: 'rgba(99,102,241,0.15)',
  },
  optionText: {
    fontSize: 13,
    color: '#8B949E',
    fontWeight: '500',
  },
  optionTextActive: {
    color: '#6366F1',
    fontWeight: '700',
  },
});

// ─── App Header ───────────────────────────────────────────────────────────────

const AppHeader: React.FC<{
  items: NavEntry[];
  showNotifications?: boolean;
  stateModel: any;
  onAction: (name: string, ctx: any) => void;
}> = ({ items, showNotifications, stateModel, onAction }) => {
  const currentLang = String(
    readStatePath(stateModel, '/core/user/language')
      || readStatePath(stateModel, '/system/user/language')
      || 'en',
  ).trim().toLowerCase();
  const languages = readStatePath(stateModel, '/core/supported_languages');
  const pendingCount = Math.max(0, Number(readStatePath(stateModel, '/core/notifications/pending_count') ?? 0) || 0);
  const notificationsPath = String(readStatePath(stateModel, '/core/notifications/view_path') || '').trim();
  const hasNotifications = pendingCount > 0;
  const logoUri = RNImage.resolveAssetSource(HEADER_LOGO)?.uri;

  return (
    <View style={headerStyles.container}>
      <View style={headerStyles.logoSlot}>
        {logoUri ? (
          <SvgUri uri={logoUri} width="100%" height="100%" />
        ) : null}
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={headerStyles.navScroll}
        contentContainerStyle={headerStyles.right}
      >
        {showNotifications ? (
          <TouchableOpacity
            style={[headerStyles.iconBtn, headerStyles.relativeBtn]}
            disabled={!notificationsPath}
            onPress={() => onAction('open_drawer', { path: notificationsPath, position: 'right', dim: 680 })}
            activeOpacity={0.7}
          >
            <Icon name={hasNotifications ? 'ri-notification-3-fill' : 'ri-notification-3-line'} size={20} color="#8B949E" />
            {hasNotifications ? (
              <View style={headerStyles.badge}>
                <Text style={headerStyles.badgeText}>{pendingCount > 99 ? '99+' : String(pendingCount)}</Text>
              </View>
            ) : null}
          </TouchableOpacity>
        ) : null}
        <LanguagePicker
          current={currentLang}
          languages={Array.isArray(languages) ? languages : undefined}
          onSelect={(lang) => onAction('set_user_language', { value: lang })}
        />
        {items.map((entry, index) => {
          const isActive = evaluateRule(entry?.active_condition, { stateModel, item: entry }, false);
          const label = getLiteral(entry?.label, '');
          return (
            <TouchableOpacity
              key={entry?.id || `header_${index}`}
              style={headerStyles.btn}
              onPress={() => {
                const action = entry?.action;
                if (action?.name) onAction(action.name, action.context || {});
              }}
              activeOpacity={0.7}
            >
              <Icon name={entry?.icon} size={20} color={isActive ? '#6366F1' : '#8B949E'} />
              {label ? (
                <Text style={[headerStyles.btnLabel, isActive && headerStyles.btnLabelActive]} numberOfLines={1}>
                  {label}
                </Text>
              ) : null}
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
};

const headerStyles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#161B22',
    borderBottomWidth: 1,
    borderBottomColor: '#21262D',
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  logoSlot: {
    width: 36,
    height: 36,
    flexShrink: 0,
    justifyContent: 'center',
  },
  navScroll: {
    flex: 1,
    minWidth: 0,
  },
  right: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 4,
    flexGrow: 1,
    paddingLeft: 8,
  },
  langBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#1C2128',
    minWidth: 40,
    alignItems: 'center',
  },
  langLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: '#8B949E',
  },
  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
  },
  iconBtn: {
    width: 36,
    height: 36,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  relativeBtn: {
    position: 'relative',
  },
  badge: {
    position: 'absolute',
    top: 2,
    right: 1,
    minWidth: 16,
    height: 16,
    paddingHorizontal: 3,
    borderRadius: 8,
    backgroundColor: '#F85149',
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: 9,
    fontWeight: '800',
  },
  btnLabel: {
    fontSize: 13,
    color: '#8B949E',
    fontWeight: '500',
  },
  btnLabelActive: {
    color: '#6366F1',
    fontWeight: '600',
  },
});

// ─── App ─────────────────────────────────────────────────────────────────────

export default function App() {
  const a2ui = useA2UI();
  const { surfaces, connectionState, stateModel, sendAction, closeSurface } = a2ui;

  const mainSurface = surfaces['main'];

  // Read the ClientTags already declared by the backend template.
  // top_nav has position="bottom" and remains the bottom tab bar.
  // bottom_nav is presented in the React Native app header.
  const headerNavTag = useMemo(
    () => findClientTagById(mainSurface, 'bottom_nav'),
    [mainSurface],
  );
  const tabNavTag = useMemo(
    () => findClientTagByPosition(mainSurface, 'bottom'),
    [mainSurface],
  );
  const notificationsTag = useMemo(
    () => findClientTagById(mainSurface, 'notifications_bell'),
    [mainSurface],
  );

  // Content surface
  const hostedSurfaceIds = useMemo(() => {
    const hosted = new Set<string>();
    Object.values(surfaces).forEach((surface: any) => {
      Object.values(surface?.components || {}).forEach((cd: any) => {
        const type = Object.keys(cd?.component || {})[0];
        if (type === 'SurfaceHost') {
          const sid = cd.component.SurfaceHost?.surface_id || cd.component.SurfaceHost?.surfaceId;
          if (sid) hosted.add(sid);
        }
      });
    });
    return hosted;
  }, [surfaces]);

  // Always render `main` directly — sub-surfaces (main_content, components_preview, etc.)
  // are rendered inline by the SurfaceHost component in the renderer tree.
  // This matches the webclient's approach exactly.
  const contentSurfaceId = useMemo(() => {
    if (surfaces['main'] && !hostedSurfaceIds.has('main')) return 'main';
    for (const id of Object.keys(surfaces)) {
      if (id === 'modal' || id.includes('__tab_route__')) continue;
      if (!hostedSurfaceIds.has(id)) {
        const s = surfaces[id] as any;
        if (s?.rootId || s?.components?.root) return id;
      }
    }
    return 'main';
  }, [surfaces, hostedSurfaceIds]);

  // Items always come from stateModel (already resolved by the backend
  // per authentication state). Tag from ClientTag determines which list to use.
  const headerNavItems: NavEntry[] = useMemo(
    () => resolveNavItems(headerNavTag?.tag, stateModel),
    [headerNavTag, stateModel],
  );

  const tabNavItems: NavEntry[] = useMemo(
    () => resolveNavItems(tabNavTag?.tag, stateModel),
    [tabNavTag, stateModel],
  );

  const contentSurface = surfaces[contentSurfaceId];
  const contentRootId = contentSurface?.rootId || (contentSurface?.components?.root ? 'root' : '');
  const hasAppShell = headerNavItems.length > 0 || tabNavItems.length > 0 || Boolean(notificationsTag);
  const drawerSurface = surfaces.drawer as any;
  const modalSurface = surfaces.modal as any;

  // Only the dedicated `modal` surface is rendered as an overlay.
  // Sub-surfaces (main_content, components_preview, etc.) are always rendered
  // inline via SurfaceHost — never as floating overlays.
  const overlaySurfaces = useMemo(() => {
    if (modalSurface?.rootId) return [['modal', modalSurface] as [string, any]];
    return [];
  }, [modalSurface]);

  if (connectionState === 'connecting') {
    return (
      <SafeAreaProvider>
        <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
          <StatusBar barStyle="light-content" backgroundColor="#0D1117" />
          <View style={styles.centered}>
            <ActivityIndicator size="large" color="#6366F1" />
            <Text style={styles.muted}>Connecting to Democr.ai...</Text>
          </View>
        </SafeAreaView>
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.safe} edges={['top']}>
        <StatusBar barStyle="light-content" backgroundColor="#0D1117" />

        {/* Header — React Native presentation of the template's bottom_nav and notifications_bell ClientTags */}
        {(headerNavItems.length > 0 || notificationsTag) && (
          <AppHeader
            items={headerNavItems}
            showNotifications={Boolean(notificationsTag)}
            stateModel={stateModel}
            onAction={sendAction}
          />
        )}

        {/* Main content */}
        <View style={[styles.content, !hasAppShell && styles.loginContent]}>
          <View style={!hasAppShell ? styles.loginFrame : styles.content}>
            <A2UIRenderer
              {...a2ui}
              surfaceId={contentSurfaceId}
              componentId={contentRootId}
              centerRootContent={!hasAppShell}
            />
          </View>
        </View>

        {/* Bottom tab bar — rendered from the backend template's top_nav ClientTag with position="bottom" */}
        {tabNavTag && tabNavItems.length > 0 && (
          <SafeAreaView edges={['bottom']} style={{ backgroundColor: '#161B22' }}>
            <BottomTabBar
              items={tabNavItems}
              stateModel={stateModel}
              onAction={sendAction}
            />
          </SafeAreaView>
        )}

        {/* Persistent drawer — open when the backend loads the drawer surface */}
        {drawerSurface?.rootId ? (
          <DrawerSurface
            key={`${drawerSide(drawerSurface?.options?.position)}_${drawerSurface.rootId}`}
            surface={drawerSurface}
            rendererProps={a2ui}
            onClose={() => closeSurface('drawer')}
          />
        ) : null}

        {/* Overlay surfaces (modals) */}
        {overlaySurfaces.map(([id, surface]: [string, any]) => (
          <ModalSurface
            key={`${id}_${surface.rootId || ''}_${surface.options?.width || ''}_${Object.keys(surface.components || {}).length}`}
            surfaceId={id}
            surface={surface}
            rendererProps={a2ui}
            onClose={() => closeSurface(id)}
          />
        ))}

        <ToastHost notification={stateModel?.last_event_notification} />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#0D1117',
  },
  content: {
    flex: 1,
  },
  loginContent: {
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 24,
  },
  loginFrame: {
    flex: 1,
    width: '100%',
    maxWidth: 420,
    alignSelf: 'center',
    alignItems: 'center',
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#0D1117',
  },
  muted: {
    color: '#8B949E',
    fontSize: 14,
  },
});
