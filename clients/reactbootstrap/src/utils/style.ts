import React from 'react';

/**
 * Parses a CSS string into a React CSSProperties object.
 * This is necessary because the SDK often sends styles as raw strings,
 * which React cannot directly spread into its style prop.
 */
export function parseStyle(style: any): React.CSSProperties {
    if (!style) return {};
    if (typeof style !== 'string') return style;

    const styleObj: any = {};
    style.split(';').forEach(rule => {
        const [key, value] = rule.split(':');
        if (key && value) {
            // Convert kebab-case (background-color) to camelCase (backgroundColor)
            const camelKey = key.trim().replace(/-./g, x => x[1].toUpperCase());
            styleObj[camelKey] = value.trim();
        }
    });
    return styleObj;
}
