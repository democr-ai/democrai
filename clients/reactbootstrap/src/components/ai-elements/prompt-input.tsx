"use client";

import type { ChatStatus, FileUIPart, SourceDocumentUIPart } from "ai";
import React, {
  type ChangeEvent,
  type ChangeEventHandler,
  type ClipboardEventHandler,
  type ComponentProps,
  type FormEvent,
  type FormEventHandler,
  type HTMLAttributes,
  type KeyboardEventHandler,
  type PropsWithChildren,
  type ReactNode,
  type RefObject,
} from "react";

import {
  Input,
  FormGroup,
  Label,
  UncontrolledTooltip
} from 'design-react-kit';
import { UncontrolledDropdown, DropdownItem, DropdownToggle, DropdownMenu } from 'reactstrap';
import { cn } from "@/lib/utils";
import { nanoid } from "nanoid";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

// ============================================================================
// Helpers
// ============================================================================

const convertBlobUrlToDataUrl = async (url: string): Promise<string | null> => {
  try {
    const response = await fetch(url);
    const blob = await response.blob();
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result as string);
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
};

// ============================================================================
// Provider Context & Types
// ============================================================================

export interface AttachmentsContext {
  files: (FileUIPart & { id: string })[];
  add: (files: File[] | FileList) => void;
  remove: (id: string) => void;
  clear: () => void;
  openFileDialog: () => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
}

export interface TextInputContext {
  value: string;
  setInput: (v: string) => void;
  clear: () => void;
}

export interface PromptInputControllerProps {
  textInput: TextInputContext;
  attachments: AttachmentsContext;
  __registerFileInput: (
    ref: RefObject<HTMLInputElement | null>,
    open: () => void
  ) => void;
}

const PromptInputController = createContext<PromptInputControllerProps | null>(null);
const ProviderAttachmentsContext = createContext<AttachmentsContext | null>(null);

export const usePromptInputController = () => {
  const ctx = useContext(PromptInputController);
  if (!ctx) throw new Error("Wrap your component inside <PromptInputProvider> to use usePromptInputController().");
  return ctx;
};

const useOptionalPromptInputController = () => useContext(PromptInputController);

export const useProviderAttachments = () => {
  const ctx = useContext(ProviderAttachmentsContext);
  if (!ctx) throw new Error("Wrap your component inside <PromptInputProvider> to use useProviderAttachments().");
  return ctx;
};

const useOptionalProviderAttachments = () => useContext(ProviderAttachmentsContext);

