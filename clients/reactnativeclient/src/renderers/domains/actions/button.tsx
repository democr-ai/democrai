import React from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { getLiteral, toBoolean, emitActionSpec, isAnyTrackedActionPending } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

type Tone = {
  solidBg: string;
  solidBorder: string;
  solidText: string;
  subtleBg: string;
  border: string;
  text: string;
};

const TONES: Record<string, Tone> = {
  default: {
    solidBg: '#21262D',
    solidBorder: '#30363D',
    solidText: '#E6EDF3',
    subtleBg: 'rgba(139,148,158,0.10)',
    border: '#30363D',
    text: '#C9D1D9',
  },
  secondary: {
    solidBg: '#21262D',
    solidBorder: '#30363D',
    solidText: '#E6EDF3',
    subtleBg: 'rgba(139,148,158,0.10)',
    border: '#30363D',
    text: '#C9D1D9',
  },
  primary: {
    solidBg: '#6366F1',
    solidBorder: '#6366F1',
    solidText: '#FFFFFF',
    subtleBg: 'rgba(99,102,241,0.10)',
    border: '#6366F1',
    text: '#8B8DFF',
  },
  success: {
    solidBg: '#238636',
    solidBorder: '#238636',
    solidText: '#FFFFFF',
    subtleBg: 'rgba(63,185,80,0.10)',
    border: '#3FB950',
    text: '#56D364',
  },
  warning: {
    solidBg: '#9E6A03',
    solidBorder: '#D29922',
    solidText: '#FFFFFF',
    subtleBg: 'rgba(210,153,34,0.12)',
    border: '#D29922',
    text: '#E3B341',
  },
  info: {
    solidBg: '#1F6FEB',
    solidBorder: '#388BFD',
    solidText: '#FFFFFF',
    subtleBg: 'rgba(88,166,255,0.11)',
    border: '#58A6FF',
    text: '#79C0FF',
  },
  danger: {
    solidBg: '#DA3633',
    solidBorder: '#F85149',
    solidText: '#FFFFFF',
    subtleBg: 'rgba(248,81,73,0.10)',
    border: '#F85149',
    text: '#FF7B72',
  },
  destructive: {
    solidBg: '#DA3633',
    solidBorder: '#F85149',
    solidText: '#FFFFFF',
    subtleBg: 'rgba(248,81,73,0.10)',
    border: '#F85149',
    text: '#FF7B72',
  },
};

const normalizeVariant = (variant: any, appearance: any): string => {
  const raw = String(appearance || variant || 'default').trim().toLowerCase();
  if (raw === 'outline' || raw === 'outlined') return 'default';
  if (raw === 'error') return 'danger';
  return raw || 'default';
};

const normalizeMode = (mode: any, variant: any): 'solid' | 'outline' | 'ghost' | 'link' => {
  const raw = String(mode || '').trim().toLowerCase();
  if (raw === 'link') return 'link';
  if (raw === 'ghost') return 'ghost';
  if (raw === 'outline' || raw === 'outlined' || variant === 'outline' || variant === 'outlined') return 'outline';
  return 'solid';
};

const buttonSize = (btnsize: any, shape: any) => {
  const normalizedSize = String(btnsize || 'default').trim().toLowerCase();
  const normalizedShape = String(shape || '').trim().toLowerCase();
  const iconOnly = normalizedShape === 'round' || normalizedShape === 'icon';

  if (iconOnly) {
    return {
      button: { width: 42, height: 42, paddingHorizontal: 0, paddingVertical: 0, borderRadius: normalizedShape === 'round' ? 21 : 8 },
      text: { fontSize: 14 },
      icon: 19,
    };
  }
  if (normalizedSize === 'sm' || normalizedSize === 'small') {
    return {
      button: { minHeight: 34, paddingHorizontal: 12, paddingVertical: 7 },
      text: { fontSize: 13 },
      icon: 16,
    };
  }
  if (normalizedSize === 'lg' || normalizedSize === 'large') {
    return {
      button: { minHeight: 46, paddingHorizontal: 20, paddingVertical: 12 },
      text: { fontSize: 15 },
      icon: 20,
    };
  }
  return {
    button: { minHeight: 40, paddingHorizontal: 16, paddingVertical: 10 },
    text: { fontSize: 14 },
    icon: 18,
  };
};

export const Button: React.FC<any> = ({
  label,
  text,
  onAction,
  action,
  params,
  style,
  variant = 'default',
  appearance,
  mode,
  btnsize,
  shape,
  icon,
  active,
  collect_input_ids,
  pendingActions,
  track_loading,
}) => {
  const labelText = getLiteral(label || text);
  const isActive = toBoolean(active);
  const actionName = typeof action === 'string' ? action : String(action?.name || '');
  const isLoading = isAnyTrackedActionPending(pendingActions, track_loading, actionName);
  const resolvedVariant = normalizeVariant(variant, appearance);
  const resolvedMode = normalizeMode(mode, variant);
  const tone = TONES[resolvedVariant] || TONES.default;
  const sizing = buttonSize(btnsize, shape);
  const actionContext = {
    ...(params && typeof params === 'object' ? params : {}),
    ...(Array.isArray(collect_input_ids) && collect_input_ids.length > 0
      ? { __client__: { collect_input_ids } }
      : {}),
  };

  const visual = (() => {
    if (resolvedMode === 'link') {
      return {
        backgroundColor: 'transparent',
        borderColor: 'transparent',
        borderWidth: 0,
        textColor: tone.text,
        iconColor: tone.text,
      };
    }
    if (resolvedMode === 'ghost') {
      return {
        backgroundColor: 'transparent',
        borderColor: tone.border,
        borderWidth: 1,
        textColor: tone.text,
        iconColor: tone.text,
      };
    }
    if (resolvedMode === 'outline') {
      return {
        backgroundColor: tone.subtleBg,
        borderColor: tone.border,
        borderWidth: 1,
        textColor: tone.text,
        iconColor: tone.text,
      };
    }
    return {
      backgroundColor: tone.solidBg,
      borderColor: tone.solidBorder,
      borderWidth: 1,
      textColor: tone.solidText,
      iconColor: tone.solidText,
    };
  })();

  const disabled = isLoading;

  return (
    <TouchableOpacity
      style={[
        styles.base,
        sizing.button,
        {
          backgroundColor: visual.backgroundColor,
          borderColor: visual.borderColor,
          borderWidth: visual.borderWidth,
        },
        isActive && { borderColor: tone.border, borderWidth: 2 },
        disabled && styles.disabled,
        style,
      ]}
      onPress={() => emitActionSpec(action, onAction, actionContext)}
      disabled={disabled}
      activeOpacity={0.72}
    >
      <View style={styles.content}>
        {isLoading ? (
          <ActivityIndicator size="small" color={visual.iconColor} style={labelText ? styles.icon : undefined} />
      ) : icon ? (
        <Icon name={icon} size={sizing.icon} color={visual.iconColor} style={labelText ? styles.icon : undefined} />
      ) : null}
        {labelText ? (
          <Text style={[styles.text, sizing.text, { color: visual.textColor }]} numberOfLines={1}>
            {labelText}
          </Text>
        ) : null}
      </View>
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  base: {
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'flex-start',
    maxWidth: '100%',
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    maxWidth: '100%',
  },
  text: {
    fontWeight: '700',
  },
  icon: {
    marginRight: 7,
  },
  disabled: {
    opacity: 0.62,
  },
});
