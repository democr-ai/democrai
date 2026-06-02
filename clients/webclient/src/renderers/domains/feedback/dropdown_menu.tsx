import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import {
  DropdownMenu as UIDropdownMenu,
  DropdownMenuContent as UIDropdownMenuContent,
  DropdownMenuItem as UIDropdownMenuItem,
  DropdownMenuTrigger as UIDropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';

export const DropdownMenu: React.FC<any> = ({ label, items = [], onAction, style }) => (
  <div style={parseStyle(style)}>
    <UIDropdownMenu>
      <UIDropdownMenuTrigger asChild>
        <Button variant="outline">{getLiteral(label)}</Button>
      </UIDropdownMenuTrigger>
      <UIDropdownMenuContent align="end">
        {items.map((item: any, index: number) => (
          <UIDropdownMenuItem key={`menu_item_${index}`} onClick={() => emitActionSpec(item?.action, onAction, {})}>
            {getLiteral(item?.label)}
          </UIDropdownMenuItem>
        ))}
      </UIDropdownMenuContent>
    </UIDropdownMenu>
  </div>
);
