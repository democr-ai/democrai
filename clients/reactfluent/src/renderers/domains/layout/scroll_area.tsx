import React from 'react';
import { parseStyle } from '@/utils/style';

export const ScrollArea: React.FC<any> = ({
  ExplicitList,
  style,
  stretch,
  content_style,
  transparent,
  scroll_x = true,
  scroll_y = true,
}) => (
  <div
    className={`scroll-area-viewport min-vh-0 w-100 h-100 ${stretch ? 'flex-grow-1' : ''} ${transparent ? '' : 'bg-transparent'}`}
    style={{
      ...parseStyle(style),
      minHeight: 0,
      overflowX: scroll_x ? 'auto' : 'hidden',
      overflowY: scroll_y ? 'auto' : 'hidden',
    }}
  >
    <div className="w-100 min-vh-0" style={parseStyle(content_style)}>{ExplicitList}</div>
  </div>
);
