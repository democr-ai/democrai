import React from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Icon } from '../../../components/a2ui/Icon';
import { getLiteral } from '../../shared';
import { resolveActiveValue } from '../../rules';
import { IconGallery } from './icon_gallery';

const APP_MAIN_LIST_TAG = 'appmainlist';
const APP_BOTTOM_MAIN_LIST_TAG = 'appbottommainlist';
const APP_NOTIFICATIONS_TAG = 'notifications';
const APP_LANGUAGE_TAG = 'language';
const APP_THEME_TAG = 'theme';
const ICON_CONTROLS_TAG = 'icon_controls';
const ICON_GALLERY_TAG = 'icon_gallery';
const THEME_STORAGE_KEY = 'democrai_mobile_theme';

type ClientTheme = 'dark' | 'light';

const readStateValue = (stateModel: any, scope: 'global' | 'page' | 'auto', path: string): any => {
  const read = (source: any) => String(path || '')
    .replace(/^\//, '')
    .split(/[./]/)
    .filter(Boolean)
    .reduce((cursor: any, key) => (cursor == null ? undefined : cursor[key]), source);

  if (scope === 'page') return read(stateModel?.page);
  if (scope === 'global') {
    const scoped = read(stateModel?.global);
    return scoped !== undefined ? scoped : read(stateModel);
  }
  const page = read(stateModel?.page);
  if (page !== undefined) return page;
  const global = read(stateModel?.global);
  return global !== undefined ? global : read(stateModel);
};

const normalizeItems = (items: any): any[] => (
  Array.isArray(items) ? items.filter((entry) => entry && typeof entry === 'object') : []
);

const invokeEntryAction = (entry: any, onAction?: (name: string, ctx: any) => void) => {
  const action = entry?.action;
  const actionName = typeof action?.name === 'string' ? action.name : '';
  const actionContext = action?.context && typeof action.context === 'object' ? action.context : {};
  if (actionName) onAction?.(actionName, actionContext);
};

const MenuModal: React.FC<{
  visible: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}> = ({ visible, title, onClose, children }) => (
  <Modal transparent animationType="fade" visible={visible} onRequestClose={onClose}>
    <TouchableOpacity style={styles.modalBackdrop} activeOpacity={1} onPress={onClose}>
      <TouchableOpacity style={styles.modalSheet} activeOpacity={1}>
        <View style={styles.modalHeader}>
          <Text style={styles.modalTitle}>{title}</Text>
          <TouchableOpacity style={styles.modalClose} onPress={onClose} hitSlop={{ top: 8, right: 8, bottom: 8, left: 8 }}>
            <Icon name="ri-close-line" size={20} color="#E6EDF3" />
          </TouchableOpacity>
        </View>
        <ScrollView style={styles.modalList} contentContainerStyle={styles.modalListContent}>
          {children}
        </ScrollView>
      </TouchableOpacity>
    </TouchableOpacity>
  </Modal>
);

export const ClientTag: React.FC<any> = ({ tag, stateModel, onAction, style, setInput }) => {
  const [languageOpen, setLanguageOpen] = React.useState(false);
  const [overflowOpen, setOverflowOpen] = React.useState(false);
  const [clientTheme, setClientThemeState] = React.useState<ClientTheme>('dark');

  React.useEffect(() => {
    AsyncStorage.getItem(THEME_STORAGE_KEY).then((raw) => {
      setClientThemeState(raw === 'light' ? 'light' : 'dark');
    }).catch(() => undefined);
  }, []);

  const items = React.useMemo(() => {
    if (tag === APP_MAIN_LIST_TAG) return readStateValue(stateModel, 'global', '/system/modules/top');
    if (tag === APP_BOTTOM_MAIN_LIST_TAG) return readStateValue(stateModel, 'global', '/system/modules/bottom');
    return [];
  }, [stateModel, tag]);

  const normalizedItems = React.useMemo(() => normalizeItems(items), [items]);
  const activeByIndex = React.useMemo(() => normalizedItems.map((entry) => resolveActiveValue(entry?.active_condition, {
    stateModel,
    item: entry,
  })), [normalizedItems, stateModel]);

  const languageOptions = React.useMemo(() => {
    const raw = readStateValue(stateModel, 'global', '/core/supported_languages');
    return normalizeItems(raw).filter((entry) => entry.value && entry.label);
  }, [stateModel]);

  const currentLanguage = String(readStateValue(stateModel, 'global', '/core/user/language') || 'en').trim().toLowerCase() || 'en';
  const showLanguageMenu = tag === APP_LANGUAGE_TAG && languageOptions.length > 0;
  const showThemeToggle = tag === APP_THEME_TAG;

  const visibleItems = tag === APP_MAIN_LIST_TAG ? normalizedItems.slice(0, 7) : normalizedItems;
  const overflowItems = tag === APP_MAIN_LIST_TAG ? normalizedItems.slice(7) : [];

  const toggleTheme = React.useCallback(() => {
    const next: ClientTheme = clientTheme === 'dark' ? 'light' : 'dark';
    setClientThemeState(next);
    AsyncStorage.setItem(THEME_STORAGE_KEY, next).catch(() => undefined);
    setInput?.('__client_theme', next);
  }, [clientTheme, setInput]);

  if (tag === ICON_GALLERY_TAG) {
    return <IconGallery />;
  }

  if (tag === ICON_CONTROLS_TAG || tag === APP_MAIN_LIST_TAG || tag === APP_BOTTOM_MAIN_LIST_TAG || tag === APP_NOTIFICATIONS_TAG) {
    return <View style={style} />;
  }

  if (tag === APP_NOTIFICATIONS_TAG) {
    const pendingCount = Math.max(0, Number(readStateValue(stateModel, 'global', '/core/notifications/pending_count') ?? 0) || 0);
    const viewPath = String(readStateValue(stateModel, 'global', '/core/notifications/view_path') || '').trim();
    const hasNotifications = pendingCount > 0;
    const badgeText = pendingCount > 99 ? '99+' : String(pendingCount);
    return (
      <TouchableOpacity
        style={[styles.navButton, styles.relativeButton, style]}
        disabled={!viewPath}
        onPress={() => onAction?.('open_drawer', { path: viewPath, position: 'right', dim: 680 })}
        activeOpacity={0.75}
        accessibilityLabel="Notifications"
      >
        <Icon name={hasNotifications ? 'ri-notification-3-fill' : 'ri-notification-3-line'} size={22} color="#A1A1AA" />
        {hasNotifications ? (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{badgeText}</Text>
          </View>
        ) : null}
      </TouchableOpacity>
    );
  }

  if (!normalizedItems.length && !showLanguageMenu && !showThemeToggle) {
    return <View style={style} />;
  }

  return (
    <View style={[styles.container, style]}>
      {visibleItems.map((entry: any, index: number) => {
        const active = Boolean(activeByIndex[index]);
        const label = getLiteral(entry?.label, '');
        return (
          <TouchableOpacity
            key={entry?.id || `tag_${tag}_${index}`}
            style={[styles.navButton, active && styles.navButtonActive]}
            onPress={() => invokeEntryAction(entry, onAction)}
            activeOpacity={0.75}
            accessibilityLabel={label || 'Navigation item'}
          >
            <Icon name={entry?.icon} size={22} color={active ? '#FFFFFF' : '#A1A1AA'} />
          </TouchableOpacity>
        );
      })}

      {overflowItems.length > 0 ? (
        <>
          <TouchableOpacity style={styles.navButton} onPress={() => setOverflowOpen(true)} activeOpacity={0.75} accessibilityLabel="More modules">
            <Icon name="ri-more-fill" size={22} color="#A1A1AA" />
          </TouchableOpacity>
          <MenuModal visible={overflowOpen} title="Modules" onClose={() => setOverflowOpen(false)}>
            {overflowItems.map((entry: any, index: number) => {
              const active = Boolean(activeByIndex[index + visibleItems.length]);
              const label = getLiteral(entry?.label, String(entry?.id || `Item ${index + 1}`));
              return (
                <TouchableOpacity
                  key={entry?.id || `overflow_${index}`}
                  style={[styles.menuRow, active && styles.menuRowActive]}
                  onPress={() => {
                    setOverflowOpen(false);
                    invokeEntryAction(entry, onAction);
                  }}
                  activeOpacity={0.75}
                >
                  <Icon name={entry?.icon} size={20} color={active ? '#FFFFFF' : '#A1A1AA'} />
                  <Text style={[styles.menuText, active && styles.menuTextActive]}>{label}</Text>
                </TouchableOpacity>
              );
            })}
          </MenuModal>
        </>
      ) : null}

      {showThemeToggle ? (
        <TouchableOpacity style={styles.navButton} onPress={toggleTheme} activeOpacity={0.75} accessibilityLabel="Theme selector">
          <Icon name={clientTheme === 'dark' ? 'ri-moon-clear-fill' : 'ri-sun-line'} size={22} color="#A1A1AA" />
        </TouchableOpacity>
      ) : null}

      {showLanguageMenu ? (
        <>
          <TouchableOpacity style={styles.languageButton} onPress={() => setLanguageOpen(true)} activeOpacity={0.75} accessibilityLabel="Language selector">
            <Text style={styles.languageText}>{currentLanguage.toUpperCase()}</Text>
          </TouchableOpacity>
          <Modal transparent animationType="fade" visible={languageOpen} onRequestClose={() => setLanguageOpen(false)}>
            <TouchableOpacity style={styles.languageBackdrop} activeOpacity={1} onPress={() => setLanguageOpen(false)}>
              <View style={styles.languageMenu}>
                {languageOptions.map((entry: any) => {
                  const value = String(entry.value || '').trim().toLowerCase();
                  const selected = value === currentLanguage;
                  return (
                    <TouchableOpacity
                      key={value}
                      style={[styles.languageOption, selected && styles.languageOptionActive]}
                      onPress={() => {
                        setLanguageOpen(false);
                        onAction?.('set_user_language', { value });
                      }}
                      activeOpacity={0.75}
                    >
                      <Text style={[styles.languageOptionText, selected && styles.languageOptionTextActive]}>
                        {getLiteral(entry.label)}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </TouchableOpacity>
          </Modal>
        </>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'column',
    alignItems: 'center',
    gap: 8,
  },
  navButton: {
    width: 42,
    height: 42,
    borderRadius: 10,
    backgroundColor: 'transparent',
    alignItems: 'center',
    justifyContent: 'center',
  },
  navButtonActive: {
    backgroundColor: 'rgba(99,102,241,0.28)',
  },
  relativeButton: {
    position: 'relative',
  },
  badge: {
    position: 'absolute',
    top: 2,
    right: 1,
    minWidth: 17,
    height: 17,
    paddingHorizontal: 3,
    borderRadius: 9,
    backgroundColor: '#F85149',
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: 9,
    lineHeight: 12,
    fontWeight: '800',
  },
  languageButton: {
    width: 42,
    height: 42,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#30363D',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.03)',
  },
  languageText: {
    color: '#E6EDF3',
    fontSize: 12,
    fontWeight: '800',
  },
  languageBackdrop: {
    flex: 1,
  },
  languageMenu: {
    position: 'absolute',
    top: 56,
    alignSelf: 'center',
    minWidth: 80,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#1C2128',
    overflow: 'hidden',
  },
  languageOption: {
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  languageOptionActive: {
    backgroundColor: 'rgba(99,102,241,0.15)',
  },
  languageOptionText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#8B949E',
  },
  languageOptionTextActive: {
    color: '#6366F1',
    fontWeight: '700',
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.55)',
    justifyContent: 'flex-end',
  },
  modalSheet: {
    maxHeight: '72%',
    borderTopLeftRadius: 14,
    borderTopRightRadius: 14,
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#161B22',
    paddingTop: 12,
    paddingHorizontal: 12,
    paddingBottom: 24,
  },
  modalHeader: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
  },
  modalTitle: {
    color: '#E6EDF3',
    fontSize: 16,
    fontWeight: '700',
  },
  modalClose: {
    width: 34,
    height: 34,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#0D1117',
  },
  modalList: {
    marginTop: 8,
  },
  modalListContent: {
    gap: 6,
    paddingBottom: 8,
  },
  menuRow: {
    minHeight: 46,
    borderRadius: 9,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    backgroundColor: '#0D1117',
  },
  menuRowActive: {
    backgroundColor: 'rgba(99,102,241,0.28)',
  },
  menuText: {
    flex: 1,
    color: '#C9D1D9',
    fontSize: 14,
    fontWeight: '600',
  },
  menuTextActive: {
    color: '#FFFFFF',
  },
});
