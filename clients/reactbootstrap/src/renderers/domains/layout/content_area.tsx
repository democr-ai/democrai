import React from 'react';
import { Column } from './column';

export const ContentArea: React.FC<any> = ({ padding: _ignoredPadding, ...props }) => (
  <div className="module-content-panel h-100 min-vh-0 d-flex flex-column flex-grow-1 overflow-auto">
    <Column {...props} stretch />
  </div>
);
