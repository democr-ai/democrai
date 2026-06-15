import React from 'react';
import { parseStyle } from '@/utils/style';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { getLiteral, toBoolean } from '@/renderers/shared';
import { DefaultButton, IconButton } from '@fluentui/react';
import { useI18n } from '@/utils/i18n';

export const Audio: React.FC<any> = ({
  source,
  title,
  autoplay = false,
  muted = false,
  loop = false,
  controls = true,
  poster,
  width,
  height,
  style,
  stateModel,
  sendAction,
}) => {
  const messages = useI18n(stateModel);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = React.useState(false);
  const [currentTime, setCurrentTime] = React.useState(0);
  const [duration, setDuration] = React.useState(0);
  const [blocked, setBlocked] = React.useState(false);
  const [retryKey, setRetryKey] = React.useState(0);
  const resolvedSource = useResolvedMediaUrl(getLiteral(source));
  const resolvedPoster = useResolvedMediaUrl(getLiteral(poster));

  React.useEffect(() => {
    setBlocked(false);
  }, [resolvedSource]);
  const parsedWidth = Number(width);
  const safeWidth = Number.isFinite(parsedWidth) ? Math.max(parsedWidth, 320) : undefined;

  React.useEffect(() => {
    const node = audioRef.current;
    if (!node) return;
    node.muted = toBoolean(muted);
  }, [muted]);

  const togglePlayback = async () => {
    const node = audioRef.current;
    if (!node) return;
    if (node.paused) {
      await node.play();
      setPlaying(true);
      return;
    }
    node.pause();
    setPlaying(false);
  };

  const formatTime = (value: number) => {
    if (!Number.isFinite(value) || value <= 0) return '0:00';
    const minutes = Math.floor(value / 60);
    const seconds = Math.floor(value % 60);
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  };

  const handleAudioError = () => {
    if (resolvedSource && resolvedSource.includes('/media/proxy')) {
      setBlocked(true);
      // Trigger notification refresh to update the badge immediately
      sendAction?.('get_notifications_count', {});
    }
  };

  const handleReload = () => {
    setBlocked(false);
    setRetryKey((k) => k + 1);
  };

  if (blocked) {
    return (
      <div style={{ ...parseStyle(style), width: safeWidth }}>
        <div className="a2ui-audio-player a2ui-audio-blocked">
          <div className="a2ui-audio-art" aria-hidden="true">
            <i className="ri-music-2-line" />
          </div>
          <div className="a2ui-audio-main">
            <span className="a2ui-audio-meta">{messages.blockedUrl}</span>
            <DefaultButton
              className="a2ui-button a2ui-button-small"
              onClick={handleReload}
            >
              {messages.reload}
            </DefaultButton>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ ...parseStyle(style), width: safeWidth }} className="a2ui-audio-player">
      <audio
        key={`${resolvedSource}-${retryKey}`}
        ref={audioRef}
        src={resolvedSource}
        autoPlay={toBoolean(autoplay)}
        loop={toBoolean(loop)}
        muted={toBoolean(muted)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration || 0)}
        onTimeUpdate={() => setCurrentTime(audioRef.current?.currentTime || 0)}
        onError={handleAudioError}
      />

      <div className="a2ui-audio-layout">
        <div className="a2ui-audio-art">
          {resolvedPoster ? (
            <img src={resolvedPoster} alt={getLiteral(title || 'Audio artwork')} />
          ) : (
            <i className="ri-music-2-line" aria-hidden="true" />
          )}
        </div>

        <div className="a2ui-audio-main">
          <div className="a2ui-audio-title">{getLiteral(title || 'Audio track')}</div>

          {toBoolean(controls) ? (
            <div className="a2ui-audio-controls">
              <IconButton
                className="a2ui-audio-play"
                ariaLabel={playing ? 'Pause' : 'Play'}
                onClick={() => { void togglePlayback(); }}
                onRenderIcon={() => <i className={playing ? 'ri-pause-fill' : 'ri-play-fill'} aria-hidden="true" />}
              />
              <div className="a2ui-audio-timeline">
                <input
                  type="range"
                  className="a2ui-audio-range"
                  min={0}
                  max={duration || 0}
                  step="any"
                  value={currentTime}
                  style={{ '--a2ui-audio-progress': `${duration > 0 ? Math.max(0, Math.min(100, (currentTime / duration) * 100)) : 0}%` } as React.CSSProperties}
                  onChange={(e) => {
                    const next = Number(e.target.value);
                    setCurrentTime(next);
                    if (audioRef.current) audioRef.current.currentTime = next;
                  }}
                />
                <div className="a2ui-audio-times">
                  <span>{formatTime(currentTime)}</span>
                  <span>{formatTime(duration)}</span>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
