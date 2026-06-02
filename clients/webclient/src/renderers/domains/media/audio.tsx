import React from 'react';
import { parseStyle } from '@/utils/style';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { getLiteral, toBoolean } from '@/renderers/shared';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
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
        <div className="flex items-center gap-4 rounded-md border bg-muted p-4">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center bg-muted-foreground/10 text-xl text-muted-foreground">♪</div>
          <div className="flex flex-col gap-2">
            <span className="text-sm text-muted-foreground">{messages.blockedUrl}</span>
            <button
              type="button"
              onClick={handleReload}
              className="w-fit rounded border border-border bg-background px-3 py-1 text-xs hover:bg-muted"
            >
              {messages.reload}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ ...parseStyle(style), width: safeWidth }}>
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

      <div className="flex gap-4 p-1">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden border bg-muted">
          {resolvedPoster ? (
            <img src={resolvedPoster} alt={getLiteral(title || 'Audio artwork')} className="h-full w-full object-cover" />
          ) : (
            <span className="text-xl text-muted-foreground">♪</span>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{getLiteral(title || 'Audio track')}</div>

          {toBoolean(controls) ? (
            <div className="mt-3 flex items-center gap-3">
              <Button type="button" size="sm" onClick={() => { void togglePlayback(); }}>
                {playing ? 'Pause' : 'Play'}
              </Button>
              <Slider
                min={0}
                max={duration || 0}
                value={[Math.min(currentTime, duration || 0)]}
                onValueChange={(vals) => {
                  const next = Number(vals[0] || 0);
                  setCurrentTime(next);
                  if (audioRef.current) audioRef.current.currentTime = next;
                }}
              />
              <span className="text-xs text-muted-foreground">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
