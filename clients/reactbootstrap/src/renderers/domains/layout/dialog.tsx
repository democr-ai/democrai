import React from 'react';
import { parseStyle } from '@/utils/style';
import { Card, CardBody, CardHeader } from 'design-react-kit';

export const Dialog: React.FC<any> = ({ title, ExplicitList, style }) => (
  <Card style={parseStyle(style)}>
    {title ? (
      <CardHeader className="pb-1">
        <h6 className="m-0 small fw-bold">{title}</h6>
      </CardHeader>
    ) : null}
    <CardBody className="d-grid gap-2">{ExplicitList}</CardBody>
  </Card>
);
