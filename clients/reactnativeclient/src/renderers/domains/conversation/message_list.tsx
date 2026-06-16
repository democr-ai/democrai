import React from 'react';
import { InteractionManager, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Icon } from '../../../components/a2ui/Icon';
import { MessageItem } from './message_item';
import { emitActionSpec } from '../../shared';

const messageKey = (message: any, index: number): string => String(message?.id || `msg_${index}`);

const messageSignature = (message: any): string => {
  if (!message || typeof message !== 'object') return '';
  const content = message.content && typeof message.content === 'object' ? message.content : {};
  const text = content.text ?? content.markdown ?? content.summary ?? message.text ?? message.markdown ?? message.value ?? '';
  const status = message.status ?? content.status ?? '';
  const kind = message.kind ?? '';
  return `${kind}:${status}:${String(text).length}`;
};

export const MessageList: React.FC<any> = ({
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
  pendingActions,
  backgroundTasks,
  jwt,
  on_attachment_click,
  on_load_more,
  id,
}) => {
  const scrollRef = React.useRef<ScrollView | null>(null);
  const isAtBottomRef = React.useRef(true);
  const didInitialScrollRef = React.useRef(false);
  const forceFollowRef = React.useRef(true);
  const loadMoreLastAtRef = React.useRef(0);
  const scrollMetricsRef = React.useRef({ y: 0, contentHeight: 0, viewportHeight: 0 });
  const prependSnapshotRef = React.useRef<{ count: number; firstId: string; contentHeight: number; y: number } | null>(null);
  const lastMessageCountRef = React.useRef(0);
  const resolvedMessages = Array.isArray(messages) ? messages : [];
  const firstMessageId = String(resolvedMessages[0]?.id || '');
  const lastMessageId = String(resolvedMessages[resolvedMessages.length - 1]?.id || '');
  const lastMessageSignature = messageSignature(resolvedMessages[resolvedMessages.length - 1]);
  const [showJump, setShowJump] = React.useState(false);

  const scrollToBottom = React.useCallback((animated = true) => {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollToEnd({ animated });
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated }), 80);
    });
  }, []);

  const scrollToBottomAfterOpen = React.useCallback(() => {
    if (didInitialScrollRef.current || !resolvedMessages.length) return;
    didInitialScrollRef.current = true;
    isAtBottomRef.current = true;
    setShowJump(false);

    InteractionManager.runAfterInteractions(() => {
      scrollRef.current?.scrollToEnd({ animated: false });
      [50, 150, 350, 700].forEach((delay) => {
        setTimeout(() => scrollRef.current?.scrollToEnd({ animated: false }), delay);
      });
    });
  }, [resolvedMessages.length]);

  React.useEffect(() => {
    const countChanged = lastMessageCountRef.current !== resolvedMessages.length;
    lastMessageCountRef.current = resolvedMessages.length;
    const snapshot = prependSnapshotRef.current;
    if (snapshot && resolvedMessages.length > snapshot.count && firstMessageId !== snapshot.firstId) {
      return;
    }
    if (countChanged || isAtBottomRef.current || forceFollowRef.current) {
      scrollToBottom(countChanged);
    }
  }, [resolvedMessages.length, firstMessageId, lastMessageId, lastMessageSignature, scrollToBottom]);

  React.useEffect(() => {
    scrollToBottomAfterOpen();
  }, [scrollToBottomAfterOpen]);

  const handleScroll = (event: any) => {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
    scrollMetricsRef.current = {
      y: contentOffset.y,
      contentHeight: contentSize.height,
      viewportHeight: layoutMeasurement.height,
    };
    const distance = contentSize.height - (contentOffset.y + layoutMeasurement.height);
    const nextAtBottom = distance < 80;
    isAtBottomRef.current = nextAtBottom;
    if (!nextAtBottom && contentOffset.y > 32) {
      forceFollowRef.current = false;
    }
    setShowJump(!nextAtBottom);

    if (on_load_more && onAction && contentSize.height > layoutMeasurement.height + 32 && contentOffset.y <= 32) {
      const now = Date.now();
      if (now - loadMoreLastAtRef.current >= 700) {
        loadMoreLastAtRef.current = now;
        prependSnapshotRef.current = {
          count: resolvedMessages.length,
          firstId: String(resolvedMessages[0]?.id || ''),
          contentHeight: contentSize.height,
          y: contentOffset.y,
        };
        emitActionSpec(on_load_more, onAction, { target: id, source: 'scroll_top' });
      }
    }
  };

  const handleContentSizeChange = (_width: number, height: number) => {
    const snapshot = prependSnapshotRef.current;
    if (snapshot && height > snapshot.contentHeight) {
      const delta = height - snapshot.contentHeight;
      requestAnimationFrame(() => {
        scrollRef.current?.scrollTo({ y: snapshot.y + delta, animated: false });
      });
      prependSnapshotRef.current = null;
      return;
    }
    if (!didInitialScrollRef.current) {
      scrollToBottomAfterOpen();
      return;
    }
    if (isAtBottomRef.current) {
      scrollToBottom(false);
      return;
    }
    if (forceFollowRef.current) {
      scrollToBottom(false);
    }
  };

  if (!resolvedMessages.length) {
    return (
      <View style={[styles.container, styles.emptyContainer, style]}>
        <Icon name="ri-chat-3-line" size={28} color="#6E7681" />
        <Text style={styles.emptyTitle}>No messages</Text>
        <Text style={styles.emptyText}>The conversation will appear here.</Text>
      </View>
    );
  }

  return (
    <View style={[styles.container, style]}>
      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        onScroll={handleScroll}
        onContentSizeChange={handleContentSizeChange}
        onLayout={() => {
          scrollToBottomAfterOpen();
          if (isAtBottomRef.current) scrollToBottom(false);
        }}
        scrollEventThrottle={120}
      >
        {resolvedMessages.map((message: any, index: number) => (
          <MessageItem
            key={messageKey(message, index)}
            {...message}
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
            pendingActions={pendingActions}
            backgroundTasks={backgroundTasks}
            jwt={jwt}
            onAttachmentClick={on_attachment_click}
          />
        ))}
      </ScrollView>

      {showJump ? (
        <TouchableOpacity
          style={styles.jumpButton}
          onPress={() => {
            isAtBottomRef.current = true;
            forceFollowRef.current = true;
            setShowJump(false);
            scrollToBottom(true);
          }}
          activeOpacity={0.8}
          accessibilityLabel="Scroll to bottom"
        >
          <Icon name="ri-arrow-down-line" size={18} color="#FFFFFF" />
        </TouchableOpacity>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    width: '100%',
    minHeight: 0,
    backgroundColor: '#0D1117',
  },
  scroll: {
    flex: 1,
    width: '100%',
  },
  content: {
    paddingVertical: 10,
    paddingBottom: 18,
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    gap: 6,
  },
  emptyTitle: {
    color: '#E6EDF3',
    fontSize: 15,
    fontWeight: '700',
  },
  emptyText: {
    color: '#8B949E',
    fontSize: 13,
    textAlign: 'center',
  },
  jumpButton: {
    position: 'absolute',
    right: 14,
    bottom: 14,
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1F6FEB',
    borderWidth: 1,
    borderColor: '#58A6FF',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.24,
    shadowRadius: 6,
    elevation: 5,
  },
});
