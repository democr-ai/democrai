import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { UncontrolledDropdown, DropdownItem, DropdownToggle, DropdownMenu as UIDropdownMenu } from 'reactstrap';

export const DropdownMenu: React.FC<any> = ({ label, items = [], onAction, style }) => (
  <div style={parseStyle(style)}>
    <UncontrolledDropdown>
      <DropdownToggle caret color="primary" outline size="sm">
        {getLiteral(label)}
      </DropdownToggle>
      <UIDropdownMenu right>
        {items.map((item: any, index: number) => (
          <DropdownItem key={`menu_item_${index}`} onClick={() => emitActionSpec(item?.action, onAction, {})}>
            {getLiteral(item?.label)}
          </DropdownItem>
        ))}
      </UIDropdownMenu>
    </UncontrolledDropdown>
  </div>
);
