import React from 'react';
import {
  Image as RNImage,
  Pressable,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useAudioPlayer, useAudioPlayerStatus, type AudioSource } from 'expo-audio';
import { getLiteral, toBoolean } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';
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

const formatTime = (value: number): string => {
  if (!Number.isFinite(value) || value <= 0) return '0:00';
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
};

export const Audio: React.FC<any> = ({
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
  style,
  jwt,
  stateModel,
}) => {
  const [trackWidth, setTrackWidth] = React.useState(0);
  const rawSource = getLiteral(source ?? src ?? url, '').trim();
  const rawPoster = getLiteral(poster, '').trim();
  const label = getLiteral(title || 'Audio track');
  const moduleName = moduleNameFromState(stateModel);
  const resolvedSource = rawSource ? resolveMediaUrl(rawSource, moduleName) : '';
  const resolvedPoster = rawPoster ? resolveMediaUrl(rawPoster, moduleName) : '';
  const headers = authHeadersForMediaUrl(resolvedSource, jwt);
  const sourceObject = React.useMemo<AudioSource>(() => {
    if (!resolvedSource) return null;
    return {
      uri: resolvedSource,
      headers,
      name: label,
    };
  }, [headers, label, resolvedSource]);

  const player = useAudioPlayer(sourceObject, { updateInterval: 250 });
  const status = useAudioPlayerStatus(player);
  const parsedStyle = parseStyle(style);
  const resolvedWidth = toDimension(width);
  const duration = Number(status?.duration || player.duration || 0);
  const currentTime = Math.min(Number(status?.currentTime || player.currentTime || 0), duration || Number.MAX_SAFE_INTEGER);
  const playing = Boolean(status?.playing ?? player.playing);
  const progress = duration > 0 ? Math.max(0, Math.min(1, currentTime / duration)) : 0;

  React.useEffect(() => {
    player.loop = toBoolean(loop);
    player.muted = toBoolean(muted);
    if (toBoolean(autoplay) && resolvedSource) player.play();
  }, [autoplay, loop, muted, player, resolvedSource]);

  const togglePlayback = React.useCallback(() => {
    if (!resolvedSource) return;
    if (playing) {
      player.pause();
      return;
    }
    player.play();
  }, [player, playing, resolvedSource]);

  const seekFromPress = React.useCallback((event: any) => {
    if (!duration) return;
    const locationX = Number(event?.nativeEvent?.locationX || 0);
    if (!trackWidth || !Number.isFinite(locationX)) return;
    player.seekTo(Math.max(0, Math.min(duration, (locationX / trackWidth) * duration))).catch(() => undefined);
  }, [duration, player, trackWidth]);

  const containerStyle: any = {
    ...parsedStyle,
    width: resolvedWidth ?? parsedStyle?.width ?? '100%',
    maxWidth: '100%',
  };

  return (
    <View style={[styles.container, containerStyle]}>
      <View style={styles.row}>
        <View style={styles.artwork}>
          {resolvedPoster ? (
            <RNImage
              source={{ uri: resolvedPoster }}
              style={styles.artworkImage}
              resizeMode="cover"
            />
          ) : (
            <Icon name="ri-music-2-line" size={24} color="#8B949E" />
          )}
        </View>

        <View style={styles.info}>
          <Text style={styles.title} numberOfLines={1}>
            {label}
          </Text>

          {toBoolean(controls) ? (
            <View style={styles.controls}>
              <TouchableOpacity
                style={[styles.playBtn, !resolvedSource && styles.disabledBtn]}
                activeOpacity={0.7}
                disabled={!resolvedSource}
                onPress={togglePlayback}
              >
                <Icon name={playing ? 'ri-pause-fill' : 'ri-play-fill'} size={20} color="#FFFFFF" />
              </TouchableOpacity>

              <Pressable
                style={styles.track}
                onLayout={(event) => setTrackWidth(event.nativeEvent.layout.width)}
                onPress={seekFromPress}
              >
                <View style={[styles.progress, { width: `${progress * 100}%` }]} />
              </Pressable>

              <Text style={styles.time} numberOfLines={1}>
                {formatTime(currentTime)} / {formatTime(duration)}
              </Text>
            </View>
          ) : null}
        </View>
      </View>

      {!resolvedSource ? (
        <Text style={styles.missing}>Missing audio source</Text>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    alignSelf: 'stretch',
    flexShrink: 1,
    minWidth: 0,
    padding: 12,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    marginVertical: 4,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    minWidth: 0,
  },
  artwork: {
    width: 48,
    height: 48,
    borderRadius: 8,
    backgroundColor: '#0D1117',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    flexShrink: 0,
  },
  artworkImage: {
    width: '100%',
    height: '100%',
  },
  info: {
    flex: 1,
    minWidth: 0,
  },
  title: {
    fontSize: 15,
    fontWeight: '600',
    color: '#E6EDF3',
    marginBottom: 8,
  },
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minWidth: 0,
  },
  playBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: '#3B82F6',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  disabledBtn: {
    opacity: 0.45,
  },
  track: {
    flex: 1,
    minWidth: 44,
    height: 6,
    backgroundColor: '#30363D',
    borderRadius: 3,
    overflow: 'hidden',
  },
  progress: {
    height: '100%',
    backgroundColor: '#3B82F6',
    borderRadius: 3,
  },
  time: {
    fontSize: 11,
    color: '#8B949E',
    minWidth: 72,
    textAlign: 'right',
    flexShrink: 0,
  },
  missing: {
    fontSize: 12,
    color: '#8B949E',
    marginTop: 8,
    textAlign: 'center',
  },
});
