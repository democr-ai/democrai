import React from 'react';
import { InternalRenderer } from '@/components/a2ui/Renderer';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { resolveIconClass } from '@/utils/icons';
import ReactMarkdown from 'react-markdown';
import { ArrowDown, Bot, Check, ChevronRight, Copy, Download, Hammer, User } from 'lucide-react';
import { BackgroundTaskCard } from '@/renderers/domains/tasks/background_task_card';

type AttachmentEntry = {
  name?: string;
  mime_type?: string;
  storage_path?: string;
  file_id?: string;
  url?: string;
};

const VIRTUALIZATION_THRESHOLD = 30;
const VIRTUAL_OVERSCAN = 8;
const DEFAULT_MESSAGE_HEIGHT = 128;
const ESTIMATED_MESSAGE_GAP = 12;

type VirtualRange = {
  start: number;
  end: number;
};

const messageKey = (message: any, index: number): string => (
  String(message?.id || `message_${index}`)
);

const estimatedMessageHeight = (
  messages: any[],
  index: number,
  heights: Map<string, number>,
  averageHeight: number,
): number => {
  const key = messageKey(messages[index], index);
  return (heights.get(key) ?? averageHeight) + ESTIMATED_MESSAGE_GAP;
};

const estimateHeightRange = (
  messages: any[],
  start: number,
  end: number,
  heights: Map<string, number>,
  averageHeight: number,
): number => {
  let total = 0;
  const safeStart = Math.max(0, start);
  const safeEnd = Math.min(messages.length, end);
  for (let index = safeStart; index < safeEnd; index += 1) {
    total += estimatedMessageHeight(messages, index, heights, averageHeight);
  }
  return total;
};

const computeVirtualRange = (
  messages: any[],
  scrollTop: number,
  viewportHeight: number,
  heights: Map<string, number>,
  averageHeight: number,
): VirtualRange => {
  const total = messages.length;
  if (total <= VIRTUALIZATION_THRESHOLD) return { start: 0, end: total };

  const overscanPx = averageHeight * VIRTUAL_OVERSCAN;
  const startOffset = Math.max(0, scrollTop - overscanPx);
  const endOffset = scrollTop + viewportHeight + overscanPx;
  let start = 0;
  let end = total;
  let offset = 0;

  for (let index = 0; index < total; index += 1) {
    const height = estimatedMessageHeight(messages, index, heights, averageHeight);
    const nextOffset = offset + height;
    if (nextOffset >= startOffset) {
      start = Math.max(0, index - VIRTUAL_OVERSCAN);
      break;
    }
    offset = nextOffset;
  }

  offset = 0;
  for (let index = 0; index < total; index += 1) {
    const height = estimatedMessageHeight(messages, index, heights, averageHeight);
    if (offset > endOffset) {
      end = Math.min(total, index + VIRTUAL_OVERSCAN);
      break;
    }
    offset += height;
  }

  return { start, end: Math.max(end, start + 1) };
};

const scrollOffsetWithinTarget = (root: HTMLElement, target: HTMLElement): number => {
  const rootRect = root.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  return rootRect.top - targetRect.top + target.scrollTop;
};

const MeasuredMessage: React.FC<{
  messageKey: string;
  onMeasure: (key: string, height: number) => void;
  children: React.ReactNode;
}> = ({ messageKey: key, onMeasure, children }) => {
  const ref = React.useRef<HTMLDivElement | null>(null);

  React.useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;

    const measure = () => onMeasure(key, node.getBoundingClientRect().height);
    measure();

    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [key, onMeasure]);

  return <div ref={ref}>{children}</div>;
};

