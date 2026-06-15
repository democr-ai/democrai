import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral, toBoolean } from '@/renderers/shared';
import { ProgressIndicator } from '@fluentui/react';

export const Progress: React.FC<any> = ({ value = 0, maximum = 100, label, show_label = true, style }) => {
  const safeMaximum = Math.max(1, Number(maximum) || 100);
  const safeValue = Math.max(0, Math.min(Number(value) || 0, safeMaximum));
  const pct = Math.round((safeValue / safeMaximum) * 100);

  return (
    <ProgressIndicator
      className="ds-progress"
      style={parseStyle(style)}
      label={toBoolean(show_label) ? getLiteral(label) : undefined}
      description={toBoolean(show_label) ? `${pct}%` : undefined}
      percentComplete={pct / 100}
    />
  );
};
