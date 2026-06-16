import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, LayoutAnimation } from 'react-native';
import { getLiteral, toBoolean } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

export const Accordion: React.FC<any> = ({
  items = [],
  ExplicitList,
  multiple = false,
  collapsible = true,
  style,
}) => {
  const safeItems = React.useMemo(() => (Array.isArray(items) ? items : []), [items]);
  const initialSignature = React.useMemo(
    () => safeItems
      .map((item: any, index: number) => `${String(item?.id ?? index)}:${toBoolean(item?.open) ? '1' : '0'}`)
      .join('|'),
    [safeItems],
  );
  const initial = React.useMemo(
    () => safeItems
      .map((item: any, index: number) => (toBoolean(item?.open) ? index : null))
      .filter((value: number | null): value is number => value !== null),
    [safeItems, initialSignature],
  );

  const [openIndices, setOpenIndices] = React.useState<number[]>(initial);
  const syncedSignatureRef = React.useRef('');

  React.useEffect(() => {
    const signature = `${toBoolean(multiple) ? 'multiple' : 'single'}:${initialSignature}`;
    if (syncedSignatureRef.current === signature) return;
    syncedSignatureRef.current = signature;
    setOpenIndices(toBoolean(multiple) ? initial : (initial.length ? [initial[0]] : []));
  }, [multiple, initial, initialSignature]);

  const toggle = (index: number) => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    const allowMultiple = toBoolean(multiple);
    const allowCollapse = toBoolean(collapsible);
    setOpenIndices((current) => {
      if (allowMultiple) {
        if (current.includes(index)) {
          if (allowCollapse || current.length > 1) {
            return current.filter(i => i !== index);
          }
          return current;
        }
        return [...current, index];
      }

      if (current.includes(index)) {
        return allowCollapse ? [] : current;
      }
      return [index];
    });
  };

  return (
    <View style={[styles.container, style]}>
      {safeItems.map((item: any, index: number) => {
        const isOpen = openIndices.includes(index);
        const isLast = index === safeItems.length - 1;
        const bodyNode = Array.isArray(ExplicitList) ? ExplicitList[index] : null;
        const contentText = getLiteral(item?.content);
        const title = getLiteral(item?.title || item?.label || `Item ${index + 1}`);
        return (
          <View key={String(item?.id || `accordion_${index}`)} style={[styles.item, isLast && styles.itemLast, isOpen && styles.itemOpen]}>
            <TouchableOpacity 
              style={[styles.trigger, isOpen && styles.triggerOpen]} 
              onPress={() => toggle(index)}
              activeOpacity={0.7}
            >
              <View style={styles.titleWrap}>
                <Text style={[styles.title, isOpen && styles.titleOpen]} numberOfLines={2}>{title}</Text>
                {item?.meta ? <Text style={styles.meta} numberOfLines={1}>{getLiteral(item.meta)}</Text> : null}
              </View>
              <Icon 
                name={isOpen ? "ri-arrow-up-s-line" : "ri-arrow-down-s-line"} 
                size={20} 
                color={isOpen ? '#E6EDF3' : '#8B949E'} 
              />
            </TouchableOpacity>
            {isOpen && (
              <View style={styles.content}>
                {bodyNode}
                {contentText ? <Text style={[styles.contentText, bodyNode && styles.contentTextAfterChild]}>{contentText}</Text> : null}
              </View>
            )}
          </View>
        );
      })}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: '#161B22',
  },
  item: {
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
    backgroundColor: '#161B22',
  },
  itemOpen: {
    backgroundColor: '#1C2128',
  },
  itemLast: {
    borderBottomWidth: 0,
  },
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 14,
    paddingHorizontal: 14,
    gap: 12,
  },
  triggerOpen: {
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
  },
  titleWrap: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  title: {
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '700',
    color: '#C9D1D9',
  },
  titleOpen: {
    color: '#E6EDF3',
  },
  meta: {
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '700',
    color: '#8B949E',
    textTransform: 'uppercase',
  },
  content: {
    paddingVertical: 13,
    paddingHorizontal: 14,
    backgroundColor: '#0D1117',
  },
  contentText: {
    fontSize: 14,
    color: '#8B949E',
    lineHeight: 20,
  },
  contentTextAfterChild: {
    marginTop: 8,
  },
});
