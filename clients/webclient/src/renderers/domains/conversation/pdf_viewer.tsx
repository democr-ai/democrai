import React from 'react';
import { parseStyle } from '@/utils/style';
import { Button } from '@/components/ui/button';
import { Download } from 'lucide-react';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { getLiteral } from '@/renderers/shared';
import { resolveBindings } from '@/renderers/rules';
import { useI18n } from '@/utils/i18n';

export const PdfViewer: React.FC<any> = ({
  id,
  name,
  storage_path,
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
  const resolvedStoragePath = resolveBindings(storage_path, bindingOptions);
  const resolvedUrl = resolveBindings(url, bindingOptions);
  const resolvedHeight = resolveBindings(height, bindingOptions);
  const rawSrc = String(getLiteral(resolvedStoragePath) || getLiteral(resolvedUrl) || '').trim();
  const src = useResolvedMediaUrl(rawSrc);
  const h = Math.max(300, Number(resolvedHeight || 520));
  const frameSrc = React.useMemo(() => {
    if (!src) return '';
    return src;
  }, [src]);

  const onDownload = async () => {
    if (!src) return;
    const fallbackName = String(resolvedName || 'document.pdf').trim() || 'document.pdf';
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
    <div id={id} className="w-full" style={parseStyle(style)}>
      <div className="mb-2 flex items-center justify-end">
        <div>
          <Button type="button" variant="outline" className="h-8 gap-1 px-2 text-xs" onClick={onDownload}>
            <Download className="h-3.5 w-3.5" />
            Download
          </Button>
        </div>
      </div>

      {!frameSrc ? (
        <div className="rounded border p-3 text-sm text-muted-foreground">{messages.pdfSourceUnavailable}</div>
      ) : (
        <div className="ui-pdf-shell rounded-md border p-3">
          <div className="ui-pdf-frame overflow-auto rounded border" style={{ height: `${h}px` }}>
            <iframe title="pdf-viewer" src={frameSrc} className="h-full w-full border-0" />
          </div>
        </div>
      )}
    </div>
  );
};
