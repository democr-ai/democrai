import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { resolveActiveValue } from '@/renderers/rules';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { IconGallery } from './icon_gallery';
import { resolveMediaUrl } from '@/utils/media';
import { readClientStateValue, useClientStateSnapshot } from '@/state/clientState';
import { readStoredClientTheme, toggleClientTheme, type ClientTheme } from '@/utils/theme';

const APP_MAIN_LIST_TAG = 'appmainlist';
const APP_BOTTOM_MAIN_LIST_TAG = 'appbottommainlist';
const APP_NOTIFICATIONS_TAG = 'notifications';
const APP_LANGUAGE_TAG = 'language';

const iconRawValue = (icon: any): string => {
  const raw = String(icon?.iconName || icon || '').trim();
  return raw || 'ric.apps-2-line';
};

const isInlineSvg = (raw: string): boolean => {
  const value = String(raw || '').trim();
  return value.startsWith('<svg') || value.includes('http://www.w3.org/2000/svg');
};

const isImageIcon = (raw: string): boolean => {
  const value = String(raw || '').trim().toLowerCase();
  if (!value) return false;
  if (value.startsWith('data:image/')) return true;
  if (value.startsWith('/media/')) return true;
  if (value.startsWith('http://') || value.startsWith('https://')) return true;
  if (value.startsWith('blob:')) return true;
  if (/\.(svg|png|jpe?g|gif|webp|ico)(\?|#|$)/i.test(value)) return true;
  if (value.includes('/assets/')) return true;
  return false;
};

const toRemixClass = (icon: any): string => {
  const raw = iconRawValue(icon);
  if (!raw) return 'ri-apps-2-line';
  if (raw.startsWith('ric.')) return `ri-${raw.slice(4)}`;
  if (raw.startsWith('ri.')) return `ri-${raw.slice(3)}`;
  if (raw.startsWith('ri-')) return raw;
  return 'ri-apps-2-line';
};

const sanitizeInlineSvg = (svg: string): string =>
  svg
    .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, '')
    .replace(/\son\w+=(['"]).*?\1/gi, '')
    .replace(/\sjavascript:/gi, '');

const SidebarIcon: React.FC<{ icon: any; className?: string }> = ({
  icon,
  className,
}) => {
  const raw = iconRawValue(icon);
  if (isInlineSvg(raw)) {
    const safeSvg = sanitizeInlineSvg(raw);
    return (
      <span
        aria-hidden="true"
        className={cn('main-sidebar-nav-icon main-sidebar-nav-icon-svg', className)}
        dangerouslySetInnerHTML={{ __html: safeSvg }}
      />
    );
  }

  if (isImageIcon(raw)) {
    const resolved = resolveMediaUrl(raw);
    return (
      <img
        src={resolved}
        alt=""
        aria-hidden="true"
        className={cn('main-sidebar-nav-icon h-5 w-5 object-contain', className)}
      />
    );
  }

  return <i className={cn(toRemixClass(raw), 'main-sidebar-nav-icon', className)} />;
};

export const ClientTag: React.FC<any> = ({ tag, stateModel, onAction, style }) => {
  const contextState = useClientStateSnapshot();
  const resolvedState = stateModel || contextState;
  const items = React.useMemo(() => {
    if (tag === APP_MAIN_LIST_TAG) return readClientStateValue(resolvedState, 'global', '/system/modules/top');
    if (tag === APP_BOTTOM_MAIN_LIST_TAG) return readClientStateValue(resolvedState, 'global', '/system/modules/bottom');
    return [];
  }, [resolvedState, tag]);
  const normalizedItems = React.useMemo(
    () => (Array.isArray(items) ? items.filter((entry: any) => entry && typeof entry === 'object') : []),
    [items],
  );
  const languageOptions = React.useMemo(() => {
    const raw = readClientStateValue(resolvedState, 'global', '/core/supported_languages');
    return Array.isArray(raw)
      ? raw.filter((entry: any) => entry && typeof entry === 'object' && entry.value && entry.label)
      : [];
  }, [resolvedState]);
  const currentLanguage = React.useMemo(() => {
    const raw = String(readClientStateValue(resolvedState, 'global', '/core/user/language') || 'en').trim().toLowerCase();
    return raw || 'en';
  }, [resolvedState]);
  const showLanguageMenu = (tag === APP_BOTTOM_MAIN_LIST_TAG || tag === APP_LANGUAGE_TAG) && languageOptions.length > 0;
  const showThemeToggle = tag === APP_BOTTOM_MAIN_LIST_TAG && languageOptions.length > 0;
  const [clientTheme, setClientThemeState] = React.useState<ClientTheme>(() => readStoredClientTheme());
  const mainListRef = React.useRef<HTMLDivElement | null>(null);
  const [visibleCount, setVisibleCount] = React.useState<number>(normalizedItems.length);

  React.useEffect(() => {
    const syncTheme = () => setClientThemeState(readStoredClientTheme());
    window.addEventListener('storage', syncTheme);
    return () => window.removeEventListener('storage', syncTheme);
  }, []);

  React.useLayoutEffect(() => {
    if (tag !== APP_MAIN_LIST_TAG) return;
    const root = mainListRef.current;
    if (!root) return;

    const recompute = () => {
      const available = root.clientHeight;
      if (!available || available < 8) {
        setVisibleCount(normalizedItems.length);
        return;
      }

      const firstBtn = root.querySelector<HTMLButtonElement>('.main-sidebar-nav-btn');
      const btnHeight = Math.max(1, Math.round(firstBtn?.getBoundingClientRect().height || 45));
      const style = window.getComputedStyle(root);
      const gapRaw = style.rowGap || style.gap || '6';
      const gap = Number.parseFloat(gapRaw) || 6;
      const slot = btnHeight + gap;
      const maxSlots = Math.max(0, Math.floor((available + gap) / slot));

      if (normalizedItems.length <= maxSlots) {
        setVisibleCount(normalizedItems.length);
        return;
      }
      setVisibleCount(Math.max(0, maxSlots - 1));
    };

    recompute();
    const ro = new ResizeObserver(recompute);
    ro.observe(root);
    window.addEventListener('resize', recompute);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', recompute);
    };
  }, [tag, normalizedItems.length]);

  const activeByIndex = React.useMemo(
    () =>
      normalizedItems.map((entry: any) =>
        resolveActiveValue(entry?.active_condition, {
          stateModel: resolvedState,
          item: entry,
        }),
      ),
    [normalizedItems, resolvedState],
  );

  const { visibleItems, overflowItems } = React.useMemo(() => {
    if (tag !== APP_MAIN_LIST_TAG) {
      return { visibleItems: normalizedItems, overflowItems: [] as any[] };
    }

    const slots = Math.max(0, Math.min(visibleCount, normalizedItems.length));
    if (slots >= normalizedItems.length) {
      return { visibleItems: normalizedItems, overflowItems: [] as any[] };
    }

    const activeIndex = activeByIndex.findIndex(Boolean);
    let visibleIndices = Array.from({ length: slots }, (_, idx) => idx);
    if (activeIndex >= 0 && slots > 0 && !visibleIndices.includes(activeIndex)) {
      visibleIndices[slots - 1] = activeIndex;
      visibleIndices = Array.from(new Set(visibleIndices)).sort((a, b) => a - b);
      while (visibleIndices.length < slots) {
        const candidate = normalizedItems.findIndex(
          (_entry: any, idx: number) => !visibleIndices.includes(idx),
        );
        if (candidate < 0) break;
        visibleIndices.push(candidate);
      }
      visibleIndices.sort((a, b) => a - b);
    }

    const visibleSet = new Set(visibleIndices);
    const visible = normalizedItems.filter((_entry: any, idx: number) => visibleSet.has(idx));
    const overflow = normalizedItems.filter((_entry: any, idx: number) => !visibleSet.has(idx));
    return { visibleItems: visible, overflowItems: overflow };
  }, [tag, visibleCount, normalizedItems, activeByIndex]);

  const invokeEntry = React.useCallback(
    (entry: any) => {
      const action = entry?.action;
      const actionName = typeof action?.name === 'string' ? action.name : '';
      const actionContext = action?.context && typeof action.context === 'object' ? action.context : {};
      if (actionName) onAction?.(actionName, actionContext);
    },
    [onAction],
  );

  if (tag === 'icon_gallery') {
    return <IconGallery />;
  }

  if (tag === APP_NOTIFICATIONS_TAG) {
    const pendingCount = Number(readClientStateValue(resolvedState, 'global', '/core/notifications/pending_count') ?? 0);
    const viewPath = String(readClientStateValue(resolvedState, 'global', '/core/notifications/view_path') || '').trim();
    const hasNotifications = pendingCount > 0;
    const badgeText = pendingCount > 99 ? '99+' : String(pendingCount);
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={!viewPath}
              onClick={() => viewPath &&
                onAction?.('open_drawer', {
                  path: viewPath,
                  position: 'right',
                  dim: 680,
                })
              }
              className="main-sidebar-nav-btn main-sidebar-nav-btn-idle relative"
              aria-label="Notifications"
            >
              <i
                className={cn(
                  hasNotifications ? 'ri-notification-3-fill' : 'ri-notification-3-line',
                  'main-sidebar-nav-icon',
                  'main-sidebar-nav-icon-idle',
                )}
              />
              {hasNotifications && (
                <span className="notification-badge pointer-events-none absolute right-0.5 top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full px-0.5 text-[10px] font-bold leading-none">
                  {badgeText}
                </span>
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">
            {hasNotifications ? `${pendingCount} notification${pendingCount === 1 ? '' : 's'} pending` : 'Notifications'}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  if (!normalizedItems.length && !showLanguageMenu) {
    return <div style={parseStyle(style)} />;
  }

  return (
    <TooltipProvider>
      <div
        ref={tag === APP_MAIN_LIST_TAG ? mainListRef : undefined}
        className={cn(
          'flex w-full flex-col items-center gap-1.5',
          tag === APP_MAIN_LIST_TAG && 'h-full min-h-0 justify-start',
        )}
        style={parseStyle(style)}
      >
        {visibleItems.map((entry: any, index: number) => {
          const active = resolveActiveValue(entry?.active_condition, { stateModel, item: entry });
          const label = getLiteral(entry?.label);

          return (
            <Tooltip key={entry?.id || `client_tag_item_${index}`}>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => invokeEntry(entry)}
                  className={cn(
                    'main-sidebar-nav-btn',
                    active ? 'main-sidebar-nav-btn-active' : 'main-sidebar-nav-btn-idle',
                  )}
                  aria-label={label || 'nav-item'}
                >
                  <SidebarIcon
                    icon={entry?.icon}
                    className={active ? 'main-sidebar-nav-icon-active' : 'main-sidebar-nav-icon-idle'}
                  />
                </Button>
              </TooltipTrigger>
              {label ? <TooltipContent side="right">{label}</TooltipContent> : null}
            </Tooltip>
          );
        })}
        {tag === APP_MAIN_LIST_TAG && overflowItems.length > 0 ? (
          <DropdownMenu>
            <Tooltip>
              <TooltipTrigger asChild>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="main-sidebar-nav-btn main-sidebar-nav-btn-idle"
                    aria-label="More modules"
                  >
                    <i className="ri-more-fill main-sidebar-nav-icon main-sidebar-nav-icon-idle" />
                  </Button>
                </DropdownMenuTrigger>
              </TooltipTrigger>
              <TooltipContent side="right">More</TooltipContent>
            </Tooltip>
            <DropdownMenuContent side="right" align="start" className="main-sidebar-overflow-menu">
              {overflowItems.map((entry: any, index: number) => {
                const label = getLiteral(entry?.label, String(entry?.id || `Item ${index + 1}`));
                const active = resolveActiveValue(entry?.active_condition, { stateModel, item: entry });
                return (
                  <DropdownMenuItem
                    key={entry?.id || `overflow_${index}`}
                    onSelect={() => invokeEntry(entry)}
                    className={cn(active && 'bg-accent text-accent-foreground')}
                  >
                    <SidebarIcon
                      icon={entry?.icon}
                      className={cn(
                        'mr-2',
                        active ? 'main-sidebar-nav-icon-active' : 'main-sidebar-nav-icon-idle',
                      )}
                    />
                    {label}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
        {showThemeToggle ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="main-sidebar-nav-btn main-sidebar-nav-btn-idle"
                onClick={() => setClientThemeState(toggleClientTheme(clientTheme))}
                aria-label="Theme selector"
              >
                <i
                  className={cn(
                    clientTheme === 'dark' ? 'ri-moon-clear-fill' : 'ri-sun-line',
                    'main-sidebar-nav-icon',
                    'main-sidebar-nav-icon-idle',
                  )}
                />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">{clientTheme === 'dark' ? 'Dark theme' : 'Light theme'}</TooltipContent>
          </Tooltip>
        ) : null}
        {showLanguageMenu ? (
          <DropdownMenu>
            <Tooltip>
              <TooltipTrigger asChild>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="main-sidebar-nav-btn main-sidebar-nav-btn-idle"
                    aria-label="Language selector"
                  >
                    {currentLanguage.toUpperCase()}
                  </Button>
                </DropdownMenuTrigger>
              </TooltipTrigger>
              <TooltipContent side="right">Language</TooltipContent>
            </Tooltip>
            <DropdownMenuContent side="right" align="start" className="main-sidebar-overflow-menu">
              {languageOptions.map((entry: any) => (
                <DropdownMenuItem
                  key={entry.value}
                  onSelect={() => onAction?.('set_user_language', { value: entry.value })}
                  className={cn(entry.value === currentLanguage && 'bg-accent text-accent-foreground')}
                >
                  {entry.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    </TooltipProvider>
  );
};
