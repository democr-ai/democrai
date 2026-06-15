import React from 'react';
import { parseStyle } from '@/utils/style';

export const Skeleton: React.FC<any> = ({ lines = 3, widths = [], avatar = false, style }) => (
  <div className="ds-card ds-skeleton-card" style={parseStyle(style)} aria-label="Loading content">
    <div className="d-grid gap-3 p-4">
      {avatar ? <span className="ds-skeleton-item ds-skeleton-avatar" style={{ height: '44px', width: '44px' }} /> : null}
      {Array.from({ length: Number(lines) || 3 }).map((_, index) => (
        <span
          key={`skeleton_${index}`}
          className="ds-skeleton-item"
          style={{ height: '12px', width: `${widths[index] || 100}%` }}
        />
      ))}
    </div>
  </div>
);
