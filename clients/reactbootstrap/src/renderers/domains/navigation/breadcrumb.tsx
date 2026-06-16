import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral, toBoolean } from '@/renderers/shared';

export const Breadcrumb: React.FC<any> = ({ segments = [], separator = '/', onAction, style }) => {
  const separatorText = getLiteral(separator, '/');
  const items = Array.isArray(segments) ? segments : [];

  return (
    <nav className="a2ui-breadcrumb" aria-label="Breadcrumb" style={parseStyle(style)}>
      <ol className="a2ui-breadcrumb-list">
        {items.map((segment: any, index: number) => {
      const label = getLiteral(segment?.label);
      const current = toBoolean(segment?.current) || index === items.length - 1;
      const path = segment?.path;

      return (
        <li
          key={`crumb_${index}`}
          className={`a2ui-breadcrumb-item ${current ? 'active' : ''}`}
          aria-current={current ? 'page' : undefined}
        >
          {index > 0 ? <span className="a2ui-breadcrumb-separator" aria-hidden="true">{separatorText}</span> : null}
          {current || !path ? (
            <span className="a2ui-breadcrumb-current">{label}</span>
          ) : (
            <button 
              type="button"
              className="a2ui-breadcrumb-link"
              onClick={() => onAction?.('navigate', { path })}
            >
              {label}
            </button>
          )}
        </li>
      );
        })}
      </ol>
    </nav>
  );
};
