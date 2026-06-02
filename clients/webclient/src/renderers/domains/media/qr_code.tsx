import React from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { Card, CardContent } from '@/components/ui/card';

export const QRCode: React.FC<any> = ({ content, value, size = 220, style, fill_color = 'var(--qr-fill)', back_color = 'var(--qr-bg)' }) => {
  const text = getLiteral(content || value);
  const safeSize = Math.max(40, Number(size) || 220);

  return (
    <Card style={parseStyle(style)}>
      <CardContent className="flex items-center justify-center p-4">
        {text ? (
          <QRCodeSVG value={text} size={safeSize} fgColor={String(fill_color || 'var(--qr-fill)')} bgColor={String(back_color || 'var(--qr-bg)')} />
        ) : (
          <div className="text-xs text-muted-foreground">[QR: empty content]</div>
        )}
      </CardContent>
    </Card>
  );
};
