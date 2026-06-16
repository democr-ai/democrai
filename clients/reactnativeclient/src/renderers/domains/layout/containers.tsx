import React from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import { numberOrDefault, usePhoneLayout, useResponsiveStyle } from '../../../utils/responsive';

const isStretchValue = (value: any): boolean => (
  value === true || value === 1 || (typeof value === 'number' && value > 0)
);

const computePadding = (padding: any): ViewStyle => {
  if (!Array.isArray(padding) || padding.length !== 4) return {};
  return {
    paddingTop: numberOrDefault(padding[0], 0),
    paddingRight: numberOrDefault(padding[1], 0),
    paddingBottom: numberOrDefault(padding[2], 0),
    paddingLeft: numberOrDefault(padding[3], 0),
  };
};

const rowAlignmentStyle = (align: any, collapsed: boolean): ViewStyle => {
  const value = String(align || 'top').toLowerCase();
  if (collapsed) {
    switch (value) {
      case 'right':
        return { alignItems: 'flex-end' };
      case 'center':
        return { alignItems: 'center' };
      case 'fill':
        return { alignItems: 'stretch' };
      case 'left':
      case 'top':
      default:
        return { alignItems: 'flex-start' };
    }
  }

  switch (value) {
    case 'right':
      return { justifyContent: 'flex-end', alignItems: 'flex-start' };
    case 'center':
      return { justifyContent: 'center', alignItems: 'center' };
    case 'bottom':
      return { justifyContent: 'flex-start', alignItems: 'flex-end' };
    case 'fill':
      return { justifyContent: 'flex-start', alignItems: 'stretch' };
    case 'left':
    case 'top':
    default:
      return { justifyContent: 'flex-start', alignItems: 'flex-start' };
  }
};

const columnAlignmentStyle = (align: any): ViewStyle => {
  const value = String(align || 'top').toLowerCase();
  switch (value) {
    case 'bottom':
      return { justifyContent: 'flex-end', alignItems: 'stretch' };
    case 'left':
      return { justifyContent: 'flex-start', alignItems: 'flex-start' };
    case 'right':
      return { justifyContent: 'flex-start', alignItems: 'flex-end' };
    case 'center':
      return { justifyContent: 'center', alignItems: 'center' };
    case 'fill':
    case 'top':
    default:
      return { justifyContent: 'flex-start', alignItems: 'stretch' };
  }
};

const sanitizeMobileContainerStyle = (style: ViewStyle, isPhone: boolean): ViewStyle => {
  if (!isPhone) return style;
  const next: ViewStyle = { ...(style || {}) };
  delete next.flex;
  delete next.flexGrow;
  delete next.flexShrink;
  delete (next as any).flexBasis;
  delete next.minWidth;
  delete next.maxWidth;
  if (typeof next.width === 'number') {
    next.width = '100%';
  }
  next.maxWidth = '100%';
  next.minWidth = 0;
  next.flexShrink = 1;
  return next;
};

const isCompactNavigationRow = (children: any): boolean => {
  const list = React.Children.toArray(children);
  if (list.length < 2 || list.length > 4) return false;
  return list.every((child: any) => {
    const componentData = child?.props?.componentData;
    const type = Object.keys(componentData?.component || {})[0];
    return type === 'Button' || type === 'Text';
  });
};

export const Row: React.FC<any> = ({
  id,
  ExplicitList,
  style,
  gap,
  spacing,
  stretch,
  align,
  mobile_direction,
  mobileDirection,
  padding,
}) => {
  const isPhone = usePhoneLayout();
  const responsiveStyle = useResponsiveStyle(style as ViewStyle);
  const requestedMobileDirection = String(mobile_direction || mobileDirection || '').toLowerCase();
  const normalizedId = String(id || '').toLowerCase();
  const keepRowOnPhone = normalizedId === 'login_container' || isCompactNavigationRow(ExplicitList);
  const isLoginContainer = isPhone && normalizedId === 'login_container';
  const isEmptyLanguageBar = isPhone && normalizedId === 'empty_language_bar';
  const structuralFill = normalizedId === 'module_root';
  const collapse = isPhone && requestedMobileDirection !== 'row' && !keepRowOnPhone;
  const fill = isStretchValue(stretch) || (!collapse && String(align || '').toLowerCase() === 'fill');
  const safeGap = numberOrDefault(gap ?? spacing, 0);
  const safeResponsiveStyle = sanitizeMobileContainerStyle(responsiveStyle as ViewStyle, isPhone);
  const mobileColumnChildStyle: ViewStyle = collapse
    ? { width: '100%', maxWidth: '100%', minWidth: 0 }
    : {};

  return (
    <View style={[
      collapse ? styles.rowAsColumn : styles.row,
      keepRowOnPhone && styles.noWrap,
      keepRowOnPhone && styles.centerRow,
      (fill || structuralFill) && styles.fill,
      rowAlignmentStyle(align, collapse),
      computePadding(padding),
      { gap: safeGap },
      safeResponsiveStyle,
      mobileColumnChildStyle,
      isLoginContainer && styles.loginContainerPhone,
      isEmptyLanguageBar && styles.emptyLanguageBarPhone,
    ]}>
      {ExplicitList}
    </View>
  );
};