const parseStatusMessagePayload = (rawText: any): { status: 'ok' | 'ko'; message: string } | null => {
  let payload: any = rawText;
  if (payload && typeof payload === 'object' && 'literalString' in payload) {
    payload = payload.literalString;
  }

  let candidate: any = null;
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    candidate = payload;
  } else {
    let text = String(payload ?? '').trim();
    if (!text) return null;
    if (text.startsWith('```')) {
      const lines = text.split('\n');
      if (lines.length >= 3 && lines[lines.length - 1]?.trim() === '```') {
        text = lines.slice(1, -1).join('\n').trim();
      }
    }
    try {
      candidate = JSON.parse(text);
    } catch {
      return null;
    }
  }

  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) return null;

  let status = String(candidate.status ?? '').trim().toLowerCase();
  if (status === 'error') status = 'ko';
  const message = String(candidate.message ?? '').trim();
  if ((status === 'ok' || status === 'ko') && message) {
    return { status: status as 'ok' | 'ko', message };
  }
  if (status === 'ko') {
    const error = String(candidate.error ?? '').trim();
    if (error) return { status: 'ko', message: error };
  }

  const okValue = candidate.ok;
  if (typeof okValue === 'boolean') {
    const derivedStatus: 'ok' | 'ko' = okValue ? 'ok' : 'ko';
    if (message) return { status: derivedStatus, message };
    const error = String(candidate.error ?? '').trim();
    if (error) return { status: 'ko', message: error };
    const fragments = ['status', 'ingestion', 'result', 'detail']
      .map((key) => String(candidate[key] ?? '').trim())
      .filter(Boolean)
      .map((value) => value.replaceAll('_', ' '));
    if (fragments.length) return { status: derivedStatus, message: fragments.join(' - ') };
    return { status: derivedStatus, message: okValue ? 'Operazione completata' : 'Operazione fallita' };
  }

  return null;
};

const CompactToolMessage: React.FC<{ rawText: any }> = ({ rawText }) => {
  const payload = parseStatusMessagePayload(rawText);
  const text = payload ? payload.message : String(getLiteral(rawText) || '');
  const icon = payload
    ? (payload.status === 'ok' ? 'ric.checkbox-circle-line' : 'ric.close-circle-line')
    : 'ric.information-line';
  const color = payload
    ? (payload.status === 'ok' ? 'ui-tone-success' : 'ui-tone-danger')
    : 'ui-tone-info';
  const iconClass = resolveIconClass(icon);

  return (
    <div className="flex items-start gap-2 text-sm leading-relaxed">
      <i className={cn(iconClass ?? '', 'mt-0.5 shrink-0 text-base', color)} />
      <span className="min-w-0 break-words text-foreground/95">{text}</span>
    </div>
  );
};

const normalizeSurfaceComponents = (message: any): any[] => {
  const content = message?.content && typeof message.content === 'object' ? message.content : {};
  const raw = Array.isArray(content?.components)
    ? content.components
    : (content?.component && typeof content.component === 'object'
      ? [content.component]
      : Array.isArray(message?.surface_components)
    ? message.surface_components
    : (Array.isArray(message?.components) ? message.components : []));
  return raw.filter((entry: any) => entry && typeof entry === 'object' && entry.component && typeof entry.component === 'object');
};

const normalizeAttachments = (message: any): AttachmentEntry[] => {
  const content = message?.content && typeof message.content === 'object' ? message.content : {};
  const raw = Array.isArray(content?.attachments) ? content.attachments : message?.attachments;
  if (!Array.isArray(raw)) return [];
  return raw.filter((entry: any) => entry && typeof entry === 'object');
};

const messageContent = (message: any): any => (
  message?.content && typeof message.content === 'object' && !Array.isArray(message.content) ? message.content : {}
);

const messageKind = (message: any): string => String(message?.kind || 'text').trim().toLowerCase() || 'text';

const formatMessageMeta = (value: any): string => {
  const raw = String(getLiteral(value) || '').trim();
  if (!raw) return '';
  if (!/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(raw)) return raw;
  let candidate = raw.replace(' ', 'T').replace(/\.(\d{3})\d+/, '.$1');
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(candidate)) candidate = `${candidate}Z`;
  const parsed = new Date(candidate);
  if (Number.isNaN(parsed.getTime())) return raw;
  return new Intl.DateTimeFormat(undefined, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
};

const messageText = (message: any): any => {
  const content = messageContent(message);
  return content.text ?? content.summary ?? message?.text ?? '';
};

const messageReasoning = (message: any): any => {
  const content = messageContent(message);
  return content.reasoning ?? message?.reasoning ?? '';
};

const messageTaskId = (message: any): string => {
  const content = messageContent(message);
  const meta = message?.meta && typeof message.meta === 'object' ? message.meta : {};
  return String(content.task_id || message?.task_id || meta.task_id || '').trim();
};

