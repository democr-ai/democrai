import React, { useState } from 'react';
import { Icon } from '@fluentui/react';
import { parseStyle } from '@/utils/style';
import { getLiteral, toBoolean } from '@/renderers/shared';

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
    <div style={parseStyle(style)} className="a2ui-accordion w-100">
      {safeItems.map((item: any, index: number) => {
        const id = String(index);
        const isOpen = openItems.includes(id);
        const bodyNode = Array.isArray(ExplicitList) ? ExplicitList[index] : null;
        const contentText = getLiteral(item?.content);
        const title = getLiteral(item?.title || item?.label || `Item ${index + 1}`);
        
        return (
          <section className={`a2ui-accordion-item ${isOpen ? 'a2ui-accordion-item-open' : ''}`} key={id}>
            <button
              type="button"
              className="a2ui-accordion-header"
              aria-expanded={isOpen}
              aria-controls={`a2ui-accordion-panel-${id}`}
              id={`a2ui-accordion-header-${id}`}
              onClick={() => toggle(id)}
            >
              <span className="a2ui-accordion-title">{title}</span>
              <Icon className="a2ui-accordion-caret" iconName="ChevronDown" aria-hidden="true" />
            </button>
            {isOpen ? (
              <div
                id={`a2ui-accordion-panel-${id}`}
                className="a2ui-accordion-panel"
                role="region"
                aria-labelledby={`a2ui-accordion-header-${id}`}
              >
                {bodyNode}
                {contentText ? <div className="a2ui-accordion-text">{contentText}</div> : null}
              </div>
            ) : null}
          </section>
        );
      })}
    </div>
  );
};
