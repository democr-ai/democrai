import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, isAnyTrackedActionPending, toBoolean } from '@/renderers/shared';
import {
  DefaultButton,
  IconButton,
  PrimaryButton,
  Spinner,
  SpinnerSize,
} from '@fluentui/react';

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
  
  const mapTone = (): string => {
    if (sourceVariant === 'default') return 'default';
    if (sourceVariant === 'danger' || sourceVariant === 'destructive') return 'danger';
    if (sourceVariant === 'secondary') return 'secondary';
    if (sourceVariant === 'success') return 'success';
    if (sourceVariant === 'warning') return 'warning';
    if (sourceVariant === 'info') return 'info';
    return 'primary';
  };

  const isOutline = mode === 'outline' || sourceVariant === 'outline';
  const isLink = mode === 'link';
  const isGhost = mode === 'ghost';

  const mapSizeClass = (): string => {
    if (btnsize === 'small' || btnsize === 'sm') return 'small';
    if (btnsize === 'large' || btnsize === 'lg') return 'large';
    return 'medium';
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

  const buttonTone = mapTone();
  const iconNode = isLoading ? (
    <Spinner size={SpinnerSize.xSmall} />
  ) : iconClass ? (
    <i className={`${iconClass} ${labelText ? 'me-2' : ''}`} aria-hidden="true" />
  ) : undefined;

  const ButtonComponent = sourceVariant === 'default' || sourceVariant === 'secondary' || isOutline || isGhost ? DefaultButton : PrimaryButton;
  const sizeClass = mapSizeClass();
  const className = [
    'ds-button',
    `ds-button-${buttonTone}`,
    `ds-button-${sizeClass}`,
    isLink ? 'ds-button-link' : '',
    isGhost ? 'ds-button-ghost' : '',
    isOutline ? 'ds-button-outline' : '',
    effectiveShape === 'round' ? 'ds-button-round' : '',
    isActive ? 'active' : '',
    'd-inline-flex align-items-center justify-content-center',
  ].filter(Boolean).join(' ');

  if (isLink) {
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={handleClick}
        style={{ ...parseStyle(style), minWidth: 'auto' }}
        className={className}
      >
        {iconNode}
        {labelText ? <span>{labelText}</span> : null}
      </button>
    );
  }

  const commonProps = {
    disabled,
    onClick: handleClick,
    style: { ...parseStyle(style), minWidth: 'auto' },
    className,
    onRenderIcon: iconNode ? () => iconNode : undefined,
  };

  if (!labelText && iconNode) {
    return (
      <IconButton
        {...commonProps}
        ariaLabel={labelText || 'action'}
      />
    );
  }

  return (
    <ButtonComponent {...commonProps}>
      {labelText ? <span>{labelText}</span> : null}
    </ButtonComponent>
  );
};
