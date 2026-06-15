import React, { useCallback, useEffect, useState } from 'react';
import { parseStyle } from '@/utils/style';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { getLiteral, toBoolean } from '@/renderers/shared';
import { useI18n } from '@/utils/i18n';
import { DefaultButton } from '@fluentui/react';

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

  const parsedWidth = Number(width);
  const parsedHeight = Number(height);
  const safeWidth = Number.isFinite(parsedWidth) && parsedWidth > 0 ? parsedWidth : undefined;
  const aspectRatio = Number.isFinite(parsedWidth) && parsedWidth > 0 && Number.isFinite(parsedHeight) && parsedHeight > 0
    ? `${parsedWidth} / ${parsedHeight}`
    : '16 / 9';

  return (
    <div className="a2ui-video" style={{ ...parseStyle(style), width: safeWidth }}>
      {title ? (
        <div className="a2ui-video-title">{getLiteral(title)}</div>
      ) : null}

      {blocked ? (
        <div
          className="a2ui-video-frame a2ui-video-blocked"
          style={{ aspectRatio }}
        >
          <span>{messages.blockedUrl}</span>
          <DefaultButton
            className="a2ui-button a2ui-button-small"
            onClick={handleReload}
          >
            {messages.reload}
          </DefaultButton>
        </div>
      ) : resolvedSource ? (
        <div className="a2ui-video-frame" style={{ aspectRatio }}>
          <video
            key={`${resolvedSource}-${retryKey}`}
            src={resolvedSource}
            poster={resolvedPoster || undefined}
            autoPlay={toBoolean(autoplay)}
            muted={toBoolean(muted)}
            loop={toBoolean(loop)}
            controls={toBoolean(controls)}
            className="a2ui-video-player"
            onError={handleError}
          />
        </div>
      ) : (
        <div className="a2ui-video-missing">{messages.missingVideoSource}</div>
      )}
    </div>
  );
};
