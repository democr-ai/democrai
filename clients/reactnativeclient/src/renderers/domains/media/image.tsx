import React from 'react';
import { View, Image as RNImage, StyleSheet, Text, TouchableOpacity, type ImageResizeMode, type ImageSourcePropType } from 'react-native';
import { SvgUri } from 'react-native-svg';
import { getLiteral } from '../../shared';
import { parseStyle } from '../../../utils/style';
import { authHeadersForMediaUrl, resolveMediaUrl } from '../../../utils/media';

const LOCAL_SVG_IMAGES: Record<string, ImageSourcePropType> = {
  'assets/logo.svg': require('../../../../assets/logo.svg'),
  'assets/logo_full.svg': require('../../../../assets/logo_full.svg'),
  'logo.svg': require('../../../../assets/logo.svg'),
  'logo_full.svg': require('../../../../assets/logo_full.svg'),
};

const toDimension = (value: any): number | undefined => {
  if (typeof value === 'number') return value;
  const raw = getLiteral(value, '').trim();
  if (!raw) return undefined;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) return undefined;
  return parsed;
};

const moduleNameFromState = (stateModel: any): string => {
  const rawPath = String(stateModel?.current_path || stateModel?.currentPath || '').trim();
  const firstSegment = rawPath.replace(/^\/+/, '').split('/').filter(Boolean)[0];
  return firstSegment || 'dashboard';
};

export const Image: React.FC<any> = ({ id, alt, url, width, height, style, fit, jwt, stateModel }) => {
  const [retryKey, setRetryKey] = React.useState(0);
  const [blocked, setBlocked] = React.useState(false);
  const raw = getLiteral(url, '').trim();
  const normalizedRaw = raw.replace(/^\/+/, '');
  const localSvgSource = LOCAL_SVG_IMAGES[normalizedRaw];
  const localSvgUri = localSvgSource ? RNImage.resolveAssetSource(localSvgSource)?.uri : '';
  const src = localSvgSource ? '' : resolveMediaUrl(raw, moduleNameFromState(stateModel));
  const headers = authHeadersForMediaUrl(src, jwt);
  const altText = getLiteral(alt, '');
  const fitMode = String(getLiteral(fit, '') || '').trim().toLowerCase();
  const resizeMode: ImageResizeMode =
    fitMode === 'cover'
      ? 'cover'
      : fitMode === 'fill' || fitMode === 'stretch'
        ? 'stretch'
        : 'contain';
  const isAuthLogo =
    id === 'logo_img' ||
    /(?:^|\/)logo(?:_full)?\.svg(?:[?#].*)?$/i.test(normalizedRaw) ||
    altText.trim().toLowerCase() === 'logo';

  const resolvedWidth = toDimension(width);
  const resolvedHeight = toDimension(height);

  const containerStyle: any = {
    ...parseStyle(style),
    width: fitMode === 'container' ? '100%' : (resolvedWidth ?? (isAuthLogo ? 45 : '100%')),
    height: resolvedHeight ?? (isAuthLogo ? 45 : 200),
  };

  React.useEffect(() => {
    setBlocked(false);
    setRetryKey(0);
  }, [src]);

  return (
    <View style={[styles.container, isAuthLogo && styles.logoContainer, containerStyle, !isAuthLogo && styles.rounded]}>
      {localSvgUri ? (
        <SvgUri
          uri={localSvgUri}
          width="100%"
          height="100%"
          accessibilityLabel={altText}
        />
      ) : src && !blocked ? (
        <RNImage
          key={`${src}_${retryKey}`}
          source={headers ? { uri: src, headers } : { uri: src }}
          style={styles.image}
          resizeMode={resizeMode}
          accessibilityLabel={altText}
          onError={(event) => {
            console.error('[Image] failed to load', {
              id,
              url: raw,
              resolvedUrl: src,
              error: event.nativeEvent?.error,
              hasJwt: Boolean(jwt),
            });
            setBlocked(true);
          }}
        />
      ) : (
        <View style={styles.fallback}>
          <Text style={styles.fallbackText}>{src ? 'Image unavailable' : 'No image'}</Text>
          {src ? (
            <TouchableOpacity
              style={styles.reloadButton}
              onPress={() => {
                setBlocked(false);
                setRetryKey((key) => key + 1);
              }}
              activeOpacity={0.75}
            >
              <Text style={styles.reloadText}>Reload</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
    backgroundColor: '#0D1117',
  },
  logoContainer: {
    backgroundColor: 'transparent',
  },
  image: {
    width: '100%',
    height: '100%',
  },
  rounded: {
    borderRadius: 8,
  },
  fallback: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 10,
    padding: 12,
  },
  fallbackText: {
    color: '#8B949E',
    fontSize: 14,
    textAlign: 'center',
  },
  reloadButton: {
    minHeight: 34,
    paddingHorizontal: 14,
    borderRadius: 7,
    borderWidth: 1,
    borderColor: '#30363D',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#161B22',
  },
  reloadText: {
    color: '#58A6FF',
    fontSize: 13,
    fontWeight: '600',
  },
});
