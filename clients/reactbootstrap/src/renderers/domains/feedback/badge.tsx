import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { resolveBindings } from '@/renderers/rules';
import { Badge as UIBadge } from 'design-react-kit';

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
  
  const color = normalized === 'destructive' ? 'danger' : (normalized === 'default' ? 'secondary' : normalized);

  return (
    <UIBadge
      color={color}
      pill
      className={`a2ui-badge a2ui-badge-${color} d-inline-flex align-items-center`}
      style={parseStyle(style)}
    >
      {getLiteral(resolvedText)}
    </UIBadge>
  );
};
