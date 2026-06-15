import { useMemo } from 'react';
import { useA2UI } from './hooks/useA2UI';
import { A2UIRenderer } from './components/a2ui/Renderer';
import { 
  Dialog,
  DialogBody,
  DialogContent,
  DialogSurface,
  Spinner,
} from '@fluentui/react-components';
import { DrawerBody, OverlayDrawer } from '@fluentui/react-components/unstable';
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

const drawerSize = (dim: number | null): 'small' | 'medium' | 'large' | 'full' => {
  if (!dim) return 'medium';
  if (dim <= 360) return 'small';
  if (dim <= 680) return 'medium';
  if (dim <= 980) return 'large';
  return 'full';
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
    if (surfaces.main && !hostedSurfaceIds.has('main')) {
      return 'main';
    }
    for (const id of Object.keys(surfaces)) {
      if (id === 'modal' || isTabRouteSurfaceId(id)) continue;
      if (!hostedSurfaceIds.has(id)) {
        const surface = surfaces[id] as any;
        if (surface?.rootId || surface?.components?.root) {
          return id;
        }
      }
    }
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
  const isVerticalDrawer = drawerPosition === 'top' || drawerPosition === 'bottom';
  
  const drawerClassName = `a2ui-drawer-surface a2ui-drawer-${drawerPosition}`;
  const fluentDrawerPosition = drawerPosition === 'left' ? 'start' : isVerticalDrawer ? 'bottom' : 'end';

  const drawerStyle =
    !isVerticalDrawer
      ? {
          overflowX: 'hidden',
          minWidth: 0,
          width: `min(${drawerDim || defaultDrawerDim}px, 96vw)`,
          maxWidth: `min(${drawerDim || defaultDrawerDim}px, 96vw, 100vw)`
        }
      : {
          overflowX: 'hidden',
          minWidth: 0,
          width: '100vw',
          maxWidth: '100vw',
          height: drawerDim ? `min(${drawerDim}px, 96vh)` : 'auto',
          maxHeight: '96vh',
        };

  const modalWidth = positiveNumber(modalSurface?.options?.width);
  const modalStyle = modalWidth
    ? { maxWidth: `min(${modalWidth}px, 94vw)` }
    : { maxWidth: 'min(960px, 94vw)' };

  const rendererProps = {
    surfaces,
    dataModel,
    stateModel,
    sendAction,
    setInput,
    userRole,
    userRoleRaw: userRole,
    userPermissions,
    pendingActions,
  };

  if (connectionState !== 'connected' && !mainComponentId) {
    const isRetrying = connectionState === 'disconnected';
    return (
      <div className="vh-100 w-100 d-flex flex-column align-items-center justify-content-center gap-3">
        <Spinner label="Loading..." />
        <span className="small">
          {isRetrying ? 'Server non raggiungibile, riconnessione in corso…' : 'Connessione al server in corso…'}
        </span>
      </div>
    );
  }

  return (
    <ClientStateProvider value={stateModel}>
      <div className="a2ui-app vh-100 w-100 overflow-hidden d-flex flex-column">
        <main className="flex-grow-1 min-vh-0 min-vw-0 w-100 overflow-y-auto overflow-x-hidden">
          {mainComponentId ? (
            <A2UIRenderer
              surfaceId={mainSurfaceId}
              componentId={mainComponentId}
              {...rendererProps}
            />
          ) : (
            <div className="p-4 d-flex flex-column gap-2 h-100">
               <Spinner />
            </div>
          )}
        </main>

        {drawerPosition === 'top' ? (
          <Dialog open={!!drawerSurface?.rootId} onOpenChange={(_, data) => { if (!data.open) closeSurface('drawer'); }}>
            <DialogSurface className={drawerClassName} style={drawerStyle}>
              <DialogBody>
                <DialogContent className="a2ui-dialog-content">
                  {drawerSurface?.rootId ? (
                    <A2UIRenderer
                      surfaceId="drawer"
                      componentId={drawerSurface.rootId}
                      {...rendererProps}
                    />
                  ) : null}
                </DialogContent>
              </DialogBody>
            </DialogSurface>
          </Dialog>
        ) : (
          <OverlayDrawer
            open={!!drawerSurface?.rootId}
            position={fluentDrawerPosition}
            size={isVerticalDrawer ? undefined : drawerSize(drawerDim || defaultDrawerDim)}
            modalType="modal"
            onOpenChange={(_, data) => { if (!data.open) closeSurface('drawer'); }}
            className={drawerClassName}
            style={drawerStyle}
          >
            <DrawerBody className="a2ui-dialog-content">
              {drawerSurface?.rootId ? (
                <A2UIRenderer
                  surfaceId="drawer"
                  componentId={drawerSurface.rootId}
                  {...rendererProps}
                />
              ) : null}
            </DrawerBody>
          </OverlayDrawer>
        )}

        <Dialog open={!!modalSurface?.rootId} onOpenChange={(_, data) => { if (!data.open) closeSurface('modal'); }}>
          <DialogSurface className="a2ui-modal-surface" style={modalStyle}>
            <DialogBody>
              <DialogContent className="a2ui-dialog-content">
                {modalSurface?.rootId ? (
                  <A2UIRenderer
                    surfaceId="modal"
                    componentId={modalSurface.rootId}
                    {...rendererProps}
                  />
                ) : null}
              </DialogContent>
            </DialogBody>
          </DialogSurface>
        </Dialog>

        {overlaySurfaces.map(([surfaceId, surface]) => (
          <Dialog key={surfaceId} open onOpenChange={(_, data) => { if (!data.open) closeSurface(surfaceId); }}>
            <DialogSurface className="a2ui-modal-surface">
              <DialogBody>
                <DialogContent className="a2ui-dialog-content">
                  <A2UIRenderer
                    surfaceId={surfaceId}
                    componentId={surface.rootId as string}
                    {...rendererProps}
                  />
                </DialogContent>
              </DialogBody>
            </DialogSurface>
          </Dialog>
        ))}

      </div>
      <Toaster position="bottom-right" richColors />
    </ClientStateProvider>
  );
}

export default App;
