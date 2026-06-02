import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, parseActionSpec, requestActionConfirm } from '@/renderers/shared';
import { Button } from '@/components/ui/button';

export const ScrollToBottomButton: React.FC<any> = ({ label, action, onAction, style }) => (
  <div style={parseStyle(style)}>
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={async () => {
        const parsed = parseActionSpec(action);
        if (parsed.confirm && !(await requestActionConfirm(parsed.confirm))) {
          return;
        }
        const viewport = document.querySelector('[data-radix-scroll-area-viewport]');
        if (viewport) {
          viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' });
        } else {
          window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
        }
        const actionWithoutConfirm = action && typeof action === 'object'
          ? { ...action, confirm: undefined }
          : action;
        emitActionSpec(actionWithoutConfirm, onAction, {});
      }}
    >
      {getLiteral(label || 'Jump to latest')}
    </Button>
  </div>
);
