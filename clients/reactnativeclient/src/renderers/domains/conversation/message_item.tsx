import React from 'react';
import { Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import MarkdownDisplay from 'react-native-markdown-display';
import { InternalRenderer } from '../../../components/a2ui/Renderer';
import { Icon } from '../../../components/a2ui/Icon';
import { emitActionSpec, getLiteral } from '../../shared';

type AttachmentEntry = {
  name?: string;
  mime_type?: string;
  mimeType?: string;
  type?: string;
  storage_path?: string;
  file_id?: string;
  url?: string;
  uri?: string;
};

const messageContent = (message: any): any => (
  message?.content && typeof message.content === 'object' && !Array.isArray(message.content) ? message.content : {}
);

const messageKind = (message: any): string => String(message?.kind || 'text').trim().toLowerCase() || 'text';

const messageText = (message: any): any => {
  const content = messageContent(message);
  return content.text ?? content.markdown ?? content.summary ?? message?.text ?? message?.markdown ?? message?.value ?? '';
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

const normalizeSurfaceComponents = (message: any): any[] => {
  const content = messageContent(message);
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
  const content = messageContent(message);
  const raw = Array.isArray(content?.attachments) ? content.attachments : message?.attachments;
  if (!Array.isArray(raw)) return [];
  return raw.filter((entry: any) => entry && typeof entry === 'object');
};

const cloneWithUniqueIds = (node: any, suffix: string): any => {
  if (!node || typeof node !== 'object') return node;
  const clone: any = Array.isArray(node) ? node.map((child) => cloneWithUniqueIds(child, suffix)) : { ...node };

  if (typeof clone.id === 'string' && clone.id.trim()) clone.id = `${clone.id}_${suffix}`;

  if (clone.component && typeof clone.component === 'object') {
    const componentType = Object.keys(clone.component)[0];
    const componentProps = clone.component[componentType];
    if (componentProps && typeof componentProps === 'object' && typeof componentProps.id === 'string' && componentProps.id.trim()) {
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

const inferMime = (entry: AttachmentEntry): string => {
  const explicit = String(entry.mime_type || entry.mimeType || entry.type || '').trim().toLowerCase();
  if (explicit) return explicit;
  const hint = String(entry.name || entry.storage_path || entry.url || entry.uri || '').toLowerCase();
  if (hint.endsWith('.pdf')) return 'application/pdf';
  if (/\.(png|jpe?g|gif|webp|svg)$/.test(hint)) return 'image/*';
  return '';
};

const isImageAttachment = (entry: AttachmentEntry): boolean => inferMime(entry).startsWith('image/');

const formatMessageMeta = (value: any): string => {
  const raw = String(getLiteral(value) || '').trim();
  if (!raw) return '';
  if (!/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(raw)) return raw;
  let candidate = raw.replace(' ', 'T').replace(/\.(\d{3})\d+/, '.$1');
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(candidate)) candidate = `${candidate}Z`;
  const parsed = new Date(candidate);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleString(undefined, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};

const parseStatusMessagePayload = (rawText: any): { status: 'ok' | 'ko'; message: string } | null => {
  let payload: any = rawText;
  if (payload && typeof payload === 'object' && 'literalString' in payload) payload = payload.literalString;

  let candidate: any = null;
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    candidate = payload;
  } else {
    let text = String(payload ?? '').trim();
    if (!text) return null;
    if (text.startsWith('```')) {
      const lines = text.split('\n');
      if (lines.length >= 3 && lines[lines.length - 1]?.trim() === '```') text = lines.slice(1, -1).join('\n').trim();
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
  const message = String(candidate.message ?? candidate.error ?? '').trim();
  if ((status === 'ok' || status === 'ko') && message) return { status: status as 'ok' | 'ko', message };
  if (typeof candidate.ok === 'boolean') return { status: candidate.ok ? 'ok' : 'ko', message: message || (candidate.ok ? 'Operazione completata' : 'Operazione fallita') };
  return null;
};

export const MessageItem: React.FC<any> = ({
  id,
  role,
  text,
  reasoning,
  actions = [],
  meta,
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
  pendingActions,
  backgroundTasks,
  jwt,
  onAttachmentClick,
}) => {
  const fullMessage = message || { id, role, text, reasoning, actions, meta };
  const messageId = String(id || fullMessage?.id || '').trim();
  const normalizedRole = String(role || fullMessage?.role || 'assistant').toLowerCase();
  const kind = messageKind(fullMessage);
  const isUser = normalizedRole === 'user';
  const isTool = normalizedRole === 'tool' || kind === 'tool_call' || kind === 'tool_result';
  const isTask = normalizedRole === 'task' || kind === 'task';
  const isComponent = kind === 'component';
  const textValue = messageText(fullMessage);
  const displayText = String(getLiteral(textValue) || '').trim();
  const reasoningText = String(getLiteral(reasoning ?? messageReasoning(fullMessage)) || '').trim();
  const attachments = React.useMemo(() => normalizeAttachments(fullMessage), [fullMessage]);
  const surfaceComponents = React.useMemo(() => (
    normalizeSurfaceComponents(fullMessage).map((entry, index) => cloneWithUniqueIds(entry, `${messageId || 'message'}_${index}`))
  ), [fullMessage, messageId]);
  const [reasoningOpen, setReasoningOpen] = React.useState(false);

  const renderComponents = (variant: 'inline' | 'componentOnly') => {
    if (!surfaceComponents.length) return null;
    return (
      <View style={variant === 'componentOnly' ? styles.componentOnlyWrap : styles.embeddedSurface}>
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
            pendingActions={pendingActions}
            backgroundTasks={backgroundTasks}
            jwt={jwt}
            item={fullMessage}
          />
        ))}
      </View>
    );
  };

  if (isTask) {
    const taskId = messageTaskId(fullMessage);
    return (
      <View style={[styles.row, styles.assistantRow, style]}>
        <View style={[styles.bubble, styles.assistantBubble, styles.taskBubble]}>
          <View style={styles.headerLine}>
            <Icon name="ri-hammer-line" size={14} color="#8B949E" />
            <Text style={styles.senderText}>Task</Text>
          </View>
          <Text style={styles.assistantText}>{taskId || displayText || getLiteral(fullMessage?.title || 'Background task')}</Text>
          {fullMessage?.status ? <Text style={styles.metaText}>{String(fullMessage.status)}</Text> : null}
        </View>
      </View>
    );
  }

  if (isComponent) {
    return (
      <View style={[styles.row, styles.assistantRow, style]}>
        {renderComponents('componentOnly')}
      </View>
    );
  }

  return (
    <View style={[styles.row, isUser ? styles.userRow : styles.assistantRow, style]}>
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.assistantBubble, isTool && styles.toolBubble]}>
        <View style={styles.headerLine}>
          <Icon
            name={isUser ? 'ri-user-3-line' : isTool ? 'ri-hammer-line' : 'ri-robot-2-line'}
            size={14}
            color={isUser ? '#FFFFFF' : '#8B949E'}
          />
          <Text style={[styles.senderText, isUser && styles.userSenderText]}>{isUser ? 'User' : isTool ? 'Tool' : 'Assistant'}</Text>
          {meta ? <Text style={[styles.metaText, isUser && styles.userMetaText]} numberOfLines={1}>{formatMessageMeta(meta)}</Text> : null}
        </View>

        {isTool ? (
          <ToolMessage textValue={textValue} />
        ) : displayText ? (
          isUser ? (
            <Text style={styles.userText}>{displayText}</Text>
          ) : (
            <MarkdownDisplay style={markdownStyles}>{displayText}</MarkdownDisplay>
          )
        ) : surfaceComponents.length || attachments.length ? null : (
          <Text style={isUser ? styles.userMutedText : styles.mutedText}>Messaggio vuoto</Text>
        )}

        {attachments.length ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.attachments}>
            {attachments.map((entry, index) => {
              const label = String(entry.name || entry.storage_path || `attachment_${index + 1}`);
              const source = String(entry.url || entry.uri || '').trim();
              return (
                <TouchableOpacity
                  key={`${messageId || 'message'}_att_${index}`}
                  style={styles.attachmentCard}
                  onPress={() => {
                    if (!onAttachmentClick || !onAction) return;
                    emitActionSpec(onAttachmentClick, onAction, {
                      message_id: messageId,
                      message_role: normalizedRole,
                      name: label,
                      mime_type: inferMime(entry),
                      storage_path: String(entry.storage_path || ''),
                      file_id: String(entry.file_id || ''),
                      url: source,
                    });
                  }}
                >
                  <View style={styles.attachmentPreview}>
                    {isImageAttachment(entry) && source ? (
                      <Image source={{ uri: source }} style={styles.attachmentImage} />
                    ) : (
                      <Icon name="ri-file-text-line" size={18} color="#8B949E" />
                    )}
                  </View>
                  <Text style={styles.attachmentName} numberOfLines={1}>{label}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        ) : null}

        {reasoningText && !isUser ? (
          <View style={styles.reasoningBox}>
            <TouchableOpacity style={styles.reasoningTrigger} onPress={() => setReasoningOpen((prev) => !prev)}>
              <Icon name={reasoningOpen ? 'ri-arrow-down-s-line' : 'ri-arrow-right-s-line'} size={16} color="#8B949E" />
              <Text style={styles.reasoningTitle}>Reasoning</Text>
            </TouchableOpacity>
            {reasoningOpen ? <Text style={styles.reasoningText}>{reasoningText}</Text> : null}
          </View>
        ) : null}

        {renderComponents('inline')}

        {Array.isArray(actions) && actions.length > 0 ? (
          <View style={styles.actions}>
            {actions.map((entry: any, index: number) => (
              <TouchableOpacity
                key={`${messageId || 'message'}_action_${index}`}
                style={[styles.actionBtn, isUser && styles.userActionBtn]}
                onPress={() => emitActionSpec(entry?.action, onAction, {})}
                activeOpacity={0.75}
              >
                <Text style={[styles.actionText, isUser && styles.userActionText]} numberOfLines={1}>
                  {getLiteral(entry?.label || 'Action')}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        ) : null}
      </View>
    </View>
  );
};

const ToolMessage: React.FC<{ textValue: any }> = ({ textValue }) => {
  const payload = parseStatusMessagePayload(textValue);
  const text = payload ? payload.message : String(getLiteral(textValue) || '');
  const color = payload?.status === 'ok' ? '#3FB950' : payload?.status === 'ko' ? '#F85149' : '#8B949E';
  return (
    <View style={styles.toolContent}>
      <Icon name={payload?.status === 'ok' ? 'ri-checkbox-circle-line' : payload?.status === 'ko' ? 'ri-close-circle-line' : 'ri-information-line'} size={16} color={color} />
      <Text style={styles.assistantText}>{text}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  row: {
    width: '100%',
    flexDirection: 'row',
    paddingHorizontal: 10,
    marginVertical: 5,
  },
  assistantRow: {
    justifyContent: 'flex-start',
  },
  userRow: {
    justifyContent: 'flex-end',
  },
  bubble: {
    maxWidth: '88%',
    minWidth: 72,
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: 1,
  },
  assistantBubble: {
    backgroundColor: '#161B22',
    borderColor: '#30363D',
    borderBottomLeftRadius: 5,
  },
  userBubble: {
    backgroundColor: '#1F6FEB',
    borderColor: '#388BFD',
    borderBottomRightRadius: 5,
  },
  toolBubble: {
    backgroundColor: '#0D1117',
    borderStyle: 'dashed',
  },
  taskBubble: {
    maxWidth: '92%',
  },
  headerLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginBottom: 5,
  },
  senderText: {
    color: '#8B949E',
    fontSize: 11,
    fontWeight: '700',
  },
  userSenderText: {
    color: '#DDEBFF',
  },
  metaText: {
    marginLeft: 'auto',
    color: '#6E7681',
    fontSize: 10,
  },
  userMetaText: {
    color: '#C7DBFF',
  },
  assistantText: {
    color: '#E6EDF3',
    fontSize: 14,
    lineHeight: 20,
  },
  userText: {
    color: '#FFFFFF',
    fontSize: 14,
    lineHeight: 20,
  },
  mutedText: {
    color: '#6E7681',
    fontSize: 13,
    fontStyle: 'italic',
  },
  userMutedText: {
    color: '#DDEBFF',
    fontSize: 13,
    fontStyle: 'italic',
  },
  toolContent: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'flex-start',
  },
  attachments: {
    gap: 8,
    paddingTop: 8,
  },
  attachmentCard: {
    width: 126,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#0D1117',
    padding: 6,
    gap: 5,
  },
  attachmentPreview: {
    height: 54,
    borderRadius: 6,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#161B22',
  },
  attachmentImage: {
    width: '100%',
    height: '100%',
    resizeMode: 'cover',
  },
  attachmentName: {
    color: '#C9D1D9',
    fontSize: 11,
    fontWeight: '600',
  },
  reasoningBox: {
    marginTop: 8,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#0D1117',
    padding: 7,
  },
  reasoningTrigger: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  reasoningTitle: {
    color: '#8B949E',
    fontSize: 12,
    fontWeight: '700',
  },
  reasoningText: {
    color: '#8B949E',
    fontSize: 12,
    lineHeight: 17,
    marginTop: 6,
  },
  embeddedSurface: {
    marginTop: 8,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: '#30363D',
    borderRadius: 8,
    padding: 8,
    gap: 8,
  },
  componentOnlyWrap: {
    width: '92%',
    gap: 8,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#30363D',
  },
  actionBtn: {
    maxWidth: 170,
    backgroundColor: '#21262D',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 7,
    borderWidth: 1,
    borderColor: '#30363D',
  },
  userActionBtn: {
    backgroundColor: '#FFFFFF22',
    borderColor: '#FFFFFF44',
  },
  actionText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#58A6FF',
  },
  userActionText: {
    color: '#FFFFFF',
  },
});

const markdownStyles = StyleSheet.create({
  body: {
    color: '#E6EDF3',
    fontSize: 14,
    lineHeight: 20,
  },
  paragraph: {
    marginTop: 0,
    marginBottom: 8,
  },
  text: {
    color: '#E6EDF3',
  },
  heading1: {
    color: '#E6EDF3',
    fontSize: 20,
    fontWeight: '700',
    marginTop: 4,
    marginBottom: 8,
  },
  heading2: {
    color: '#E6EDF3',
    fontSize: 18,
    fontWeight: '700',
    marginTop: 4,
    marginBottom: 8,
  },
  bullet_list: {
    marginBottom: 8,
  },
  ordered_list: {
    marginBottom: 8,
  },
  code_inline: {
    color: '#E6EDF3',
    backgroundColor: '#0D1117',
    borderRadius: 4,
    paddingHorizontal: 4,
    fontFamily: 'Menlo',
  },
  fence: {
    color: '#E6EDF3',
    backgroundColor: '#0D1117',
    borderColor: '#30363D',
    borderWidth: 1,
    borderRadius: 6,
    padding: 8,
    fontFamily: 'Menlo',
  },
  link: {
    color: '#58A6FF',
  },
});
