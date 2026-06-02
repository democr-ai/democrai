import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, normalizeOptions, requestActionConfirm } from '@/renderers/shared';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { Check, ChevronsUpDown } from 'lucide-react';

export const Combobox: React.FC<any> = ({
  id,
  label,
  options = [],
  value,
  placeholder,
  action,
  onAction,
  setInput,
  style,
  syncInitialInput = true,
}) => {
  const normalized = React.useMemo(() => normalizeOptions(options), [options]);
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState('');
  const [selected, setSelected] = React.useState(value == null ? '' : String(value));

  React.useEffect(() => {
    const next = value == null ? '' : String(value);
    setSelected(next);
    if (syncInitialInput) setInput?.(id, next);
  }, [id, setInput, syncInitialInput, value]);

  const selectedLabel = normalized.find((entry) => String(entry.value) === selected)?.label || '';

  const filtered = normalized.filter((entry) => entry.label.toLowerCase().includes(query.trim().toLowerCase()));

  return (
    <div className="grid gap-1.5" style={parseStyle(style)}>
      {label ? <Label>{getLiteral(label)}</Label> : null}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" role="combobox" aria-expanded={open} className="w-full justify-between">
            {selectedLabel || getLiteral(placeholder || 'Search...')}
            <ChevronsUpDown className="h-4 w-4 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0">
          <div className="p-2">
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search..." className="mb-2" />
            <ScrollArea className="max-h-60">
              <div className="grid gap-1">
                {filtered.length ? filtered.map((entry, index) => {
                  const isSelected = String(entry.value) === selected;
                  return (
                    <Button
                      key={`${id}_combo_${index}`}
                      variant="ghost"
                      className="justify-start"
                      onClick={async () => {
                        const next = String(entry.value);
                        if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
                          setOpen(false);
                          return;
                        }
                        setSelected(next);
                        setInput?.(id, next);
                        const actionWithoutConfirm = action && typeof action === 'object'
                          ? { ...action, confirm: undefined }
                          : action;
                        emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
                        setOpen(false);
                      }}
                    >
                      <Check className={cn('mr-2 h-4 w-4', isSelected ? 'opacity-100' : 'opacity-0')} />
                      {entry.label}
                    </Button>
                  );
                }) : (
                  <p className="px-2 py-1 text-sm text-muted-foreground">No results</p>
                )}
              </div>
            </ScrollArea>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
};
