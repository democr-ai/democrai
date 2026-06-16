import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral, toBoolean } from '@/renderers/shared';
import { Progress as UIProgress } from 'design-react-kit';

export const Progress: React.FC<any> = ({ value = 0, maximum = 100, label, show_label = true, style }) => {
  const safeMaximum = Math.max(1, Number(maximum) || 100);
  const safeValue = Math.max(0, Math.min(Number(value) || 0, safeMaximum));
  const pct = Math.round((safeValue / safeMaximum) * 100);

  return (
    <div className="a2ui-progress d-grid gap-2" style={parseStyle(style)}>
      {toBoolean(show_label) ? (
        <div className="d-flex align-items-center justify-content-between small">
          <span>{getLiteral(label)}</span>
          <span className="text-muted">{pct}%</span>
        </div>
      ) : null}
      <UIProgress value={pct} />
    </div>
  );
};