export const PromptInputProvider = ({
  initialInput: initialTextInput = "",
  children,
}: PropsWithChildren<{ initialInput?: string }>) => {
  const [textInput, setTextInput] = useState(initialTextInput);
  const clearInput = useCallback(() => setTextInput(""), []);

  const [attachmentFiles, setAttachmentFiles] = useState<(FileUIPart & { id: string })[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const openRef = useRef<() => void>(() => {});

  const add = useCallback((files: File[] | FileList) => {
    const incoming = [...files];
    if (incoming.length === 0) return;
    setAttachmentFiles((prev) => [
      ...prev,
      ...incoming.map((file) => ({
        filename: file.name,
        id: nanoid(),
        mediaType: file.type,
        type: "file" as const,
        url: URL.createObjectURL(file),
      })),
    ]);
  }, []);

  const remove = useCallback((id: string) => {
    setAttachmentFiles((prev) => {
      const found = prev.find((f) => f.id === id);
      if (found?.url) URL.revokeObjectURL(found.url);
      return prev.filter((f) => f.id !== id);
    });
  }, []);

  const clear = useCallback(() => {
    setAttachmentFiles((prev) => {
      for (const f of prev) if (f.url) URL.revokeObjectURL(f.url);
      return [];
    });
  }, []);

  const attachmentsRef = useRef(attachmentFiles);
  useEffect(() => { attachmentsRef.current = attachmentFiles; }, [attachmentFiles]);

  useEffect(() => () => {
    for (const f of attachmentsRef.current) if (f.url) URL.revokeObjectURL(f.url);
  }, []);

  const openFileDialog = useCallback(() => { openRef.current?.(); }, []);

  const attachments = useMemo<AttachmentsContext>(
    () => ({ add, clear, fileInputRef, files: attachmentFiles, openFileDialog, remove }),
    [attachmentFiles, add, remove, clear, openFileDialog]
  );

  const __registerFileInput = useCallback((ref: RefObject<HTMLInputElement | null>, open: () => void) => {
    fileInputRef.current = ref.current;
    openRef.current = open;
  }, []);

  const controller = useMemo<PromptInputControllerProps>(
    () => ({ __registerFileInput, attachments, textInput: { clear: clearInput, setInput: setTextInput, value: textInput } }),
    [textInput, clearInput, attachments, __registerFileInput]
  );

  return (
    <PromptInputController.Provider value={controller}>
      <ProviderAttachmentsContext.Provider value={attachments}>
        {children}
      </ProviderAttachmentsContext.Provider>
    </PromptInputController.Provider>
  );
};

const LocalAttachmentsContext = createContext<AttachmentsContext | null>(null);

export const usePromptInputAttachments = () => {
  const provider = useOptionalProviderAttachments();
  const local = useContext(LocalAttachmentsContext);
  const context = local ?? provider;
  if (!context) throw new Error("usePromptInputAttachments must be used within a PromptInput or PromptInputProvider");
  return context;
};

export interface ReferencedSourcesContext {
  sources: (SourceDocumentUIPart & { id: string })[];
  add: (sources: SourceDocumentUIPart[] | SourceDocumentUIPart) => void;
  remove: (id: string) => void;
  clear: () => void;
}

export const LocalReferencedSourcesContext = createContext<ReferencedSourcesContext | null>(null);

export const usePromptInputReferencedSources = () => {
  const ctx = useContext(LocalReferencedSourcesContext);
  if (!ctx) throw new Error("usePromptInputReferencedSources must be used within a LocalReferencedSourcesContext.Provider");
  return ctx;
};

export const PromptInputActionAddAttachments = ({
  label = "Aggiungi file o foto",
  ...props
}: any) => {
  const attachments = usePromptInputAttachments();
  const handleSelect = useCallback((e: any) => {
    e.preventDefault();
    attachments.openFileDialog();
  }, [attachments]);

  return (
    <DropdownItem {...props} onClick={handleSelect}>
      <i className="ri-image-line me-2" /> {label}
    </DropdownItem>
  );
};

export interface PromptInputMessage {
  text: string;
  files: FileUIPart[];
}

export type PromptInputProps = Omit<HTMLAttributes<HTMLFormElement>, "onSubmit" | "onError"> & {
  accept?: string;
  multiple?: boolean;
  globalDrop?: boolean;
  syncHiddenInput?: boolean;
  maxFiles?: number;
  maxFileSize?: number;
  onError?: (err: { code: "max_files" | "max_file_size" | "accept"; message: string }) => void;
  onSubmit: (message: PromptInputMessage, event: FormEvent<HTMLFormElement>) => void | Promise<void>;
};

export const PromptInput = ({
  className,
  accept,
  multiple,
  globalDrop,
  syncHiddenInput,
  maxFiles,
  maxFileSize,
  onError,
  onSubmit,
  children,
  ...props
}: PromptInputProps) => {
  const controller = useOptionalPromptInputController();
  const usingProvider = !!controller;

  const inputRef = useRef<HTMLInputElement | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);

  const [items, setItems] = useState<(FileUIPart & { id: string })[]>([]);
  const files = usingProvider ? controller.attachments.files : items;

  const [referencedSources, setReferencedSources] = useState<(SourceDocumentUIPart & { id: string })[]>([]);
  const filesRef = useRef(files);
  useEffect(() => { filesRef.current = files; }, [files]);

  const openFileDialogLocal = useCallback(() => { inputRef.current?.click(); }, []);

  const matchesAccept = useCallback((f: File) => {
    if (!accept || accept.trim() === "") return true;
    const patterns = accept.split(",").map((s) => s.trim()).filter(Boolean);
    return patterns.some((pattern) => {
      if (pattern.endsWith("/*")) return f.type.startsWith(pattern.slice(0, -1));
      return f.type === pattern;
    });
  }, [accept]);

  const addLocal = useCallback((fileList: File[] | FileList) => {
    const incoming = [...fileList];
    const accepted = incoming.filter((f) => matchesAccept(f));
    if (incoming.length && accepted.length === 0) {
      onError?.({ code: "accept", message: "No files match the accepted types." });
      return;
    }
    const sized = accepted.filter((f) => maxFileSize ? f.size <= maxFileSize : true);
    if (accepted.length > 0 && sized.length === 0) {
      onError?.({ code: "max_file_size", message: "All files exceed the maximum size." });
      return;
    }

    setItems((prev) => {
      const capacity = typeof maxFiles === "number" ? Math.max(0, maxFiles - prev.length) : undefined;
      const capped = typeof capacity === "number" ? sized.slice(0, capacity) : sized;
      if (typeof capacity === "number" && sized.length > capacity) {
        onError?.({ code: "max_files", message: "Too many files. Some were not added." });
      }
      const next = capped.map(file => ({
        filename: file.name,
        id: nanoid(),
        mediaType: file.type,
        type: "file" as const,
        url: URL.createObjectURL(file),
      }));
      return [...prev, ...next];
    });
  }, [matchesAccept, maxFiles, maxFileSize, onError]);

  const removeLocal = useCallback((id: string) => setItems((prev) => {
    const found = prev.find((file) => file.id === id);
    if (found?.url) URL.revokeObjectURL(found.url);
    return prev.filter((file) => file.id !== id);
  }), []);

  const addWithProviderValidation = useCallback((fileList: File[] | FileList) => {
    const incoming = [...fileList];
    const accepted = incoming.filter((f) => matchesAccept(f));
    if (incoming.length && accepted.length === 0) {
      onError?.({ code: "accept", message: "No files match the accepted types." });
      return;
    }
    const sized = accepted.filter((f) => maxFileSize ? f.size <= maxFileSize : true);
    if (accepted.length > 0 && sized.length === 0) {
      onError?.({ code: "max_file_size", message: "All files exceed the maximum size." });
      return;
    }
    const capacity = typeof maxFiles === "number" ? Math.max(0, maxFiles - files.length) : undefined;
    const capped = typeof capacity === "number" ? sized.slice(0, capacity) : sized;
    if (typeof capacity === "number" && sized.length > capacity) {
      onError?.({ code: "max_files", message: "Too many files. Some were not added." });
    }
    if (capped.length > 0) controller?.attachments.add(capped);
  }, [matchesAccept, maxFileSize, maxFiles, onError, files.length, controller]);

  const clearAttachments = useCallback(() => usingProvider ? controller?.attachments.clear() : setItems((prev) => {
    prev.forEach(f => { if (f.url) URL.revokeObjectURL(f.url); });
    return [];
  }), [usingProvider, controller]);

  const clearReferencedSources = useCallback(() => setReferencedSources([]), []);
  const add = usingProvider ? addWithProviderValidation : addLocal;
  const remove = usingProvider ? controller.attachments.remove : removeLocal;
  const openFileDialog = usingProvider ? controller.attachments.openFileDialog : openFileDialogLocal;
  const clear = useCallback(() => { clearAttachments(); clearReferencedSources(); }, [clearAttachments, clearReferencedSources]);

  useEffect(() => {
    if (!usingProvider) return;
    controller.__registerFileInput(inputRef, () => inputRef.current?.click());
  }, [usingProvider, controller]);

  useEffect(() => {
    const onDrop = (e: DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        e.preventDefault();
        if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) add(e.dataTransfer.files);
      }
    };
    const onDragOver = (e: DragEvent) => { if (e.dataTransfer?.types?.includes("Files")) e.preventDefault(); };
    
    const target = globalDrop ? document : formRef.current;
    if (!target) return;
    target.addEventListener("dragover", onDragOver as any);
    target.addEventListener("drop", onDrop as any);
    return () => {
      target.removeEventListener("dragover", onDragOver as any);
      target.removeEventListener("drop", onDrop as any);
    };
  }, [add, globalDrop]);

  useEffect(() => () => {
    if (!usingProvider) filesRef.current.forEach(f => { if (f.url) URL.revokeObjectURL(f.url); });
  }, [usingProvider]);

  const handleChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    if (event.currentTarget.files) add(event.currentTarget.files);
    event.currentTarget.value = "";
  }, [add]);

  const attachmentsCtx = useMemo(() => ({ add, clear: clearAttachments, fileInputRef: inputRef, files, openFileDialog, remove }), [files, add, remove, clearAttachments, openFileDialog]);
  const refsCtx = useMemo(() => ({
    add: (incoming: any) => {
      const array = Array.isArray(incoming) ? incoming : [incoming];
      setReferencedSources((prev) => [...prev, ...array.map((s) => ({ ...s, id: nanoid() }))]);
    },
    clear: clearReferencedSources,
    remove: (id: string) => setReferencedSources((prev) => prev.filter((s) => s.id !== id)),
    sources: referencedSources,
  }), [referencedSources, clearReferencedSources]);

  const handleSubmit = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const text = usingProvider ? controller.textInput.value : (new FormData(form).get("message") as string || "");
    if (!usingProvider) form.reset();

    try {
      const convertedFiles = await Promise.all(files.map(async ({ id: _id, ...item }) => {
        if (item.url?.startsWith("blob:")) {
          const dataUrl = await convertBlobUrlToDataUrl(item.url);
          return { ...item, url: dataUrl ?? item.url };
        }
        return item;
      }));

      const result = onSubmit({ files: convertedFiles, text }, event);
      if (result instanceof Promise) {
        await result;
        clear();
        if (usingProvider) controller.textInput.clear();
      } else {
        clear();
        if (usingProvider) controller.textInput.clear();
      }
    } catch {}
  }, [usingProvider, controller, files, onSubmit, clear]);

  return (
    <>
      <input accept={accept} className="d-none" multiple={multiple} onChange={handleChange} ref={inputRef} type="file" />
      <form className={cn("w-100", className)} onSubmit={handleSubmit} ref={formRef} {...props}>
        <LocalAttachmentsContext.Provider value={attachmentsCtx}>
          <LocalReferencedSourcesContext.Provider value={refsCtx}>
            {children}
          </LocalReferencedSourcesContext.Provider>
        </LocalAttachmentsContext.Provider>
      </form>
    </>
  );
};

