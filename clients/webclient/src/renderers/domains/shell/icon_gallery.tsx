import React, { useState, useEffect, useMemo } from 'react';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { toast } from 'sonner';
import { Search, Copy, Check, ChevronLeft, ChevronRight } from 'lucide-react';
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

  const copyToClipboard = (name: string) => {
    const iconName = name.startsWith('ric.') ? name : `ric.${name}`;
    navigator.clipboard.writeText(iconName).then(() => {
      setCopiedId(name);
      toast.success(`Copied: ${iconName}`);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  if (loading) {
    return <div className="flex h-64 items-center justify-center text-muted-foreground animate-pulse">Loading icons...</div>;
  }

  return (
    <div className="flex flex-col gap-4 h-full min-h-0">
      <div className="flex items-center gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search icons (e.g. file, user, arrows...)"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10 h-10"
          />
        </div>
        
        {totalPages > 1 && (
          <div className="flex items-center gap-2 bg-muted/30 p-1 rounded-md border text-sm">
             <button 
              disabled={page === 0}
              onClick={() => setPage(p => Math.max(0, p - 1))}
              className="p-1 hover:bg-accent rounded-sm disabled:opacity-30 transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="px-2 font-medium min-w-[80px] text-center text-xs">
              {page + 1} / {totalPages}
            </span>
            <button 
              disabled={page >= totalPages - 1}
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              className="p-1 hover:bg-accent rounded-sm disabled:opacity-30 transition-colors"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      <div className="text-xs text-muted-foreground/60 px-1">
        Found {filteredIcons.length} icons
      </div>
      
      <div className="flex-1 overflow-auto min-h-0 custom-scrollbar pr-1">
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10 gap-2 p-1">
          {paginatedIcons.map((name) => (
            <button
              key={name}
              onClick={() => copyToClipboard(name)}
              className={cn(
                "group relative border rounded-md p-4 flex flex-col items-center justify-center gap-2 hover:bg-accent hover:text-accent-foreground transition-all duration-200",
                copiedId === name && "ring-2 ring-primary bg-primary/5 border-primary/20"
              )}
              title={name}
            >
              <i className={`ri-${name} text-2xl group-hover:scale-110 transition-transform`} />
              <span className="text-[10px] text-muted-foreground truncate w-full text-center">
                {name}
              </span>
              <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
                {copiedId === name ? <Check className="h-3 w-3 text-primary" /> : <Copy className="h-3 w-3 text-muted-foreground" />}
              </div>
            </button>
          ))}
        </div>
        
        {filteredIcons.length === 0 && (
          <div className="text-center py-12 text-muted-foreground">
            No icons found matching "{search}"
          </div>
        )}
      </div>
    </div>
  );
};
