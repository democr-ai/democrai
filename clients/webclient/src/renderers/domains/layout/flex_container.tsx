import React from 'react';
import { parseStyle } from '@/utils/style';

/**
 * FlexContainer — a direction-agnostic container that always fills available space.
 * With children it wraps them in a flex-1 div; with no children it acts as a spacer.
 */
export const FlexContainer: React.FC<any> = ({ ExplicitList, style }) => {
  let classes = ["flex", "flex-1", "flex-col", "min-h-0", "min-w-0", "w-full", ...(ExplicitList && Array.isArray(ExplicitList) && ExplicitList.length > 0 ? ExplicitList.map(l => l.props?.componentId) : [])]

  return <div className={classes.join(" ")} style={parseStyle(style)}>
    {ExplicitList}
  </div>
}
