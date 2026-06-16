import React from 'react';
import { parseStyle } from '@/utils/style';

/**
 * FlexContainer — a direction-agnostic container that always fills available space.
 */
export const FlexContainer: React.FC<any> = ({ ExplicitList, style }) => {
  return (
    <div 
      className="a2ui-flex-container d-flex flex-fill flex-column min-vh-0 min-vw-0 w-100 h-100" 
      style={parseStyle(style)}
    >
      {ExplicitList}
    </div>
  );
}
