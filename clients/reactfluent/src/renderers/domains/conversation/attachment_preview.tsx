import React from 'react';
import { parseStyle } from '@/utils/style';
import { Button } from '@/design/system';
import { Image as MediaImage } from '@/renderers/domains/media/image';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { getLiteral } from '@/renderers/shared';
import { cn } from '@/lib/utils';

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
    <div id={id} className="w-100 rounded border p-3 bg-white" style={parseStyle(style)}>
      <div className="mb-3 d-flex align-items-center justify-content-between border-bottom pb-2">
        <div className="xsmall text-muted text-uppercase fw-bold">
          <i className="ri-attachment-2 me-1" />
          {String(name || 'Attachment')} <span className="mx-1">·</span> {normalizedMime || 'unknown'}
        </div>
        <div className="xsmall text-muted">{String(file_id || '-')}</div>
      </div>

      <div className="mb-3 d-flex align-items-center gap-2">
        <div className="btn-group shadow-sm">
          <Button type="button" color="outline-primary" size="xs" className="px-3" onClick={() => setZoom((z) => Math.max(0.3, z - 0.15))}>
            <i className="ri-subtract-line" />
          </Button>
          <div className="bg-light border-top border-bottom px-2 d-flex align-items-center xsmall fw-bold" style={{ minWidth: '50px', justifyContent: 'center' }}>
            {Math.round(zoom * 100)}%
          </div>
          <Button type="button" color="outline-primary" size="xs" className="px-3" onClick={() => setZoom((z) => Math.min(4, z + 0.15))}>
            <i className="ri-add-line" />
          </Button>
        </div>
        
        <div className="ms-auto">
          <Button type="button" color="primary" size="xs" className="d-flex align-items-center gap-2" onClick={onDownload}>
            <i className="ri-download-2-line" />
            Download
          </Button>
        </div>
      </div>

      <div className="preview-container bg-light rounded overflow-hidden d-flex align-items-center justify-content-center" style={{ minHeight: '200px' }}>
        {!src ? (
          <div className="text-muted small p-4 text-center">
            <i className="ri-error-warning-line d-block fs-3 mb-2" />
            Preview is not available in this client.
          </div>
        ) : normalizedMime.startsWith('image/') ? (
          <div ref={imageWrapRef} className="overflow-auto w-100" style={{ maxHeight: `${h}px` }}>
            <MediaImage
              id={`${String(id || 'attachment_preview')}_image`}
              alt={String(name || 'attachment')}
              url={src}
              width={imageWidth}
              height={imageHeight}
              className="img-fluid d-block mx-auto"
            />
          </div>
        ) : normalizedMime === 'application/pdf' ? (
          <div className="overflow-auto w-100" style={{ height: `${h}px` }}>
            <iframe
              title="attachment-preview-pdf"
              src={src}
              className="border-0 w-100"
              style={{ height: `${h * zoom}px`, minWidth: '100%' }}
            />
          </div>
        ) : (
          <div className="text-muted small p-4 text-center">
            <i className="ri-file-unknow-line d-block fs-3 mb-2" />
            Preview is not supported for this file type.
          </div>
        )}
      </div>
    </div>
  );
};
