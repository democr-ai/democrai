import React, { useState, useEffect, useMemo } from 'react';
import { Button } from 'design-react-kit';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
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
    <div className="d-flex flex-column gap-4 h-100 min-vh-0">
      <div className="a2ui-icon-gallery-toolbar">
        <div className="a2ui-icon-gallery-search">
          <i className="ri-search-line a2ui-icon-gallery-search-icon" />
          <input
            type="search"
            aria-label="Cerca icone"
            placeholder="Cerca icone (es. file, user, arrows...)"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="form-control a2ui-icon-gallery-search-input"
          />
        </div>
        
        {totalPages > 1 && (
          <div className="a2ui-icon-gallery-pager">
             <Button 
              size="xs"
              outline
              color="primary"
              disabled={page === 0}
              onClick={() => setPage(p => Math.max(0, p - 1))}
              className="a2ui-icon-gallery-page-button"
            >
              <i className="ri-arrow-left-s-line" />
            </Button>
            <span className="a2ui-icon-gallery-page-count">
              {page + 1} / {totalPages}
            </span>
            <Button 
              size="xs"
              outline
              color="primary"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              className="a2ui-icon-gallery-page-button"
            >
              <i className="ri-arrow-right-s-line" />
            </Button>
          </div>
        )}
      </div>

      <div className="xsmall text-muted px-1">
        Found {filteredIcons.length} icons
      </div>
      
      <div className="flex-grow-1 overflow-auto min-vh-0 pr-1">
        <div className="row row-cols-2 row-cols-sm-4 row-cols-md-6 row-cols-lg-8 row-cols-xl-10 g-2 p-1 m-0">
          {paginatedIcons.map((name) => (
            <div key={name} className="col p-1">
              <button
                type="button"
                onClick={() => copyToClipboard(name)}
                className={cn(
                  "btn btn-outline-secondary w-100 h-100 p-3 d-flex flex-column align-items-center justify-content-center gap-2 position-relative border",
                  copiedId === name && "border-primary bg-primary-subtle"
                )}
                title={name}
              >
                <i className={`ri-${name} h2 m-0`} />
                <span className="xsmall text-truncate w-100 text-center">
                  {name}
                </span>
                <div className="position-absolute top-0 end-0 p-1">
                  {copiedId === name ? <i className="ri-check-line text-primary" /> : <i className="ri-file-copy-line text-muted xsmall" />}
                </div>
              </button>
            </div>
          ))}
        </div>
        
        {filteredIcons.length === 0 && (
          <div className="text-center py-5 text-muted">
            No icons found matching "{search}"
          </div>
        )}
      </div>
    </div>
  );
};
