import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, LayoutAnimation } from 'react-native';
import { getLiteral, toBoolean } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

export const Collapsible: React.FC<any> = ({ title, content, open = false, style }) => {
  const [isOpen, setIsOpen] = React.useState(toBoolean(open));

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setIsOpen(!isOpen);
  };

  return (
    <View style={[styles.container, style]}>
      <TouchableOpacity 
        style={styles.trigger} 
        onPress={toggle}
        activeOpacity={0.7}
      >
        <Text style={styles.title}>{getLiteral(title)}</Text>
        <Icon 
          name={isOpen ? "ri-arrow-up-s-line" : "ri-arrow-down-s-line"} 
          size={20} 
          color="#6b7280" 
        />
      </TouchableOpacity>
      {isOpen && (
        <View style={styles.content}>
          <Text style={styles.contentText}>{getLiteral(content)}</Text>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 8,
    backgroundColor: '#fff',
    marginVertical: 4,
    overflow: 'hidden',
  },
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 12,
    backgroundColor: '#f9fafb',
  },
  title: {
    fontSize: 15,
    fontWeight: '600',
    color: '#374151',
  },
  content: {
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
  },
  contentText: {
    fontSize: 14,
    color: '#6b7280',
    lineHeight: 20,
  },
});
