import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { Suggestions as AISuggestions, Suggestion } from '@/components/ai-elements/suggestion';

export const Suggestions: React.FC<any> = ({ suggestions = [], action, onAction, style }) => (
  <div style={parseStyle(style)}>
    <AISuggestions>
      {suggestions.map((entry: any, index: number) => (
        <Suggestion
          key={`suggestion_${index}`}
          suggestion={getLiteral(entry?.label || entry?.prompt)}
          onClick={() => {
            emitActionSpec(action, onAction, {
              prompt: entry?.prompt,
              label: entry?.label,
              suggestion: entry,
            });
          }}
        />
      ))}
    </AISuggestions>
  </div>
);