export const Column: React.FC<any> = ({
  id,
  ExplicitList,
  style,
  gap,
  spacing,
  stretch,
  align,
  padding,
  width,
  max_width,
  maxWidth,
}) => {
  const isPhone = usePhoneLayout();
  const normalizedId = String(id || '').toLowerCase();
  const isLoginCard = isPhone && normalizedId === 'login_card';
  const isLoginSpacer = isPhone && (normalizedId === 'spacer_1' || normalizedId === 'spacer_2');
  const structuralFill = normalizedId === 'content_area_container' || normalizedId === 'comp_list_container';
  const fill = isStretchValue(stretch) || String(align || '').toLowerCase() === 'fill';
  const responsiveStyle = useResponsiveStyle(style as ViewStyle);
  const safeResponsiveStyle = sanitizeMobileContainerStyle(responsiveStyle as ViewStyle, isPhone);
  const safeGap = numberOrDefault(gap ?? spacing, 0);
  const declaredWidth = width != null ? Number(width) : undefined;
  const declaredMaxWidth = max_width ?? maxWidth;
  const columnSize: ViewStyle = {
    ...(Number.isFinite(declaredWidth)
      ? (isPhone ? { width: '100%', minWidth: 0 } : { minWidth: declaredWidth })
      : {}),
    ...(Number.isFinite(Number(declaredMaxWidth))
      ? (isPhone ? { maxWidth: '100%' } : { maxWidth: Number(declaredMaxWidth) })
      : {}),
  };

  if (isLoginSpacer) return null;

  return (
    <View style={[
      styles.column,
      (fill || structuralFill) && styles.fill,
      isLoginCard && styles.loginCard,
      columnAlignmentStyle(align),
      computePadding(padding),
      columnSize,
      { gap: safeGap },
      safeResponsiveStyle,
    ]}>
      {ExplicitList}
    </View>
  );
};

// A direction-agnostic container that fills available space.
// With no children it acts as a spacer; with children it wraps them in a flex:1 view.
export const FlexContainer: React.FC<any> = ({ ExplicitList, style }) => {
  const isPhone = usePhoneLayout();
  const responsiveStyle = useResponsiveStyle(style as ViewStyle);
  const isEmptySpacer = React.Children.count(ExplicitList) === 0;
  if (isPhone && isEmptySpacer) return null;

  return (
    <View style={[styles.fill, responsiveStyle as ViewStyle]}>
      {ExplicitList}
    </View>
  );
};

// A horizontal wrapping container — lays out children left-to-right, wrapping to new lines.
export const Flow: React.FC<any> = ({ ExplicitList, style, spacing }) => {
  const responsiveStyle = useResponsiveStyle(style as ViewStyle);
  return (
    <View style={[styles.flow, { gap: numberOrDefault(spacing, 10) }, responsiveStyle as ViewStyle]}>
      {ExplicitList}
    </View>
  );
};

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    flexWrap: 'wrap',
    width: '100%',
    maxWidth: '100%',
    minWidth: 0,
    overflow: 'hidden',
  },
  rowAsColumn: {
    flexDirection: 'column',
    alignItems: 'stretch',
    width: '100%',
    maxWidth: '100%',
    minWidth: 0,
    overflow: 'visible',
  },
  mobileColumn: {
    flexDirection: 'column',
    flexWrap: 'nowrap',
  },
  noWrap: {
    flexWrap: 'nowrap',
  },
  centerRow: {
    justifyContent: 'center',
  },
  loginContainerPhone: {
    flex: 0,
    flexGrow: 0,
    flexShrink: 0,
    marginTop: 0,
    transform: [{ translateY: -35 }],
  },
  emptyLanguageBarPhone: {
    flexGrow: 0,
    flexShrink: 0,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 6,
    paddingBottom: 8,
  },
  column: {
    flexDirection: 'column',
    width: '100%',
    maxWidth: '100%',
    minWidth: 0,
    overflow: 'hidden',
  },
  fill: {
    flex: 1,
    minWidth: 0,
    overflow: 'hidden',
  },
  flow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    maxWidth: '100%',
    minWidth: 0,
    overflow: 'hidden',
  },
  loginCard: {
    alignSelf: 'center',
  },
});
