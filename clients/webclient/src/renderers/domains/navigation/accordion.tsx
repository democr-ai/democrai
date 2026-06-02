import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral, toBoolean } from '@/renderers/shared';
import {
  Accordion as UIAccordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';

export const Accordion: React.FC<any> = ({ items = [], ExplicitList, multiple = false, collapsible = true, style }) => {
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
      .filter(Boolean),
    [initialSignature, safeItems],
  );

  const [value, setValue] = React.useState<string | string[]>(multiple ? initial : (initial[0] || ''));
  const syncedSignatureRef = React.useRef('');

  React.useEffect(() => {
    const signature = `${multiple ? 'multiple' : 'single'}:${initialSignature}`;
    if (syncedSignatureRef.current === signature) return;
    syncedSignatureRef.current = signature;
    setValue(multiple ? initial : (initial[0] || ''));
  }, [multiple, initial, initialSignature]);

  const rootProps = multiple
    ? { type: 'multiple' as const }
    : { type: 'single' as const, collapsible: toBoolean(collapsible) };

  return (
    <UIAccordion
      {...rootProps}
      value={value as any}
      onValueChange={setValue as any}
      className="w-full"
      style={parseStyle(style)}
    >
      {safeItems.map((item: any, index: number) => {
        const id = String(index);
        const bodyNode = Array.isArray(ExplicitList) ? ExplicitList[index] : null;
        const contentText = getLiteral(item?.content);
        return (
          <AccordionItem key={`accordion_${id}`} value={id}>
            <AccordionTrigger>{getLiteral(item?.title || item?.label || `Item ${index + 1}`)}</AccordionTrigger>
            <AccordionContent>
              {bodyNode}
              {contentText ? <div className="mt-2">{contentText}</div> : null}
            </AccordionContent>
          </AccordionItem>
        );
      })}
    </UIAccordion>
  );
};
