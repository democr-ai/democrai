import React from 'react';
import { Column } from './column';

export const ContentArea: React.FC<any> = ({ padding: _ignoredPadding, ...props }) => (
  <div className="module-content-panel min-h-0 flex-1">
    <Column {...props} stretch />
  </div>
);
