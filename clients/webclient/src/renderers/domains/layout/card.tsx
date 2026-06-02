import React from 'react';
import { parseStyle } from '@/utils/style';
import { Card as UICard, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { resolveIconClass } from '@/renderers/domains/actions/button';
import { cn } from '@/lib/utils';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { isNestedActionVisible } from '@/renderers/rules';

const mapVariant = (v: string): 'default' | 'outline' | 'secondary' | 'ghost' | 'destructive' => {
  if (v === 'primary') return 'default';
  if (v === 'danger' || v === 'destructive') return 'destructive';
  if (v === 'secondary') return 'secondary';
  if (v === 'outline') return 'outline';
  return 'ghost';
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

  const contentStyle: React.CSSProperties | undefined =
    Array.isArray(contentPadding) &&
    contentPadding.length === 4 &&
    contentPadding.every((v: any) => Number.isFinite(Number(v)))
      ? {
          padding: `${Number(contentPadding[0])}px ${Number(contentPadding[1])}px ${Number(contentPadding[2])}px ${Number(contentPadding[3])}px`,
        }
      : undefined;
  const visibleActions = Array.isArray(itemActions)
    ? itemActions.filter((actionDef: any) => isNestedActionVisible(
        actionDef,
        { stateModel, item: itemData },
        String(userRole || 'Guest'),
        Array.isArray(userPermissions) ? userPermissions.map((entry: any) => String(entry)) : [],
      ))
    : [];
  return (
    <UICard className="w-full" style={cardStyle}>
      <CardContent className="p-3.5" style={contentStyle}>
        {ExplicitList}
      </CardContent>
      {hasActions && visibleActions.length > 0 && (
        <CardFooter className={cn("flex w-full gap-1 px-3 py-2", resolvedBackgroundImage ? "bg-card" : "")}>
          {visibleActions.map((actionDef: any, i: number) => {
            const label = getLiteral(actionDef.label, '');
            const iconClass = actionDef.icon ? resolveIconClass(actionDef.icon) : null;
            return (
              <Button
                key={i}
                variant={mapVariant(actionDef.variant || 'ghost')}
                size="sm"
                className="min-w-0 flex-1"
                onClick={() => emitActionSpec(actionDef.action, onAction, itemData)}
              >
                {iconClass && <i className={cn(iconClass, label ? 'mr-1' : '')} />}
                {label && <span className="truncate">{label}</span>}
              </Button>
            );
          })}
        </CardFooter>
      )}
    </UICard>
  );
};
