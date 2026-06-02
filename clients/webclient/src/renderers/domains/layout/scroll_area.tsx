import React from 'react';
import { parseStyle } from '@/utils/style';
import { cn } from '@/lib/utils';
import { ScrollArea as UIScrollArea } from '@/components/ui/scroll-area';

export const ScrollArea: React.FC<any> = ({
  ExplicitList,
  style,
  stretch,
  content_style,
  transparent,
  scroll_x = true,
  scroll_y = true,
}) => (
  <UIScrollArea
    className={cn(
      stretch ? 'min-h-0 flex-1' : '',
      'min-h-0 h-full w-full overflow-hidden bg-transparent [&_[data-slot=scroll-area-viewport]]:bg-transparent',
      transparent ? 'bg-transparent' : '',
      scroll_x ? '' : 'overflow-x-hidden',
      scroll_y ? '' : 'overflow-y-hidden',
    )}
    style={parseStyle(style)}
  >
    <div className="min-h-0 h-full w-full" style={parseStyle(content_style)}>{ExplicitList}</div>
  </UIScrollArea>
);
