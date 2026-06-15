import React from 'react';
import { parseStyle } from '@/utils/style';
import { Card, Skeleton as FluentSkeleton, SkeletonItem } from '@fluentui/react-components';

export const Skeleton: React.FC<any> = ({ lines = 3, widths = [], avatar = false, style }) => (
  <Card appearance="outline" className="a2ui-card" style={parseStyle(style)}>
    <FluentSkeleton className="d-grid gap-3 p-4" aria-label="Loading content">
      {avatar ? <SkeletonItem shape="circle" style={{ height: '44px', width: '44px' }} /> : null}
      {Array.from({ length: Number(lines) || 3 }).map((_, index) => (
        <SkeletonItem
          key={`skeleton_${index}`}
          shape="rectangle"
          style={{ height: '12px', width: `${widths[index] || 100}%` }}
        />
      ))}
    </FluentSkeleton>
  </Card>
);
