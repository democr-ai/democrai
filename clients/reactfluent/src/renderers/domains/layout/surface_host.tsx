import React from 'react';
import { parseStyle } from '@/utils/style';

export const SurfaceHost: React.FC<any> = ({ ExplicitList, style, surface_id, ui_role }) => {
  const normalizedUiRole = String(ui_role || '').trim();

  return (
    <div
      data-surface-host-id={surface_id || undefined}
      data-ui-role={normalizedUiRole || undefined}
      style={parseStyle(style)}
      className={['min-h-0 min-w-0 w-full h-full', normalizedUiRole].filter(Boolean).join(' ')}
    >
      {ExplicitList}
    </div>
  );
};
