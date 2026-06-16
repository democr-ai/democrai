import React from 'react';
export const Spacer: React.FC<any> = ({ size = 12, horizontal = false }) => (
  <div style={horizontal ? { width: size, minWidth: size } : { height: size, minHeight: size }} />
);
