import { useMemo } from 'react';
import { useClientRuntime } from './hooks/useClientRuntime';
import { ClientRenderer } from './components/renderer/Renderer';
import { 
  IconButton,
  Modal,
  Spinner,
} from '@fluentui/react';
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
  } = useClientRuntime({
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
  const drawerClosable = drawerSurface?.options?.closable !== false && drawerSurface?.options?.dismissible !== false;
  
  const drawerClassName = `ds-drawer-surface ds-drawer-${drawerPosition}`;
  const drawerStyle =
    !isVerticalDrawer
      ? {
          overflowX: 'hidden',
          position: 'fixed',
          top: 0,
          bottom: 0,
          ...(drawerPosition === 'left' ? { left: 0 } : { right: 0 }),
          minWidth: 0,
          height: '100vh',
          maxHeight: '100vh',
          width: `min(${drawerDim || defaultDrawerDim}px, 96vw)`,
          maxWidth: `min(${drawerDim || defaultDrawerDim}px, 96vw, 100vw)`
        }
      : {
          overflowX: 'hidden',
          position: 'fixed',
          right: 0,
          left: 0,
          ...(drawerPosition === 'top' ? { top: 0 } : { bottom: 0 }),
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
      <div className="ds-app vh-100 w-100 overflow-hidden d-flex flex-column">
        <main className="flex-grow-1 min-vh-0 min-vw-0 w-100 overflow-y-auto overflow-x-hidden">
          {mainComponentId ? (
            <ClientRenderer
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

        <Modal
          isOpen={!!drawerSurface?.rootId}
          isModeless
          onDismiss={() => closeSurface('drawer')}
          containerClassName={drawerClassName}
          styles={{ main: drawerStyle as any }}
        >
          <div className="ds-dialog-content">
            {drawerClosable ? (
              <IconButton
                className="ds-drawer-close"
                iconProps={{ iconName: 'Cancel' }}
                ariaLabel="Close drawer"
                title="Close"
                onClick={() => closeSurface('drawer')}
              />
            ) : null}
            {drawerSurface?.rootId ? (
              <ClientRenderer
                surfaceId="drawer"
                componentId={drawerSurface.rootId}
                {...rendererProps}
              />
            ) : null}
          </div>
        </Modal>

        <Modal
          isOpen={!!modalSurface?.rootId}
          onDismiss={() => closeSurface('modal')}
          containerClassName="ds-modal-surface"
          styles={{ main: modalStyle as any }}
        >
          <div className="ds-dialog-content">
            {modalSurface?.rootId ? (
              <ClientRenderer
                surfaceId="modal"
                componentId={modalSurface.rootId}
                {...rendererProps}
              />
            ) : null}
          </div>
        </Modal>

        {overlaySurfaces.map(([surfaceId, surface]) => (
          <Modal
            key={surfaceId}
            isOpen
            onDismiss={() => closeSurface(surfaceId)}
            containerClassName="ds-modal-surface"
          >
            <div className="ds-dialog-content">
              <ClientRenderer
                surfaceId={surfaceId}
                componentId={surface.rootId as string}
                {...rendererProps}
              />
            </div>
          </Modal>
        ))}

      </div>
      <Toaster position="bottom-right" richColors />
    </ClientStateProvider>
  );
}

export default App;
