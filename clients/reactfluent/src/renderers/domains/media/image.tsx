import React, { useCallback, useEffect, useMemo, useState } from 'react';
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

const withResizeParams = (url: string, width?: number, height?: number): string => {
  if (!url || !url.includes('/media/proxy')) return url;

  try {
    const parsed = new URL(url, window.location.origin);
    if (width && width > 0) parsed.searchParams.set('width', String(Math.round(width)));
    if (height && height > 0) parsed.searchParams.set('height', String(Math.round(height)));
    return parsed.toString();
  } catch {
    const params = new URLSearchParams();
    if (width && width > 0) params.set('width', String(Math.round(width)));
    if (height && height > 0) params.set('height', String(Math.round(height)));
    const suffix = params.toString();
    if (!suffix) return url;
    return `${url}${url.includes('?') ? '&' : '?'}${suffix}`;
  }
};

export const Image: React.FC<any> = ({ id, alt, url, width, height, fit, style, className, sendAction }) => {
  const messages = useI18n();
  const raw = getLiteral(url, '');
  const altText = getLiteral(alt, '');
  const iconClass = resolveIconClass(raw);
  const isIconImage = typeof raw === 'string' && /^(ric\.|ri\.|ri-)/.test(raw.trim());
  const fitMode = String(getLiteral(fit, '') || '').trim().toLowerCase();
  const fitContainer = fitMode === 'container';
  const objectFit = fitMode === 'cover' ? 'cover' : fitMode === 'fill' ? 'fill' : 'contain';
  const [retryKey, setRetryKey] = useState(0);
  const [blocked, setBlocked] = useState(false);
  const resolvedWidth = toDimension(width);
  const resolvedHeight = toDimension(height);
  const resolvedSrc = useResolvedMediaUrl(raw);
  const src = useMemo(
    () => withResizeParams(resolvedSrc, resolvedWidth, resolvedHeight),
    [resolvedSrc, resolvedWidth, resolvedHeight],
  );
  const isLogo = id === 'logo_img';
  const isAuthLogo =
    /(?:^|\/)logo(?:_full)?\.svg(?:[?#].*)?$/i.test(String(raw || '').trim()) ||
    String(altText || '').trim().toLowerCase() === 'logo';
  const shouldTintLogo = isLogo || isAuthLogo;

  useEffect(() => {
    setBlocked(false);
  }, [src]);

  const handleError = useCallback(() => {
    if (src && src.includes('/media/proxy')) {
      setBlocked(true);
      sendAction?.('get_notifications_count', {});
    }
  }, [src, sendAction]);

  const handleReload = useCallback(() => {
    setBlocked(false);
    setRetryKey((k) => k + 1);
  }, []);

  const containerStyle: React.CSSProperties = {
    ...parseStyle(style),
    width: fitContainer ? '100%' : (resolvedWidth ?? (shouldTintLogo ? 45 : undefined)),
    height: resolvedHeight ?? (shouldTintLogo ? 45 : undefined),
  };

  const fallbackHeight = resolvedHeight ?? 160;

  const placeholderContent = (
    <div
      className='d-flex w-100 flex-column align-items-center justify-content-center gap-2 bg-light text-muted'
      style={{ height: fallbackHeight }}
    >
      <span className='small'>{messages.blockedUrl}</span>
      <button
        type='button'
        onClick={handleReload}
        className='btn btn-outline-secondary btn-xs'
      >
        {messages.reload}
      </button>
    </div>
  );

  return (
    <div
      className={`d-flex align-items-center justify-content-center overflow-hidden ${shouldTintLogo ? 'flex-shrink-0' : 'rounded'} ${(!resolvedWidth && !shouldTintLogo) ? 'w-100' : ''} ${(!resolvedHeight && !shouldTintLogo) ? 'min-vh-0' : ''} ${className || ''}`}
      style={containerStyle}
    >
      {blocked ? (
        placeholderContent
      ) : isIconImage && iconClass ? (
        <div className='d-flex h-100 w-100 align-items-center justify-content-center text-muted'>
          <i
            className={`${iconClass} lh-1`}
            aria-hidden='true'
            style={{ fontSize: Math.min(resolvedWidth ?? 32, resolvedHeight ?? 32, 48) }}
          />
        </div>
      ) : src ? (
        <img
          key={`${src}-${retryKey}`}
          src={src}
          className={`ds-image-img h-100 w-100 ${shouldTintLogo ? 'webclient-logo-img' : ''}`}
          style={{ objectFit }}
          alt={altText}
          onError={handleError}
        />
      ) : (
        <div
          className='d-flex w-100 align-items-center justify-content-center bg-light text-muted'
          style={{ height: fallbackHeight }}
        >
          {messages.noImage}
        </div>
      )}
    </div>
  );
};
