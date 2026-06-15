import React from 'react';
import { parseStyle } from '@/utils/style';

export const Dialog: React.FC<any> = ({ title, ExplicitList, style }) => (
  <section className="a2ui-dialog-surface" style={parseStyle(style)}>
    {title ? <div className="a2ui-dialog-title">{title}</div> : null}
    <div className="d-grid gap-2">{ExplicitList}</div>
  </section>
);
