import React from 'react';
import { View, Text, TouchableOpacity, Image, StyleSheet, ScrollView } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { getLiteral, emitActionSpec } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

export const Attachment: React.FC<any> = ({
  id,
  label,
  accept,
  multiple,
  value = [],
  action,
  onAction,
  setInput,
  style,
  error,
}) => {
  const [files, setFiles] = React.useState<any[]>(Array.isArray(value) ? value : []);

  React.useEffect(() => {
    setFiles(Array.isArray(value) ? value : []);
  }, [value]);

  const publishFiles = (nextFiles: any[]) => {
    setFiles(nextFiles);
    setInput?.(id, nextFiles);

    if (action && onAction) {
      emitActionSpec(action, onAction, { [id]: nextFiles, value: nextFiles });
    }
  };

  const removeFile = (index: number) => {
    publishFiles(files.filter((_, i) => i !== index));
  };

  const handleUploadClick = async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: getLiteral(accept || '*/*') || '*/*',
      multiple: Boolean(multiple),
      copyToCacheDirectory: true,
    });
    if (result.canceled) return;
    const picked = result.assets.map((asset) => ({
      name: asset.name,
      uri: asset.uri,
      url: asset.uri,
      type: asset.mimeType || '',
      mimeType: asset.mimeType || '',
      size: asset.size,
      lastModified: asset.lastModified,
    }));
    publishFiles(multiple ? [...files, ...picked] : picked.slice(0, 1));
  };

  return (
    <View style={[styles.container, style]}>
      {getLiteral(label) ? (
        <Text style={[styles.label, error && styles.labelError]}>
          {getLiteral(label)}
        </Text>
      ) : null}
      
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filesRow}>
        {files.map((file, i) => {
          if (!file) return null;
          const fileName = file.name || 'Unknown';
          const fileUrl = file.url;
          const isImage = file.type?.startsWith('image/') || /\.(png|jpe?g|gif|webp)$/i.test(fileName);
          
          return (
            <View key={`${id}_file_${i}`} style={[styles.fileCard, error && styles.fileCardError]}>
              {isImage && fileUrl ? (
                <Image source={{ uri: fileUrl }} style={styles.previewImage} />
              ) : (
                <View style={styles.placeholderIcon}>
                  <Icon name="ri-file-text-line" size={32} color="#8B949E" />
                  <Text style={styles.fileName} numberOfLines={1}>{fileName}</Text>
                </View>
              )}
              <TouchableOpacity 
                style={styles.removeBtn} 
                onPress={() => removeFile(i)}
                activeOpacity={0.7}
              >
                <Icon name="ri-close-line" size={14} color="#fff" />
              </TouchableOpacity>
            </View>
          );
        })}
        
        {(multiple || files.length === 0) && (
          <TouchableOpacity 
            style={[styles.uploadBtn, error && styles.uploadBtnError]} 
            onPress={handleUploadClick}
            activeOpacity={0.7}
          >
            <Icon name="ri-upload-2-line" size={24} color="#FFFFFF" />
            <Text style={styles.uploadText}>Upload</Text>
          </TouchableOpacity>
        )}
      </ScrollView>

      {error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginVertical: 6,
  },
  label: {
    fontSize: 13,
    fontWeight: '500',
    color: '#8B949E',
    marginBottom: 8,
  },
  labelError: {
    color: '#FF7B72',
  },
  filesRow: {
    gap: 10,
    paddingRight: 20,
  },
  fileCard: {
    width: 90,
    height: 90,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#161B22',
    overflow: 'hidden',
    position: 'relative',
    justifyContent: 'center',
    alignItems: 'center',
  },
  fileCardError: {
    borderColor: '#F85149',
  },
  previewImage: {
    width: '100%',
    height: '100%',
    resizeMode: 'cover',
  },
  placeholderIcon: {
    alignItems: 'center',
    padding: 4,
  },
  fileName: {
    fontSize: 10,
    color: '#C9D1D9',
    marginTop: 4,
    textAlign: 'center',
  },
  removeBtn: {
    position: 'absolute',
    top: 4,
    right: 4,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: 'rgba(13,17,23,0.82)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  uploadBtn: {
    width: 90,
    height: 90,
    borderRadius: 8,
    backgroundColor: '#1F6FEB',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
  uploadBtnError: {
    backgroundColor: '#F85149',
  },
  uploadText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '600',
  },
  errorText: {
    fontSize: 12,
    color: '#FF7B72',
    marginTop: 4,
  },
});
