import React from 'react';
import { parseStyle } from '@/utils/style';
import { DefaultButton, PrimaryButton } from '@fluentui/react';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { resolveIconClass } from '@/renderers/domains/actions/button';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { isNestedActionVisible } from '@/renderers/rules';

export const Card: React.FC<any> = ({
  ExplicitList,
  style,
  itemActions,
  data,
  onAction,
  background_image,
  backgroundImage,
  padding,
  max_width,
  maxWidth,
  stateModel,
  userRole,
  userPermissions,
}) => {
  const hasActions = Array.isArray(itemActions) && itemActions.length > 0;
  const itemData = data && typeof data === 'object' ? data : {};
  const contentPadding = Array.isArray(padding) ? padding : undefined;
  const rawBackgroundImage = getLiteral(background_image || backgroundImage, '');
  const resolvedBackgroundImage = useResolvedMediaUrl(rawBackgroundImage);
  const parsedStyle = parseStyle(style);
  const resolvedMaxWidth = Number(max_width ?? maxWidth ?? 0);
  
  const cardStyle: React.CSSProperties = {
    ...parsedStyle,
    ...(Number.isFinite(resolvedMaxWidth) && resolvedMaxWidth > 0
      ? { maxWidth: resolvedMaxWidth, width: '100%' }
      : {}),
    ...(resolvedBackgroundImage
      ? {
          backgroundImage: `linear-gradient(var(--ds-card-media-overlay, rgba(0, 0, 0, 0.66)), var(--ds-card-media-overlay, rgba(0, 0, 0, 0.66))), url("${resolvedBackgroundImage}")`,
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
          backgroundSize: 'cover',
        }
      : {}),
  };

  const bodyStyle: React.CSSProperties | undefined =
    Array.isArray(contentPadding) &&
    contentPadding.length === 4 &&
    contentPadding.every((v: any) => Number.isFinite(Number(v)))
      ? {
          padding: `${Number(contentPadding[0])}px ${Number(contentPadding[1])}px ${Number(contentPadding[2])}px ${Number(contentPadding[3])}px`,
        }
      : { padding: '1rem' };

  const visibleActions = Array.isArray(itemActions)
    ? itemActions.filter((actionDef: any) => isNestedActionVisible(
        actionDef,
        { stateModel, item: itemData },
        String(userRole || 'Guest'),
        Array.isArray(userPermissions) ? userPermissions.map((entry: any) => String(entry)) : [],
      ))
    : [];

  return (
    <section
      className={`ds-card w-100 ${resolvedBackgroundImage ? 'ds-card-media' : ''}`}
      style={cardStyle}
    >
      <div className="ds-card-body" style={bodyStyle}>
        {ExplicitList}
      </div>
      {hasActions && visibleActions.length > 0 && (
        <div
          className="ds-card-footer d-flex w-100 gap-2"
        >
          {visibleActions.map((actionDef: any, i: number) => {
            const label = getLiteral(actionDef.label, '');
            const iconClass = actionDef.icon ? resolveIconClass(actionDef.icon) : null;
            const isDanger = actionDef.variant === 'danger' || actionDef.variant === 'destructive';
            const isPrimary = actionDef.variant === 'primary';
            const ActionButton = isPrimary ? PrimaryButton : DefaultButton;
            return (
              <ActionButton
                key={i}
                className={`ds-button ds-button-small ds-card-action flex-grow-1 text-truncate ${isDanger ? 'ds-button-danger' : ''}`}
                onRenderIcon={iconClass ? () => <i className={`${iconClass} me-2`} aria-hidden="true" /> : undefined}
                onClick={() => emitActionSpec(actionDef.action, onAction, itemData)}
                style={isDanger ? { color: 'var(--ui-tone-danger)' } : undefined}
              >
                {label && <span>{label}</span>}
              </ActionButton>
            );
          })}
        </div>
      )}
    </section>
  );
};
