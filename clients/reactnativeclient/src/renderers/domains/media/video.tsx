import React from 'react';
import {
  Image as RNImage,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { VideoView, useVideoPlayer, type VideoContentFit, type VideoSource } from 'expo-video';
import { getLiteral, toBoolean } from '../../shared';
import { parseStyle } from '../../../utils/style';
import { authHeadersForMediaUrl, resolveMediaUrl } from '../../../utils/media';

const toDimension = (value: any): number | string | undefined => {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) return value;
  const raw = getLiteral(value, '').trim();
  if (!raw) return undefined;
  if (raw.endsWith('%')) return raw;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
};

const moduleNameFromState = (stateModel: any): string => {
  const rawPath = String(stateModel?.current_path || stateModel?.currentPath || '').trim();
  const firstSegment = rawPath.replace(/^\/+/, '').split('/').filter(Boolean)[0];
  return firstSegment || 'dashboard';
};

const fitFromProp = (fit: any): VideoContentFit => {
  const normalized = String(getLiteral(fit, '') || '').trim().toLowerCase();
  if (normalized === 'cover') return 'cover';
  if (normalized === 'fill' || normalized === 'stretch') return 'fill';
  return 'contain';
};

export const Video: React.FC<any> = ({
  source,
  src,
  url,
  title,
  autoplay = false,
  muted = false,
  loop = false,
  controls = true,
  poster,
  width,
  height,
  fit,
  style,
  jwt,
  stateModel,
}) => {
  const [retryKey, setRetryKey] = React.useState(0);
  const [firstFrameRendered, setFirstFrameRendered] = React.useState(false);
  const rawSource = getLiteral(source ?? src ?? url, '').trim();
  const rawPoster = getLiteral(poster, '').trim();
  const moduleName = moduleNameFromState(stateModel);
  const resolvedSource = rawSource ? resolveMediaUrl(rawSource, moduleName) : '';
  const resolvedPoster = rawPoster ? resolveMediaUrl(rawPoster, moduleName) : '';
  const headers = authHeadersForMediaUrl(resolvedSource, jwt);
  const contentFit = fitFromProp(fit);
  const resolvedWidth = toDimension(width);
  const resolvedHeight = toDimension(height);
  const parsedStyle = parseStyle(style);
  const label = getLiteral(title, '');

  const videoSource = React.useMemo<VideoSource>(() => {
    if (!resolvedSource) return null;
    return {
      uri: resolvedSource,
      headers,
      metadata: label ? { title: label } : undefined,
    };
  }, [headers, label, resolvedSource, retryKey]);

  const player = useVideoPlayer(videoSource, (instance) => {
    instance.loop = toBoolean(loop);
    instance.muted = toBoolean(muted);
    if (toBoolean(autoplay)) instance.play();
  });

  React.useEffect(() => {
    player.loop = toBoolean(loop);
    player.muted = toBoolean(muted);
    if (toBoolean(autoplay)) player.play();
  }, [autoplay, loop, muted, player]);

  React.useEffect(() => {
    setFirstFrameRendered(false);
  }, [resolvedSource, retryKey]);

  const containerStyle: any = {
    ...parsedStyle,
    width: resolvedWidth ?? parsedStyle?.width ?? '100%',
    maxWidth: '100%',
  };

  const frameStyle: any = {
    height: resolvedHeight ?? parsedStyle?.height,
    aspectRatio: resolvedHeight || parsedStyle?.height ? undefined : 16 / 9,
  };

  return (
    <View style={[styles.container, containerStyle]}>
      {label ? (
        <Text style={styles.title} numberOfLines={1}>
          {label}
        </Text>
      ) : null}

      <View style={[styles.frame, frameStyle]}>
        {resolvedSource ? (
          <>
            <VideoView
              key={`${resolvedSource}_${retryKey}`}
              player={player}
              style={styles.video}
              nativeControls={toBoolean(controls)}
              contentFit={contentFit}
              onFirstFrameRender={() => setFirstFrameRendered(true)}
            />
            {resolvedPoster && !firstFrameRendered ? (
              <RNImage
                source={{ uri: resolvedPoster }}
                style={styles.poster}
                resizeMode="cover"
              />
            ) : null}
          </>
        ) : (
          <View style={styles.fallback}>
            <Text style={styles.fallbackText}>Missing video source</Text>
          </View>
        )}
      </View>

      {resolvedSource ? (
        <TouchableOpacity
          style={styles.reloadButton}
          onPress={() => setRetryKey((key) => key + 1)}
          activeOpacity={0.75}
        >
          <Text style={styles.reloadText}>Reload</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    alignSelf: 'stretch',
    flexShrink: 1,
    minWidth: 0,
    marginVertical: 4,
    overflow: 'hidden',
  },
  title: {
    color: '#E6EDF3',
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  frame: {
    width: '100%',
    maxWidth: '100%',
    minHeight: 120,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: '#000000',
  },
  video: {
    width: '100%',
    height: '100%',
  },
  poster: {
    ...StyleSheet.absoluteFillObject,
    width: '100%',
    height: '100%',
  },
  fallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
  },
  fallbackText: {
    color: '#8B949E',
    fontSize: 13,
  },
  reloadButton: {
    alignSelf: 'flex-start',
    marginTop: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#161B22',
  },
  reloadText: {
    color: '#C9D1D9',
    fontSize: 12,
    fontWeight: '600',
  },
});
