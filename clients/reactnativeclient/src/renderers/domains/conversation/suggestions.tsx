import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import { getLiteral, emitActionSpec } from '../../shared';

export const Suggestions: React.FC<any> = ({ suggestions = [], action, onAction, style }) => (
  <View style={[styles.container, style]}>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
      {suggestions.map((entry: any, index: number) => (
        <TouchableOpacity
          key={`suggestion_${index}`}
          style={styles.suggestion}
          onPress={() => {
            const actionName = typeof action === 'string' ? action : action?.name;
            if (!actionName || !onAction) return;
            onAction(actionName, {
              ...(action?.context || {}),
              prompt: entry?.prompt,
              label: entry?.label,
              suggestion: entry,
            });
          }}
          activeOpacity={0.7}
        >
          <Text style={styles.text}>{getLiteral(entry?.label || entry?.prompt)}</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  </View>
);

const styles = StyleSheet.create({
  container: {
    marginVertical: 8,
  },
  scrollContent: {
    paddingHorizontal: 12,
    gap: 8,
  },
  suggestion: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#eff6ff',
    borderWidth: 1,
    borderColor: '#bfdbfe',
  },
  text: {
    fontSize: 13,
    color: '#1d4ed8',
    fontWeight: '500',
  },
});
