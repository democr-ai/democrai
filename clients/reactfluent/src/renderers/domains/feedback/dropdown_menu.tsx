import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { Button, DropdownItem } from '@/design/system';

export const DropdownMenu: React.FC<any> = ({ label, items = [], onAction, style }) => {
  const [open, setOpen] = React.useState(false);

  return (
    <div className="ds-dropdown" style={parseStyle(style)}>
      <Button color="primary" outline size="sm" onClick={() => setOpen((value) => !value)}>
        {getLiteral(label)}
        <i className="ri-arrow-down-s-line" aria-hidden="true" />
      </Button>
      {open ? (
      <div className="ds-dropdown-menu">
        {items.map((item: any, index: number) => (
          <DropdownItem
            key={`menu_item_${index}`}
            onClick={() => {
              setOpen(false);
              emitActionSpec(item?.action, onAction, {});
            }}
          >
            {getLiteral(item?.label)}
          </DropdownItem>
        ))}
      </div>
      ) : null}
    </div>
  );
};
