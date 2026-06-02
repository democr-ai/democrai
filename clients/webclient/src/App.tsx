import { useMemo } from 'react';
import { useA2UI } from './hooks/useA2UI';
import { A2UIRenderer } from './components/a2ui/Renderer';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { Spinner } from '@/components/ui/spinner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Toaster } from 'sonner';
import { ClientStateProvider } from './state/clientState';

const isTabRouteSurfaceId = (surfaceId: string): boolean => surfaceId.includes('__tab_route__');

const isExplicitOverlaySurface = (surface: any): boolean => {
  const options = surface?.options;
  if (!options || typeof options !== 'object') return false;
  if (options.overlay === true) return true;
  const presentation = String(options.presentation || options.type || options.kind || '').trim().toLowerCase();
  return presentation === 'overlay' || presentation === 'dialog' || presentation === 'modal';
};

const drawerSide = (value: unknown): 'top' | 'right' | 'bottom' | 'left' => {
  return value === 'top' || value === 'bottom' || value === 'left' || value === 'right' ? value : 'right';
};

const positiveNumber = (value: unknown): number | null => {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};

function App() {
  const {
    surfaces,
    dataModel,
    stateModel,
    sendAction,
    setInput,
    backgroundTasks,
    closeSurface,
    userRole,
    userPermissions,
    pendingActions,
    connectionState,
  } = useA2UI({
    codec: import.meta.env.VITE_WS_CODEC as string | undefined,
  });

  const hostedSurfaceIds = useMemo(() => {
    const hosted = new Set<string>();
    Object.values(surfaces).forEach((surface: any) => {
      const components = surface?.components || {};
      Object.values(components).forEach((componentData: any) => {
        const props = componentData?.component?.SurfaceHost;
        const surfaceId = typeof props?.surface_id === 'string' ? props.surface_id : '';
        if (surfaceId) hosted.add(surfaceId);
      });
    });
    return hosted;
  }, [surfaces]);

  const mainSurfaceId = useMemo(() => {
    // 1. Prefer 'main' if it's present and NOT hosted by another surface
    if (surfaces.main && !hostedSurfaceIds.has('main')) {
      return 'main';
    }

    // 2. Search for any surface that is NOT hosted, NOT 'modal', and NOT a tab route surface
    for (const id of Object.keys(surfaces)) {
      if (id === 'modal' || isTabRouteSurfaceId(id)) continue;
      if (!hostedSurfaceIds.has(id)) {
        const surface = surfaces[id] as any;
        if (surface?.rootId || surface?.components?.root) {
          return id;
        }
      }
    }

    // 3. Final fallback
    return 'main';
  }, [surfaces, hostedSurfaceIds]);

  const mainSurface = surfaces[mainSurfaceId];
  const mainComponentId = mainSurface?.rootId || (mainSurface?.components?.root ? 'root' : '');

  const approvalSurfaceIds = useMemo(() => {
    const ids = new Set<string>();
    Object.values(backgroundTasks).forEach((task: any) => {
      if (task?.status !== 'waiting_confirmation') return;
      const sid = typeof task?.confirmSurfaceId === 'string' ? task.confirmSurfaceId : '';
      if (sid) ids.add(sid);
    });
    return ids;
  }, [backgroundTasks]);

  // drawer and modal are always rendered as persistent elements — exclude from dynamic map
  const overlaySurfaces = useMemo(
    () =>
      Object.entries(surfaces).filter(([id, surface]) => {
        if (id === 'main' || id === 'main_content' || !surface?.rootId) return false;
        if (isTabRouteSurfaceId(id)) return false;
        if (id === 'drawer' || id === 'modal') return false;
        if (approvalSurfaceIds.has(id)) return true;
        if (hostedSurfaceIds.has(id)) return false;
        return isExplicitOverlaySurface(surface);
      }),
    [surfaces, hostedSurfaceIds, approvalSurfaceIds],
  );

  const drawerSurface = surfaces.drawer as any;
  const modalSurface = surfaces.modal as any;
  const drawerPosition = drawerSide(drawerSurface?.options?.position);
  const defaultDrawerDim = 720;
  const drawerDim = positiveNumber(drawerSurface?.options?.dim);
  const drawerStyle =
    drawerPosition === 'left' || drawerPosition === 'right'
      ? {
          overflow: 'auto',
          overflowX: 'hidden',
          minWidth: 0,
          width: `min(${drawerDim || defaultDrawerDim}px, 96vw)`,
          maxWidth: `min(${drawerDim || defaultDrawerDim}px, 96vw, 100vw)`,
        }
      : {
          overflow: 'auto',
          overflowX: 'hidden',
          minWidth: 0,
          height: drawerDim ? `min(${drawerDim}px, 96vh)` : undefined,
          maxHeight: drawerDim ? `min(${drawerDim}px, 96vh)` : undefined,
        };
  const drawerClassName =
    drawerPosition === 'top' || drawerPosition === 'bottom'
      ? 'w-full p-3 pt-14'
      : 'w-[min(720px,96vw)] p-3 pt-14';
  const modalWidth = positiveNumber(modalSurface?.options?.width);
  const modalStyle = modalWidth
    ? { width: `min(${modalWidth}px, 94vw)`, maxWidth: `min(${modalWidth}px, 94vw)` }
    : undefined;

  const rendererProps = {
    surfaces,
    dataModel,
    stateModel,
    sendAction,
    setInput,
    userRole,
    userPermissions,
    pendingActions,
  };

  if (connectionState !== 'connected' && !mainComponentId) {
    const isRetrying = connectionState === 'disconnected';
    return (
      <div className="h-dvh w-full flex flex-col items-center justify-center gap-3 text-muted-foreground">
        <Spinner className="size-8" />
        <span className="text-sm">
          {isRetrying ? 'Server non raggiungibile, riconnessione in corso…' : 'Connessione al server in corso…'}
        </span>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <ClientStateProvider value={stateModel}>
        <div className="h-dvh w-full overflow-hidden">
          <main className="h-full w-full min-h-0 overflow-auto">
            {mainComponentId ? (
              <A2UIRenderer
                surfaceId={mainSurfaceId}
                componentId={mainComponentId}
                {...rendererProps}
              />
            ) : (
              <div className="grid gap-2">
                <Skeleton className="h-6 w-56" />
                <Skeleton className="h-4 w-72" />
                <Skeleton className="h-4 w-64" />
              </div>
            )}
          </main>

          {/* Persistent drawer — always in DOM, open when backend loads content */}
          <Sheet
            open={!!drawerSurface?.rootId}
            onOpenChange={(open) => { if (!open) closeSurface('drawer'); }}
          >
            <SheetContent style={drawerStyle} side={drawerPosition} className={drawerClassName}>
              {drawerSurface?.rootId ? (
                <A2UIRenderer
                  surfaceId="drawer"
                  componentId={drawerSurface.rootId}
                  {...rendererProps}
                />
              ) : null}
            </SheetContent>
          </Sheet>

          {/* Persistent modal — always in DOM, open when backend loads content */}
          <Dialog
            open={!!modalSurface?.rootId}
            onOpenChange={(open) => { if (!open) closeSurface('modal'); }}
          >
            <DialogContent
              style={modalStyle}
              className="max-w-[min(960px,94vw)] p-3"
            >
              {modalSurface?.rootId ? (
                <A2UIRenderer
                  surfaceId="modal"
                  componentId={modalSurface.rootId}
                  {...rendererProps}
                />
              ) : null}
            </DialogContent>
          </Dialog>

          {overlaySurfaces.map(([surfaceId, surface]) => (
            <Dialog key={surfaceId} open>
              <DialogContent className="max-w-[min(960px,94vw)] p-3">
                <A2UIRenderer
                  surfaceId={surfaceId}
                  componentId={surface.rootId as string}
                  {...rendererProps}
                />
              </DialogContent>
            </Dialog>
          ))}

        </div>
      </ClientStateProvider>
      <Toaster position="bottom-right" richColors />
    </TooltipProvider>
  );
}

export default App;
