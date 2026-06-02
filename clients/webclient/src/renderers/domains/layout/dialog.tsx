import React from 'react';
import { parseStyle } from '@/utils/style';
import { Card as UICard, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export const Dialog: React.FC<any> = ({ title, ExplicitList, style }) => (
  <UICard style={parseStyle(style)}>
    {title ? (
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
    ) : null}
    <CardContent className="grid gap-2">{ExplicitList}</CardContent>
  </UICard>
);
