import React from 'react';
import { View, StyleSheet } from 'react-native';

export const Thread: React.FC<any> = ({ ExplicitList, style }) => (
  <View style={[styles.thread, style]}>
    {ExplicitList}
  </View>
);

const styles = StyleSheet.create({
  thread: { flex: 1, width: '100%', minHeight: 280 },
});
