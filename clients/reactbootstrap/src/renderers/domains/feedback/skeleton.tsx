import React from 'react';
import { parseStyle } from '@/utils/style';
import { Card, CardBody } from 'design-react-kit';

export const Skeleton: React.FC<any> = ({ lines = 3, widths = [], avatar = false, style }) => (
  <Card style={parseStyle(style)}>
    <CardBody className="d-grid gap-3 p-4">
      {avatar ? <div className="skeleton rounded-circle" style={{ height: '44px', width: '44px' }} /> : null}
      {Array.from({ length: Number(lines) || 3 }).map((_, index) => (
        <div 
          key={`skeleton_${index}`} 
          className="skeleton" 
          style={{ height: '12px', width: `${widths[index] || 100}%` }} 
        />
      ))}
    </CardBody>
  </Card>
);
