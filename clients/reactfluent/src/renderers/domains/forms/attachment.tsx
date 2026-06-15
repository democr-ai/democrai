import React from 'react';
import { DefaultButton, IconButton } from '@fluentui/react';
import { Field } from '@fluentui/react-components';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm } from '@/renderers/shared';
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

  const labelText = getLiteral(label);

  return (
    <Field
      label={labelText || undefined}
      validationState={error ? 'error' : undefined}
      validationMessage={error || undefined}
      style={parseStyle(style)}
    >
      <div className="a2ui-attachment-list">
        {files.map((file, i) => {
          if (!file) return null;
          const fileName = file.name || 'Unknown';
          const rawFileUrl = file.preview_url || file.url || file.path;
          const fileUrl = typeof rawFileUrl === 'string' ? resolveMediaUrl(rawFileUrl) : rawFileUrl;
          const fileType = file.type || file.mime || 'application/octet-stream';
          const isImage = fileType.startsWith('image/') || /\.(png|jpe?g|gif|webp)$/i.test(fileName);
          const isPdf = fileType === 'application/pdf' || fileName.toLowerCase().endsWith('.pdf');
          
          return (
            <div key={`${id}_file_${i}`} className={`a2ui-attachment-tile ${error ? 'is-invalid' : ''}`}>
              {isImage && fileUrl ? (
                <img src={fileUrl} alt={fileName} className="a2ui-attachment-preview-image" />
              ) : (isPdf && fileUrl) ? (
                <iframe 
                  src={`${fileUrl}#toolbar=0&navpanes=0&scrollbar=0`} 
                  className="a2ui-attachment-preview-frame"
                  style={{ pointerEvents: 'none' }}
                  title={fileName}
                />
              ) : (
                <div className="a2ui-attachment-file">
                  <i className="ri-file-text-line" />
                  <span>{fileName}</span>
                </div>
              )}
              <IconButton
                type="button"
                onClick={() => removeFile(i)}
                className="a2ui-attachment-remove-btn"
                title="Remove"
                aria-label="Remove"
                iconProps={{ iconName: 'Cancel' }}
              />
            </div>
          );
        })}
        
        {(multiple || files.length === 0) && (
          <DefaultButton
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className={`a2ui-attachment-upload-btn ${error ? 'is-invalid' : ''}`}
          >
            <span className="a2ui-attachment-upload-icon" aria-hidden="true">
              <i className="ri-upload-2-line" />
            </span>
            <span className="a2ui-attachment-upload-copy">
              <span className="a2ui-attachment-upload-label">Upload</span>
              {accept ? <span className="a2ui-attachment-upload-hint">{accept}</span> : null}
            </span>
          </DefaultButton>
        )}
      </div>

      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept={accept}
        multiple={multiple}
        className="d-none"
      />
    </Field>
  );
};
