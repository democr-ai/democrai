import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, isAnyTrackedActionPending, toBoolean } from '@/renderers/shared';
import { Button as UIButton, UncontrolledTooltip } from 'design-react-kit';
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
  const targetId = `vertical-btn-${id || Math.random().toString(36).substr(2, 9)}`;

  const handleClick = () => emitActionSpec(action, onAction, {
    ...(params && typeof params === 'object' ? params : {}),
    ...(Array.isArray(collect_input_ids) && collect_input_ids.length > 0
      ? { __client__: { collect_input_ids } }
      : {}),
  });

  return (
    <>
      <button
        id={targetId}
        type="button"
        onClick={handleClick}
        disabled={disabled}
        className={`main-sidebar-nav-btn ${isActive ? 'active' : ''}`}
        style={parseStyle(style)}
        aria-label={tooltip || 'nav-item'}
      >
        <i className={`${isLoading ? 'ri-loader-4-line ri-spin' : iconName} main-sidebar-nav-icon`} />
      </button>
      {tooltip && (
        <UncontrolledTooltip placement="right" target={targetId}>
          {tooltip}
        </UncontrolledTooltip>
      )}
    </>
  );
};
