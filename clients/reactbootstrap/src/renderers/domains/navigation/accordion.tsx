import React, { useState } from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral, toBoolean } from '@/renderers/shared';
import {
  Accordion as UIAccordion,
  AccordionBody,
  AccordionHeader,
  AccordionItem,
} from 'design-react-kit';

export const Accordion: React.FC<any> = ({ items = [], ExplicitList, multiple = false, style }) => {
  const safeItems = React.useMemo(() => (Array.isArray(items) ? items : []), [items]);
  const initialSignature = React.useMemo(
    () => safeItems
      .map((item: any, index: number) => `${String(item?.id ?? index)}:${toBoolean(item?.open) ? '1' : '0'}`)
      .join('|'),
    [safeItems],
  );
  const initial = React.useMemo(
    () => safeItems
      .map((item: any, index: number) => (toBoolean(item?.open) ? String(index) : null))
      .filter((n: any): n is string => n !== null),
    [initialSignature, safeItems],
  );
  const [openItems, setOpenItems] = useState<string[]>(() => initial);
  const syncedSignatureRef = React.useRef('');

  React.useEffect(() => {
    const signature = `${multiple ? 'multiple' : 'single'}:${initialSignature}`;
    if (syncedSignatureRef.current === signature) return;
    syncedSignatureRef.current = signature;
    setOpenItems(initial);
  }, [initial, initialSignature, multiple]);

  const toggle = (id: string) => {
    if (multiple) {
      setOpenItems(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]);
    } else {
      setOpenItems(prev => prev.includes(id) ? [] : [id]);
    }
  };

  return (
    <UIAccordion style={parseStyle(style)} className="a2ui-accordion w-100">
      {safeItems.map((item: any, index: number) => {
        const id = String(index);
        const isOpen = openItems.includes(id);
        const bodyNode = Array.isArray(ExplicitList) ? ExplicitList[index] : null;
        const contentText = getLiteral(item?.content);
        
        return (
          <AccordionItem key={id}>
            <AccordionHeader active={isOpen} onToggle={() => toggle(id)}>
              {getLiteral(item?.title || item?.label || `Item ${index + 1}`)}
            </AccordionHeader>
            <AccordionBody active={isOpen}>
              {bodyNode}
              {contentText ? <div className="mt-2">{contentText}</div> : null}
            </AccordionBody>
          </AccordionItem>
        );
      })}
    </UIAccordion>
  );
};
