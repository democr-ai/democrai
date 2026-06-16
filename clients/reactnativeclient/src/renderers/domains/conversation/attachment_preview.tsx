import React from 'react';
import { View, Text, Image as RNImage, TouchableOpacity, Linking, StyleSheet } from 'react-native';
import { getLiteral } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

export const AttachmentPreview: React.FC<any> = ({
  name,
  mime_type,
  storage_path,
  file_id,
  url,
  height,
  style,
}) => {
  const mime = String(mime_type || '').trim().toLowerCase();
  const src = String(getLiteral(url) || getLiteral(storage_path) || '').trim();
  const previewHeight = Math.max(180, Number(height || 260));

  return (
    <View style={[styles.card, style]}>
      <View style={styles.header}>
        <Icon name={mime.startsWith('image/') ? 'ri-image-line' : mime === 'application/pdf' ? 'ri-file-pdf-2-line' : 'ri-file-line'} size={18} color="#8B949E" />
        <View style={styles.meta}>
          <Text style={styles.name} numberOfLines={1}>{String(name || 'Attachment')}</Text>
          <Text style={styles.sub} numberOfLines={1}>{mime || 'unknown'} {file_id ? `· ${file_id}` : ''}</Text>
        </View>
        {src ? (
          <TouchableOpacity style={styles.openButton} onPress={() => Linking.openURL(src)}>
            <Icon name="ri-external-link-line" size={16} color="#58A6FF" />
          </TouchableOpacity>
        ) : null}
      </View>
      {src && mime.startsWith('image/') ? (
        <RNImage source={{ uri: src }} style={[styles.image, { height: previewHeight }]} resizeMode="contain" />
      ) : (
        <Text style={styles.note}>{src ? 'Preview non disponibile in mobile, puoi aprire il file.' : 'Sorgente preview non disponibile.'}</Text>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  card: { width: '100%', borderWidth: 1, borderColor: '#30363D', borderRadius: 8, backgroundColor: '#161B22', padding: 10, marginVertical: 6 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  meta: { flex: 1 },
  name: { color: '#E6EDF3', fontSize: 13, fontWeight: '600' },
  sub: { color: '#8B949E', fontSize: 11, marginTop: 2 },
  openButton: { width: 32, height: 32, borderRadius: 7, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0D1117' },
  image: { width: '100%', marginTop: 10, borderRadius: 6, backgroundColor: '#0D1117' },
  note: { color: '#6E7681', fontSize: 13, marginTop: 10 },
});
