import React from 'react';
import { parseStyle } from '@/utils/style';
import { Button } from '@/design/system';
import { Image as MediaImage } from '@/renderers/domains/media/image';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { getLiteral } from '@/renderers/shared';

export const AttachmentPreview: React.FC<any> = ({
  id,
  name,
  mime,
  path,
  source_path,
  file_id,
  url,
  height,
  style,
}) => {
  const normalizedMime = String(mime || '').trim().toLowerCase();
  const rawSrc = String(
    getLiteral(url) || getLiteral(source_path) || getLiteral(path) || ''
  ).trim();
  const src = useResolvedMediaUrl(rawSrc);
  const h = Math.max(260, Number(height || 460));
  const [zoom, setZoom] = React.useState(1);
  const imageWrapRef = React.useRef<HTMLDivElement | null>(null);
  const [imageWrapWidth, setImageWrapWidth] = React.useState(0);
  const imageWidth = Math.max(260, Math.round((imageWrapWidth || 640) * zoom));
  const imageHeight = Math.max(220, Math.round(h * zoom));

  React.useEffect(() => {
    const node = imageWrapRef.current;
    if (!node || typeof ResizeObserver === 'undefined') return;
    const sync = () => setImageWrapWidth(node.clientWidth || 0);
    sync();
    const observer = new ResizeObserver(() => sync());
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const onDownload = async () => {
    if (!src) return;
    const fallbackName = String(name || 'allegato').trim() || 'allegato';
    try {
      if (rawSrc.startsWith('data:')) {
        const link = document.createElement('a');
        link.href = rawSrc;
        link.download = fallbackName;
        link.click();
        return;
      }
      const resp = await fetch(src);
      const blob = await resp.blob();
      const obj = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = obj;
      link.download = fallbackName;
      link.click();
      URL.revokeObjectURL(obj);
    } catch {
      const link = document.createElement('a');
      link.href = src;
      link.download = fallbackName;
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.click();
    }
  };

  return (
    <div id={id} className="ds-preview ds-attachment-preview" style={parseStyle(style)}>
      <div className="ds-preview-header">
        <div className="ds-preview-title">
          <i className="ri-attachment-2" />
          <span>{String(name || 'Attachment')}</span>
          <span className="ds-preview-meta">{normalizedMime || 'unknown'}</span>
        </div>
        <div className="ds-preview-id">{String(file_id || '-')}</div>
      </div>

      <div className="ds-preview-toolbar">
        <div className="ds-preview-zoom" role="group" aria-label="Zoom">
          <Button type="button" color="default" size="xs" className="ds-preview-icon-button" onClick={() => setZoom((z) => Math.max(0.3, z - 0.15))}>
            <i className="ri-subtract-line" />
          </Button>
          <div className="ds-preview-zoom-value">
            {Math.round(zoom * 100)}%
          </div>
          <Button type="button" color="default" size="xs" className="ds-preview-icon-button" onClick={() => setZoom((z) => Math.min(4, z + 0.15))}>
            <i className="ri-add-line" />
          </Button>
        </div>
        
        <div className="ds-preview-toolbar-spacer" />
        <Button type="button" color="default" size="xs" className="ds-preview-button" onClick={onDownload}>
          <i className="ri-download-2-line" />
          Download
        </Button>
      </div>

      <div className="ds-preview-surface">
        {!src ? (
          <div className="ds-preview-empty">
            <i className="ri-error-warning-line" />
            Preview is not available in this client.
          </div>
        ) : normalizedMime.startsWith('image/') ? (
          <div ref={imageWrapRef} className="ds-preview-scroll" style={{ maxHeight: `${h}px` }}>
            <MediaImage
              id={`${String(id || 'attachment_preview')}_image`}
              alt={String(name || 'attachment')}
              url={src}
              width={imageWidth}
              height={imageHeight}
              className="ds-preview-image"
            />
          </div>
        ) : normalizedMime === 'application/pdf' ? (
          <div className="ds-preview-scroll" style={{ height: `${h}px` }}>
            <iframe
              title="attachment-preview-pdf"
              src={src}
              className="ds-preview-frame"
              style={{ height: `${h * zoom}px`, minWidth: '100%' }}
            />
          </div>
        ) : (
          <div className="ds-preview-empty">
            <i className="ri-file-unknow-line" />
            Preview is not supported for this file type.
          </div>
        )}
      </div>
    </div>
  );
};
