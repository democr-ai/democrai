import React from 'react';
import { View, Text, TouchableOpacity, Linking, StyleSheet } from 'react-native';
import { getLiteral } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

export const PdfViewer: React.FC<any> = ({ url, src, title, style }) => {
  const href = String(getLiteral(url) || getLiteral(src) || '').trim();
  return (
    <View style={[styles.card, style]}>
      <Icon name="ri-file-pdf-2-line" size={28} color="#FF7B72" />
      <View style={styles.texts}>
        <Text style={styles.title}>{getLiteral(title || 'PDF')}</Text>
        <Text style={styles.note} numberOfLines={1}>{href || 'No URL'}</Text>
      </View>
      {href ? (
        <TouchableOpacity style={styles.button} onPress={() => Linking.openURL(href)}>
          <Icon name="ri-external-link-line" size={16} color="#58A6FF" />
        </TouchableOpacity>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  card: { width: '100%', borderWidth: 1, borderColor: '#30363D', borderRadius: 8, backgroundColor: '#161B22', padding: 12, flexDirection: 'row', alignItems: 'center', gap: 10, marginVertical: 6 },
  texts: { flex: 1 },
  title: { color: '#E6EDF3', fontSize: 14, fontWeight: '700' },
  note: { color: '#8B949E', fontSize: 12, marginTop: 2 },
  button: { width: 34, height: 34, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0D1117' },
});
