import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { numberOrDefault, useResponsiveStyle } from '../../../utils/responsive';

const computePadding = (padding: any): ViewStyle => {
  const values = Array.isArray(padding) && padding.length === 4 ? padding : [8, 4, 8, 4];
  return {
    paddingTop: numberOrDefault(values[0], 8),
    paddingRight: numberOrDefault(values[1], 4),
    paddingBottom: numberOrDefault(values[2], 8),
    paddingLeft: numberOrDefault(values[3], 4),
  };
};

export const Sidebar: React.FC<any> = ({
  ExplicitList,
  style,
  padding = [8, 4, 8, 4],
  width,
  max_width,
  maxWidth,
  stretch = true,
}) => {
  const responsiveStyle = useResponsiveStyle(style as ViewStyle);
  const declaredWidth = Number(width);
  const declaredMaxWidth = Number(max_width ?? maxWidth);
  const sizeStyle: ViewStyle = {
    ...(Number.isFinite(declaredWidth) ? { width: declaredWidth, minWidth: declaredWidth } : {}),
    ...(Number.isFinite(declaredMaxWidth) ? { maxWidth: declaredMaxWidth } : {}),
  };
  const children = React.Children.toArray(ExplicitList);

  return (
    <View style={[
      styles.sidebar,
      stretch ? styles.stretch : null,
      sizeStyle,
      responsiveStyle as ViewStyle,
    ]}>
      <View style={[styles.content, computePadding(padding)]}>
        {children.map((child, index) => (
          <View key={(child as any)?.key || `sidebar_child_${index}`} style={index === 1 && children.length >= 3 ? styles.middle : null}>
            {child}
          </View>
        ))}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  sidebar: {
    width: '100%',
    minHeight: 0,
    alignSelf: 'stretch',
    backgroundColor: '#161B22',
    borderRightWidth: 1,
    borderRightColor: '#21262D',
  },
  stretch: {
    flex: 1,
  },
  scroll: {
    flex: 1,
    width: '100%',
  },
  content: {
    flex: 1,
    width: '100%',
    gap: 8,
    minHeight: 0,
  },
  middle: {
    flex: 1,
    minHeight: 0,
    justifyContent: 'flex-start',
  },
});
