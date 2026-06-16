import React from 'react';

export const StreamBinding: React.FC<any> = ({ id, stream, event, target, transformer, sendAction, surfaceId }) => {
  const sendActionRef = React.useRef(sendAction);
  const bindingId = String(id || '').trim();
  const sourceStream = String(stream || '').trim();
  const eventName = String(event || '').trim();
  const resolvedSurfaceId = surfaceId || 'main';
  const subscriptionKey = JSON.stringify({
    bindingId,
    stream: sourceStream,
    event: eventName,
    target: target || {},
    transformer: transformer || {},
    surfaceId: resolvedSurfaceId,
  });

  React.useEffect(() => {
    sendActionRef.current = sendAction;
  }, [sendAction]);

  React.useEffect(() => {
    const payload = JSON.parse(subscriptionKey || '{}');
    if (!payload.bindingId || !payload.stream || typeof sendActionRef.current !== 'function') return;

    sendActionRef.current(
      '__stream_binding.subscribe',
      {
        bindingId: payload.bindingId,
        stream: payload.stream,
        event: payload.event,
        target: payload.target,
        transformer: payload.transformer,
      },
      payload.surfaceId || 'main',
      payload.bindingId,
    );

    return () => {
      sendActionRef.current?.(
        '__stream_binding.unsubscribe',
        { bindingId: payload.bindingId },
        payload.surfaceId || 'main',
        payload.bindingId,
      );
    };
  }, [subscriptionKey]);

  return null;
};
