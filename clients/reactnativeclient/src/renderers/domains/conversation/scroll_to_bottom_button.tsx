import React from 'react';
import { Text, TouchableOpacity, StyleSheet } from 'react-native';
import { emitActionSpec, getLiteral } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

export const ScrollToBottomButton: React.FC<any> = ({ label, action, onAction, style }) => (
  <TouchableOpacity style={[styles.button, style]} onPress={() => emitActionSpec(action, onAction, {})} activeOpacity={0.75}>
    <Icon name="ri-arrow-down-line" size={16} color="#E6EDF3" />
    <Text style={styles.text}>{getLiteral(label || 'Bottom')}</Text>
  </TouchableOpacity>
);

const styles = StyleSheet.create({
  button: {
    alignSelf: 'center',
    minHeight: 36,
    borderRadius: 999,
    paddingHorizontal: 12,
    backgroundColor: '#238636',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginVertical: 6,
  },
  text: { color: '#E6EDF3', fontSize: 13, fontWeight: '700' },
});
