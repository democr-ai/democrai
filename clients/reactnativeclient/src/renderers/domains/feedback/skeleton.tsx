import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated } from 'react-native';

export const Skeleton: React.FC<any> = ({ lines = 3, widths = [], avatar = false, style }) => {
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: 0.7,
          duration: 1000,
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 0.3,
          duration: 1000,
          useNativeDriver: true,
        }),
      ])
    ).start();
  }, [opacity]);

  return (
    <View style={[styles.card, style]}>
      {avatar ? (
        <Animated.View style={[styles.avatar, { opacity }]} />
      ) : null}
      <View style={styles.lines}>
        {Array.from({ length: Number(lines) || 3 }).map((_, index) => (
          <Animated.View
            key={`skeleton_${index}`}
            style={[
              styles.line,
              { opacity, width: `${widths[index] || 100}%` }
            ]}
          />
        ))}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e5e7eb',
    marginVertical: 4,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#e5e7eb',
    marginBottom: 12,
  },
  lines: {
    gap: 8,
  },
  line: {
    height: 12,
    backgroundColor: '#e5e7eb',
    borderRadius: 6,
  },
});
