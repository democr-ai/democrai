import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { resolveBindings } from '@/renderers/rules';

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
  
  const color =
    normalized === 'destructive' || normalized === 'danger' ? 'danger'
      : normalized === 'success' ? 'success'
        : normalized === 'warning' ? 'warning'
          : normalized === 'info' ? 'info'
            : normalized === 'subtle' ? 'subtle'
              : normalized === 'default' ? 'info'
                : 'brand';

  return (
    <span
      className={`ds-badge ds-badge-${color}`}
      style={parseStyle(style)}
    >
      {getLiteral(resolvedText)}
    </span>
  );
};
