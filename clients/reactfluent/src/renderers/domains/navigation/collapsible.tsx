import React from 'react';
import { parseStyle } from '@/utils/style';
import { toBoolean, getLiteral } from '@/renderers/shared';
import { Button, Collapse } from '@/design/system';

export const Collapsible: React.FC<any> = ({ title, content, ExplicitList, open = false, style }) => {
  const [isOpen, setIsOpen] = React.useState(toBoolean(open));

  React.useEffect(() => {
    setIsOpen(toBoolean(open));
  }, [open]);

  return (
    <div style={parseStyle(style)} className="w-100">
      <Button
        outline
        color="primary"
        className="w-100 d-flex justify-content-between align-items-center mb-2"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span>{getLiteral(title)}</span>
        <i className={isOpen ? "ri-arrow-up-s-line" : "ri-arrow-down-s-line"} />
      </Button>
      <Collapse isOpen={isOpen}>
        <div className="p-3 border rounded bg-light small text-muted">
          {ExplicitList}
          {getLiteral(content)}
        </div>
      </Collapse>
    </div>
  );
};