const statusTone = (status: any): string => {
  const value = String(status || '').trim().toLowerCase();
  if (['completed', 'success', 'ok'].includes(value)) return 'text-emerald-500';
  if (['failed', 'error', 'ko'].includes(value)) return 'text-red-500';
  if (['running', 'pending'].includes(value)) return 'text-blue-500';
  return 'text-muted-foreground';
};

const inferMime = (entry: AttachmentEntry): string => {
  const explicit = String(entry.mime_type || '').trim().toLowerCase();
  if (explicit) return explicit;
  const hint = String(entry.name || entry.storage_path || '').toLowerCase();
  if (hint.endsWith('.pdf')) return 'application/pdf';
  if (/\.(png|jpe?g|gif|webp|svg)$/.test(hint)) return 'image/*';
  return '';
};

const isPreviewable = (entry: AttachmentEntry): boolean => {
  const mime = inferMime(entry);
  return mime === 'application/pdf' || mime.startsWith('image/');
};

const cloneWithUniqueIds = (node: any, suffix: string): any => {
  if (!node || typeof node !== 'object') return node;
  const clone: any = Array.isArray(node) ? node.map((child) => cloneWithUniqueIds(child, suffix)) : { ...node };

  if (typeof clone.id === 'string' && clone.id.trim()) {
    clone.id = `${clone.id}_${suffix}`;
  }

  if (clone.component && typeof clone.component === 'object') {
    const componentType = Object.keys(clone.component)[0];
    const componentProps = clone.component[componentType];
    if (componentProps && typeof componentProps === 'object' && componentProps.id && typeof componentProps.id === 'string') {
      componentProps.id = `${componentProps.id}_${suffix}`;
    }
    if (componentType === 'Tabs' && componentProps && typeof componentProps === 'object' && Array.isArray(componentProps.tabs)) {
      componentProps.tabs = componentProps.tabs.map((tab: any) => (
        tab && typeof tab === 'object' && typeof tab.id === 'string' && tab.id.trim()
          ? { ...tab, id: `${tab.id}_${suffix}` }
          : tab
      ));
    }
  }

  if (clone.children && typeof clone.children === 'object' && Array.isArray(clone.children.explicitList)) {
    clone.children = {
      ...clone.children,
      explicitList: clone.children.explicitList.map((child: any) => cloneWithUniqueIds(child, suffix)),
    };
  }

  return clone;
};

