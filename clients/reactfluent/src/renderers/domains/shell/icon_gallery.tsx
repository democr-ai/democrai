import React, { useState, useEffect, useMemo } from 'react';
import { IconButton, SearchBox, Text } from '@fluentui/react';
import { toast } from 'sonner';
import iconsData from '@/assets/fonts/remixicon-custom.json';

export const IconGallery: React.FC = () => {
  const [icons, setIcons] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 200;

  useEffect(() => {
    setIcons(Object.keys(iconsData).sort());
    setLoading(false);
    /*fetch('./fonts/remixicon-custom.json')
      .then((res) => res.json())
      .then((data) => {
        setIcons(Object.keys(data).sort());
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load icons:', err);
        setLoading(false);
      });*/
  }, []);

  const filteredIcons = useMemo(() => {
    const s = search.toLowerCase();
    return icons.filter((name) => name.toLowerCase().includes(s));
  }, [icons, search]);

  useEffect(() => {
    setPage(0);
  }, [search]);

  const totalPages = Math.ceil(filteredIcons.length / PAGE_SIZE);
  const paginatedIcons = useMemo(() => {
    return filteredIcons.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  }, [filteredIcons, page]);

  const copyToClipboard = async (name: string) => {
    const iconName = name.startsWith('ric.') ? name : `ric.${name}`;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(iconName);
      } else {
        const input = document.createElement('textarea');
        input.value = iconName;
        input.style.position = 'fixed';
        input.style.opacity = '0';
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        input.remove();
      }
      setCopiedId(name);
      toast.success(`Copied: ${iconName}`);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      toast.error(`Copy failed: ${iconName}`);
    }
  };

  if (loading) {
    return <div className="d-flex align-items-center justify-content-center text-muted" style={{ height: '16rem' }}>Loading icons...</div>;
  }

  return (
    <div className="ds-icon-gallery">
      <div className="ds-icon-gallery-toolbar">
        <div className="ds-icon-gallery-search">
          <SearchBox
            placeholder="Search icons"
            value={search}
            onChange={(_, nextValue) => setSearch(nextValue || '')}
          />
        </div>
        
        {totalPages > 1 && (
          <div className="ds-icon-gallery-pager">
             <IconButton
              disabled={page === 0}
              onClick={() => setPage(p => Math.max(0, p - 1))}
              iconProps={{ iconName: 'ChevronLeft' }}
              ariaLabel="Previous page"
            />
            <span className="ds-icon-gallery-page">
              {page + 1} / {totalPages}
            </span>
            <IconButton
              disabled={page >= totalPages - 1}
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              iconProps={{ iconName: 'ChevronRight' }}
              ariaLabel="Next page"
            />
          </div>
        )}
      </div>

      <Text variant="small" className="ds-icon-gallery-count">
        Found {filteredIcons.length} icons
      </Text>
      
      <div className="ds-icon-gallery-scroll">
        <div className="ds-icon-gallery-grid">
          {paginatedIcons.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => copyToClipboard(name)}
              className={`ds-icon-gallery-tile ${copiedId === name ? 'is-copied' : ''}`}
              title={name}
            >
              <span className="ds-icon-gallery-copy" aria-hidden="true">
                {copiedId === name ? <i className="ri-check-line" /> : <i className="ri-file-copy-line" />}
              </span>
              <i className={`ri-${name} ds-icon-gallery-icon`} aria-hidden="true" />
              <span className="ds-icon-gallery-name">{name}</span>
            </button>
          ))}
        </div>
        
        {filteredIcons.length === 0 && (
          <div className="ds-icon-gallery-empty">
            No icons found matching "{search}"
          </div>
        )}
      </div>
    </div>
  );
};
