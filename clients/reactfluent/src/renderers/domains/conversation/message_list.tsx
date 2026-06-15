import React from 'react';
import { InternalRenderer } from '@/components/a2ui/Renderer';
import { cn } from '@/lib/utils';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { resolveIconClass } from '@/utils/icons';
import ReactMarkdown from 'react-markdown';
import { BackgroundTaskCard } from '@/renderers/domains/tasks/background_task_card';

type AttachmentEntry = {
  name?: string;
  mime?: string;
  path?: string;
  source_path?: string;
  file_id?: string;
  media_file_id?: string;
  url?: string;
};

const VIRTUALIZATION_THRESHOLD = 30;
const VIRTUAL_OVERSCAN = 8;
const DEFAULT_MESSAGE_HEIGHT = 128;
const ESTIMATED_MESSAGE_GAP = 8;

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
    return { status: derivedStatus, message: okValue ? 'Operation completed' : 'Operation failed' };
  }

  return null;
};

const CompactToolMessage: React.FC<{ rawText: any }> = ({ rawText }) => {
  const payload = parseStatusMessagePayload(rawText);
  const text = payload ? payload.message : String(getLiteral(rawText) || '');
  const icon = payload
    ? (payload.status === 'ok' ? 'ri-checkbox-circle-line' : 'ri-close-circle-line')
    : 'ri-information-line';
  const colorClass = payload
    ? (payload.status === 'ok' ? 'text-success' : 'text-danger')
    : 'text-info';

  return (
    <div className="d-flex align-items-start gap-2 small">
      <i className={cn(icon, 'mt-1 flex-shrink-0', colorClass)} />
      <span className="text-break">{text}</span>
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

const statusClass = (status: any): string => {
  const value = String(status || '').trim().toLowerCase();
  if (['completed', 'success', 'ok'].includes(value)) return 'text-success';
  if (['failed', 'error', 'ko'].includes(value)) return 'text-danger';
  if (['running', 'pending'].includes(value)) return 'text-primary';
  return 'text-muted';
};

const inferMime = (entry: AttachmentEntry): string => {
  const explicit = String(entry.mime || '').trim().toLowerCase();
  if (explicit) return explicit;
  const hint = String(entry.name || entry.path || entry.source_path || '').toLowerCase();
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
    } catch { }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  if (isTask) {
    return (
      <div className="a2ui-chat-message-row" style={parseStyle(style)}>
        <div className="a2ui-chat-message-card a2ui-chat-message-task">
          {taskId ? (
            <BackgroundTaskCard task_id={taskId} sendAction={sendAction} />
          ) : (
            <div className="a2ui-chat-tool-card">
              <div className="a2ui-chat-tool-title">{String(messageContent(message).title || message?.title || 'Task')}</div>
              <div className={statusClass(message?.status)}>{String(message?.status || 'pending')}</div>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (isComponent) {
    return (
      <div className="a2ui-chat-message-row" style={parseStyle(style)}>
        <div className="a2ui-chat-message-card a2ui-chat-message-component">
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
    <div className={cn("a2ui-chat-message-row", isUser && "is-user")} style={parseStyle(style)}>
      <div className={cn(
        "a2ui-chat-message-card",
        isUser ? "is-user" : "is-assistant",
        isTool && "is-tool"
      )}>
        {!isTool && (
          <div className="a2ui-chat-message-meta">
            <i className={isUser ? "ri-user-line" : "ri-robot-line"} />
            <span>{isUser ? 'User' : 'Assistant'}</span>
            <button type="button" className="a2ui-chat-icon-button" onClick={onCopy} title="Copy" aria-label="Copy message">
              <i className={copied ? "ri-check-line text-success" : "ri-file-copy-line"} />
            </button>
            {copied && <span className="a2ui-chat-copy-state">Copied</span>}
          </div>
        )}

        {isTool || kind === 'tool_call' || kind === 'tool_result' ? (
          <div className="a2ui-chat-tool-card">
            <div className="a2ui-chat-tool-header">
              <i className="ri-tools-line" />
              <span>{String(messageContent(message).tool_name || messageContent(message).name || message?.name || 'Tool')}</span>
              {message?.status ? <span className={cn('a2ui-chat-tool-status', statusClass(message.status))}>{String(message.status)}</span> : null}
            </div>
            <CompactToolMessage rawText={textValue} />
          </div>
        ) : isUser ? (
          <div className="a2ui-chat-message-text">{getLiteral(textValue)}</div>
        ) : (
          <div className="markdown-content a2ui-chat-markdown">
            <ReactMarkdown>{String(getLiteral(textValue) || '')}</ReactMarkdown>
          </div>
        )}

        {!!attachments.length && (
          <div className="a2ui-chat-attachments">
            {attachments.map((entry, index) => {
              const label = String(entry.name || entry.path || entry.source_path || `allegato_${index + 1}`);
              const previewable = isPreviewable(entry);
              return (
                <button
                  key={`${messageId || 'message'}_att_${index}`}
                  type="button"
                  className={cn("a2ui-chat-attachment", previewable && "is-previewable")}
                  onClick={() => {
                    if (!previewable) return;
                    const payload = {
                      message_id: messageId,
                      message_role: String(role || ''),
                      name: label,
                      mime: inferMime(entry),
                      path: String(entry.path || ''),
                      source_path: String(entry.source_path || ''),
                      file_id: String(entry.file_id || entry.media_file_id || ''),
                      url: String(entry.url || ''),
                    };
                    if (onAttachmentClick && onAction) {
                      emitActionSpec(onAttachmentClick, onAction, payload);
                    }
                  }}
                >
                  <i className={inferMime(entry).startsWith('image/') ? "ri-image-line" : "ri-file-text-line"} />
                  <span className="text-truncate">{label}</span>
                </button>
              );
            })}
          </div>
        )}

        {!isUser && String(reasoningValue || '').trim() ? (
          <div className="a2ui-chat-reasoning">
            <button
              type="button"
              className="a2ui-chat-reasoning-trigger"
              onClick={() => setReasoningOpen((v) => !v)}
            >
              <i className={cn("ri-arrow-right-s-line transition-transform", reasoningOpen && "rotate-90")} />
              <span>Assistant Reasoning</span>
            </button>
            {reasoningOpen && (
              <div className="a2ui-chat-reasoning-content">
                {String(reasoningValue)}
              </div>
            )}
          </div>
        ) : null}

        {surfaceComponents.length > 0 && (
          <div
            id={messageId ? `${messageId}_surface` : undefined}
            className="a2ui-chat-surface"
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
        )}

        {!isTool && (
          <div className="a2ui-chat-message-footer">
            {meta ? <span>{formatMessageMeta(meta)}</span> : <div />}
            <div className="a2ui-chat-message-actions">
              {Array.isArray(actions) && actions.map((entry: any, index: number) => (
                <button
                  type="button"
                  key={`${messageId || 'message'}_action_${index}`}
                  className="a2ui-chat-action"
                  onClick={() => emitActionSpec(entry?.action, onAction, {})}
                >
                  {getLiteral(entry?.label || 'Action')}
                </button>
              ))}
            </div>
          </div>
        )}
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
    const viewport = root.closest('.scroll-area-viewport') as HTMLElement | null;
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
    <div ref={rootRef} id={id} className={cn("a2ui-message-list", id)} style={parseStyle(style)}>
      {downloadEnabled && (
        <div className="a2ui-message-list-toolbar">
          <button type="button" className="a2ui-chat-action a2ui-chat-download" onClick={onDownload}>
            <i className="ri-download-2-line" />
            Download History
          </button>
        </div>
      )}

      {virtualEnabled && topSpacer > 0 ? <div aria-hidden="true" style={{ height: topSpacer, flexShrink: 0 }} /> : null}

      {visibleMessages.map((message: any, visibleIndex: number) => {
        const index = safeRange.start + visibleIndex;
        const key = messageKey(message, index);
        const card = (
          <MessageCard
            id={message?.id}
            role={message?.role}
            text={message?.text}
            meta={message?.meta}
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
        <button
          type="button"
          className="a2ui-message-scroll-bottom position-sticky bottom-0 z-3 mx-auto shadow-sm"
          onClick={scrollToBottom}
          title="Go to latest message"
          aria-label="Go to latest message"
        >
          <i className="ri-arrow-down-line" />
        </button>
      ) : null}
    </div>
  );
};