const MessageCard: React.FC<any> = ({
  id,
  role,
  text,
  meta,
  reasoning,
  actions,
  message,
  onAction,
  style,
  surfaceId,
  surfaces,
  dataModel,
  stateModel,
  sendAction,
  setInput,
  userRole,
  userPermissions,
  onAttachmentClick,
}) => {
  const messageId = String(id || message?.id || '').trim();
  const normalizedRole = String(role || 'assistant').toLowerCase();
  const kind = messageKind(message);
  const isUser = normalizedRole === 'user';
  const isTool = normalizedRole === 'tool';
  const isTask = normalizedRole === 'task' || kind === 'task';
  const isComponent = kind === 'component';
  const textValue = messageText(message);
  const reasoningValue = messageReasoning(message);
  const taskId = isTask ? messageTaskId(message) : '';
  const [copied, setCopied] = React.useState(false);
  const [reasoningOpen, setReasoningOpen] = React.useState(false);

  const surfaceComponents = React.useMemo(() => {
    const normalized = normalizeSurfaceComponents(message);
    return normalized.map((entry: any, index: number) => cloneWithUniqueIds(entry, `${messageId || 'message'}_${index}`));
  }, [message, messageId]);

  const attachments = React.useMemo(() => normalizeAttachments(message), [message]);

  const onCopy = async () => {
    const plain = String(getLiteral(textValue) || '');
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(plain);
      }
    } catch {
      // Clipboard API can fail in non-secure contexts.
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  if (isTask) {
    return (
      <div className="w-full" style={parseStyle(style)}>
        <div className="mr-auto max-w-[88%]">
          {taskId ? (
            <BackgroundTaskCard task_id={taskId} sendAction={sendAction} />
          ) : (
            <div className="rounded-md border border-border/60 bg-muted/20 px-3 py-2 text-sm">
              <div className="font-medium">{String(messageContent(message).title || message?.title || 'Task')}</div>
              <div className={cn('text-xs', statusTone(message?.status))}>{String(message?.status || 'pending')}</div>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (isComponent) {
    return (
      <div className="w-full" style={parseStyle(style)}>
        <div className="mr-auto flex min-h-8 w-[80%] min-w-0 flex-col gap-2">
          {surfaceComponents.map((entry: any, index: number) => (
            <InternalRenderer
              key={`${messageId || 'message'}_component_${index}`}
              componentData={entry}
              surfaceId={surfaceId}
              surfaces={surfaces}
              dataModel={dataModel}
              stateModel={stateModel}
              sendAction={sendAction}
              setInput={setInput}
              componentId={String(entry?.id || `${messageId || 'message'}_component_${index}`)}
              userRole={userRole}
              userPermissions={userPermissions}
              item={message}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="w-full" style={parseStyle(style)}>
      <div className={`max-w-[88%] rounded-xl border px-3 py-2 ${isUser ? 'ml-auto bg-muted/50' : 'mr-auto bg-background'}`}>
        {!isTool ? (
          <div className="mb-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
            {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
            <span>{isUser ? 'User' : 'Assistant'}</span>
            <Button type="button" variant="ghost" size="icon" className="h-6 w-6" onClick={onCopy} title="Copy">
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
            {copied ? <span className="text-[10px] text-muted-foreground/90">Copied</span> : null}
          </div>
        ) : null}
        {isTool || kind === 'tool_call' || kind === 'tool_result' ? (
          <div className="rounded-md border border-border/60 bg-muted/20 px-2 py-1.5">
            <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
              <Hammer className="h-3.5 w-3.5" />
              <span>{String(messageContent(message).tool_name || messageContent(message).name || message?.name || 'Tool')}</span>
              {message?.status ? <span className={cn('ml-auto', statusTone(message.status))}>{String(message.status)}</span> : null}
            </div>
            <CompactToolMessage rawText={textValue} />
          </div>
        ) : isUser ? (
          <div className="whitespace-pre-wrap text-sm leading-relaxed">{getLiteral(textValue)}</div>
        ) : (
          <div className="prose prose-sm max-w-none dark:prose-invert prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-pre:my-2">
            <ReactMarkdown>{String(getLiteral(textValue) || '')}</ReactMarkdown>
          </div>
        )}

        {!!attachments.length && (
          <div className="mt-2 flex flex-col gap-1 rounded-md border border-border/50 p-2">
            {attachments.map((entry, index) => {
              const label = String(entry.name || entry.storage_path || `attachment_${index + 1}`);
              const previewable = isPreviewable(entry);
              return (
                <button
                  key={`${messageId || 'message'}_att_${index}`}
                  type="button"
                  className={`text-left text-xs ${previewable ? 'text-primary hover:underline' : 'text-muted-foreground'}`}
                  onClick={() => {
                    if (!previewable) return;
                    const payload = {
                      message_id: messageId,
                      message_role: String(role || ''),
                      name: label,
                      mime_type: inferMime(entry),
                      storage_path: String(entry.storage_path || ''),
                      file_id: String(entry.file_id || ''),
                      url: String(entry.url || ''),
                    };
                    if (onAttachmentClick && onAction) {
                      emitActionSpec(onAttachmentClick, onAction, payload);
                    }
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>
        )}

        {!isUser && String(reasoningValue || '').trim() ? (
          <div className="mt-2 rounded-md border border-border/60 bg-muted/20 px-2 py-1">
            <button
              type="button"
              className="flex w-full items-center gap-1 text-left text-xs font-medium text-muted-foreground"
              onClick={() => setReasoningOpen((v) => !v)}
            >
              <ChevronRight className={`h-3.5 w-3.5 transition-transform ${reasoningOpen ? 'rotate-90' : ''}`} />
              <span>Reasoning</span>
            </button>
            {reasoningOpen ? (
              <div className="mt-1 whitespace-pre-wrap text-xs text-muted-foreground/70">{String(reasoningValue)}</div>
            ) : null}
          </div>
        ) : null}

        {surfaceComponents.length ? (
          <div
            id={messageId ? `${messageId}_surface` : undefined}
            className="mt-2 flex min-h-8 flex-col gap-2 rounded-md border border-dashed border-border/60 p-2"
          >
            {surfaceComponents.map((entry: any, index: number) => (
              <InternalRenderer
                key={`${messageId || 'message'}_surface_component_${index}`}
                componentData={entry}
                surfaceId={surfaceId}
                surfaces={surfaces}
                dataModel={dataModel}
                stateModel={stateModel}
                sendAction={sendAction}
                setInput={setInput}
                componentId={String(entry?.id || `${messageId || 'message'}_surface_${index}`)}
                userRole={userRole}
                userPermissions={userPermissions}
                item={message}
              />
            ))}
          </div>
        ) : null}

        {!isTool ? (
        <div className="mt-2 flex items-center gap-1.5">
          {meta ? <span className="text-[11px] text-muted-foreground">{formatMessageMeta(meta)}</span> : null}
          <div className="ml-auto flex items-center gap-1">
            {Array.isArray(actions)
              ? actions.map((entry: any, index: number) => (
                <Button
                  key={`${messageId || 'message'}_action_${index}`}
                  type="button"
                  variant="ghost"
                  className="h-7 px-2 text-[11px]"
                  onClick={() => emitActionSpec(entry?.action, onAction, {})}
                >
                  {getLiteral(entry?.label || 'Action')}
                </Button>
              ))
              : null}
          </div>
        </div>
        ) : null}
      </div>
    </div>
  );
};

export const MessageList: React.FC<any> = ({
  id,
  messages = [],
  onAction,
  style,
  surfaceId,
  surfaces,
  dataModel,
  stateModel,
  sendAction,
  setInput,
  userRole,
  userPermissions,
  on_attachment_click,
  download_enabled,
  download_filename,
  on_load_more,
}) => {
  const rootRef = React.useRef<HTMLDivElement | null>(null);
  const loadMoreLastAtRef = React.useRef(0);
  const heightCacheRef = React.useRef<Map<string, number>>(new Map());
  const averageHeightRef = React.useRef(DEFAULT_MESSAGE_HEIGHT);
  const measureFrameRef = React.useRef<number | null>(null);
  const downloadEnabled = Boolean(download_enabled ?? false);
  const exportName = String(download_filename || 'messages.json').trim() || 'messages.json';
  const resolvedMessages = Array.isArray(messages) ? messages : [];
  const virtualEnabled = resolvedMessages.length > VIRTUALIZATION_THRESHOLD;
  const initialStart = virtualEnabled ? Math.max(0, resolvedMessages.length - 40) : 0;
  const [showScrollBottom, setShowScrollBottom] = React.useState(false);
  const [virtualRange, setVirtualRange] = React.useState<VirtualRange>({
    start: initialStart,
    end: resolvedMessages.length,
  });
  const scrollSnapshotRef = React.useRef<{
    count: number;
    firstId: string;
    lastId: string;
    scrollTop: number;
    scrollHeight: number;
    clientHeight: number;
  } | null>(null);

  const scrollTarget = React.useCallback((): HTMLElement | null => {
    const root = rootRef.current;
    if (!root) return null;
    const viewport = root.closest('[data-radix-scroll-area-viewport]') as HTMLElement | null;
    return viewport ?? root.parentElement;
  }, []);

  const updateScrollBottomVisibility = React.useCallback(() => {
    const target = scrollTarget();
    if (!target) {
      setShowScrollBottom(false);
      return;
    }
    const distance = target.scrollHeight - (target.scrollTop + target.clientHeight);
    setShowScrollBottom(distance > 160);
  }, [scrollTarget]);

  const scrollToBottom = React.useCallback(() => {
    const target = scrollTarget();
    if (!target) return;
    target.scrollTo({ top: target.scrollHeight, behavior: 'smooth' });
  }, [scrollTarget]);

  const updateVirtualRange = React.useCallback(() => {
    if (!virtualEnabled) {
      setVirtualRange((previous) => (
        previous.start === 0 && previous.end === resolvedMessages.length
          ? previous
          : { start: 0, end: resolvedMessages.length }
      ));
      return;
    }

    const root = rootRef.current;
    const target = scrollTarget();
    if (!root || !target) {
      const end = resolvedMessages.length;
      const start = Math.max(0, end - 40);
      setVirtualRange((previous) => (
        previous.start === start && previous.end === end ? previous : { start, end }
      ));
      return;
    }

    const listOffset = scrollOffsetWithinTarget(root, target);
    const listScrollTop = Math.max(0, target.scrollTop - listOffset);
    const next = computeVirtualRange(
      resolvedMessages,
      listScrollTop,
      target.clientHeight,
      heightCacheRef.current,
      averageHeightRef.current,
    );
    setVirtualRange((previous) => (
      previous.start === next.start && previous.end === next.end ? previous : next
    ));
  }, [resolvedMessages, scrollTarget, virtualEnabled]);

  const scheduleVirtualRangeUpdate = React.useCallback(() => {
    if (measureFrameRef.current !== null) return;
    measureFrameRef.current = window.requestAnimationFrame(() => {
      measureFrameRef.current = null;
      updateVirtualRange();
    });
  }, [updateVirtualRange]);

  const onMeasureMessage = React.useCallback((key: string, height: number) => {
    if (!virtualEnabled || height <= 0) return;
    const previous = heightCacheRef.current.get(key);
    if (previous !== undefined && Math.abs(previous - height) < 1) return;
    heightCacheRef.current.set(key, height);
    const measured = Array.from(heightCacheRef.current.values());
    averageHeightRef.current = measured.length
      ? measured.reduce((total, value) => total + value, 0) / measured.length
      : DEFAULT_MESSAGE_HEIGHT;
    scheduleVirtualRangeUpdate();
  }, [scheduleVirtualRangeUpdate, virtualEnabled]);

  React.useLayoutEffect(() => {
    const target = scrollTarget();
    if (!target) return;

    const firstId = String(resolvedMessages[0]?.id || '');
    const lastId = String(resolvedMessages[resolvedMessages.length - 1]?.id || '');
    const previous = scrollSnapshotRef.current;
    const nearBottom = previous
      ? previous.scrollHeight - (previous.scrollTop + previous.clientHeight) <= 96
      : true;

    if (!previous) {
      target.scrollTo({ top: target.scrollHeight, behavior: 'auto' });
    } else if (resolvedMessages.length > previous.count) {
      const prepended = previous.lastId === lastId && previous.firstId !== firstId;
      const appended = previous.lastId !== lastId && previous.firstId === firstId;
      if (prepended) {
        target.scrollTop = previous.scrollTop + (target.scrollHeight - previous.scrollHeight);
      } else if (appended && nearBottom) {
        target.scrollTo({ top: target.scrollHeight, behavior: 'smooth' });
      }
    }

    scrollSnapshotRef.current = {
      count: resolvedMessages.length,
      firstId,
      lastId,
      scrollTop: target.scrollTop,
      scrollHeight: target.scrollHeight,
      clientHeight: target.clientHeight,
    };
    updateVirtualRange();
    updateScrollBottomVisibility();
  }, [resolvedMessages, scrollTarget, updateScrollBottomVisibility, updateVirtualRange]);

  React.useEffect(() => {
    updateVirtualRange();
    updateScrollBottomVisibility();
  }, [updateScrollBottomVisibility, updateVirtualRange]);

  React.useEffect(() => {
    const target = scrollTarget();
    if (!target) return;

    const onScroll = () => {
      if (virtualEnabled) updateVirtualRange();
      updateScrollBottomVisibility();
    };
    target.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      target.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (measureFrameRef.current !== null) {
        window.cancelAnimationFrame(measureFrameRef.current);
        measureFrameRef.current = null;
      }
    };
  }, [scrollTarget, updateScrollBottomVisibility, updateVirtualRange, virtualEnabled]);

  React.useEffect(() => {
    if (!on_load_more || !onAction) return;
    const target = scrollTarget();
    if (!target) return;

    const onScroll = () => {
      if (target.scrollHeight <= target.clientHeight + 32) return;
      if (target.scrollTop > 32) return;
      const now = Date.now();
      if (now - loadMoreLastAtRef.current < 700) return;
      loadMoreLastAtRef.current = now;
      scrollSnapshotRef.current = {
        count: resolvedMessages.length,
        firstId: String(resolvedMessages[0]?.id || ''),
        lastId: String(resolvedMessages[resolvedMessages.length - 1]?.id || ''),
        scrollTop: target.scrollTop,
        scrollHeight: target.scrollHeight,
        clientHeight: target.clientHeight,
      };
      emitActionSpec(on_load_more, onAction, { target: id, source: 'scroll_top' });
    };

    target.addEventListener('scroll', onScroll, { passive: true });
    return () => target.removeEventListener('scroll', onScroll);
  }, [id, onAction, on_load_more, resolvedMessages, scrollTarget]);

  const onDownload = () => {
    const payload = JSON.stringify(resolvedMessages, null, 2);
    const blob = new Blob([payload], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = exportName;
    link.click();
    URL.revokeObjectURL(url);
  };

  const safeRange = virtualEnabled
    ? {
      start: Math.max(0, Math.min(virtualRange.start, resolvedMessages.length)),
      end: Math.max(
        Math.max(0, Math.min(virtualRange.start, resolvedMessages.length)),
        Math.min(virtualRange.end, resolvedMessages.length),
      ),
    }
    : { start: 0, end: resolvedMessages.length };
  const visibleMessages = virtualEnabled
    ? resolvedMessages.slice(safeRange.start, safeRange.end)
    : resolvedMessages;
  const topSpacer = virtualEnabled
    ? estimateHeightRange(
      resolvedMessages,
      0,
      safeRange.start,
      heightCacheRef.current,
      averageHeightRef.current,
    )
    : 0;
  const bottomSpacer = virtualEnabled
    ? estimateHeightRange(
      resolvedMessages,
      safeRange.end,
      resolvedMessages.length,
      heightCacheRef.current,
      averageHeightRef.current,
    )
    : 0;

  return (
    <div ref={rootRef} id={id} className={"relative flex min-h-0 flex-col gap-3 thread_messages "+id} style={parseStyle(style)}>
      {downloadEnabled ? (
        <div className="sticky top-0 z-10 flex justify-end bg-background/95 py-1 backdrop-blur supports-[backdrop-filter]:bg-background/75">
          <Button type="button" variant="outline" className="h-8 gap-1.5 text-xs" onClick={onDownload}>
            <Download className="h-3.5 w-3.5" />
            Download
          </Button>
        </div>
      ) : null}

      {virtualEnabled && topSpacer > 0 ? <div aria-hidden="true" style={{ height: topSpacer, flexShrink: 0 }} /> : null}

      {visibleMessages.map((message: any, visibleIndex: number) => {
        const index = safeRange.start + visibleIndex;
        const key = messageKey(message, index);
        const card = (
          <MessageCard
            id={message?.id}
            role={message?.role}
            text={message?.text}
            meta={message?.meta ?? message?.created_at}
            reasoning={message?.reasoning}
            actions={message?.actions}
            message={message}
            onAction={onAction}
            surfaceId={surfaceId}
            surfaces={surfaces}
            dataModel={dataModel}
            stateModel={stateModel}
            sendAction={sendAction}
            setInput={setInput}
            userRole={userRole}
            userPermissions={userPermissions}
            onAttachmentClick={on_attachment_click}
          />
        );
        return virtualEnabled ? (
          <MeasuredMessage key={key} messageKey={key} onMeasure={onMeasureMessage}>
            {card}
          </MeasuredMessage>
        ) : (
          <React.Fragment key={key}>{card}</React.Fragment>
        );
      })}

      {virtualEnabled && bottomSpacer > 0 ? <div aria-hidden="true" style={{ height: bottomSpacer, flexShrink: 0 }} /> : null}

      {showScrollBottom ? (
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="sticky bottom-4 z-20 mx-auto h-9 w-9 rounded-full bg-background/95 shadow-sm backdrop-blur"
          onClick={scrollToBottom}
          title="Scroll to bottom"
        >
          <ArrowDown className="h-4 w-4" />
        </Button>
      ) : null}
    </div>
  );
};
