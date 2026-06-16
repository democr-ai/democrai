import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, isAnyTrackedActionPending, toBoolean } from '@/renderers/shared';
import { IconButton, Spinner, SpinnerSize } from '@fluentui/react';
import { resolveIconClass } from './button';

export const VerticalButton: React.FC<any> = ({
  id,
  label,
  action,
  params,
  onAction,
  icon,
  style,
  active,
  collect_input_ids,
  pendingActions,
  track_loading,
}) => {
  const iconName = resolveIconClass(icon);
  const isActive = toBoolean(active);
  const tooltip = getLiteral(label);
  const actionName = typeof action === 'string' ? action : String(action?.name || '');
  const isLoading = isAnyTrackedActionPending(pendingActions, track_loading, actionName);
  const disabled = isLoading;
  const handleClick = () => emitActionSpec(action, onAction, {
    ...(params && typeof params === 'object' ? params : {}),
    ...(Array.isArray(collect_input_ids) && collect_input_ids.length > 0
      ? { __client__: { collect_input_ids } }
      : {}),
  });

  return (
    <IconButton
      type="button"
      onClick={handleClick}
      disabled={disabled}
      className={`main-sidebar-nav-btn ${isActive ? 'active' : ''}`}
      style={parseStyle(style)}
      ariaLabel={tooltip || 'nav-item'}
      title={tooltip || undefined}
      onRenderIcon={() => (
        isLoading
          ? <Spinner size={SpinnerSize.xSmall} />
          : <i className={`${iconName} main-sidebar-nav-icon`} aria-hidden="true" />
      )}
    />
  );
};
