import React from 'react';
import { StyleSheet, View, Text } from 'react-native';
import MarkdownDisplay from 'react-native-markdown-display';
import { getLiteral } from '../../shared';

export const Markdown: React.FC<any> = ({ text, style }) => {
  const content = getLiteral(text);
  
  if (!content) return null;

  return (
    <View style={[styles.container, style]}>
      <MarkdownDisplay style={markdownStyles}>
        {content}
      </MarkdownDisplay>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    padding: 8,
  },
});

const markdownStyles = StyleSheet.create({
  body: {
    color: '#333',
    fontSize: 16,
    lineHeight: 24,
  },
  heading1: {
    fontSize: 28,
    fontWeight: 'bold',
    marginVertical: 12,
    color: '#000',
  },
  heading2: {
    fontSize: 22,
    fontWeight: 'bold',
    marginVertical: 10,
    color: '#000',
  },
  paragraph: {
    marginVertical: 8,
  },
  link: {
    color: '#007AFF',
    textDecorationLine: 'underline',
  },
});
