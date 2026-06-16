import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { emitActionSpec, getLiteral } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

export const DropdownMenu: React.FC<any> = ({ label, items = [], onAction, style }) => {
  const [open, setOpen] = React.useState(false);

  return (
    <View style={[styles.container, style]}>
      <TouchableOpacity style={styles.trigger} onPress={() => setOpen((prev) => !prev)} activeOpacity={0.75}>
        <Text style={styles.triggerText}>{getLiteral(label || 'Menu')}</Text>
        <Icon name={open ? 'ri-arrow-up-s-line' : 'ri-arrow-down-s-line'} size={18} color="#8B949E" />
      </TouchableOpacity>
      {open ? (
        <View style={styles.menu}>
          {Array.isArray(items) && items.length ? items.map((item: any, index: number) => (
            <TouchableOpacity
              key={`menu_item_${index}`}
              style={styles.item}
              onPress={() => {
                setOpen(false);
                emitActionSpec(item?.action, onAction, item?.params || {});
              }}
              activeOpacity={0.7}
            >
              {item?.icon ? <Icon name={item.icon} size={16} color="#8B949E" /> : null}
              <Text style={styles.itemText}>{getLiteral(item?.label)}</Text>
            </TouchableOpacity>
          )) : (
            <Text style={styles.empty}>No items</Text>
          )}
        </View>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: { alignSelf: 'flex-start', marginVertical: 4, minWidth: 150 },
  trigger: {
    minHeight: 38,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  triggerText: { color: '#E6EDF3', fontSize: 14, fontWeight: '500' },
  menu: {
    marginTop: 6,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#0D1117',
    paddingVertical: 4,
    minWidth: 180,
  },
  item: { minHeight: 38, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', gap: 8 },
  itemText: { color: '#C9D1D9', fontSize: 14 },
  empty: { color: '#6E7681', fontSize: 13, padding: 12 },
});
