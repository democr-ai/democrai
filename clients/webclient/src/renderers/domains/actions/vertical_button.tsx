import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, isAnyTrackedActionPending, toBoolean } from '@/renderers/shared';
import { Button as UIButton } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { resolveIconClass } from './button';

export const VerticalButton: React.FC<any> = ({
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

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <UIButton
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => emitActionSpec(action, onAction, {
              ...(params && typeof params === 'object' ? params : {}),
              ...(Array.isArray(collect_input_ids) && collect_input_ids.length > 0
                ? { __client__: { collect_input_ids } }
                : {}),
            })}
            disabled={disabled}
            className={cn(
              'main-sidebar-nav-btn',
              isActive ? 'main-sidebar-nav-btn-active' : 'main-sidebar-nav-btn-idle',
            )}
            style={parseStyle(style)}
            aria-label={tooltip || 'nav-item'}
          >
            <i className={cn(isLoading ? 'ri-loader-4-line animate-spin' : iconName, 'main-sidebar-nav-icon')} />
          </UIButton>
        </TooltipTrigger>
        {tooltip ? <TooltipContent>{tooltip}</TooltipContent> : null}
      </Tooltip>
    </TooltipProvider>
  );
};
