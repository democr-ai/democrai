import React from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { Card, CardBody } from '@/design/system';

export const QRCode: React.FC<any> = ({ content, value, size = 220, style, fill_color = 'var(--qr-fill)', back_color = 'var(--qr-bg)' }) => {
  const text = getLiteral(content || value);
  const safeSize = Math.max(40, Number(size) || 220);

  return (
    <Card style={parseStyle(style)} className="border shadow-sm">
      <CardBody className="d-flex align-items-center justify-content-center p-4">
        {text ? (
          <QRCodeSVG value={text} size={safeSize} fgColor={String(fill_color || 'var(--qr-fill)')} bgColor={String(back_color || 'var(--qr-bg)')} />
        ) : (
          <div className="xsmall text-muted">[QR: contenuto vuoto]</div>
        )}
      </CardBody>
    </Card>
  );
};
