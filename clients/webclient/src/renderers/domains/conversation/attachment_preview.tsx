import React from 'react';
import { parseStyle } from '@/utils/style';
import { Button } from '@/components/ui/button';
import { Download } from 'lucide-react';
import { Image as MediaImage } from '@/renderers/domains/media/image';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { getLiteral } from '@/renderers/shared';

export const AttachmentPreview: React.FC<any> = ({
  id,
  name,
  mime_type,
  storage_path,
  file_id,
  url,
  height,
  style,
}) => {
  const normalizedMime = String(mime_type || '').trim().toLowerCase();
  const rawSrc = String(
    getLiteral(url) || getLiteral(storage_path) || ''
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
    const fallbackName = String(name || 'attachment').trim() || 'attachment';
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
    <div id={id} className="w-full rounded-md border p-2" style={parseStyle(style)}>
      <div className="mb-2 text-xs text-muted-foreground">
        {String(name || 'Attachment')} · {normalizedMime || 'unknown'} · {String(file_id || '-')}
      </div>

      <div className="mb-2 flex items-center gap-2">
        <Button type="button" variant="outline" className="h-7 px-2 text-xs" onClick={() => setZoom((z) => Math.max(0.3, z - 0.15))}>-</Button>
        <span className="text-xs text-muted-foreground">{Math.round(zoom * 100)}%</span>
        <Button type="button" variant="outline" className="h-7 px-2 text-xs" onClick={() => setZoom((z) => Math.min(4, z + 0.15))}>+</Button>
        <div className="ml-auto">
          <Button type="button" variant="outline" className="h-7 gap-1 px-2 text-xs" onClick={onDownload}>
            <Download className="h-3.5 w-3.5" />
            Download
          </Button>
        </div>
      </div>

      {!src ? (
        <div className="text-sm text-muted-foreground">Preview source not available in this client.</div>
      ) : normalizedMime.startsWith('image/') ? (
        <div ref={imageWrapRef} className="overflow-auto rounded border" style={{ maxHeight: `${h}px`, maxWidth: '100%' }}>
          <MediaImage
            id={`${String(id || 'attachment_preview')}_image`}
            alt={String(name || 'attachment')}
            url={src}
            width={imageWidth}
            height={imageHeight}
          />
        </div>
      ) : normalizedMime === 'application/pdf' ? (
        <div className="overflow-auto rounded border" style={{ height: `${h}px` }}>
          <iframe
            title="attachment-preview-pdf"
            src={src}
            className="border-0"
            style={{ height: `${h * zoom}px`, width: `${100 * zoom}%`, minWidth: '100%' }}
          />
        </div>
      ) : (
        <div className="text-sm text-muted-foreground">Preview not supported for this file type.</div>
      )}
    </div>
  );
};
