import React from 'react';
import { StyleSheet, ViewStyle } from 'react-native';
import RemixIcon from 'react-native-remix-icon';
import { resolveIconName } from '../../utils/icons';

type IconProps = {
  name: any;
  size?: number;
  color?: string;
  style?: ViewStyle;
};

export const Icon: React.FC<IconProps> = ({ name, size = 24, color = '#333', style }) => {
  const iconName = resolveIconName(name);

  if (!iconName) return null;

  return (
    <RemixIcon
      name={iconName as any}
      size={size}
      color={color}
      style={style}
    />
  );
};
