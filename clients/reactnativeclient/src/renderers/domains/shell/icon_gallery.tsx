import React from 'react';
import { FlatList, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import iconsData from '../../../../assets/fonts/remixicon-custom.json';
import { Icon } from '../../../components/a2ui/Icon';

const PAGE_SIZE = 80;
const ICONS = Object.keys(iconsData).sort();

export const IconGallery: React.FC = () => {
  const [search, setSearch] = React.useState('');
  const [page, setPage] = React.useState(0);
  const [copiedId, setCopiedId] = React.useState<string | null>(null);

  const filteredIcons = React.useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return ICONS;
    return ICONS.filter((name) => name.toLowerCase().includes(needle));
  }, [search]);

  React.useEffect(() => {
    setPage(0);
  }, [search]);

  const totalPages = Math.max(1, Math.ceil(filteredIcons.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pagedIcons = React.useMemo(() => (
    filteredIcons.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE)
  ), [filteredIcons, safePage]);

  const markCopied = React.useCallback((name: string) => {
    setCopiedId(name);
    setTimeout(() => setCopiedId((current) => (current === name ? null : current)), 1200);
  }, []);

  return (
    <View style={styles.root}>
      <View style={styles.toolbar}>
        <View style={styles.searchBox}>
          <Icon name="ri-search-line" size={18} color="#8B949E" />
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Search icons"
            placeholderTextColor="#6E7681"
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
          />
        </View>
        <View style={styles.pager}>
          <TouchableOpacity
            style={[styles.pagerButton, safePage === 0 && styles.pagerButtonDisabled]}
            disabled={safePage === 0}
            onPress={() => setPage((current) => Math.max(0, current - 1))}
            activeOpacity={0.75}
          >
            <Icon name="ri-arrow-left-s-line" size={20} color={safePage === 0 ? '#484F58' : '#C9D1D9'} />
          </TouchableOpacity>
          <Text style={styles.pageText}>{safePage + 1} / {totalPages}</Text>
          <TouchableOpacity
            style={[styles.pagerButton, safePage >= totalPages - 1 && styles.pagerButtonDisabled]}
            disabled={safePage >= totalPages - 1}
            onPress={() => setPage((current) => Math.min(totalPages - 1, current + 1))}
            activeOpacity={0.75}
          >
            <Icon name="ri-arrow-right-s-line" size={20} color={safePage >= totalPages - 1 ? '#484F58' : '#C9D1D9'} />
          </TouchableOpacity>
        </View>
      </View>

      <Text style={styles.count}>Found {filteredIcons.length} icons</Text>

      {filteredIcons.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyText}>No icons found matching "{search}"</Text>
        </View>
      ) : (
        <FlatList
          data={pagedIcons}
          keyExtractor={(name) => name}
          numColumns={3}
          scrollEnabled={false}
          contentContainerStyle={styles.grid}
          columnWrapperStyle={styles.gridRow}
          renderItem={({ item }) => {
            const copied = copiedId === item;
            return (
              <TouchableOpacity
                style={[styles.tile, copied && styles.tileCopied]}
                onPress={() => markCopied(item)}
                activeOpacity={0.75}
              >
                <View style={styles.copyIcon}>
                  <Icon name={copied ? 'ri-check-line' : 'ri-file-copy-line'} size={13} color={copied ? '#56D364' : '#6E7681'} />
                </View>
                <Icon name={item} size={26} color="#E6EDF3" />
                <Text style={styles.iconName} numberOfLines={1}>{item}</Text>
              </TouchableOpacity>
            );
          }}
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  root: {
    width: '100%',
    gap: 12,
  },
  toolbar: {
    width: '100%',
    gap: 10,
  },
  searchBox: {
    height: 44,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    gap: 8,
  },
  input: {
    flex: 1,
    minWidth: 0,
    color: '#E6EDF3',
    fontSize: 15,
    paddingVertical: 0,
  },
  pager: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    padding: 3,
    gap: 6,
  },
  pagerButton: {
    width: 34,
    height: 34,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pagerButtonDisabled: {
    opacity: 0.55,
  },
  pageText: {
    minWidth: 64,
    color: '#C9D1D9',
    textAlign: 'center',
    fontSize: 12,
    fontWeight: '700',
  },
  count: {
    color: '#8B949E',
    fontSize: 12,
  },
  grid: {
    gap: 8,
    paddingBottom: 24,
  },
  gridRow: {
    gap: 8,
    marginBottom: 8,
  },
  tile: {
    flex: 1,
    minWidth: 0,
    height: 104,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#0D1117',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
    gap: 8,
    position: 'relative',
  },
  tileCopied: {
    borderColor: '#6366F1',
    backgroundColor: 'rgba(99,102,241,0.12)',
  },
  copyIcon: {
    position: 'absolute',
    top: 6,
    right: 6,
  },
  iconName: {
    width: '100%',
    color: '#8B949E',
    fontSize: 10,
    textAlign: 'center',
  },
  empty: {
    minHeight: 160,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyText: {
    color: '#8B949E',
    fontSize: 13,
    textAlign: 'center',
  },
});
