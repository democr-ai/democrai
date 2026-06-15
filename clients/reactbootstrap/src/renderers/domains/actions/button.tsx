import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, isAnyTrackedActionPending, toBoolean } from '@/renderers/shared';
import { Button as UIButton } from 'design-react-kit';

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
  const isActive = toBoolean(active);
  const labelText = getLiteral(label);
  const actionName = typeof action === 'string' ? action : String(action?.name || '');
  const isLoading = isAnyTrackedActionPending(pendingActions, track_loading, actionName);
  const disabled = isLoading;
  const iconClass = isLoading ? 'ri-loader-4-line' : (icon ? resolveIconClass(icon) : null);
  const effectiveShape = shape === 'icon' ? 'round' : shape;
  const isNavButton = mode === 'ghost' && effectiveShape === 'round' && !labelText;
  
  const mapColor = (): string => {
    if (sourceVariant === 'danger' || sourceVariant === 'destructive') return 'danger';
    if (sourceVariant === 'secondary') return 'secondary';
    if (sourceVariant === 'success') return 'success';
    if (sourceVariant === 'warning') return 'warning';
    if (sourceVariant === 'info') return 'info';
    return 'primary';
  };
  const mapTone = (): string => {
    if (sourceVariant === 'default') return 'default';
    return mapColor();
  };

  const isOutline = mode === 'outline' || sourceVariant === 'outline';
  const isLink = mode === 'link';
  const isGhost = mode === 'ghost';

  const mapSize = (): string | undefined => {
    if (btnsize === 'small' || btnsize === 'sm') return 'sm';
    if (btnsize === 'large' || btnsize === 'lg') return 'lg';
    return undefined;
  };

  const handleClick = () => emitActionSpec(action, onAction, {
    ...(params && typeof params === 'object' ? params : {}),
    ...(Array.isArray(collect_input_ids) && collect_input_ids.length > 0
      ? { __client__: { collect_input_ids } }
      : {}),
  });

  if (isNavButton) {
    return (
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled}
        className={`main-sidebar-nav-btn ${isActive ? 'active' : ''}`}
        style={parseStyle(style)}
        title={labelText || undefined}
      >
        {iconClass && <i className={`${iconClass} ${isLoading ? 'ri-spin' : ''}`} />}
      </button>
    );
  }

  const buttonColor = mapColor();
  const buttonTone = mapTone();
  const buttonProps: any = {
    color: buttonColor,
    outline: isOutline,
    size: mapSize(),
    disabled: disabled,
    onClick: handleClick,
    style: { ...parseStyle(style), minWidth: 'auto' },
    className: `a2ui-button a2ui-button-${buttonTone}`,
  };

  if (isLink) {
    buttonProps.color = 'link';
    buttonProps.className = `a2ui-button a2ui-button-link a2ui-button-${buttonTone}`;
  }
  if (isGhost) {
    buttonProps.outline = true;
    buttonProps.className = `a2ui-button a2ui-button-ghost a2ui-button-${buttonTone}`;
  }

  return (
    <UIButton
      {...buttonProps}
      className={`${buttonProps.className || ''} ${isActive ? 'active' : ''} d-inline-flex align-items-center justify-content-center`}
    >
      {iconClass && <i className={`${iconClass} ${labelText ? 'me-2' : ''} ${isLoading ? 'ri-spin' : ''}`} />}
      {!iconClass && isLoading && <i className="ri-loader-4-line ri-spin me-2" />}
      {labelText ? <span>{labelText}</span> : null}
    </UIButton>
  );
};
