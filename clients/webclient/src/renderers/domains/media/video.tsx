import React, { useCallback, useEffect, useState } from 'react';
import { parseStyle } from '@/utils/style';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { getLiteral, toBoolean } from '@/renderers/shared';
import { useI18n } from '@/utils/i18n';

export const Video: React.FC<any> = ({
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
  const [retryKey, setRetryKey] = useState(0);
  const [blocked, setBlocked] = useState(false);
  const resolvedSource = useResolvedMediaUrl(getLiteral(source));
  const resolvedPoster = useResolvedMediaUrl(getLiteral(poster));

  useEffect(() => {
    setBlocked(false);
  }, [resolvedSource]);

  const handleError = useCallback(() => {
    if (resolvedSource && resolvedSource.includes('/media/proxy')) {
      setBlocked(true);
      // Trigger notification refresh to update the badge immediately
      sendAction?.('get_notifications_count', {});
    }
  }, [resolvedSource, sendAction]);

  const handleReload = useCallback(() => {
    setBlocked(false);
    setRetryKey((k) => k + 1);
  }, []);

  const fallbackHeight = height || 200;

  return (
    <div style={{ ...parseStyle(style), width: width || undefined }}>
      {title ? (
        <div className="mb-2 text-sm font-semibold">{getLiteral(title)}</div>
      ) : null}

      {blocked ? (
        <div
          className="flex w-full flex-col items-center justify-center gap-2 rounded-md bg-muted text-muted-foreground"
          style={{ height: fallbackHeight }}
        >
          <span className="text-sm">{messages.blockedUrl}</span>
          <button
            type="button"
            onClick={handleReload}
            className="rounded border border-border bg-background px-3 py-1 text-xs hover:bg-muted"
          >
            {messages.reload}
          </button>
        </div>
      ) : resolvedSource ? (
        <video
          key={`${resolvedSource}-${retryKey}`}
          src={resolvedSource}
          poster={resolvedPoster || undefined}
          autoPlay={toBoolean(autoplay)}
          muted={toBoolean(muted)}
          loop={toBoolean(loop)}
          controls={toBoolean(controls)}
          className="block w-full rounded-md bg-[var(--media-video-bg)]"
          style={{ height: height || undefined }}
          onError={handleError}
        />
      ) : (
        <div className="px-2 py-6 text-sm text-muted-foreground">{messages.missingVideoSource}</div>
      )}
    </div>
  );
};
