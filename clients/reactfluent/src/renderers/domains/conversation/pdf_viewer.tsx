import React from 'react';
import { parseStyle } from '@/utils/style';
import { Button } from '@/design/system';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { getLiteral } from '@/renderers/shared';
import { resolveBindings } from '@/renderers/rules';
import { useI18n } from '@/utils/i18n';

export const PdfViewer: React.FC<any> = ({
  id,
  name,
  source_path,
  url,
  height,
  style,
  stateModel,
  surfaceModel,
}) => {
  const messages = useI18n(stateModel);
  const bindingOptions = React.useMemo(() => ({
    stateModel,
    surfaceModel,
    item: undefined,
    role: '',
    permissions: [],
  }), [stateModel, surfaceModel]);
  
  const resolvedName = resolveBindings(name, bindingOptions);
  const resolvedSourcePath = resolveBindings(source_path, bindingOptions);
  const resolvedUrl = resolveBindings(url, bindingOptions);
  const resolvedHeight = resolveBindings(height, bindingOptions);
  const rawSrc = String(getLiteral(resolvedSourcePath) || getLiteral(resolvedUrl) || '').trim();
  const src = useResolvedMediaUrl(rawSrc);
  const h = Math.max(300, Number(resolvedHeight || 520));

  const onDownload = async () => {
    if (!src) return;
    const fallbackName = String(resolvedName || 'documento.pdf').trim() || 'documento.pdf';
    try {
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
    <div id={id} className="w-100" style={parseStyle(style)}>
      <div className="mb-3 d-flex align-items-center justify-content-between border-bottom pb-2">
        <div className="small fw-bold text-muted">
          <i className="ri-file-pdf-2-line me-2 text-danger" />
          {getLiteral(resolvedName || 'PDF Viewer')}
        </div>
        <Button type="button" color="primary" outline size="xs" className="d-flex align-items-center gap-2" onClick={onDownload}>
          <i className="ri-download-2-line" />
          Download PDF
        </Button>
      </div>

      {!src ? (
        <div className="rounded border p-4 text-center bg-light text-muted small">
          <i className="ri-error-warning-line d-block fs-3 mb-2" />
          {messages.pdfSourceUnavailable || 'PDF source is not available.'}
        </div>
      ) : (
        <div className="p-2 border rounded bg-light">
          <div className="bg-white rounded border overflow-hidden" style={{ height: `${h}px` }}>
            <iframe title="pdf-viewer" src={src} className="h-100 w-100 border-0" />
          </div>
        </div>
      )}
    </div>
  );
};
