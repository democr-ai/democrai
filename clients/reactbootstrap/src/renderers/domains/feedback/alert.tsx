import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { resolveBindings } from '@/renderers/rules';
import { Alert as UIAlert } from 'design-react-kit';

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
  const color = normalized === 'destructive' ? 'danger' : (normalized === 'default' ? 'primary' : normalized);
  
  const titleText = getLiteral(resolvedTitle);
  const descriptionText = getLiteral(resolvedDescription);

  return (
    <UIAlert color={color} style={parseStyle(style)} className={`a2ui-alert a2ui-alert-${color} w-100`}>
      {titleText && <h4 className="alert-heading">{titleText}</h4>}
      {descriptionText && <p className="mb-0">{descriptionText}</p>}
    </UIAlert>
  );
};
