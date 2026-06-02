import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral, toBoolean } from '@/renderers/shared';
import { Progress as UIProgress } from '@/components/ui/progress';

export const Progress: React.FC<any> = ({ value = 0, maximum = 100, label, show_label = true, style }) => {
  const safeMaximum = Math.max(1, Number(maximum) || 100);
  const safeValue = Math.max(0, Math.min(Number(value) || 0, safeMaximum));
  const pct = Math.round((safeValue / safeMaximum) * 100);

  return (
    <div className="grid gap-2" style={parseStyle(style)}>
      {toBoolean(show_label) ? (
        <div className="flex items-center justify-between text-sm">
          <span>{getLiteral(label)}</span>
          <span className="text-muted-foreground">{pct}%</span>
        </div>
      ) : null}
      <UIProgress value={pct} />
    </div>
  );
};
