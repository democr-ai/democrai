import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { resolveBindings } from '@/renderers/rules';
import { MessageBar, MessageBarType } from '@fluentui/react';

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
  const intent =
    normalized === 'destructive' || normalized === 'danger' ? MessageBarType.error
      : normalized === 'success' ? MessageBarType.success
        : normalized === 'warning' ? MessageBarType.warning
          : MessageBarType.info;
  
  const titleText = getLiteral(resolvedTitle);
  const descriptionText = getLiteral(resolvedDescription);

  return (
    <MessageBar
      messageBarType={intent}
      isMultiline={Boolean(descriptionText)}
      style={parseStyle(style)}
      className={`ds-alert ds-alert-${normalized} w-100`}
    >
      <span className="ds-alert-content">
        {titleText && <strong className="ds-alert-title">{titleText}</strong>}
        {descriptionText && <span className="ds-alert-description">{descriptionText}</span>}
      </span>
    </MessageBar>
  );
};
