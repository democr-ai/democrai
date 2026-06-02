import React from 'react';
import { parseStyle } from '@/utils/style';
import { toBoolean, getLiteral } from '@/renderers/shared';
import {
  Collapsible as UICollapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Button } from '@/components/ui/button';

export const Collapsible: React.FC<any> = ({ title, content, ExplicitList, open = false, style }) => {
  const [isOpen, setIsOpen] = React.useState(toBoolean(open));

  React.useEffect(() => {
    setIsOpen(toBoolean(open));
  }, [open]);

  return (
    <UICollapsible open={isOpen} onOpenChange={setIsOpen} style={parseStyle(style)}>
      <CollapsibleTrigger asChild>
        <Button variant="outline" className="w-full justify-between">
          {getLiteral(title)}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-2 text-sm text-muted-foreground">
        {ExplicitList}
        {getLiteral(content)}
      </CollapsibleContent>
    </UICollapsible>
  );
};
