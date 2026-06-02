import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, isAnyTrackedActionPending, toBoolean } from '@/renderers/shared';
import { Button as UIButton } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export const resolveIconClass = (icon: any): string => {
  const raw = String(icon?.iconName || icon || '').trim();
  if (!raw) return '';

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
  };

  return map[raw.toLowerCase()] || '';
};

export const Button: React.FC<any> = ({
  label,
  action,
  params,
  onAction,
  icon,
  style,
  variant = 'default',
  mode = 'solid',
  appearance,
  btnsize = 'normal',
  active,
  shape = 'default',
  collect_input_ids,
  pendingActions,
  track_loading,
}) => {
  const sourceVariant = appearance || variant;
  const resolvedVariant = sourceVariant === 'danger' ? 'destructive' : sourceVariant;
  const isActive = toBoolean(active);
  const labelText = getLiteral(label);
  const actionName = typeof action === 'string' ? action : String(action?.name || '');
  const isLoading = isAnyTrackedActionPending(pendingActions, track_loading, actionName);
  const disabled = isLoading;
  const iconClass = isLoading ? 'ri-loader-4-line' : (icon ? resolveIconClass(icon) : null);
  const effectiveShape = shape === 'icon' ? 'round' : shape;
  const isNavButton = mode === 'ghost' && effectiveShape === 'round' && !labelText;
  const isRoundShape = effectiveShape === 'round';

  const mapVariant = (): 'default' | 'outline' | 'secondary' | 'ghost' | 'link' | 'destructive' => {
    if (mode === 'link') return 'link';
    if (mode === 'ghost') return 'ghost';
    if (resolvedVariant === 'destructive' || resolvedVariant === 'danger') return 'destructive';
    if (resolvedVariant === 'secondary') return 'secondary';
    if (resolvedVariant === 'outline') return 'outline';
    if (resolvedVariant === 'default') return 'outline';
    // success/info/warning: use ghost as a clean base (no bg-primary conflict)
    if (resolvedVariant === 'success' || resolvedVariant === 'info' || resolvedVariant === 'warning') return 'ghost';
    return 'default'; // primary
  };

  // Extra Tailwind classes for variants/modes without native shadcn support.
  const variantExtraClass = (): string => {
    const v = resolvedVariant;
    if (mode === 'link') {
      if (v === 'destructive') return 'text-destructive hover:text-destructive';
      if (v === 'success')     return 'text-[var(--ui-tone-success)] hover:text-[var(--ui-tone-success)]';
      if (v === 'warning')     return 'text-[var(--ui-tone-warning)] hover:text-[var(--ui-tone-warning)]';
      if (v === 'info')        return 'text-[var(--ui-tone-info)] hover:text-[var(--ui-tone-info)]';
      return 'text-primary hover:text-primary';
    }
    if (mode === 'ghost') {
      if (v === 'primary')     return 'ui-btn-ghost-primary';
      if (v === 'destructive') return 'text-destructive hover:text-destructive hover:bg-destructive/10';
      if (v === 'success')     return 'ui-btn-ghost-success';
      if (v === 'warning')     return 'ui-btn-ghost-warning';
      if (v === 'info')        return 'ui-btn-ghost-info';
      return '';
    }
    // Solid soft — subtle tinted bg + colored text (mirrors shadcn destructive style)
    if (v === 'success') return 'ui-btn-soft-success';
    if (v === 'warning') return 'ui-btn-soft-warning';
    if (v === 'info')    return 'ui-btn-soft-info';
    return '';
  };

  const mapSize = (): 'default' | 'sm' | 'lg' | 'icon' => {
    if (effectiveShape === 'round') return 'icon';
    if (btnsize === 'small' || btnsize === 'sm') return 'sm';
    if (btnsize === 'large' || btnsize === 'lg') return 'lg';
    return 'default';
  };

  const handleClick = () => emitActionSpec(action, onAction, {
    ...(params && typeof params === 'object' ? params : {}),
    ...(Array.isArray(collect_input_ids) && collect_input_ids.length > 0
      ? { __client__: { collect_input_ids } }
      : {}),
  });

  if (isNavButton) {
    return (
      <UIButton
        type="button"
        variant="ghost"
        size="icon"
        onClick={handleClick}
        disabled={disabled}
        className={cn(
          'main-sidebar-nav-btn',
          isActive ? 'main-sidebar-nav-btn-active' : 'main-sidebar-nav-btn-idle',
        )}
        style={parseStyle(style)}
      >
        {iconClass && <i className={cn(iconClass, 'main-sidebar-nav-icon', isLoading && 'animate-spin')} />}
      </UIButton>
    );
  }

  return (
    <UIButton
      type="button"
      variant={mapVariant()}
      size={mapSize()}
      onClick={handleClick}
      disabled={disabled}
      className={cn(
        variantExtraClass(),
        isRoundShape && 'aspect-square rounded-[4px]',
        'self-start w-auto max-w-full',
        isActive && 'ring-2 ring-ring',
      )}
      style={parseStyle(style)}
    >
      {iconClass && <i className={cn(iconClass, 'text-base', isLoading && 'animate-spin')} />}
      {!iconClass && isLoading && <i className="ri-loader-4-line text-base animate-spin" />}
      {labelText ? <span>{labelText}</span> : null}
    </UIButton>
  );
};
