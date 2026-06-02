import React from 'react';
import useEmblaCarousel from 'embla-carousel-react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec } from '@/renderers/shared';
import { InternalRenderer } from '@/components/a2ui/Renderer';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { readClientStateValue } from '@/state/clientState';

const resolvePath = (root: any, path: string): any => {
  const clean = String(path || '').replace(/^\//, '');
  if (!clean) return root;
  return clean.split('/').reduce((acc, segment) => (acc == null ? undefined : acc[segment]), root);
};

const resolveItems = (dataSource: any, dataModel: any, stateModel: any, surfaceId: string): any[] => {
  const source = dataSource || {};
  const type = String(source?.type || 'inline').toLowerCase();
  if (type === 'inline') return Array.isArray(source?.data) ? source.data : [];
  if (type === 'binding') {
    const data = source?.data;
    if (Array.isArray(data)) return data;
    if (data && typeof data === 'object' && typeof data.path === 'string') {
      if (String(data?.type || '').toLowerCase() === 'store') {
        const fromState = readClientStateValue(stateModel, String(data?.scope || 'auto').toLowerCase() as any, data.path);
        if (Array.isArray(fromState)) return fromState;
        return [];
      }
      const fromSurface = resolvePath(dataModel?.[surfaceId] || {}, data.path);
      if (Array.isArray(fromSurface)) return fromSurface;
    }
  }
  return [];
};

export const Carousel: React.FC<any> = ({
  id,
  dataSource,
  itemTemplate,
  onItemClick,
  onChange,
  activeIndex = 0,
  autoplay = false,
  intervalMs = 3000,
  showDots = true,
  showArrows = true,
  loop = true,
  style,
  surfaceId,
  surfaces,
  dataModel,
  stateModel,
  sendAction,
  onAction,
  setInput,
  userRole,
  userPermissions,
}) => {
  const items = React.useMemo(() => resolveItems(dataSource, dataModel, stateModel, surfaceId), [dataSource, dataModel, stateModel, surfaceId]);
  const [emblaRef, emblaApi] = useEmblaCarousel({ loop: Boolean(loop) });
  const [selected, setSelected] = React.useState(Math.max(0, Number(activeIndex) || 0));

  React.useEffect(() => {
    if (!emblaApi) return;
    emblaApi.scrollTo(Math.max(0, Number(activeIndex) || 0));
    setSelected(Math.max(0, Number(activeIndex) || 0));
  }, [emblaApi, activeIndex]);

  React.useEffect(() => {
    if (!emblaApi) return;
    const onSelect = () => {
      const next = emblaApi.selectedScrollSnap();
      setSelected(next);
      emitActionSpec(onChange, onAction || sendAction, { source: 'carousel', index: next, itemId: items[next]?.id });
    };
    emblaApi.on('select', onSelect);
    return () => { emblaApi.off('select', onSelect); };
  }, [emblaApi, onChange, onAction, sendAction, items]);

  React.useEffect(() => {
    if (!emblaApi || !autoplay || items.length <= 1) return;
    const timer = window.setInterval(() => emblaApi.scrollNext(), Math.max(300, Number(intervalMs) || 3000));
    return () => window.clearInterval(timer);
  }, [emblaApi, autoplay, intervalMs, items.length]);

  if (!itemTemplate) {
    return <Card style={parseStyle(style)}><CardContent className="p-4 text-sm text-muted-foreground">No carousel template</CardContent></Card>;
  }

  return (
    <Card style={parseStyle(style)}>
      <CardContent className="grid gap-3 p-3">
        <div className="overflow-hidden" ref={emblaRef}>
          <div className="flex">
            {items.map((item: any, index: number) => (
              <div key={item?.id || `${id}_slide_${index}`} className="min-w-0 shrink-0 grow-0 basis-full px-1">
                <div onClick={() => emitActionSpec(onItemClick, onAction || sendAction, { item, index, itemId: item?.id })}>
                  <InternalRenderer
                    componentData={itemTemplate}
                    surfaceId={surfaceId}
                    surfaces={surfaces}
                    dataModel={dataModel}
                    stateModel={stateModel}
                    sendAction={sendAction}
                    setInput={setInput}
                    componentId={`${id}_item_${index}`}
                    userRole={userRole}
                    userPermissions={userPermissions}
                    item={item}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-center gap-2">
          {showArrows ? <Button type="button" variant="outline" size="sm" onClick={() => emblaApi?.scrollPrev()}>{'<'}</Button> : null}
          {showDots ? items.map((_: any, idx: number) => (
            <Button key={`dot_${idx}`} type="button" variant={idx === selected ? 'default' : 'ghost'} size="sm" onClick={() => emblaApi?.scrollTo(idx)}>
              {idx + 1}
            </Button>
          )) : null}
          {showArrows ? <Button type="button" variant="outline" size="sm" onClick={() => emblaApi?.scrollNext()}>{'>'}</Button> : null}
        </div>
      </CardContent>
    </Card>
  );
};
