import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm } from '@/renderers/shared';
import { Label } from '@/components/ui/label';
import { FileText } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  sanitizeAttachmentEntriesForTransport,
  toLocalAttachmentValue,
} from '@/utils/uploads';
import { resolveMediaUrl } from '@/utils/media';

export const Attachment: React.FC<any> = ({
  id,
  label,
  accept,
  multiple,
  ingest = true,
  value = [],
  action,
  onAction,
  setInput,
  style,
  error,
  syncInitialInput = true,
}) => {
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [files, setFiles] = React.useState<any[]>(Array.isArray(value) ? value : []);
  const lastSyncedValueRef = React.useRef<string>('');

  React.useEffect(() => {
    const nextFiles = Array.isArray(value) ? value : [];
    const serialized = JSON.stringify(nextFiles);
    if (lastSyncedValueRef.current === serialized) return;
    lastSyncedValueRef.current = serialized;
    setFiles(nextFiles);
    if (syncInitialInput) setInput?.(id, nextFiles);
  }, [id, setInput, syncInitialInput, value]);

  React.useEffect(() => () => {
    files.forEach((file) => {
      const url = file?.preview_url || file?.url;
      if (typeof url === 'string' && url.startsWith('blob:')) {
        URL.revokeObjectURL(url);
      }
    });
  }, [files]);

  const dispatchFiles = (nextFiles: any[]) => {
    if (action && onAction) {
      const safeValue = sanitizeAttachmentEntriesForTransport(nextFiles);
      const actionWithoutConfirm = action && typeof action === 'object'
        ? { ...action, confirm: undefined }
        : action;
      emitActionSpec(actionWithoutConfirm, onAction, { [id]: safeValue, value: safeValue });
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.length) return;

    // Reset input value to allow selecting the same file again if removed
    const pickedFiles = Array.from(e.target.files);
    e.target.value = '';

    const newFiles = pickedFiles.map((file) => ({
      ...toLocalAttachmentValue(file),
      ingest: ingest !== false,
    }));
    const nextFiles = multiple ? [...files, ...newFiles] : newFiles;
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      newFiles.forEach((file) => {
        const url = file?.preview_url || file?.url;
        if (typeof url === 'string' && url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
      return;
    }
    setFiles(nextFiles);
    setInput?.(id, nextFiles);
    dispatchFiles(nextFiles);
  };

  const removeFile = async (index: number) => {
    const fileToRemove = files[index];
    const nextFiles = files.filter((_, i) => i !== index);
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      return;
    }
    const previewUrl = fileToRemove?.preview_url || fileToRemove?.url;
    if (previewUrl?.startsWith('blob:')) {
      URL.revokeObjectURL(previewUrl);
    }
    setFiles(nextFiles);
    setInput?.(id, nextFiles);
    dispatchFiles(nextFiles);
  };

  return (
    <div className="grid gap-2" style={parseStyle(style)}>
      {getLiteral(label) ? <Label className={cn(error && "text-destructive")}>{getLiteral(label)}</Label> : null}
      
      <div className="flex flex-wrap gap-2">
        {files.map((file, i) => {
          if (!file) return null;
          const fileName = file.name || 'Unknown';
          const rawFileUrl = file.preview_url || file.url || file.path;
          const fileUrl = typeof rawFileUrl === 'string' ? resolveMediaUrl(rawFileUrl) : rawFileUrl;
          const fileType = file.type || file.mime || 'application/octet-stream';
          const isImage = fileType.startsWith('image/') || /\.(png|jpe?g|gif|webp)$/i.test(fileName);
          const isPdf = fileType === 'application/pdf' || fileName.toLowerCase().endsWith('.pdf');
          
          return (
            <div key={`${id}_file_${i}`} className={cn(
              "relative group w-24 h-24 border rounded-lg overflow-hidden bg-muted flex items-center justify-center transition-all",
              error ? "border-destructive/50" : "border-border"
            )}>
              {isImage && fileUrl ? (
                <img src={fileUrl} alt={fileName} className="w-full h-full object-cover" />
              ) : (isPdf && fileUrl) ? (
                <iframe 
                  src={`${fileUrl}#toolbar=0&navpanes=0&scrollbar=0`} 
                  className="w-full h-full border-none pointer-events-none" 
                  title={fileName}
                />
              ) : (
                <div className="flex flex-col items-center gap-1 text-muted-foreground p-1 text-center">
                  <FileText className="w-8 h-8 opacity-50" />
                  <span className="text-[10px] underline decoration-dotted truncate w-full px-1">{fileName}</span>
                </div>
              )}
              <button 
                type="button"
                onClick={() => removeFile(i)}
                className="absolute top-1 right-1 bg-background/95 hover:bg-destructive hover:text-destructive-foreground rounded-full w-5 h-5 flex items-center justify-center shadow-md transition-all border border-border"
                title="Remove"
              >
                <i className="ri-close-line text-sm" />
              </button>
            </div>
          );
        })}
        
        {(multiple || files.length === 0) && (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              "w-24 h-24 rounded-lg flex flex-col items-center justify-center gap-2 transition-all border",
              "bg-primary text-primary-foreground border-primary hover:bg-primary/90",
              error && "border-destructive bg-destructive text-destructive-foreground hover:bg-destructive/90"
            )}
            disabled={false}
          >
            <i className="ri-upload-2-line text-lg" />
            <span className="text-[11px] font-medium text-center px-1 leading-tight">
              Upload
            </span>
          </button>
        )}
      </div>

      {error && (
        <p className="text-[12px] font-medium text-destructive mt-0.5 animate-in fade-in slide-in-from-top-1 duration-200">
          {error}
        </p>
      )}

      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept={accept}
        multiple={multiple}
        className="hidden"
      />
    </div>
  );
};
