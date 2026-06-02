import React from 'react';
import { parseStyle } from '@/utils/style';
import { Skeleton as UISkeleton } from '@/components/ui/skeleton';
import { Card, CardContent } from '@/components/ui/card';

export const Skeleton: React.FC<any> = ({ lines = 3, widths = [], avatar = false, style }) => (
  <Card style={parseStyle(style)}>
    <CardContent className="grid gap-3 p-4">
      {avatar ? <UISkeleton className="h-11 w-11 rounded-full" /> : null}
      {Array.from({ length: Number(lines) || 3 }).map((_, index) => (
        <UISkeleton key={`skeleton_${index}`} className="h-3" style={{ width: `${widths[index] || 100}%` }} />
      ))}
    </CardContent>
  </Card>
);