// ============================================================================
// Sub-components (Draft migration)
// ============================================================================

export const PromptInputAttachments = ({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) => {
  const { files } = usePromptInputAttachments();
  const { sources } = usePromptInputReferencedSources();
  if (files.length === 0 && sources.length === 0 && !children) return null;
  return (
    <div className={cn("d-flex flex-wrap gap-2 p-2", className)} {...props}>
      {children}
    </div>
  );
};

export const PromptInputAttachment = ({ id, ...props }: HTMLAttributes<HTMLDivElement> & { id: string }) => {
  const { files, remove } = usePromptInputAttachments();
  const file = files.find((f) => f.id === id);
  if (!file) return null;
  return (
    <div className="position-relative border rounded p-1 bg-light d-flex align-items-center gap-2" style={{ maxWidth: '200px' }} {...props}>
      {file.mediaType?.startsWith('image/') && file.url && (
        <img src={file.url} alt={file.filename} className="rounded" style={{ width: '32px', height: '32px', objectFit: 'cover' }} />
      )}
      <span className="xsmall text-truncate flex-grow-1">{file.filename}</span>
      <button type="button" className="btn btn-xs btn-link p-0 text-danger" onClick={() => remove(id)}>
        <i className="ri-close-line" />
      </button>
    </div>
  );
};

export const PromptInputTextarea = React.forwardRef<HTMLTextAreaElement, any>(({ className, ...props }, ref) => {
  const controller = useOptionalPromptInputController();
  const { value: providerValue, setInput } = controller?.textInput ?? { value: '', setInput: () => {} };
  const [localValue, setLocalValue] = useState('');
  const value = controller ? providerValue : localValue;

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    if (controller) setInput(e.target.value);
    else setLocalValue(e.target.value);
  };

  return (
    <textarea
      ref={ref}
      className={cn("form-control border-0 shadow-none bg-transparent flex-grow-1", className)}
      style={{ resize: 'none', minHeight: '44px' }}
      rows={1}
      value={value}
      onChange={handleChange}
      name="message"
      {...props}
    />
  );
});

export const PromptInputActions = ({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("d-flex align-items-center gap-1 p-1", className)} {...props}>
    {children}
  </div>
);

export const PromptInputAction = ({ children, tooltip, ...props }: any) => {
  const id = React.useId().replace(/:/g, '');
  return (
    <>
      <Button id={id} size="xs" color="link" className="p-1" {...props}>{children}</Button>
      {tooltip && <UncontrolledTooltip target={id}>{tooltip}</UncontrolledTooltip>}
    </>
  );
};
