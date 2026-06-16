import React from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Icon } from '../../../components/a2ui/Icon';
import { emitActionSpec, getLiteral } from '../../shared';

export const ThreadList: React.FC<any> = ({
  threads = [],
  active_thread_id,
  action,
  onAction,
  style,
  title,
}) => {
  const [open, setOpen] = React.useState(false);
  const safeThreads = Array.isArray(threads) ? threads : [];
  const activeThread = safeThreads.find((thread: any) => String(thread?.id) === String(active_thread_id));
  const activeTitle = getLiteral(activeThread?.title || title || 'Threads');

  const selectThread = (thread: any) => {
    setOpen(false);
    emitActionSpec(action, onAction, { threadId: thread?.id, thread });
  };

  return (
    <View style={[styles.wrap, style]}>
      <TouchableOpacity style={styles.trigger} onPress={() => setOpen(true)} activeOpacity={0.75}>
        <View style={styles.triggerIcon}>
          <Icon name="ri-chat-3-line" size={17} color="#58A6FF" />
        </View>
        <View style={styles.triggerText}>
          <Text style={styles.triggerLabel} numberOfLines={1}>{activeTitle || 'Threads'}</Text>
          <Text style={styles.triggerMeta} numberOfLines={1}>
            {safeThreads.length ? `${safeThreads.length} thread` : 'No threads'}
          </Text>
        </View>
        <Icon name="ri-arrow-down-s-line" size={18} color="#8B949E" />
      </TouchableOpacity>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <Pressable style={styles.menu} onPress={(event) => event.stopPropagation()}>
            <View style={styles.menuHeader}>
              <View>
                <Text style={styles.menuTitle}>Threads</Text>
                <Text style={styles.menuSubtitle}>{safeThreads.length} conversations</Text>
              </View>
              <TouchableOpacity style={styles.closeButton} onPress={() => setOpen(false)}>
                <Icon name="ri-close-line" size={18} color="#E6EDF3" />
              </TouchableOpacity>
            </View>

            <ScrollView style={styles.list} contentContainerStyle={styles.listContent} showsVerticalScrollIndicator={false}>
              {safeThreads.length ? safeThreads.map((thread: any, index: number) => {
                const active = String(thread?.id) === String(active_thread_id);
                return (
                  <TouchableOpacity
                    key={thread?.id || `thread_${index}`}
                    style={[styles.item, active && styles.itemActive]}
                    onPress={() => selectThread(thread)}
                    activeOpacity={0.75}
                  >
                    <View style={[styles.itemDot, active && styles.itemDotActive]} />
                    <View style={styles.itemText}>
                      <Text style={[styles.title, active && styles.titleActive]} numberOfLines={1}>
                        {getLiteral(thread?.title || 'Untitled Thread')}
                      </Text>
                      {thread?.preview ? <Text style={styles.preview} numberOfLines={2}>{getLiteral(thread.preview)}</Text> : null}
                    </View>
                    {active ? <Icon name="ri-check-line" size={17} color="#58A6FF" /> : null}
                  </TouchableOpacity>
                );
              }) : (
                <View style={styles.empty}>
                  <Icon name="ri-chat-off-line" size={24} color="#6E7681" />
                  <Text style={styles.emptyText}>No threads available</Text>
                </View>
              )}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: {
    width: '100%',
    marginVertical: 4,
  },
  trigger: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 10,
    backgroundColor: '#161B22',
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  triggerIcon: {
    width: 30,
    height: 30,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1F6FEB22',
  },
  triggerText: {
    flex: 1,
    minWidth: 0,
  },
  triggerLabel: {
    color: '#E6EDF3',
    fontSize: 13,
    fontWeight: '700',
  },
  triggerMeta: {
    color: '#8B949E',
    fontSize: 11,
    marginTop: 1,
  },
  backdrop: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: '#00000088',
    padding: 12,
  },
  menu: {
    width: '100%',
    maxHeight: '72%',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 14,
    backgroundColor: '#0D1117',
    overflow: 'hidden',
  },
  menuHeader: {
    minHeight: 54,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: '#161B22',
  },
  menuTitle: {
    color: '#E6EDF3',
    fontSize: 15,
    fontWeight: '800',
  },
  menuSubtitle: {
    color: '#8B949E',
    fontSize: 11,
    marginTop: 2,
  },
  closeButton: {
    width: 34,
    height: 34,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#21262D',
  },
  list: {
    maxHeight: 420,
  },
  listContent: {
    padding: 8,
    gap: 5,
  },
  item: {
    minHeight: 54,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  itemActive: {
    backgroundColor: '#1F6FEB26',
  },
  itemDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: '#30363D',
  },
  itemDotActive: {
    backgroundColor: '#58A6FF',
  },
  itemText: {
    flex: 1,
    minWidth: 0,
  },
  title: {
    color: '#C9D1D9',
    fontSize: 13,
    fontWeight: '700',
  },
  titleActive: {
    color: '#58A6FF',
  },
  preview: {
    color: '#8B949E',
    fontSize: 12,
    lineHeight: 16,
    marginTop: 2,
  },
  empty: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 28,
    gap: 8,
  },
  emptyText: {
    color: '#8B949E',
    fontSize: 13,
  },
});
