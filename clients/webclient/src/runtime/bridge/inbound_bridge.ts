type InboundBridgeDeps = {
  onStateUpdate?: (payload: any) => void;
  onSurfaceUpdate?: (payload: any) => void;
  onBeginRendering?: (payload: any) => void;
  onPropertyUpdate: (payload: any) => void;
  onDataModelUpdate?: (payload: any) => void;
  onDeleteSurface?: (payload: any) => void;
  onBackgroundTaskStarted?: (payload: any) => void;
  onBackgroundTaskProgress?: (payload: any) => void;
  onBackgroundTaskCompleted?: (payload: any) => void;
  onBackgroundTaskError?: (payload: any) => void;
  onBackgroundTaskConfirmation?: (payload: any) => void;
  onBackgroundTaskUpdate?: (payload: any) => void;
  onWindowAction?: (payload: any) => void;
  onAgentUICommands?: (payload: any) => void;
  onHotReload?: () => void;
  onUnhandled?: (payload: any) => void;
};

export class WebInboundBridge {
  private readonly deps: InboundBridgeDeps;

  constructor(deps: InboundBridgeDeps) {
    this.deps = deps;
  }

  dispatch(message: any): void {
    if (!message || typeof message !== 'object') return;

    if (Array.isArray(message.messages)) {
      message.messages.forEach((entry: any) => this.dispatch(entry));
      return;
    }

    if (message.message && typeof message.message === 'object') {
      this.dispatch(message.message);
      return;
    }

    if (message.type === 'ui_messages' && Array.isArray(message.messages)) {
      message.messages.forEach((entry: any) => this.dispatch(entry));
      return;
    }

    if (message.propertyUpdate || message.property_update) {
      this.deps.onPropertyUpdate(message.propertyUpdate || message.property_update);
      return;
    }

    if (message.stateUpdate || message.state_update) {
      this.deps.onStateUpdate?.(message.stateUpdate || message.state_update);
      return;
    }

    if (message.surfaceUpdate || message.surface_update) {
      this.deps.onSurfaceUpdate?.(message.surfaceUpdate || message.surface_update);
      return;
    }

    if (message.beginRendering || message.begin_rendering) {
      this.deps.onBeginRendering?.(message.beginRendering || message.begin_rendering);
      return;
    }

    if (message.dataModelUpdate || message.data_model_update) {
      this.deps.onDataModelUpdate?.(message.dataModelUpdate || message.data_model_update);
      return;
    }

    if (message.deleteSurface || message.delete_surface) {
      this.deps.onDeleteSurface?.(message.deleteSurface || message.delete_surface);
      return;
    }

    if (message.backgroundTaskStarted || message.background_task_started) {
      this.deps.onBackgroundTaskStarted?.(message.backgroundTaskStarted || message.background_task_started);
      return;
    }

    if (message.backgroundTaskProgress || message.background_task_progress) {
      this.deps.onBackgroundTaskProgress?.(message.backgroundTaskProgress || message.background_task_progress);
      return;
    }

    if (message.backgroundTaskCompleted || message.background_task_completed) {
      this.deps.onBackgroundTaskCompleted?.(message.backgroundTaskCompleted || message.background_task_completed);
      return;
    }

    if (message.backgroundTaskError || message.background_task_error) {
      this.deps.onBackgroundTaskError?.(message.backgroundTaskError || message.background_task_error);
      return;
    }

    if (message.backgroundTaskConfirmation || message.background_task_confirmation) {
      this.deps.onBackgroundTaskConfirmation?.(
        message.backgroundTaskConfirmation || message.background_task_confirmation,
      );
      return;
    }

    if (message.backgroundTaskUpdate || message.background_task_update) {
      this.deps.onBackgroundTaskUpdate?.(
        message.backgroundTaskUpdate || message.background_task_update,
      );
      return;
    }

    if (message.windowAction || message.window_action) {
      this.deps.onWindowAction?.(message.windowAction || message.window_action);
      return;
    }

    if (message.agentUICommands || message.agent_ui_commands) {
      this.deps.onAgentUICommands?.(message.agentUICommands || message.agent_ui_commands);
      return;
    }

    if (message.type === 'hot_reload') {
      this.deps.onHotReload?.();
      return;
    }

    this.deps.onUnhandled?.(message);
  }
}
