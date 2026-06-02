import React from 'react';
import { parseStyle } from '@/utils/style';
import { cn } from '@/lib/utils';
import { getLiteral } from '@/renderers/shared';
import { resolveBindings } from '@/renderers/rules';
import { Alert as UIAlert, AlertDescription, AlertTitle } from '@/components/ui/alert';

const ALERT_VARIANT_CLASS: Record<string, string> = {
  info: 'ui-alert-info',
  success: 'ui-alert-success',
  warning: 'ui-alert-warning',
  destructive: 'ui-alert-danger',
  default: 'border-border bg-card text-card-foreground',
};

export const Alert: React.FC<any> = ({
  title,
  description,
  variant = 'info',
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

  const resolvedTitle = resolveBindings(title, bindingOptions);
  const resolvedDescription = resolveBindings(description, bindingOptions);
  const resolvedVariant = resolveBindings(variant, bindingOptions);
  const normalized = String(getLiteral(resolvedVariant, 'info') || 'info').toLowerCase();
  const className = ALERT_VARIANT_CLASS[normalized] || ALERT_VARIANT_CLASS.info;
  const descriptionText = getLiteral(resolvedDescription);

  return (
    <UIAlert className={cn(className)} style={parseStyle(style)}>
      <AlertTitle>{getLiteral(resolvedTitle)}</AlertTitle>
      {descriptionText ? <AlertDescription>{descriptionText}</AlertDescription> : null}
    </UIAlert>
  );
};
