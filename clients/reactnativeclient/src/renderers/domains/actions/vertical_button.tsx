import React from 'react';
import { TouchableOpacity, StyleSheet, View } from 'react-native';
import { getLiteral, toBoolean, emitActionSpec } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

export const VerticalButton: React.FC<any> = ({
  label,
  action,
  params,
  onAction,
  icon,
  style,
  active,
  collect_input_ids,
  pendingActions,
}) => {
  const isActive = toBoolean(active);
  const actionName = typeof action === 'string' ? action : String(action?.name || '');
  const disabled = Boolean(actionName && pendingActions?.[actionName]);

  return (
    <TouchableOpacity
      style={[
        styles.btn,
        isActive ? styles.btnActive : styles.btnIdle,
        style
      ]}
      onPress={() => emitActionSpec(action, onAction, {
        ...(params && typeof params === 'object' ? params : {}),
        ...(Array.isArray(collect_input_ids) && collect_input_ids.length > 0
          ? { __client__: { collect_input_ids } }
          : {}),
      })}
      disabled={disabled}
      activeOpacity={0.7}
    >
      <Icon 
        name={icon} 
        size={24} 
        color={isActive ? '#3b82f6' : '#6b7280'} 
      />
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  btn: {
    width: 48,
    height: 48,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: 4,
  },
  btnIdle: {
    backgroundColor: 'transparent',
  },
  btnActive: {
    backgroundColor: '#eff6ff',
    borderWidth: 1,
    borderColor: '#3b82f6',
  },
});
