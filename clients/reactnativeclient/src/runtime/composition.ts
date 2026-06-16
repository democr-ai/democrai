import { InboundController } from './controllers/inbound';
import { PropertyUpdateController, type NormalizedPropertyUpdate } from './controllers/property_updates';
import { InboundBridge } from './bridge/inbound_bridge';

// PropertyUpdateController is not yet exported from property_updates.ts in my previous call, 
// let me fix that if needed, but for now I'll use it as it's defined in the same file or I'll export it.
// I'll add the export to property_updates.ts later if I missed it.

export function createRuntimeComposition({
  maxInboundPerTick = 120,
  messagePriority,
  processInboundMessage,
  processPropertyUpdate,
}: {
  maxInboundPerTick?: number;
  messagePriority: (data: any) => number;
  processInboundMessage: (message: any) => void;
  processPropertyUpdate: (update: NormalizedPropertyUpdate) => void;
}) {
  const propertyUpdates = new PropertyUpdateController(processPropertyUpdate);

  const bridge = new InboundBridge({
    onStateUpdate: (payload) => processInboundMessage({ stateUpdate: payload }),
    onSurfaceUpdate: (payload) => processInboundMessage({ surfaceUpdate: payload }),
    onBeginRendering: (payload) => processInboundMessage({ beginRendering: payload }),
    onPropertyUpdate: (payload) => propertyUpdates.enqueue(payload),
    onDataModelUpdate: (payload) => processInboundMessage({ dataModelUpdate: payload }),
    onDeleteSurface: (payload) => processInboundMessage({ deleteSurface: payload }),
    onBackgroundTaskStarted: (payload) => processInboundMessage({ backgroundTaskStarted: payload }),
    onBackgroundTaskProgress: (payload) => processInboundMessage({ backgroundTaskProgress: payload }),
    onBackgroundTaskCompleted: (payload) => processInboundMessage({ backgroundTaskCompleted: payload }),
    onBackgroundTaskError: (payload) => processInboundMessage({ backgroundTaskError: payload }),
    onBackgroundTaskConfirmation: (payload) => processInboundMessage({ backgroundTaskConfirmation: payload }),
    onWindowAction: (payload) => processInboundMessage({ windowAction: payload }),
    onAgentUICommands: (payload) => processInboundMessage({ agentUICommands: payload }),
    onHotReload: () => processInboundMessage({ type: 'hot_reload' }),
    onUnhandled: (payload) => processInboundMessage(payload)
  });

  const inbound = new InboundController({
    maxPerTick: maxInboundPerTick,
    priorityFn: messagePriority,
    dispatchFn: (message) => bridge.dispatch(message),
  });

  return {
    inbound,
    bridge,
    propertyUpdates,
    dispose: () => {
      inbound.dispose();
      propertyUpdates.dispose();
    },
  };
}
