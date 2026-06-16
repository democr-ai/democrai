import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { Button } from '@/design/system';

export const ScrollToBottomButton: React.FC<any> = ({ label, action, onAction, style }) => (
  <div style={parseStyle(style)}>
    <Button
      type="button"
      color="primary"
      outline
      size="sm"
      className="rounded-pill shadow-sm d-flex align-items-center gap-2"
      onClick={() => {
        const viewport = document.querySelector('.scroll-area-viewport');
        if (viewport) {
          viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' });
        } else {
          window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
        }
        emitActionSpec(action, onAction, {});
      }}
    >
      <i className="ri-arrow-down-line" />
      {getLiteral(label || 'Go to latest messages')}
    </Button>
  </div>
);
