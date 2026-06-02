import React from 'react';
import { parseStyle } from '@/utils/style';
import { cn } from '@/lib/utils';
import { getLiteral } from '@/renderers/shared';
import { resolveBindings } from '@/renderers/rules';
import { Badge as UIBadge } from '@/components/ui/badge';

const BADGE_VARIANT_CLASS: Record<string, string> = {
  default: 'ui-badge-default',
  success: 'ui-badge-success',
  warning: 'ui-badge-warning',
  destructive: 'ui-badge-danger',
  info: 'ui-badge-info',
};

export const Badge: React.FC<any> = ({
  text,
  variant = 'default',
  style,
  stateModel,
  surfaceModel,
}) => {
  const bindingOptions = React.useMemo(() => ({
    stateModel,
    surfaceModel,
    item: undefined,
    role: '',
    permissions: [],
  }), [stateModel, surfaceModel]);

  const resolvedText = resolveBindings(text, bindingOptions);
  const resolvedVariant = resolveBindings(variant, bindingOptions);
  const normalized = String(getLiteral(resolvedVariant, 'default') || 'default').toLowerCase();
  const visualClass = BADGE_VARIANT_CLASS[normalized] || BADGE_VARIANT_CLASS.default;

  return (
    <UIBadge
      variant="secondary"
      className={cn('inline-flex w-fit rounded-full', visualClass)}
      style={parseStyle(style)}
    >
      {getLiteral(resolvedText)}
    </UIBadge>
  );
};
