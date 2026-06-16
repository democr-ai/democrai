import React from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { numberOrDefault, usePhoneLayout, useResponsiveStyle } from '../../../utils/responsive';

export const Header: React.FC<any> = ({
  id,
  ExplicitList,
  leftExplicitList,
  centerExplicitList,
  rightExplicitList,
  style,
  spacing = 8,
}) => {
  const insets = useSafeAreaInsets();
  const isPhone = usePhoneLayout();
  const responsiveStyle = useResponsiveStyle(style as ViewStyle);
  const slotGap = numberOrDefault(spacing, 8);

  const centerNodes = centerExplicitList && React.Children.count(centerExplicitList) > 0
    ? centerExplicitList
    : ExplicitList;

  if (isPhone) {
    return (
      <View style={[styles.header, styles.headerPhone, { paddingTop: Math.max(insets.top, 8) }, responsiveStyle as ViewStyle]}>
        <View style={styles.phoneTopRow}>
          <View style={[styles.slot, styles.phoneLeftSlot, { gap: slotGap }]}>
            {leftExplicitList}
          </View>
          <View style={[styles.slot, styles.phoneRightSlot, { gap: slotGap }]}>
            {rightExplicitList}
          </View>
        </View>
        {centerNodes && React.Children.count(centerNodes) > 0 ? (
          <View style={[styles.slot, styles.phoneCenterSlot, { gap: slotGap }]}>
            {centerNodes}
          </View>
        ) : null}
      </View>
    );
  }

  return (
    <View style={[styles.header, { paddingTop: Math.max(insets.top, 8) }, responsiveStyle as ViewStyle]}>
      <View style={[styles.slot, styles.leftSide, { gap: slotGap }]}>
        {leftExplicitList}
      </View>
      <View style={[styles.slot, styles.centerSide, { gap: slotGap }]}>
        {centerNodes}
      </View>
      <View style={[styles.slot, styles.rightSide, { gap: slotGap }]}>
        {rightExplicitList}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    borderBottomWidth: 1,
    borderBottomColor: '#21262D',
    backgroundColor: '#161B22',
    paddingHorizontal: 16,
    paddingBottom: 10,
    minHeight: 56,
    gap: 8,
  },
  headerPhone: {
    flexDirection: 'column',
    alignItems: 'stretch',
    flexWrap: 'nowrap',
    paddingHorizontal: 12,
    paddingBottom: 8,
  },
  phoneTopRow: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  slot: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    minWidth: 0,
  },
  leftSide: {
    flex: 1,
    justifyContent: 'flex-start',
  },
  centerSide: {
    flex: 2,
    justifyContent: 'center',
  },
  rightSide: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  phoneLeftSlot: {
    flex: 1,
    justifyContent: 'flex-start',
    minWidth: 0,
  },
  phoneRightSlot: {
    flex: 1,
    justifyContent: 'flex-end',
    minWidth: 0,
  },
  phoneCenterSlot: {
    width: '100%',
    minWidth: 0,
    justifyContent: 'flex-start',
    marginTop: 8,
  },
});
