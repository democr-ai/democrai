import { useEffect, useRef } from 'react';

/**
 * Shared hook for auto-refresh logic across SDUI components.
 * 
 * @param auto_refresh Interval in seconds.
 * @param on_refresh Action to call on each tick.
 * @param onAction Callback to trigger SDUI actions.
 * @param context Extra data to pass to the refresh action.
 * @param deps Dependencies that should restart the timer if they change.
 */
export const useAutoRefresh = (
  auto_refresh: number | undefined,
  on_refresh: any,
  onAction: (name: string, ctx: any) => void,
  context: any = {},
  deps: any[] = []
) => {
  const containerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!auto_refresh || auto_refresh < 1 || !on_refresh) return;

    const actionName = typeof on_refresh === 'string' ? on_refresh : on_refresh.name;
    const actionCtx = typeof on_refresh === 'object' ? { ...on_refresh.context, ...context } : context;

    const interval = setInterval(() => {
      // Visibility check: stop if component is no longer in the DOM
      if (containerRef.current && !document.contains(containerRef.current)) {
        clearInterval(interval);
        return;
      }

      onAction(actionName, { ...actionCtx, autoRefresh: true });
    }, auto_refresh * 1000);

    return () => clearInterval(interval);
  }, [auto_refresh, on_refresh, onAction, ...deps]);

  return containerRef;
};
