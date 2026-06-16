import { StyleSheet, useWindowDimensions } from 'react-native';

const PHONE_BREAKPOINT = 700;

export const usePhoneLayout = (breakpoint = PHONE_BREAKPOINT): boolean => {
  const { width } = useWindowDimensions();
  return width < breakpoint;
};

export const clampResponsiveStyle = <T extends any>(
  style: T,
  screenWidth: number,
  options: { inset?: number; clampFixedWidth?: boolean; clampMinWidth?: boolean } = {},
): T => {
  const inset = Number(options.inset ?? 24) || 0;
  const maxWidth = Math.max(0, screenWidth - inset);
  const clampFixedWidth = options.clampFixedWidth !== false;
  const clampMinWidth = options.clampMinWidth !== false;
  const flat = StyleSheet.flatten(style as any);

  if (!flat || typeof flat !== 'object') return style;

  const next: any = { ...flat };
  if (clampFixedWidth && typeof next.width === 'number' && next.width > maxWidth) {
    next.width = '100%';
  }
  if (typeof next.maxWidth === 'number' && next.maxWidth > maxWidth) {
    next.maxWidth = maxWidth;
  }
  if (clampMinWidth && typeof next.minWidth === 'number' && next.minWidth > maxWidth) {
    next.minWidth = 0;
  }
  if (typeof next.marginLeft === 'number' && typeof next.marginRight === 'number') {
    const horizontalMargin = next.marginLeft + next.marginRight;
    if (horizontalMargin > screenWidth * 0.35) {
      next.marginLeft = Math.min(next.marginLeft, 12);
      next.marginRight = Math.min(next.marginRight, 12);
    }
  }

  return next;
};

export const useResponsiveStyle = <T extends any>(
  style: T,
  options: { inset?: number; clampFixedWidth?: boolean; clampMinWidth?: boolean } = {},
): T => {
  const { width } = useWindowDimensions();
  return clampResponsiveStyle(style, width, options);
};

export const numberOrDefault = (value: any, fallback: number): number => {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
};
