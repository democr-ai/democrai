import { ViewStyle, TextStyle, ImageStyle } from 'react-native';

/**
 * Parses a CSS-like style string into a React Native style object.
 * Also handles object-based styles.
 */
export function parseStyle(style: any): ViewStyle | TextStyle | ImageStyle {
  if (!style) return {};
  if (typeof style !== 'string') return style;

  const styleObj: any = {};
  style.split(';').forEach(rule => {
    const [key, value] = rule.split(':');
    if (key && value) {
      // Convert kebab-case (background-color) to camelCase (backgroundColor)
      let camelKey = key.trim().replace(/-./g, x => x[1].toUpperCase());
      let val = value.trim();

      // Properties that must always be numbers in React Native
      const MUST_BE_NUMBER = new Set([
        'letterSpacing', 'lineHeight', 'fontSize', 'fontWeight',
        'borderRadius', 'borderWidth', 'opacity', 'zIndex', 'elevation',
        'borderTopLeftRadius', 'borderTopRightRadius', 'borderBottomLeftRadius', 'borderBottomRightRadius',
      ]);

      // Basic mapping of CSS units to RN numbers if applicable
      if (val.endsWith('px') || val.endsWith('em') || val.endsWith('rem')) {
        const num = parseFloat(val);
        if (!isNaN(num)) val = num as any;
      } else if (!isNaN(parseFloat(val)) && !val.includes('%')) {
        const num = parseFloat(val);
        if (!isNaN(num)) val = num as any;
      } else if (MUST_BE_NUMBER.has(camelKey)) {
        const num = parseFloat(val);
        if (!isNaN(num)) val = num as any;
      }

      // Handle specific RN mappings
      if (camelKey === 'display' && val === 'none') {
        // In RN, display: 'none' is supported, but 'flex' is default
      }

      styleObj[camelKey] = val;
    }
  });
  return styleObj;
}
