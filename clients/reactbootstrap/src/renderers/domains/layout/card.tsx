import React from 'react';
import { parseStyle } from '@/utils/style';
import { Card as UICard, CardBody, CardFooter } from 'design-react-kit';
import { Button } from 'design-react-kit';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { resolveIconClass } from '@/renderers/domains/actions/button';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { isNestedActionVisible } from '@/renderers/rules';

const mapVariant = (v: string): 'primary' | 'secondary' | 'danger' | 'outline-primary' => {
  if (v === 'primary') return 'primary';
  if (v === 'danger' || v === 'destructive') return 'danger';
  if (v === 'secondary') return 'secondary';
  if (v === 'outline') return 'outline-primary';
  return 'outline-primary';
};

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
          backgroundImage: `url("${resolvedBackgroundImage}")`,
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
    <UICard className={`a2ui-card w-100 ${resolvedBackgroundImage ? 'a2ui-card-media' : ''}`} style={cardStyle}>
      <CardBody className="a2ui-card-body" style={bodyStyle}>
        {ExplicitList}
      </CardBody>
      {hasActions && visibleActions.length > 0 && (
        <CardFooter className={`a2ui-card-footer d-flex w-100 gap-2 px-3 py-2 ${resolvedBackgroundImage ? 'bg-white' : ''}`}>
          {visibleActions.map((actionDef: any, i: number) => {
            const label = getLiteral(actionDef.label, '');
            const iconClass = actionDef.icon ? resolveIconClass(actionDef.icon) : null;
            return (
              <Button
                key={i}
                color={mapVariant(actionDef.variant || 'ghost')}
                size="sm"
                className="a2ui-button a2ui-card-action flex-grow-1 text-truncate"
                onClick={() => emitActionSpec(actionDef.action, onAction, itemData)}
              >
                {iconClass && <i className={`${iconClass} ${label ? 'me-1' : ''}`} />}
                {label && <span>{label}</span>}
              </Button>
            );
          })}
        </CardFooter>
      )}
    </UICard>
  );
};
