import React, { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { parseStyle } from '@/utils/style';
import { resolveIconClass } from '@/utils/icons';
import { getLiteral } from '@/renderers/shared';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { useI18n } from '@/utils/i18n';

const toDimension = (value: any): number | undefined => {
  const raw = getLiteral(value, '').trim();
  if (!raw) return undefined;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) return undefined;
  return parsed;
};

export const Image: React.FC<any> = ({ id, alt, url, width, height, fit, style, sendAction }) => {
  const messages = useI18n();
  const raw = getLiteral(url, '');
  const altText = getLiteral(alt, '');
  const iconClass = resolveIconClass(raw);
  const isIconImage = typeof raw === 'string' && /^(ric\.|ri\.|ri-)/.test(raw.trim());
  const fitMode = String(getLiteral(fit, '') || '').trim().toLowerCase();
  const fitContainer = fitMode === 'container';
  const [retryKey, setRetryKey] = useState(0);
  const [blocked, setBlocked] = useState(false);
  const src = useResolvedMediaUrl(raw);
  const isLogo = id === 'logo_img';
  const isFullLogo = /(?:^|\/)logo_full\.svg(?:[?#].*)?$/i.test(String(raw || "").trim());
  const isAuthLogo =
    isFullLogo ||
    /(?:^|\/)logo(?:_full)?\.svg(?:[?#].*)?$/i.test(String(raw || '').trim()) ||
    String(altText || '').trim().toLowerCase() === 'logo';
  const shouldTintLogo = isLogo || isAuthLogo;

  // When src changes (e.g. approval revision bumped), clear blocked state so image retries.
  useEffect(() => {
    setBlocked(false);
  }, [src]);

  const handleError = useCallback(() => {
    if (src && src.includes('/media/proxy')) {
      setBlocked(true);
      // Trigger notification refresh to update the badge immediately
      sendAction?.('get_notifications_count', {});
    }
  }, [src, sendAction]);

  const handleReload = useCallback(() => {
    setBlocked(false);
    setRetryKey((k) => k + 1);
  }, []);

  const resolvedWidth = toDimension(width);
  const resolvedHeight = toDimension(height);

  const containerStyle: React.CSSProperties = {
    ...parseStyle(style),
    width: fitContainer ? '100%' : (resolvedWidth ?? (shouldTintLogo ? 45 : undefined)),
    height: resolvedHeight ?? (shouldTintLogo ? 45 : undefined),
  };

  const fallbackHeight = resolvedHeight ?? 160;

  const placeholderContent = (
    <div
      className='flex w-full flex-col items-center justify-center gap-2 bg-muted text-muted-foreground'
      style={{ height: fallbackHeight }}
    >
      <span className='text-sm'>{messages.blockedUrl}</span>
      <button
        type='button'
        onClick={handleReload}
        className='rounded border border-border bg-background px-3 py-1 text-xs hover:bg-muted'
      >
        {messages.reload}
      </button>
    </div>
  );

  return (
    <div
      className={cn(
        'flex items-center justify-center overflow-hidden',
        shouldTintLogo ? 'shrink-0' : 'rounded-md',
        !resolvedWidth && !shouldTintLogo ? 'w-full' : undefined,
        !resolvedHeight && !shouldTintLogo ? 'min-h-0' : undefined,
      )}
      style={containerStyle}
    >
      {blocked ? (
        placeholderContent
      ) : isIconImage && iconClass ? (
        <div className='flex h-full w-full items-center justify-center text-muted-foreground'>
          <i
            className={cn(iconClass, 'leading-none')}
            aria-hidden='true'
            style={{ fontSize: Math.min(resolvedWidth ?? 32, resolvedHeight ?? 32, 48) }}
          />
        </div>
      ) : src ? (
        <img
          key={`${src}-${retryKey}`}
          src={src}
          className={cn('h-full w-full object-contain', shouldTintLogo && 'webclient-logo-img', isFullLogo && 'webclient-logo-full-img')}
          alt={altText}
          onError={handleError}
        />
      ) : (
        <div
          className='flex w-full items-center justify-center bg-muted text-muted-foreground'
          style={{ height: fallbackHeight }}
        >
          {messages.noImage}
        </div>
      )}
    </div>
  );
};
