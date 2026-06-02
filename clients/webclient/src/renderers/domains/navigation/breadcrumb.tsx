import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral, toBoolean } from '@/renderers/shared';
import {
  Breadcrumb as UIBreadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';

export const Breadcrumb: React.FC<any> = ({ segments = [], onAction, style }) => (
  <UIBreadcrumb style={parseStyle(style)}>
    <BreadcrumbList>
      {Array.isArray(segments) && segments.map((segment: any, index: number) => {
        const label = getLiteral(segment?.label);
        const current = toBoolean(segment?.current) || index === segments.length - 1;
        const path = segment?.path;

        return (
          <React.Fragment key={`crumb_${index}`}>
            <BreadcrumbItem>
              {current || !path ? (
                <BreadcrumbPage>{label}</BreadcrumbPage>
              ) : (
                <Button variant="link" className="h-auto p-0" onClick={() => onAction?.('navigate', { path })}>
                  {label}
                </Button>
              )}
            </BreadcrumbItem>
            {index < segments.length - 1 ? <BreadcrumbSeparator /> : null}
          </React.Fragment>
        );
      })}
    </BreadcrumbList>
  </UIBreadcrumb>
);
