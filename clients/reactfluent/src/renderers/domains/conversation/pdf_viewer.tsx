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
    <div id={id} className="ds-preview ds-pdf-viewer" style={parseStyle(style)}>
      <div className="ds-preview-header">
        <div className="ds-preview-title">
          <i className="ri-file-pdf-2-line" />
          {getLiteral(resolvedName || 'PDF Viewer')}
        </div>
        <Button type="button" color="default" size="xs" className="ds-preview-button" onClick={onDownload}>
          <i className="ri-download-2-line" />
          Download PDF
        </Button>
      </div>

      {!src ? (
        <div className="ds-preview-empty">
          <i className="ri-error-warning-line" />
          {messages.pdfSourceUnavailable || 'PDF source is not available.'}
        </div>
      ) : (
        <div className="ds-preview-surface">
          <iframe title="pdf-viewer" src={src} className="ds-preview-frame" style={{ height: `${h}px` }} />
        </div>
      )}
    </div>
  );
};
